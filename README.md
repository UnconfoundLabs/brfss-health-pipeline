# BRFSS Health Data Engineering Pipeline

An end-to-end, tested data pipeline (Python → DuckDB → dbt → Prefect) that produces survey-weighted state-level diabetes and metabolic-risk estimates from CDC BRFSS microdata.

## Question

How does diagnosed diabetes prevalence among US adults vary by state, age group, and race/ethnicity from 2021 to 2023? And can a reviewer trust that the estimates are weighted correctly?

## Data source

- **CDC [Behavioral Risk Factor Surveillance System (BRFSS)](https://www.cdc.gov/brfss/)**, [annual survey data](https://www.cdc.gov/brfss/annual_data/annual_data.htm), **2021, 2022, 2023** (LLCP SAS transport/XPT files).
- BRFSS is the world's largest ongoing telephone health survey, with roughly 400K adult respondents a year in all 50 states, DC, and territories.
- Only an allow-list of 25 variables is loaded (outcomes, risk factors, demographics, and the design variables `_LLCPWT`, `_STSTR`, `_PSU`). See `ingestion/config.py`.
- Public-use, de-identified; public domain.

## Methods

### Architecture

```
CDC XPT files
     │
     ▼
[Python ingestion]     pyreadstat + requests; idempotent download, size check
     │
     ▼
[DuckDB raw layer]     raw.brfss_{year} tables + raw.brfss_all UNION ALL view
     │
     ▼
[Great Expectations]   raw validation: column presence, row counts, weight QC
     │
     ▼
[dbt staging]          decode codes → labels, BMI ÷ 100, refused/don't-know → NULL, drop zero-weight rows
     │
     ▼
[dbt intermediate]     diabetes flags, 0–5 metabolic risk score, weight diagnostics
     │
     ▼
[dbt marts]            survey-weighted prevalence tables
     │
     ▼
[dbt tests]            schema tests + custom epidemiological sanity checks
     │
     ▼
[Prefect flow]         orchestrates all steps; stops on a failed raw-quality gate
```

### Epidemiologic design decisions

- **Survey weighting.** BRFSS is a complex stratified probability sample, so raw percentages are biased. Every prevalence uses the weighted (Horvitz-Thompson-type) proportion Σ(wᵢyᵢ)/Σwᵢ with `_LLCPWT`. See `dbt_brfss/macros/survey_weighted_mean.sql`.
- **Case definition.** "Diagnosed diabetes" means `DIABETE4 = 1`. Gestational-only, prediabetes/borderline, and don't-know/refused are kept as separate categories, not counted as cases.
- **Small-cell suppression.** In `fct_diabetes_prevalence`, prevalence is set to NULL for any state × year × age × race cell with fewer than 50 unweighted respondents.
- **Point estimates only.** `_STSTR` and `_PSU` are carried through every layer so variance can be estimated downstream (see [Limitations](#limitations)).
- **Domain knowledge as data contracts.** Two custom dbt tests, `assert_weights_sum_to_population` and `assert_diabetes_prevalence_reasonable`, fail the build if the weights or the national prevalence fall outside plausible ranges.

### Data engineering design decisions

- **DuckDB.** A local analytical database: no cloud credentials, instant setup, full SQL, direct pandas/pyreadstat integration.
- **Layered dbt project.** `staging` → `intermediate` → `marts`, so each layer has one job and can be tested on its own.
- **Idempotent ingestion.** Downloads already on disk are skipped on re-run; a minimum file size and a minimum row count catch truncated downloads.
- **CI.** GitHub Actions runs ruff, the pytest unit tests, `dbt seed`, and `dbt compile` against an empty DuckDB.

### Stack

| Layer | Tool |
|-------|------|
| Ingestion | Python 3.11+, pyreadstat, requests |
| Storage | DuckDB 1.2+ |
| Transformation | dbt-core 1.9+, dbt-duckdb |
| Data quality | Great Expectations 1.3+, dbt tests |
| Orchestration | Prefect 3.2+ |
| CI | GitHub Actions |

## How to run

All commands run from the repo root; see the `Makefile`.

```bash
# 1. Install (Python 3.11+)
python -m venv .venv && source .venv/bin/activate
make install                 # pip install -e ".[dev]"

# 2. Download BRFSS 2021-2023 XPT files into data/raw/ (skipped on re-run)
make download

# 3. Load into data/duckdb/brfss.duckdb: raw.brfss_2021..2023 + raw.brfss_all
make load

# 4. Validate raw data (Great Expectations)
python -m expectations.validate_raw

# 5. Transform and test with dbt
make dbt-deps                # dbt_utils
make dbt-seed                # state FIPS codes, variable labels
make dbt-run                 # staging → intermediate → marts
make dbt-test                # schema tests + custom checks (--store-failures)

# 6. Unit tests + dbt tests together
make quality

# Or the whole flow orchestrated by Prefect (optional UI: `make prefect-start`, http://localhost:4200)
make pipeline                # python -m flows.brfss_pipeline [--years 2022 2023] [--skip-download]

# Browse lineage and docs at http://localhost:8080
make dbt-docs
```

`make all` runs install → download → load → dbt deps/seed/run/test in one go. `make clean-data` removes the DuckDB file and the downloaded data.

### Verify a run

dbt-duckdb prefixes custom schemas with the target schema (`main`), so the dbt models land in `main_staging`, `main_intermediate`, `main_marts`, and `main_seeds`. The raw tables stay in `raw`.

```sql
-- duckdb data/duckdb/brfss.duckdb

-- 1. Respondents per year (expect roughly 400K-500K)
SELECT survey_year, COUNT(*) AS n
FROM raw.brfss_all
GROUP BY 1 ORDER BY 1;

-- 2. Weight sum, in millions (should approximate the US adult population, ~250M)
SELECT survey_year, ROUND(SUM(llcpwt) / 1e6, 1) AS estimated_adults_millions
FROM main_staging.stg_brfss__respondents
GROUP BY 1 ORDER BY 1;

-- 3. National weighted diabetes prevalence, excluding suppressed cells (expect ~11-12%)
SELECT survey_year,
       ROUND(SUM(weighted_n_diabetic) / SUM(weighted_n_total) * 100, 1) AS diabetes_pct
FROM main_marts.fct_diabetes_prevalence
WHERE weighted_diabetes_prevalence IS NOT NULL
GROUP BY 1 ORDER BY 1;
```

`dbt_brfss/analyses/diabetes_prevalence_exploratory.sql` gives the same national trend by race/ethnicity.

### Known issues

> TODO (Hannah), found while checking the run steps against the code. I made no code changes in this PR.
> - **`make dbt-run` stops at `int_brfss__metabolic_risk`.** The model selects `fruit_frequency` and `vegetable_frequency`, which `stg_brfss__respondents` doesn't produce: `FRUIT2` and `VEGETAB2` are loaded but never decoded. I reproduced this with a one-row smoke test (DuckDB Binder Error). `fct_diabetes_risk_factors` and `fct_survey_weighted_estimates` are then skipped. `fct_diabetes_prevalence` and `dim_respondent_demographics` build fine.
> - **`make pipeline` will fail on import under Prefect 3.** `flows/brfss_pipeline.py` imports `SequentialTaskRunner`, which no longer exists in Prefect 3.x. I checked the 3.8 wheel.
> - **`expectations/validate_raw.py` uses the pre-1.0 Great Expectations API** (`gx.DataContext`, `context.sources`), but `pyproject.toml` pins `great-expectations>=1.3`. Please verify it runs.
> - **CI on `main` is currently red** (Lint & Unit Tests job; the logs have expired). CI runs `dbt compile`, not `dbt run`, so it wouldn't catch the first issue.
> - `notebooks/01_exploratory_analysis.ipynb` was listed in the old README but isn't in the repo. I removed the reference.

## Data model

### Marts (primary outputs)

| Table | Grain | Description |
|-------|-------|-------------|
| `fct_diabetes_prevalence` | state × year × age group × race/ethnicity | Survey-weighted diagnosed diabetes, prediabetes, and insulin-use prevalence; weighted and unweighted n; suppression applied |
| `fct_diabetes_risk_factors` | diabetes category × year | Risk factor burden by diabetes status |
| `fct_survey_weighted_estimates` | state × year | Wide KPI table across outcomes |
| `dim_respondent_demographics` | respondent | Demographic dimension |

Column-level documentation: [`docs/data_dictionary.md`](docs/data_dictionary.md). Survey design notes: [`docs/BRFSS_variables_reference.md`](docs/BRFSS_variables_reference.md).

### Validation checks

| Check | Where | Expected range |
|-------|-------|---------------|
| Respondent count per year | GE + `MIN_ROWS_PER_YEAR` | ≥ 400K |
| `_LLCPWT` null rate | GE | < 1% |
| Sum of `_LLCPWT` per year | dbt `assert_weights_sum_to_population` | 200M–280M (US adults) |
| National weighted diabetes prevalence | dbt `assert_diabetes_prevalence_reasonable` | 8%–15% per year (CDC: ~11–12%) |

## Key results

> TODO (Hannah): the repo has no output tables or figures yet. Once the full pipeline runs, add the national prevalence by year (query 3 above) and one or two state or subgroup findings, preferably with a figure. Then compare against [CDC's BRFSS prevalence data](https://www.cdc.gov/brfss/brfssprevalence/) as an external check.

## Limitations

- **No standard errors or confidence intervals.** The pipeline computes weighted point estimates only. For inference, use Taylor series linearization with `_STSTR` and `_PSU`: R `survey::svyby()`/`svyglm()`, Stata `svy:`, or SAS `PROC SURVEYMEANS`/`SURVEYLOGISTIC`. The 50-respondent suppression rule doesn't replace a relative-standard-error check.
- **Self-reported, diagnosed diabetes.** BRFSS asks whether a doctor ever told the respondent they have diabetes, so undiagnosed diabetes is missed and prevalence is understated compared with biomarker-based estimates such as NHANES.
- **Telephone survey.** Coverage and nonresponse bias remain after weighting. Institutionalized adults aren't sampled.
- **Pooling across years.** `raw.brfss_all` stacks years without re-weighting. That's fine for per-year estimates, but multi-year pooled estimates need adjusted weights.
- **Composite metabolic risk score** (`int_brfss__metabolic_risk`) is an unweighted sum of five binary flags. It's descriptive, not a validated clinical index. Its diet component uses a simplified vegetable-frequency threshold.
- **`winsorize_weights` macro** is for sensitivity analysis only. CDC recommends using `_LLCPWT` as-is.

## License

Data: CDC BRFSS public use files (public domain).
Code: MIT License.

> TODO (Hannah): the README says MIT, but there's no `LICENSE` file in the repo. Add one or change this line.

## Author

Hannah Choi · [Unconfound Labs](https://github.com/UnconfoundLabs)

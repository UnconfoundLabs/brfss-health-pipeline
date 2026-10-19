# Data Dictionary

## Staging Layer

### `stg_brfss__respondents`

One row per BRFSS survey respondent per year. Foundation for all downstream models.

| Column | Source Variable | Type | Description |
|--------|----------------|------|-------------|
| `respondent_id` | _(synthetic)_ | INTEGER | Unique row identifier (ROW_NUMBER) |
| `survey_year` | `IYEAR` | INTEGER | Survey year (2021, 2022, 2023) |
| `state_fips` | `_STATE` | INTEGER | State FIPS code (1–78) |
| `state_abbr` | _(seed join)_ | VARCHAR | State two-letter abbreviation |
| `state_name` | _(seed join)_ | VARCHAR | Full state name |
| `interview_month` | `IMONTH` | INTEGER | Interview month (1–12) |
| `interview_year` | `IYEAR` | INTEGER | Interview year |
| `llcpwt` | `_LLCPWT` | DOUBLE | Survey weight — use for all population estimates |
| `ststr` | `_STSTR` | DOUBLE | Stratum for variance estimation |
| `psu` | `_PSU` | DOUBLE | Primary sampling unit |
| `diabetes_status` | `DIABETE4` | VARCHAR | `Diagnosed`, `Gestational Only`, `No`, `Prediabetes`, `Unknown` |
| `has_prediabetes` | `PREDIAB2` | BOOLEAN | Prediabetes confirmed (NULL = unknown) |
| `takes_insulin` | `INSULIN1` | BOOLEAN | Currently uses insulin (NULL = unknown) |
| `bmi_calc` | `_BMI5` | DOUBLE | BMI (original / 100). NULL if missing. |
| `bmi_category` | `_BMI5CAT` | VARCHAR | `Underweight`, `Normal`, `Overweight`, `Obese` |
| `has_hypertension` | `_RFHYPE6` | BOOLEAN | High blood pressure (NULL = unknown) |
| `has_coronary_heart_disease` | `CVDCRHD4` | BOOLEAN | Coronary heart disease (NULL = unknown) |
| `any_exercise_past_30d` | `EXERANY2` | BOOLEAN | Any exercise in past 30 days |
| `physical_activity_index` | `_PAINDX3` | VARCHAR | `Met Aerobic Recommendations`, `Insufficiently Active`, `Inactive` |
| `sex` | `SEXVAR` | VARCHAR | `Male`, `Female`, `Unknown` |
| `age_group` | `_AGEG5YR` | VARCHAR | `18-24`, `25-29`, ..., `80+` |
| `race_ethnicity` | `_RACE1` | VARCHAR | 7-category race/ethnicity label |
| `race_ethnicity_collapsed` | `_RACEGR3` | VARCHAR | 5-category race/ethnicity label |
| `education_level` | `EDUCA` | VARCHAR | Highest education completed |
| `income_group` | `INCOME3` | VARCHAR | Annual household income range |
| `urban_rural` | `_URBSTAT` | VARCHAR | `Urban` or `Rural` |

---

## Intermediate Layer

### `int_brfss__diabetes_flags`

| Column | Type | Description |
|--------|------|-------------|
| `respondent_id` | INTEGER | FK to `stg_brfss__respondents` |
| `survey_year` | INTEGER | Survey year |
| `llcpwt` | DOUBLE | Survey weight |
| `is_diagnosed_diabetic` | BOOLEAN | True if `diabetes_status = 'Diagnosed'` |
| `is_prediabetic` | BOOLEAN | True if prediabetes reported |
| `is_insulin_dependent` | BOOLEAN | True if currently takes insulin |
| `diabetes_category` | VARCHAR | `Insulin-Dependent Diabetic`, `Diagnosed Diabetic`, `Prediabetic`, `No Diabetes`, `Unknown` |

### `int_brfss__metabolic_risk`

| Column | Type | Description |
|--------|------|-------------|
| `respondent_id` | INTEGER | FK to `stg_brfss__respondents` |
| `obese_flag` | INTEGER | 1 if obese |
| `hypertension_flag` | INTEGER | 1 if hypertensive |
| `inactive_flag` | INTEGER | 1 if physically inactive |
| `no_exercise_flag` | INTEGER | 1 if no exercise in past 30 days |
| `diabetes_flag` | INTEGER | 1 if diagnosed diabetic |
| `poor_diet_flag` | INTEGER | 1 if other-vegetable (VEGETAB2) consumption < once per day |
| `metabolic_risk_score` | INTEGER | Sum of above flags (0–5), NULL if all missing |
| `high_metabolic_risk` | BOOLEAN | True if score ≥ 3 |

### `int_brfss__survey_weights`

| Column | Type | Description |
|--------|------|-------------|
| `respondent_id` | INTEGER | FK |
| `normalized_weight` | DOUBLE | Weight normalized to sum to N within year |
| `year_total_weight` | DOUBLE | Sum of all weights in this year |
| `year_n_respondents` | BIGINT | Respondent count in this year |
| `is_extreme_weight` | BOOLEAN | True if weight > 20× mean (diagnostic) |

---

## Marts Layer

### `fct_diabetes_prevalence`

**Grain**: state × year × age_group × race_ethnicity

| Column | Type | Description |
|--------|------|-------------|
| `survey_year` | INTEGER | Survey year |
| `state_fips` | INTEGER | State FIPS code |
| `state_abbr` | VARCHAR | State abbreviation |
| `state_name` | VARCHAR | State name |
| `age_group` | VARCHAR | 5-year age group |
| `race_ethnicity` | VARCHAR | Race/ethnicity (5 categories) |
| `unweighted_n` | BIGINT | Raw respondent count |
| `unweighted_n_diabetic` | BIGINT | Raw diabetic respondent count |
| `weighted_n_total` | DOUBLE | Estimated adult population in stratum |
| `weighted_n_diabetic` | DOUBLE | Estimated diabetic adults in stratum |
| `weighted_diabetes_prevalence` | DOUBLE | Weighted proportion diabetic (0–1). NULL if n < 50. |
| `weighted_prediabetes_prevalence` | DOUBLE | Weighted proportion prediabetic (0–1). NULL if n < 50. |
| `weighted_insulin_dependent_prevalence` | DOUBLE | Weighted proportion on insulin (0–1). NULL if n < 50. |

### `fct_diabetes_risk_factors`

**Grain**: diabetes_category × survey_year

| Column | Type | Description |
|--------|------|-------------|
| `survey_year` | INTEGER | Survey year |
| `diabetes_category` | VARCHAR | Diabetes classification |
| `unweighted_n` | BIGINT | Raw respondent count |
| `weighted_n` | DOUBLE | Estimated adults |
| `pct_obese` | DOUBLE | Weighted prevalence of obesity |
| `pct_hypertensive` | DOUBLE | Weighted prevalence of hypertension |
| `pct_inactive` | DOUBLE | Weighted prevalence of physical inactivity |
| `pct_no_exercise` | DOUBLE | Weighted prevalence of no exercise |
| `pct_poor_diet` | DOUBLE | Weighted prevalence of poor vegetable intake |
| `pct_high_metabolic_risk` | DOUBLE | Weighted prevalence of high metabolic risk score |
| `mean_metabolic_risk_score` | DOUBLE | Weighted mean metabolic risk score |

### `fct_survey_weighted_estimates`

**Grain**: state × survey_year

Wide mart with one row per state-year. Key columns mirror `fct_diabetes_prevalence`
at the state level, covering all major outcomes. See model SQL for full column list.

### `dim_respondent_demographics`

**Grain**: one row per respondent_id

Demographic attributes only (no outcomes). Use for ad hoc joins to fact tables.

---

## Seeds

### `brfss_state_codes`

| Column | Type | Description |
|--------|------|-------------|
| `fips_code` | VARCHAR | State FIPS code |
| `state_abbr` | VARCHAR | 2-letter state abbreviation |
| `state_name` | VARCHAR | Full state name |

### `brfss_variable_labels`

Maps CDC variable names to clean SQL names and human-readable descriptions.
Used as reference documentation; not joined in production models.

| Column | Description |
|--------|-------------|
| `cdc_variable` | Original CDC variable name (e.g., `DIABETE4`) |
| `clean_name` | SQL-safe name used in staging (e.g., `diabetes_status`) |
| `description` | Human-readable description |
| `value_note` | Code → label mapping |

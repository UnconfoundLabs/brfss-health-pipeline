"""
Great Expectations checkpoint for BRFSS raw data validation.

Run before dbt transformations to validate raw XPT data loaded into DuckDB.
Validates: column presence, row counts, key variable ranges, and weight completeness.

Usage:
    python -m expectations.validate_raw
    python -m expectations.validate_raw --years 2022
"""

import argparse
import logging
import sys

import duckdb
import great_expectations as gx
import great_expectations.expectations as gxe

from ingestion.config import (
    COLUMN_NAME_MAP,
    DUCKDB_PATH,
    MIN_ROWS_PER_YEAR,
    ROTATING_CORE_COLUMNS,
    YEARS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Expected clean column names (after ingestion renaming)
EXPECTED_COLUMNS = list(COLUMN_NAME_MAP.values()) + ["survey_year", "loaded_at"]
REQUIRED_COLUMNS = [
    clean for cdc, clean in COLUMN_NAME_MAP.items() if cdc not in ROTATING_CORE_COLUMNS
]


def get_raw_dataframe(year: int):
    """Pull one year's raw table from DuckDB into a pandas DataFrame for GE validation."""
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    df = con.execute(f"SELECT * FROM raw.brfss_{year}").df()
    con.close()
    return df


def build_expectation_suite(year: int) -> gx.ExpectationSuite:
    """Build the BRFSS raw data expectation suite for one survey year."""
    suite = gx.ExpectationSuite(name=f"brfss_raw_suite_{year}")

    # ── Expectation 1: Row count ──────────────────────────────────────────────
    suite.add_expectation(
        gxe.ExpectTableRowCountToBeBetween(min_value=MIN_ROWS_PER_YEAR, max_value=600_000)
    )

    # ── Expectation 2: Expected columns present ───────────────────────────────
    # Rotating-core variables are not asked every year, so they are optional here.
    for col in REQUIRED_COLUMNS:
        suite.add_expectation(gxe.ExpectColumnToExist(column=col))

    # ── Expectation 3: Survey weight completeness (< 1% null) ─────────────────
    suite.add_expectation(gxe.ExpectColumnValuesToNotBeNull(column="llcpwt", mostly=0.99))

    # ── Expectation 4: Weight must be positive ────────────────────────────────
    suite.add_expectation(
        gxe.ExpectColumnValuesToBeBetween(
            column="llcpwt", min_value=0, max_value=100_000_000, mostly=0.99
        )
    )

    # ── Expectation 5: State FIPS in valid range ──────────────────────────────
    suite.add_expectation(
        gxe.ExpectColumnValuesToBeBetween(column="state", min_value=1, max_value=78, mostly=0.99)
    )

    # ── Expectation 6: Survey year is consistent ──────────────────────────────
    suite.add_expectation(gxe.ExpectColumnValuesToBeInSet(column="survey_year", value_set=[year]))

    # ── Expectation 7: Diabetes variable has expected code range ──────────────
    suite.add_expectation(
        gxe.ExpectColumnValuesToBeInSet(
            column="diabete4", value_set=[1, 2, 3, 4, 7, 9], mostly=0.95
        )
    )
    return suite


def validate_year(year: int, context) -> bool:
    """Run GE validations against one year of raw BRFSS data.

    Returns:
        True if all expectations passed, False otherwise.
    """
    log.info("Validating raw BRFSS data for year %d ...", year)
    df = get_raw_dataframe(year)

    # Use GX's in-memory Pandas datasource (GX 1.x fluent API)
    datasource = context.data_sources.add_pandas(name=f"brfss_raw_{year}")
    asset = datasource.add_dataframe_asset(name=f"brfss_{year}_asset")
    batch_definition = asset.add_batch_definition_whole_dataframe(f"brfss_{year}_batch")
    batch = batch_definition.get_batch(batch_parameters={"dataframe": df})

    suite = context.suites.add(build_expectation_suite(year))
    results = batch.validate(suite)
    passed = results.success

    if passed:
        log.info("Year %d: ALL expectations passed.", year)
    else:
        failed = [r for r in results.results if not r.success]
        log.error("Year %d: %d expectation(s) FAILED:", year, len(failed))
        for r in failed:
            log.error("  - %s %s", r.expectation_config.type, r.expectation_config.kwargs)

    return passed


def main():
    parser = argparse.ArgumentParser(description="Validate BRFSS raw data with Great Expectations")
    parser.add_argument("--years", nargs="+", type=int, default=YEARS)
    args = parser.parse_args()

    context = gx.get_context(mode="ephemeral")

    all_passed = True
    for year in args.years:
        passed = validate_year(year, context)
        if not passed:
            all_passed = False

    if not all_passed:
        log.error("Validation FAILED for one or more years. Halting pipeline.")
        sys.exit(1)

    log.info("All raw data validations passed.")


if __name__ == "__main__":
    main()

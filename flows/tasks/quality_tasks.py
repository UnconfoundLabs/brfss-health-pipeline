"""Prefect tasks for data quality checks."""

import subprocess
import sys
from pathlib import Path

from prefect import get_run_logger, task

from ingestion.config import DUCKDB_PATH, YEARS


@task(
    name="validate-raw-data-ge",
    description="Run Great Expectations validations on raw BRFSS data in DuckDB.",
)
def validate_raw_data(years: list[int] = YEARS, db_path: Path = DUCKDB_PATH) -> bool:
    """Run GE expectations against raw BRFSS tables. Raises on failure."""
    logger = get_run_logger()
    logger.info("Running Great Expectations raw data validation for years %s ...", years)

    result = subprocess.run(
        [sys.executable, "-m", "expectations.validate_raw", "--years"] + [str(y) for y in years],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.error("GE validation FAILED:\n%s", result.stderr)
        raise RuntimeError("Great Expectations raw data validation failed. Halting pipeline.")

    logger.info("GE validation passed.")
    return True


@task(
    name="generate-pipeline-summary",
    description="Generate a summary of pipeline run results.",
)
def generate_pipeline_summary(
    years: list[int],
    row_counts: list[int],
    dbt_test_result: dict,
) -> dict:
    logger = get_run_logger()

    total_rows = sum(row_counts)
    tests_passed = dbt_test_result.get("success", False)

    summary = {
        "years_processed": years,
        "total_rows_loaded": total_rows,
        "rows_per_year": dict(zip(years, row_counts)),
        "dbt_tests_passed": tests_passed,
    }

    logger.info("Pipeline summary: %s", summary)
    return summary

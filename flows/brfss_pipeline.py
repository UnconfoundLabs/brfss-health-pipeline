"""
BRFSS Health Data Pipeline — Main Prefect Flow

Run locally:
    python -m flows.brfss_pipeline

Skip download (if XPTs already exist):
    python -m flows.brfss_pipeline --skip-download

Start local Prefect server first for the UI:
    prefect server start
"""

import argparse

from prefect import flow, get_run_logger

from flows.tasks.ingest_tasks import (
    check_raw_data_exists,
    create_brfss_unified_view,
    download_brfss_year,
    load_year_to_duckdb,
)
from flows.tasks.quality_tasks import generate_pipeline_summary, validate_raw_data
from flows.tasks.transform_tasks import (
    dbt_deps,
    dbt_run_intermediate,
    dbt_run_marts,
    dbt_run_staging,
    dbt_seed,
    dbt_test,
)
from ingestion.config import YEARS


@flow(
    name="brfss-health-pipeline",
    description=(
        "End-to-end BRFSS diabetes/metabolic health data pipeline. "
        "Downloads CDC XPT files, loads to DuckDB, transforms with dbt, "
        "validates with GE and dbt tests."
    ),
    # DuckDB requires sequential writes. Prefect 3 removed SequentialTaskRunner;
    # tasks below are called directly (never .submit()/.map()), so they run in order.
    retries=0,
    log_prints=True,
)
def brfss_pipeline(
    years: list[int] = YEARS,
    skip_download: bool = False,
) -> dict:
    """
    Main pipeline flow.

    Args:
        years: Survey years to process (default: [2021, 2022, 2023]).
        skip_download: Skip CDC download if XPT files already exist locally.
    """
    logger = get_run_logger()
    logger.info("Starting BRFSS pipeline for years: %s", years)

    # ── Phase 1: Ingestion ────────────────────────────────────────────────────
    row_counts = []
    for year in years:
        already_downloaded = check_raw_data_exists(year)

        if not already_downloaded and not skip_download:
            download_brfss_year(year)
        elif already_downloaded:
            logger.info("Year %d XPT already exists — skipping download.", year)
        else:
            logger.info("skip_download=True — assuming XPT exists for year %d.", year)

        count = load_year_to_duckdb(year)
        row_counts.append(count)

    create_brfss_unified_view(years)

    # ── Phase 2: Raw data quality gate ────────────────────────────────────────
    # If raw validation fails, the flow raises an exception here and stops.
    validate_raw_data(years)

    # ── Phase 3: dbt transformation ───────────────────────────────────────────
    dbt_deps()
    dbt_seed()
    dbt_run_staging()
    dbt_run_intermediate()
    dbt_run_marts()

    # ── Phase 4: dbt tests (warn on failure, don't stop the flow) ─────────────
    test_result = dbt_test()

    # ── Phase 5: Summary ──────────────────────────────────────────────────────
    summary = generate_pipeline_summary(
        years=years,
        row_counts=row_counts,
        dbt_test_result=test_result,
    )

    logger.info("Pipeline complete. Summary: %s", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Run the BRFSS health data pipeline")
    parser.add_argument("--years", nargs="+", type=int, default=YEARS)
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args()

    brfss_pipeline(years=args.years, skip_download=args.skip_download)


if __name__ == "__main__":
    main()

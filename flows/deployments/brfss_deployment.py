"""
Prefect deployment for scheduled annual BRFSS pipeline runs.

Serve with:
    python flows/deployments/brfss_deployment.py

This serves a deployment named "brfss-annual-refresh" that triggers on January 1st
each year — aligned with CDC's annual BRFSS data release schedule. The process must
stay running to pick up scheduled runs (Prefect 3 `flow.serve`).

Run manually via Prefect UI or CLI:
    prefect deployment run 'brfss-health-pipeline/brfss-annual-refresh'
"""

from flows.brfss_pipeline import brfss_pipeline

if __name__ == "__main__":
    brfss_pipeline.serve(
        name="brfss-annual-refresh",
        # January 1st at 06:00 UTC — CDC typically releases prior year data in Q4/Q1
        cron="0 6 1 1 *",
        parameters={
            "years": [2021, 2022, 2023],
            "skip_download": False,
        },
        description=(
            "Annual BRFSS pipeline refresh. Runs January 1st to pick up the "
            "prior year's CDC data release. Update the `years` parameter each year."
        ),
        tags=["brfss", "health", "annual"],
    )

"""Load BRFSS XPT files into DuckDB raw schema.

Usage:
    python -m ingestion.load_to_duckdb
    python -m ingestion.load_to_duckdb --years 2021 2022 2023
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd
import pyreadstat

from ingestion.config import (
    COLUMN_NAME_MAP,
    COLUMNS_TO_KEEP,
    DUCKDB_PATH,
    INTERMEDIATE_SCHEMA,
    MARTS_SCHEMA,
    RAW_DATA_DIR,
    RAW_SCHEMA,
    STAGING_SCHEMA,
    YEARS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def xpt_path(year: int, data_dir: Path) -> Path:
    return data_dir / f"LLCP{year}.XPT"


def initialize_database(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Create DuckDB file and required schemas."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute("SET memory_limit='4GB'")
    con.execute("SET threads=4")
    for schema in (RAW_SCHEMA, STAGING_SCHEMA, INTERMEDIATE_SCHEMA, MARTS_SCHEMA):
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    log.info("Initialized DuckDB at %s", db_path)
    return con


def read_xpt(filepath: Path, columns: list[str]) -> tuple[pd.DataFrame, object]:
    """Read a BRFSS SAS transport (XPT) file using pyreadstat.

    pyreadstat is preferred over pandas.read_sas because it correctly handles
    BRFSS XPT v5 format and preserves SAS variable labels and formats.

    Only the columns in `columns` are returned to keep memory usage low.
    """
    log.info("Reading %s ...", filepath)
    df, meta = pyreadstat.read_xport(
        str(filepath), usecols=columns, disable_datetime_conversion=True
    )
    log.info("  Read %d rows, %d columns", len(df), len(df.columns))
    return df, meta


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Rename CDC variables to SQL-safe names (lowercase, strip leading underscore)."""
    rename_map = {col: COLUMN_NAME_MAP.get(col, col.lstrip("_").lower()) for col in df.columns}
    return df.rename(columns=rename_map)


def add_metadata(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Add survey_year and loaded_at columns."""
    df = df.copy()
    df["survey_year"] = year
    df["loaded_at"] = datetime.now(tz=UTC).isoformat()
    return df


def load_year(con: duckdb.DuckDBPyConnection, year: int, data_dir: Path) -> int:
    """Load one year of BRFSS data into raw.brfss_{year}.

    Returns:
        Number of rows loaded.
    """
    filepath = xpt_path(year, data_dir)
    if not filepath.exists():
        raise FileNotFoundError(
            f"XPT file not found for year {year}: {filepath}\n"
            "Run `make download` first."
        )

    # Determine which columns actually exist in this year's file
    # (BRFSS variable names are mostly stable but can differ across years)
    df, meta = read_xpt(filepath, columns=None)  # read all, then filter
    available = set(df.columns)
    cols_to_load = [c for c in COLUMNS_TO_KEEP if c in available]
    missing = set(COLUMNS_TO_KEEP) - available
    if missing:
        log.warning("Year %d is missing columns: %s", year, sorted(missing))

    df = df[cols_to_load]
    df = clean_column_names(df)
    df = add_metadata(df, year)

    table_name = f"{RAW_SCHEMA}.brfss_{year}"
    con.execute(f"DROP TABLE IF EXISTS {table_name}")
    con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")
    row_count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    log.info("Loaded %d rows into %s", row_count, table_name)
    return row_count


def create_unified_view(con: duckdb.DuckDBPyConnection, years: list[int]) -> None:
    """Create raw.brfss_all as a UNION ALL view across all year tables.

    Uses UNION ALL BY NAME so years missing a rotating-core column get NULLs
    instead of a column-count mismatch.
    """
    union_parts = [f"SELECT * FROM {RAW_SCHEMA}.brfss_{year}" for year in years]
    union_sql = "\nUNION ALL BY NAME\n".join(union_parts)
    con.execute(f"CREATE OR REPLACE VIEW {RAW_SCHEMA}.brfss_all AS {union_sql}")
    total = con.execute(f"SELECT COUNT(*) FROM {RAW_SCHEMA}.brfss_all").fetchone()[0]
    log.info("Created view %s.brfss_all with %d total rows", RAW_SCHEMA, total)


def main():
    parser = argparse.ArgumentParser(description="Load BRFSS XPTs into DuckDB")
    parser.add_argument("--years", nargs="+", type=int, default=YEARS)
    parser.add_argument("--data-dir", type=Path, default=RAW_DATA_DIR)
    parser.add_argument("--db-path", type=Path, default=DUCKDB_PATH)
    args = parser.parse_args()

    con = initialize_database(args.db_path)
    try:
        for year in args.years:
            load_year(con, year, args.data_dir)
        create_unified_view(con, args.years)
        log.info("Load complete.")
    finally:
        con.close()


if __name__ == "__main__":
    main()

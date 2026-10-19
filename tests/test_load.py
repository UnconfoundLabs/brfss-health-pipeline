"""Unit tests for ingestion/load_to_duckdb.py"""

import pandas as pd
import pytest

from ingestion.config import COLUMN_NAME_MAP
from ingestion.load_to_duckdb import add_metadata, clean_column_names


def test_clean_column_names_strips_underscores():
    df = pd.DataFrame(columns=["_BMI5", "_STATE", "DIABETE4", "_LLCPWT"])
    result = clean_column_names(df)
    assert "bmi5" in result.columns
    assert "state" in result.columns
    assert "diabete4" in result.columns
    assert "llcpwt" in result.columns


def test_clean_column_names_no_original_cols_remain():
    df = pd.DataFrame(columns=list(COLUMN_NAME_MAP.keys()))
    result = clean_column_names(df)
    # None of the original CDC names (with leading underscores) should remain
    for original_col in COLUMN_NAME_MAP:
        if original_col.startswith("_"):
            assert original_col not in result.columns


def test_add_metadata_adds_survey_year():
    df = pd.DataFrame({"llcpwt": [1.0, 2.0]})
    result = add_metadata(df, year=2022)
    assert "survey_year" in result.columns
    assert (result["survey_year"] == 2022).all()


def test_add_metadata_adds_loaded_at():
    df = pd.DataFrame({"llcpwt": [1.0]})
    result = add_metadata(df, year=2021)
    assert "loaded_at" in result.columns
    assert result["loaded_at"].iloc[0] != ""


def test_initialize_database_creates_schemas(tmp_path):
    from ingestion.load_to_duckdb import initialize_database
    import duckdb

    db_path = tmp_path / "test.duckdb"
    con = initialize_database(db_path)
    schemas = [
        row[0]
        for row in con.execute("SELECT schema_name FROM information_schema.schemata").fetchall()
    ]
    assert "raw" in schemas
    assert "staging" in schemas
    assert "intermediate" in schemas
    assert "marts" in schemas
    con.close()

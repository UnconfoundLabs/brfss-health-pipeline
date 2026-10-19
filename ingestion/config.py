"""Central configuration for BRFSS ingestion pipeline."""

from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
DUCKDB_PATH = PROJECT_ROOT / "data" / "duckdb" / "brfss.duckdb"

# ── Survey years ──────────────────────────────────────────────────────────────
YEARS = [2021, 2022, 2023]

# ── CDC download URLs ─────────────────────────────────────────────────────────
# BRFSS XPT files are distributed as zip archives from the CDC FTP server.
# File naming changed in 2015; these URLs cover 2021-2023.
BRFSS_URL_TEMPLATE = (
    "https://www.cdc.gov/brfss/annual_data/{year}/files/LLCP{year}XPT.zip"
)

# Minimum expected file size in bytes (sanity check; real files are 50-200 MB)
MIN_XPT_BYTES = 10_000_000

# Minimum expected row count per year (BRFSS is ~400K-500K respondents/year)
MIN_ROWS_PER_YEAR = 400_000

# ── DuckDB schemas ────────────────────────────────────────────────────────────
RAW_SCHEMA = "raw"
STAGING_SCHEMA = "staging"
INTERMEDIATE_SCHEMA = "intermediate"
MARTS_SCHEMA = "marts"

# ── BRFSS column allowlist ────────────────────────────────────────────────────
# Only load these columns to keep the database lean.
# CDC variable names (uppercase with leading underscores for calculated vars).
# Note: pyreadstat returns them as-is; we clean names in load_to_duckdb.py.
COLUMNS_TO_KEEP = [
    # --- Outcomes ---
    "DIABETE4",   # Ever told you have diabetes
    "PREDIAB2",   # Prediabetes / borderline diabetes
    "INSULIN1",   # Currently taking insulin

    # --- Risk factors ---
    "_BMI5",      # Calculated BMI (value * 100; divide by 100 in staging)
    "_BMI5CAT",   # BMI category (1=Underweight, 2=Normal, 3=Overweight, 4=Obese)
    "_RFHYPE6",   # High blood pressure calculated variable
    "CVDCRHD4",   # Coronary heart disease / angina
    "EXERANY2",   # Exercise in past 30 days
    "_PAINDX3",   # Physical activity index
    "FRUIT2",     # Times per day/week fruit consumed
    "FRUITJU2",   # Times per day/week fruit juice consumed
    "VEGETAB2",   # Times per day/week vegetables consumed

    # --- Demographics ---
    "_STATE",     # State FIPS code
    "IMONTH",     # Interview month
    "IYEAR",      # Interview year
    "SEXVAR",     # Sex (2021+ variable name; older years used SEX1/SEX)
    "_AGEG5YR",   # Age in 5-year groups (1=18-24 ... 13=80+)
    "_RACE1",     # Race/ethnicity (7 categories)
    "_RACEGR3",   # Race/ethnicity collapsed (5 groups)
    "EDUCA",      # Education level (1-6)
    "INCOME3",    # Annual household income (1-11)
    "_URBSTAT",   # Urban/rural status (1=Urban, 2=Rural)

    # --- Survey design (required for valid population estimates) ---
    "_LLCPWT",    # Final combined landline/cellphone survey weight
    "_STSTR",     # Stratum (for variance estimation via Taylor Series)
    "_PSU",       # Primary sampling unit (for variance estimation)
]

# Rotating-core variables asked only in some years (odd years for 2021-2023:
# fruit/vegetable, hypertension awareness, aerobic activity). Missing in an off year
# is expected; the unified view fills them with NULL. Verify against each year's codebook.
ROTATING_CORE_COLUMNS = {"FRUIT2", "FRUITJU2", "VEGETAB2", "_RFHYPE6", "_PAINDX3"}

# Map from CDC variable name to clean SQL-safe column name
# Leading underscores stripped; all lowercase
COLUMN_NAME_MAP = {col: col.lstrip("_").lower() for col in COLUMNS_TO_KEEP}

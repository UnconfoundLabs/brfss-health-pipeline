"""Write small synthetic BRFSS-shaped XPT files for smoke-testing the pipeline.

The values are random draws over each variable's codebook codes, NOT real CDC data.
Use only to check that ingestion -> GE -> dbt runs end to end (e.g. in CI, or when
the CDC download is unreachable). Weights are scaled so each year sums to ~255M adults.

Usage:
    python -m tests.fixtures.make_synthetic_brfss --rows 20000
    python -m tests.fixtures.make_synthetic_brfss --rows 450000 --years 2021 2022 2023
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

from ingestion.config import RAW_DATA_DIR, ROTATING_CORE_COLUMNS, YEARS
from ingestion.download_brfss import xpt_path

STATE_FIPS = [1, 2, 4, 5, 6, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
              25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 44, 45,
              46, 47, 48, 49, 50, 51, 53, 54, 55, 56, 66, 72, 78]


def _codes(rng, n, codes, probs):
    return rng.choice(codes, size=n, p=np.array(probs) / sum(probs)).astype(float)


def _food_freq(rng, n):
    """FRUIT2/VEGETAB2-style codes: 1__/day, 2__/week, 3__/month, 300, 555, 777, 999."""
    kind = rng.choice(["day", "week", "month", "never", "dk"], size=n, p=[.45, .38, .1, .04, .03])
    out = np.where(kind == "day", 100 + rng.integers(1, 5, n), 0)
    out = np.where(kind == "week", 200 + rng.integers(1, 7, n), out)
    out = np.where(kind == "month", 300 + rng.integers(0, 4, n), out)
    out = np.where(kind == "never", 555, out)
    out = np.where(kind == "dk", rng.choice([777, 999], size=n), out)
    return out.astype(float)


def synthetic_year(year: int, n: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed + year)
    bmi = np.clip(rng.normal(2850, 600, n), 1200, 9000).round()
    bmi = np.where(rng.random(n) < 0.08, np.nan, bmi)
    bmicat = np.select([bmi < 1850, bmi < 2500, bmi < 3000], [1, 2, 3], 4).astype(float)
    bmicat = np.where(np.isnan(bmi), np.nan, bmicat)
    weight = rng.lognormal(0, 0.8, n)
    df = pd.DataFrame({
        "DIABETE4": _codes(rng, n, [1, 2, 3, 4, 7, 9], [11.5, 1, 83, 3, .3, .2]),
        "PREDIAB2": _codes(rng, n, [1, 2, 7, 9], [15, 80, 4, 1]),
        "INSULIN1": _codes(rng, n, [1, 2, 9], [4, 95, 1]),
        "_BMI5": bmi,
        "_BMI5CAT": bmicat,
        "_RFHYPE6": _codes(rng, n, [1, 2, 9], [66, 33, 1]),
        "CVDCRHD4": _codes(rng, n, [1, 2, 7, 9], [4, 94, 1.5, .5]),
        "EXERANY2": _codes(rng, n, [1, 2, 7, 9], [75, 24, .5, .5]),
        "_PAINDX3": _codes(rng, n, [1, 2, 3, 9], [48, 20, 28, 4]),
        "FRUIT2": _food_freq(rng, n),
        "FRUITJU2": _food_freq(rng, n),
        "VEGETAB2": _food_freq(rng, n),
        "_STATE": rng.choice(STATE_FIPS, size=n).astype(float),
        "IMONTH": rng.integers(1, 13, n).astype(float),
        "IYEAR": np.full(n, float(year)),
        "SEXVAR": _codes(rng, n, [1, 2], [48, 52]),
        "_AGEG5YR": _codes(rng, n, list(range(1, 15)), [7] * 13 + [1]),
        "_RACE1": _codes(rng, n, [1, 2, 3, 4, 5, 6, 7, 9], [62, 9, 2, 4, .5, 3, 17, 2.5]),
        "_RACEGR3": _codes(rng, n, [1, 2, 3, 4, 5, 9], [62, 9, 17, 7, 3, 2]),
        "EDUCA": _codes(rng, n, [1, 2, 3, 4, 5, 6, 9], [.2, 2, 5, 26, 28, 38, .8]),
        "INCOME3": _codes(rng, n, list(range(1, 12)) + [77, 99], [3] * 11 + [8, 7]),
        "_URBSTAT": _codes(rng, n, [1, 2], [85, 15]),
        "_LLCPWT": weight / weight.sum() * 255e6,
        "_STSTR": rng.integers(11011, 78999, n).astype(float),
        "_PSU": (year * 1e6 + np.arange(n)).astype(float),
    })
    # Off-year: rotating-core modules not asked (odd years only for 2021-2023)
    if year % 2 == 0:
        df = df.drop(columns=[c for c in ROTATING_CORE_COLUMNS if c in df.columns])
    return df


def main():
    parser = argparse.ArgumentParser(description="Write synthetic BRFSS XPT fixtures")
    parser.add_argument("--years", nargs="+", type=int, default=YEARS)
    parser.add_argument("--rows", type=int, default=20_000)
    parser.add_argument("--output-dir", type=Path, default=RAW_DATA_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for year in args.years:
        path = xpt_path(year, args.output_dir)
        pyreadstat.write_xport(synthetic_year(year, args.rows), str(path), file_format_version=5)
        print(f"Wrote {path} ({args.rows} synthetic rows)")


if __name__ == "__main__":
    main()

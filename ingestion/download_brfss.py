"""Download BRFSS XPT files from CDC for specified survey years.

Usage:
    python -m ingestion.download_brfss
    python -m ingestion.download_brfss --years 2022 2023
"""

import argparse
import hashlib
import io
import logging
import zipfile
from pathlib import Path

import requests
from tqdm import tqdm

from ingestion.config import (
    BRFSS_URL_TEMPLATE,
    MIN_XPT_BYTES,
    RAW_DATA_DIR,
    YEARS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def xpt_path(year: int, output_dir: Path) -> Path:
    return output_dir / f"LLCP{year}.XPT"


def sha256_path(year: int, output_dir: Path) -> Path:
    return output_dir / f"LLCP{year}.XPT.sha256"


def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def download_year(year: int, output_dir: Path, force: bool = False) -> Path:
    """Download and extract BRFSS XPT for a given year.

    Args:
        year: Survey year (e.g. 2021).
        output_dir: Directory to write the XPT file into.
        force: Re-download even if the file already exists.

    Returns:
        Path to the extracted XPT file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = xpt_path(year, output_dir)
    sha_file = sha256_path(year, output_dir)

    if dest.exists() and not force:
        log.info("Year %d already downloaded at %s — skipping.", year, dest)
        return dest

    url = BRFSS_URL_TEMPLATE.format(year=year)
    log.info("Downloading BRFSS %d from %s ...", year, url)

    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()

    total = int(response.headers.get("content-length", 0))
    buffer = io.BytesIO()

    with tqdm(
        total=total,
        unit="B",
        unit_scale=True,
        desc=f"BRFSS {year}",
        leave=False,
    ) as pbar:
        for chunk in response.iter_content(chunk_size=1024 * 64):
            buffer.write(chunk)
            pbar.update(len(chunk))

    buffer.seek(0)

    log.info("Extracting zip for year %d ...", year)
    with zipfile.ZipFile(buffer) as zf:
        # Some CDC zips name the member with a trailing space ("LLCP2022.XPT ")
        xpt_names = [n for n in zf.namelist() if n.strip().upper().endswith(".XPT")]
        if not xpt_names:
            raise ValueError(f"No XPT file found in zip for year {year}. Contents: {zf.namelist()}")
        # CDC may vary casing; take first match
        xpt_name = xpt_names[0]
        with zf.open(xpt_name) as src, open(dest, "wb") as out:
            out.write(src.read())

    file_size = dest.stat().st_size
    if file_size < MIN_XPT_BYTES:
        dest.unlink()
        raise ValueError(
            f"XPT for year {year} is suspiciously small ({file_size} bytes). "
            "Expected at least 10 MB. Check the CDC URL."
        )

    digest = compute_sha256(dest)
    sha_file.write_text(digest)
    log.info(
        "Year %d downloaded: %s (%.1f MB, SHA256=%s...)", year, dest, file_size / 1e6, digest[:12]
    )
    return dest


def download_all_years(years: list[int], output_dir: Path, force: bool = False) -> dict[int, Path]:
    results = {}
    for year in years:
        try:
            results[year] = download_year(year, output_dir, force=force)
        except Exception as exc:
            log.error("Failed to download year %d: %s", year, exc)
            raise
    return results


def main():
    parser = argparse.ArgumentParser(description="Download BRFSS XPT files from CDC")
    parser.add_argument("--years", nargs="+", type=int, default=YEARS)
    parser.add_argument("--output-dir", type=Path, default=RAW_DATA_DIR)
    parser.add_argument("--force", action="store_true", help="Re-download even if file exists")
    args = parser.parse_args()

    paths = download_all_years(args.years, args.output_dir, force=args.force)
    log.info("All downloads complete: %s", {y: str(p) for y, p in paths.items()})


if __name__ == "__main__":
    main()

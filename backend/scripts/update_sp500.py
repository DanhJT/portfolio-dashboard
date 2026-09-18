#!/usr/bin/env python3
"""Refresh the S&P 500 constituent list that defines the strategy universe.

Scrapes Wikipedia's "List of S&P 500 companies" table and writes two files:

- ``backend/data/sp500_constituents.csv`` — symbol, name, gics_sector, cik
- ``frontend/src/sp500Sectors.json``      — {as_of, sectors: {TICKER: label}}

Run this by hand after S&P's quarterly index changes. The strategy itself only
ever reads the committed CSV, so a snapshot run never depends on Wikipedia
being up and is reproducible from the repo alone.

Symbols are normalised to Yahoo's convention (``BRK.B`` -> ``BRK-B``), and the
CIK column is kept so the strategy can collapse multiple share classes of the
same company (GOOGL/GOOG, FOX/FOXA, NWS/NWSA) into one position.

Usage:
    backend/.venv/bin/python backend/scripts/update_sp500.py
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# Wikipedia blocks requests without a descriptive User-Agent.
HEADERS = {"User-Agent": "portfolio-dashboard/1.0 (universe refresh script)"}

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CSV_PATH = REPO_ROOT / "backend" / "data" / "sp500_constituents.csv"
SECTORS_JSON_PATH = REPO_ROOT / "frontend" / "src" / "sp500Sectors.json"

# The S&P 500 sits at ~503 lines (a few companies have two share classes).
# Anything well below that means we parsed the wrong table.
MIN_EXPECTED_ROWS = 450

# Full GICS sector names -> the short labels the frontend charts already use
# (see SP500_SECTOR_WEIGHTS in frontend/src/sectors.js).
SECTOR_LABELS: dict[str, str] = {
    "Information Technology": "Info Tech",
    "Financials": "Financials",
    "Consumer Discretionary": "Cons Disc",
    "Communication Services": "Comm Services",
    "Health Care": "Health Care",
    "Industrials": "Industrials",
    "Consumer Staples": "Cons Staples",
    "Energy": "Energy",
    "Utilities": "Utilities",
    "Real Estate": "Real Estate",
    "Materials": "Materials",
}


def normalise_symbol(symbol: str) -> str:
    """Wikipedia writes class shares as BRK.B; Yahoo wants BRK-B."""
    return symbol.strip().upper().replace(".", "-")


def _squash(text: str) -> str:
    """Collapse all whitespace out of a header cell.

    Header cells contain line breaks (``GICS<br>Sector``), so matching on the
    exact rendered string is brittle — compare squashed lowercase instead.
    """
    return "".join(text.split()).lower()


def _column_index(header: list[str], *names: str) -> int:
    """Index of the first header cell matching any of `names`, whitespace-insensitively."""
    squashed = [_squash(h) for h in header]
    for name in names:
        try:
            return squashed.index(_squash(name))
        except ValueError:
            continue
    raise ValueError(f"none of {names} found in header {header}")


def fetch_rows() -> list[dict[str, str]]:
    """Parse the constituents table into symbol/name/gics_sector/cik dicts."""
    resp = requests.get(WIKI_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    # html.parser keeps this dependency-free — lxml isn't installed.
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", id="constituents")
    if table is None:
        raise RuntimeError("could not find the 'constituents' table on the page")

    header = [th.get_text(" ", strip=True) for th in table.find("tr").find_all("th")]
    try:
        idx_symbol = _column_index(header, "Symbol", "Ticker")
        idx_name = _column_index(header, "Security", "Company")
        idx_sector = _column_index(header, "GICS Sector")
        idx_cik = _column_index(header, "CIK")
    except ValueError as exc:
        raise RuntimeError(f"unexpected table header {header}") from exc

    rows: list[dict[str, str]] = []
    for tr in table.find_all("tr")[1:]:
        cells = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all(["td", "th"])]
        if len(cells) <= max(idx_symbol, idx_name, idx_sector, idx_cik):
            continue
        symbol = normalise_symbol(cells[idx_symbol])
        if not symbol:
            continue
        rows.append({
            "symbol": symbol,
            "name": cells[idx_name],
            "gics_sector": cells[idx_sector],
            # Zero-padded 10-digit CIK, as the SEC writes it.
            "cik": cells[idx_cik].zfill(10),
        })

    rows.sort(key=lambda r: r["symbol"])
    return rows


def write_csv(rows: list[dict[str, str]], as_of: str) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="") as fh:
        fh.write(f"# S&P 500 constituents — as_of: {as_of} — source: {WIKI_URL}\n")
        writer = csv.DictWriter(fh, fieldnames=["symbol", "name", "gics_sector", "cik"])
        writer.writeheader()
        writer.writerows(rows)


def write_sectors_json(rows: list[dict[str, str]], as_of: str) -> None:
    sectors = {r["symbol"]: SECTOR_LABELS[r["gics_sector"]] for r in rows}
    SECTORS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECTORS_JSON_PATH.write_text(
        json.dumps({"as_of": as_of, "sectors": sectors}, indent=2, sort_keys=True) + "\n"
    )


def main() -> int:
    as_of = date.today().isoformat()
    rows = fetch_rows()

    if len(rows) < MIN_EXPECTED_ROWS:
        print(f"ERROR: parsed only {len(rows)} rows (expected ~503)", file=sys.stderr)
        return 1

    unknown = sorted({r["gics_sector"] for r in rows} - SECTOR_LABELS.keys())
    if unknown:
        print(f"ERROR: unmapped GICS sectors: {unknown}", file=sys.stderr)
        print("Add them to SECTOR_LABELS (and to SP500_SECTOR_WEIGHTS in sectors.js).",
              file=sys.stderr)
        return 1

    missing_cik = [r["symbol"] for r in rows if not r["cik"].strip("0")]
    if missing_cik:
        print(f"WARNING: no CIK for {missing_cik} — share-class dedupe may miss these",
              file=sys.stderr)

    write_csv(rows, as_of)
    write_sectors_json(rows, as_of)

    sector_counts = {}
    for r in rows:
        sector_counts[r["gics_sector"]] = sector_counts.get(r["gics_sector"], 0) + 1
    print(f"wrote {len(rows)} constituents (as_of {as_of})")
    print(f"  {CSV_PATH.relative_to(REPO_ROOT)}")
    print(f"  {SECTORS_JSON_PATH.relative_to(REPO_ROOT)}")
    for sector, count in sorted(sector_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>3}  {sector}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

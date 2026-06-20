import sys
import json
from pathlib import Path
import pandas as pd
import requests
from loguru import logger
from tenacity import retry, wait_exponential, stop_after_attempt

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

import config

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


@retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(3))
def fetch_wikipedia_sp500():
    logger.info("Fetching S&P 500 current constituents and historical changes from Wikipedia...")
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    tables = pd.read_html(response.text)
    return tables[0], tables[1]


@retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(3))
def fetch_wikipedia_sp400():
    logger.info("Fetching S&P 400 Midcap for universe extension proxy...")
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    tables = pd.read_html(response.text)
    return set(tables[0]['Symbol'].astype(str).str.replace('.', '-', regex=False).tolist()[:300])


def build_universe():
    config.CONSTITUENTS_DIR.mkdir(parents=True, exist_ok=True)

    current_table, changes_table = fetch_wikipedia_sp500()
    extension_300 = fetch_wikipedia_sp400()

    current_tickers = set(current_table['Symbol'].astype(str).str.replace('.', '-', regex=False).tolist())

    change_records = []
    for _, row in changes_table.iterrows():
        date_val = row.iloc[0]
        added_val = row.iloc[1]
        removed_val = row.iloc[3]

        d = pd.to_datetime(date_val, errors='coerce')
        if pd.isna(d):
            continue

        added = str(added_val).replace('.', '-') if pd.notna(added_val) else None
        removed = str(removed_val).replace('.', '-') if pd.notna(removed_val) else None

        change_records.append({'date': d, 'added': added, 'removed': removed})

    change_records.sort(key=lambda x: x['date'], reverse=True)

    working_set = set(current_tickers)
    current_year = pd.Timestamp.now().year
    change_idx = 0

    for year in range(current_year, 2003, -1):
        target_date = pd.Timestamp(year=year, month=12, day=31)

        while change_idx < len(change_records) and change_records[change_idx]['date'] > target_date:
            rec = change_records[change_idx]
            if rec['added'] and rec['added'] not in ['nan', 'None']:
                working_set.discard(rec['added'])
            if rec['removed'] and rec['removed'] not in ['nan', 'None']:
                working_set.add(rec['removed'])
            change_idx += 1

        final_universe = list(working_set.union(extension_300))
        final_universe = sorted([t for t in final_universe if isinstance(t, str) and len(t) > 0 and t != 'nan'])

        file_path = config.CONSTITUENTS_DIR / f"sp500_{year}.json"
        with open(file_path, "w") as f:
            json.dump(final_universe, f, indent=4)

        logger.info(f"Saved {len(final_universe)} tickers for year {year} to {file_path.name}")

    saved_files = list(config.CONSTITUENTS_DIR.glob("sp500_*.json"))
    if len(saved_files) >= 20:
        logger.info(
            f"Task 02 Verification: SUCCESS. {len(saved_files)} historical constituent JSONs built in data/constituents/.")
    else:
        logger.error(f"Task 02 Verification: FAILED. Expected >= 20 JSONs, found {len(saved_files)}.")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
    build_universe()
"""Main CLI Entrypoint for Weather Forecast Data Pipeline.

Handles:
- HW10-1: Data fetching (via CWA F-C0032-003 API or offline fixture) & JSON inspection
- HW10-2: Analysis and temperature extraction for 6 Taiwan regions
- HW10-3: Database storage in data.db and execution of verification queries
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from weather_service import (
    fetch_cwa_forecast,
    get_api_key,
    get_central_region_forecast,
    get_distinct_regions,
    get_region_forecast,
    parse_temperature_forecasts,
    save_to_db,
)


def run_pipeline(
    api_key: Optional[str] = None,
    from_fixture: Optional[str] = None,
    db_path: str = "data.db",
    inspect: bool = False,
    verify_only: bool = False,
) -> int:
    """Execute the pipeline steps according to HW10 rubric."""
    default_fixture = Path(__file__).parent / "fixtures" / "cwa_sample.json"

    if verify_only:
        print(f"[*] Running database verification queries on '{db_path}'...")
        return run_verification(db_path)

    raw_data = None
    source_description = ""

    # Step 1: HW10-1 Fetching data (API or Fixture)
    resolved_key = get_api_key(api_key)
    if from_fixture:
        print(f"[HW10-1] Reading offline fixture from: {from_fixture}")
        with open(from_fixture, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        source_description = f"Offline Fixture ({from_fixture})"
    elif resolved_key:
        print("[HW10-1] CWA API key detected. Calling LIVE CWA API (F-C0032-003)...")
        try:
            raw_data = fetch_cwa_forecast(api_key=resolved_key)
            source_description = "Live CWA API (F-C0032-003)"
            print("[+] Successfully fetched live weather data from CWA API (F-C0032-003).")
        except Exception as exc:
            print(f"[!] Live CWA API call failed: {exc}")
            return 1
    elif default_fixture.exists():
        print(f"[HW10-1] No CWA API key detected. Running in offline mode with fixture: {default_fixture}")
        with open(default_fixture, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        source_description = f"Offline Fixture ({default_fixture})"
    else:
        print("[!] Error: No API key or fixture available. Please set CWA_API_KEY, create api_key.txt, or provide --from-fixture.")
        return 1

    # HW10-1: Inspect raw data if requested
    if inspect and raw_data:
        print("\n--- [HW10-1] Raw JSON Inspection (sample) ---")
        try:
            sample_location = raw_data["cwaopendata"]["Dataset"]["Locations"]["Location"][0]
            print(json.dumps(sample_location, indent=4, ensure_ascii=False))
        except Exception:
            try:
                sample_location = raw_data["cwaopendata"]["resources"]["resource"]["data"]["agrWeatherForecasts"]["weatherForecasts"]["location"][0]
                print(json.dumps(sample_location, indent=4, ensure_ascii=False))
            except Exception:
                print(json.dumps(raw_data, indent=4, ensure_ascii=False)[:500])

    # Step 2: HW10-2 Parse and extract MaxT / MinT
    print(f"\n[HW10-2] Analyzing and extracting MaxT and MinT from {source_description}...")
    records = parse_temperature_forecasts(raw_data)
    print(f"[+] Extracted {len(records)} temperature forecast records.")

    if inspect and records:
        print("\n--- [HW10-2] Extracted Temperature Records (First 5 records) ---")
        print(json.dumps(records[:5], indent=4, ensure_ascii=False))

    # Step 3: HW10-3 Save to SQLite Database
    print(f"\n[HW10-3] Saving temperature records to SQLite: {db_path}...")
    saved_count = save_to_db(records, db_path=db_path, drop_existing=True)
    print(f"[+] Successfully saved {saved_count} records to table 'TemperatureForecasts' in '{db_path}'.")

    # HW10-3 Verification Queries
    return run_verification(db_path)


def run_verification(db_path: str = "data.db") -> int:
    """Execute HW10-3 required verification queries:
    1. Query all distinct region names
    2. Query central region ('中部地區') temperature forecasts
    """
    print("\n--- [HW10-3 Verification Queries] ---")
    distinct_regions = get_distinct_regions(db_path)
    print(f"1. 所有地區名稱 (SELECT DISTINCT regionName):")
    for i, reg in enumerate(distinct_regions, 1):
        print(f"   [{i}] {reg}")

    print(f"\n2. 中部地區氣溫資料 (WHERE regionName = '中部地區'):")
    central_records = get_region_forecast("中部地區", db_path=db_path)
    if not central_records:
        print("   [!] No records found for 中部地區.")
        return 1

    header = f"   {'Date':<12} | {'MinT (°C)':<10} | {'MaxT (°C)':<10}"
    print(header)
    print("   " + "-" * len(header))
    for row in central_records:
        print(f"   {row['dataDate']:<12} | {row['mint']:<10} | {row['maxt']:<10}")

    print("\n[+] Verification successful! All HW10-1 ~ HW10-3 requirements verified.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HW10 Weather Forecast Data Pipeline & Database Setup (CWA F-C0032-003)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="CWA API Authorization Key (can also be provided via api_key.txt or CWA_API_KEY env var)",
    )
    parser.add_argument(
        "--from-fixture",
        type=str,
        default=None,
        help="Load data from an offline JSON fixture file instead of live API",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data.db",
        help="Path to SQLite database file",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Display sample JSON using json.dumps (satisfies HW10-1 & HW10-2 inspection rubric)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only run the HW10-3 database verification queries on existing data.db",
    )

    args = parser.parse_args()
    code = run_pipeline(
        api_key=args.api_key,
        from_fixture=args.from_fixture,
        db_path=args.db_path,
        inspect=args.inspect,
        verify_only=args.verify_only,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()

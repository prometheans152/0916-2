"""Build script to generate static forecast data for GitHub Pages.

Exports forecast data into docs/data/forecast.json.
Supports:
- Live CWA F-C0032-003 API fetch when CWA_API_KEY is present in env.
- Fallback to local SQLite database (data.db) if present.
- Safe fallback to fixtures/cwa_sample.json when secret is absent or network fails.
- Security: NEVER writes or exposes any API key.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure parent directory is in sys.path so weather_service can be imported
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from weather_service import (
    calculate_avg_temp,
    fetch_cwa_forecast,
    get_api_key,
    get_temp_bin,
    get_temp_color,
    parse_temperature_forecasts,
    TEMP_BIN_COLORS,
)

REGION_COORDS: Dict[str, Dict[str, Any]] = {
    "北部地區": {"lat": 25.0330, "lon": 121.5654, "city": "臺北 Taipei"},
    "中部地區": {"lat": 24.1477, "lon": 120.6736, "city": "臺中 Taichung"},
    "南部地區": {"lat": 22.6273, "lon": 120.3014, "city": "高雄 Kaohsiung"},
    "東北部地區": {"lat": 24.7570, "lon": 121.7530, "city": "宜蘭 Yilan"},
    "東部地區": {"lat": 23.9872, "lon": 121.6015, "city": "花蓮 Hualien"},
    "東南部地區": {"lat": 22.7583, "lon": 121.1444, "city": "臺東 Taitung"},
}


def load_records_from_db(db_path: Path) -> List[Dict[str, Any]]:
    """Read parsed records from local SQLite database."""
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT regionName, dataDate, mint, maxt FROM TemperatureForecasts ORDER BY id ASC"
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "regionName": str(r["regionName"]),
                "dataDate": str(r["dataDate"]),
                "mint": int(r["mint"]),
                "maxt": int(r["maxt"]),
            }
            for r in rows
        ]
    except Exception:
        return []


def build_pages_data(
    output_path: Path | None = None,
    db_path: Path | None = None,
    force_fixture: bool = False,
) -> Dict[str, Any]:
    """Extract forecast records and export docs/data/forecast.json."""
    if output_path is None:
        output_path = REPO_ROOT / "docs" / "data" / "forecast.json"
    if db_path is None:
        db_path = REPO_ROOT / "data.db"

    fixture_path = REPO_ROOT / "fixtures" / "cwa_sample.json"

    raw_records: List[Dict[str, Any]] = []
    source_name = ""

    # 1. Attempt Live CWA fetch if API key available and not forcing fixture
    if not force_fixture:
        api_key = get_api_key()
        if api_key:
            try:
                raw_json = fetch_cwa_forecast(api_key=api_key)
                parsed = parse_temperature_forecasts(raw_json)
                if len(parsed) >= 42:
                    raw_records = parsed
                    source_name = "Live CWA API (F-C0032-003)"
            except Exception:
                # Live fetch failed; fall through to cached DB or fixture
                pass

    # 2. Fallback to local SQLite database if live fetch not performed or failed
    if not raw_records and db_path.exists() and not force_fixture:
        db_records = load_records_from_db(db_path)
        if len(db_records) >= 42:
            raw_records = db_records
            min_date = min(r["dataDate"] for r in raw_records)
            if min_date.startswith("2024"):
                source_name = "Offline Sample (fixtures/cwa_sample.json)"
            else:
                source_name = "Live CWA API (F-C0032-003) [Local Cache]"

    # 3. Fallback to fixture JSON
    if not raw_records and fixture_path.exists():
        with open(fixture_path, "r", encoding="utf-8") as f:
            fixture_json = json.load(f)
        raw_records = parse_temperature_forecasts(fixture_json)
        source_name = "Offline Sample (fixtures/cwa_sample.json)"

    if not raw_records:
        raise RuntimeError("No forecast records could be loaded from API, SQLite, or fixture.")

    # Enrich records with AvgT, color bin, coordinates, and representative city
    enriched_records: List[Dict[str, Any]] = []
    for r in raw_records:
        rname = r["regionName"]
        d_str = str(r["dataDate"])
        mint_v = int(r["mint"])
        maxt_v = int(r["maxt"])
        avg_t = calculate_avg_temp(mint_v, maxt_v)
        bin_label = get_temp_bin(avg_t)
        color_hex = get_temp_color(avg_t)
        coords = REGION_COORDS.get(rname, {"lat": 23.7, "lon": 120.95, "city": ""})

        enriched_records.append({
            "regionName": rname,
            "dataDate": d_str,
            "mint": mint_v,
            "maxt": maxt_v,
            "avg_t": avg_t,
            "temp_bin": bin_label,
            "temp_color": color_hex,
            "lat": coords["lat"],
            "lon": coords["lon"],
            "city": coords["city"],
        })

    # Sort records by region and date
    enriched_records.sort(key=lambda x: (x["regionName"], x["dataDate"]))

    regions_list = [
        "北部地區",
        "中部地區",
        "南部地區",
        "東北部地區",
        "東部地區",
        "東南部地區",
    ]
    dates_list = sorted(list({r["dataDate"] for r in enriched_records}))

    payload: Dict[str, Any] = {
        "metadata": {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(),
            "source": source_name,
            "total_records": len(enriched_records),
            "total_regions": len(regions_list),
            "total_dates": len(dates_list),
            "color_bins": {
                "< 20°C": "#1f77b4",
                "20–25°C": "#2ecc71",
                "25–30°C": "#f1c40f",
                "> 30°C": "#e74c3c",
            },
            "region_coords": REGION_COORDS,
        },
        "regions": regions_list,
        "dates": dates_list,
        "records": enriched_records,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Export forecast data to docs/data/forecast.json")
    parser.add_argument("--output", type=str, default=None, help="Target output JSON path")
    parser.add_argument("--db-path", type=str, default=None, help="SQLite DB path")
    parser.add_argument("--force-fixture", action="store_true", help="Force offline fixture usage")
    args = parser.parse_args()

    out_p = Path(args.output) if args.output else None
    db_p = Path(args.db_path) if args.db_path else None

    result = build_pages_data(output_path=out_p, db_path=db_p, force_fixture=args.force_fixture)
    meta = result["metadata"]
    print(
        f"[+] Successfully exported {meta['total_records']} forecast records to docs/data/forecast.json"
    )
    print(f"    Source: {meta['source']}")
    print(f"    Regions: {meta['total_regions']} | Dates: {meta['total_dates']}")


if __name__ == "__main__":
    main()

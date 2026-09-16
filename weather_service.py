"""Weather Service Module for CWA Weather Forecast Pipeline.

Fulfills requirements for:
- HW10-1: Fetch weather forecast data via CWA API (F-C0032-003) with runtime config.
- HW10-2: Extract MaxT and MinT daily temperature forecasts for 6 Taiwan regions.
- HW10-3: Store temperature data in SQLite3 (data.db / TemperatureForecasts) and execute verification queries.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

CWA_API_URL = "https://opendata.cwa.gov.tw/fileapi/v1/opendataapi/F-C0032-003"
TAIWAN_FORECAST_REGIONS = [
    "北部地區",
    "中部地區",
    "南部地區",
    "東北部地區",
    "東部地區",
    "東南部地區",
]

# Temperature color bin mapping for Taiwan map visualization
# Boundary resolution convention:
# < 20°C: 藍色 (Blue)
# 20°C <= AvgT < 25°C: 綠色 (Green)
# 25°C <= AvgT <= 30°C: 黃色 (Yellow)
# > 30°C: 紅色 (Red)
TEMP_BIN_COLORS = {
    "< 20°C": "#1f77b4",   # 藍色 (Blue)
    "20–25°C": "#2ecc71",  # 綠色 (Green)
    "25–30°C": "#f1c40f",  # 黃色 (Yellow)
    "> 30°C": "#e74c3c",   # 紅色 (Red)
}


def calculate_avg_temp(mint: float | int, maxt: float | int) -> float:
    """Calculate daily average temperature as AvgT = (MinT + MaxT) / 2."""
    return round((float(mint) + float(maxt)) / 2.0, 1)


def get_temp_bin(avg_t: float) -> str:
    """Classify average temperature into color category bin.

    Boundary resolution rule:
    - < 20°C: "< 20°C" (Blue)
    - 20°C <= AvgT < 25°C: "20–25°C" (Green)
    - 25°C <= AvgT <= 30°C: "25–30°C" (Yellow)
    - > 30°C: "> 30°C" (Red)
    """
    if avg_t < 20.0:
        return "< 20°C"
    elif avg_t < 25.0:
        return "20–25°C"
    elif avg_t <= 30.0:
        return "25–30°C"
    else:
        return "> 30°C"


def get_temp_color(avg_t: float) -> str:
    """Return hex color code corresponding to the average temperature bin."""
    return TEMP_BIN_COLORS[get_temp_bin(avg_t)]


def get_api_key(api_key: Optional[str] = None) -> Optional[str]:
    """Retrieve CWA API key from argument, environment variable, or local api_key.txt."""
    if api_key and api_key.strip():
        return api_key.strip()

    env_key = os.environ.get("CWA_API_KEY", "").strip()
    if env_key:
        return env_key

    key_file = Path(__file__).parent / "api_key.txt"
    if key_file.exists():
        file_key = key_file.read_text(encoding="utf-8").strip()
        if file_key and file_key != "PASTE_YOUR_CWA_API_KEY_HERE":
            return file_key

    return None


def fetch_cwa_forecast(api_key: Optional[str] = None) -> Dict[str, Any]:
    """Fetch 7-day regional weather forecast from CWA OpenData API (F-C0032-003).
    
    Calls official live endpoint for Taiwan regional 7-day forecast:
    https://opendata.cwa.gov.tw/fileapi/v1/opendataapi/F-C0032-003?downloadType=WEB&format=JSON
    
    Security: API keys are NEVER hardcoded or leaked in exceptions.
    """
    key = get_api_key(api_key)
    if not key:
        raise ValueError(
            "CWA API key is required. Please provide it via argument or set the "
            "CWA_API_KEY environment variable. Register at https://opendata.cwa.gov.tw/ "
            "to obtain a free API key."
        )

    params = {
        "Authorization": key,
        "downloadType": "WEB",
        "format": "JSON",
    }

    try:
        response = requests.get(CWA_API_URL, params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "Unknown"
        raise RuntimeError(f"CWA API HTTP error (status code: {status}) for dataset F-C0032-003") from None
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"CWA API network request failed: {type(exc).__name__} for dataset F-C0032-003") from None


def parse_temperature_forecasts(raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse CWA F-C0032-003 weather forecast JSON data and extract MaxT & MinT for 6 Taiwan regions.
    
    Extracts daily forecasts from cwaopendata.Dataset.Locations.Location.
    
    Returns a list of dictionaries with normalized keys:
    - regionName: str (e.g., '北部地區', '中部地區')
    - dataDate: str (e.g., '2026-09-16')
    - mint: int (minimum temperature in °C)
    - maxt: int (maximum temperature in °C)
    """
    cwa = raw_data.get("cwaopendata", {})
    records: List[Dict[str, Any]] = []

    # 1. Primary F-C0032-003 schema: cwaopendata -> Dataset -> Locations -> Location
    dataset = cwa.get("Dataset") or cwa.get("dataset", {})
    locations_obj = dataset.get("Locations") or dataset.get("locations", {})
    locs = locations_obj.get("Location") or locations_obj.get("location", [])

    if locs:
        for loc in locs:
            region_name = loc.get("LocationName") or loc.get("locationName", "")
            if region_name not in TAIWAN_FORECAST_REGIONS:
                continue

            elements = loc.get("WeatherElement") or loc.get("weatherElement", [])
            maxt_by_date: Dict[str, int] = {}
            mint_by_date: Dict[str, int] = {}

            for el in elements:
                el_name = el.get("ElementName") or el.get("elementName", "")
                times = el.get("Time") or el.get("time", [])

                if el_name in ["最高溫度", "MaxT", "MaxTemperature"]:
                    for t in times:
                        d = (t.get("StartTime") or t.get("dataDate", ""))[:10]
                        val = (
                            t.get("ElementValue", {}).get("MaxTemperature")
                            if isinstance(t.get("ElementValue"), dict)
                            else t.get("temperature")
                        )
                        if d and val is not None:
                            maxt_by_date[d] = int(val)

                elif el_name in ["最低溫度", "MinT", "MinTemperature"]:
                    for t in times:
                        d = (t.get("StartTime") or t.get("dataDate", ""))[:10]
                        val = (
                            t.get("ElementValue", {}).get("MinTemperature")
                            if isinstance(t.get("ElementValue"), dict)
                            else t.get("temperature")
                        )
                        if d and val is not None:
                            mint_by_date[d] = int(val)

            for date_str in sorted(mint_by_date.keys()):
                if date_str in maxt_by_date:
                    records.append({
                        "regionName": region_name,
                        "dataDate": str(date_str),
                        "mint": int(mint_by_date[date_str]),
                        "maxt": int(maxt_by_date[date_str]),
                    })

        if records:
            return records

    # 2. Backward compatibility fallback for agrWeatherForecasts fixture schema
    if "resources" in cwa and "resource" in cwa["resources"]:
        try:
            legacy_locs = (
                cwa["resources"]["resource"]["data"][
                    "agrWeatherForecasts"
                ]["weatherForecasts"]["location"]
            )
            for loc in legacy_locs:
                region_name = loc.get("locationName", "")
                elements = loc.get("weatherElements", {})
                mint_entries = elements.get("MinT", {}).get("daily", [])
                maxt_entries = elements.get("MaxT", {}).get("daily", [])

                maxt_by_date = {
                    item["dataDate"]: int(item["temperature"])
                    for item in maxt_entries
                    if "dataDate" in item and "temperature" in item
                }

                for mint_item in mint_entries:
                    date_str = mint_item.get("dataDate")
                    mint_val = int(mint_item.get("temperature", 0))
                    if date_str in maxt_by_date:
                        records.append({
                            "regionName": region_name,
                            "dataDate": str(date_str),
                            "mint": mint_val,
                            "maxt": maxt_by_date[date_str],
                        })
            if records:
                return records
        except KeyError:
            pass

    raise ValueError("Unexpected CWA JSON structure: could not locate forecast locations.")


def init_db(db_path: str = "data.db") -> None:
    """Initialize SQLite database schema for TemperatureForecasts table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS TemperatureForecasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        regionName TEXT NOT NULL,
        dataDate TEXT NOT NULL,
        mint INTEGER NOT NULL,
        maxt INTEGER NOT NULL
    )
    """)
    conn.commit()
    conn.close()


def save_to_db(
    records: List[Dict[str, Any]],
    db_path: str = "data.db",
    drop_existing: bool = True,
) -> int:
    """Save parsed temperature records into SQLite database.
    
    Returns the number of records inserted.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if drop_existing:
        cursor.execute("DROP TABLE IF EXISTS TemperatureForecasts")
        cursor.execute("""
        CREATE TABLE TemperatureForecasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            regionName TEXT NOT NULL,
            dataDate TEXT NOT NULL,
            mint INTEGER NOT NULL,
            maxt INTEGER NOT NULL
        )
        """)

    insert_sql = """
    INSERT INTO TemperatureForecasts (regionName, dataDate, mint, maxt)
    VALUES (?, ?, ?, ?)
    """
    for r in records:
        cursor.execute(
            insert_sql,
            (r["regionName"], str(r["dataDate"]), int(r["mint"]), int(r["maxt"])),
        )

    inserted_count = len(records)
    conn.commit()
    conn.close()
    return inserted_count


def get_distinct_regions(db_path: str = "data.db") -> List[str]:
    """HW10-3 Verification Query 1: Query all distinct region names."""
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT regionName FROM TemperatureForecasts ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


def get_region_forecast(
    region_name: str,
    db_path: str = "data.db",
) -> List[Dict[str, Any]]:
    """Query temperature forecast records for a specific region."""
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT regionName, dataDate, mint, maxt FROM TemperatureForecasts WHERE regionName = ? ORDER BY dataDate ASC",
        (region_name,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_central_region_forecast(db_path: str = "data.db") -> List[Dict[str, Any]]:
    """HW10-3 Verification Query 2: Query temperature data for central region ('中部地區')."""
    return get_region_forecast("中部地區", db_path=db_path)

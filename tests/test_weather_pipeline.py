import json
import os
import sqlite3
import pytest
from pathlib import Path

# We will import from weather_service
from weather_service import (
    parse_temperature_forecasts,
    init_db,
    save_to_db,
    get_distinct_regions,
    get_region_forecast,
    fetch_cwa_forecast,
    CWA_API_URL,
    calculate_avg_temp,
    get_temp_bin,
    get_temp_color,
    TEMP_BIN_COLORS,
)


@pytest.fixture
def sample_cwa_data():
    fixture_path = Path(__file__).parent.parent / "fixtures" / "cwa_sample.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_data.db"
    return str(db_file)


def test_parse_temperature_forecasts(sample_cwa_data):
    """Test extracting MaxT and MinT for 6 Taiwan regions across 7 days."""
    records = parse_temperature_forecasts(sample_cwa_data)
    
    # 6 regions * 7 days = 42 records
    assert len(records) == 42
    
    # Check regions
    regions = sorted(list({r["regionName"] for r in records}))
    expected_regions = sorted(["北部地區", "中部地區", "南部地區", "東北部地區", "東部地區", "東南部地區"])
    assert regions == expected_regions
    
    # Check fields of each record
    for r in records:
        assert "regionName" in r
        assert "dataDate" in r
        assert "mint" in r
        assert "maxt" in r
        assert isinstance(r["mint"], int)
        assert isinstance(r["maxt"], int)
        assert r["mint"] <= r["maxt"]


def test_fetch_cwa_forecast_missing_key(monkeypatch):
    """Test that missing API key raises ValueError with clear instructions."""
    monkeypatch.delenv("CWA_API_KEY", raising=False)
    monkeypatch.setattr("weather_service.get_api_key", lambda api_key=None: None)
    with pytest.raises(ValueError) as exc_info:
        fetch_cwa_forecast(api_key=None)
    assert "CWA API key" in str(exc_info.value)


def test_db_lifecycle_and_queries(sample_cwa_data, temp_db):
    """Test SQLite initialization, record insertion, distinct regions, and central region query."""
    records = parse_temperature_forecasts(sample_cwa_data)
    
    # 1. Initialize table
    init_db(temp_db)
    
    # 2. Insert records
    inserted = save_to_db(records, db_path=temp_db)
    assert inserted == 42
    
    # 3. Query distinct regions (HW10-3 requirement)
    regions = get_distinct_regions(temp_db)
    assert len(regions) == 6
    assert "中部地區" in regions
    assert "北部地區" in regions
    
    # 4. Query central region (中部地區) (HW10-3 requirement)
    central_data = get_region_forecast("中部地區", db_path=temp_db)
    assert len(central_data) == 7
    for row in central_data:
        assert row["regionName"] == "中部地區"
        assert 20 <= row["mint"] <= 35
        assert 25 <= row["maxt"] <= 40
        assert row["mint"] <= row["maxt"]


def test_db_column_case_insensitivity(sample_cwa_data, temp_db):
    """Verify queries using MaxT / MinT work seamlessly with SQLite schema."""
    records = parse_temperature_forecasts(sample_cwa_data)
    init_db(temp_db)
    save_to_db(records, db_path=temp_db)
    
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    # Cell 19 in notebook uses `SELECT regionName, dataDate, MinT, MaxT FROM TemperatureForecasts WHERE regionName = '中部地區'`
    cursor.execute("SELECT regionName, dataDate, MinT, MaxT FROM TemperatureForecasts WHERE regionName = '中部地區'")
    rows = cursor.fetchall()
    assert len(rows) == 7
    conn.close()


def test_cli_pipeline_with_fixture(temp_db):
    """Test full CLI pipeline execution using offline fixture."""
    from main import run_pipeline
    
    fixture_path = str(Path(__file__).parent.parent / "fixtures" / "cwa_sample.json")
    exit_code = run_pipeline(
        api_key=None,
        from_fixture=fixture_path,
        db_path=temp_db,
        inspect=True,
    )
    assert exit_code == 0
    
    # Test verify_only flag
    verify_code = run_pipeline(
        db_path=temp_db,
        verify_only=True,
    )
    assert verify_code == 0


def test_app_compilation():
    """Verify app.py has valid Python syntax and compiles cleanly."""
    import py_compile
    app_path = Path(__file__).parent.parent / "app.py"
    compiled = py_compile.compile(str(app_path), doraise=True)
    assert compiled is not None


def test_streamlit_app_smoke(temp_db, sample_cwa_data):
    """Smoke test app.py execution and database queries using Streamlit AppTest."""
    from streamlit.testing.v1 import AppTest
    from weather_service import parse_temperature_forecasts, save_to_db
    
    # Initialize database with sample data
    records = parse_temperature_forecasts(sample_cwa_data)
    save_to_db(records, db_path=temp_db)
    
    # Point app to temporary database
    os.environ["WEATHER_DB_PATH"] = temp_db
    try:
        app_path = str(Path(__file__).parent.parent / "app.py")
        at = AppTest.from_file(app_path)
        at.run(timeout=10)
        assert not at.exception
        # Verify both region and forecast date selectboxes exist
        assert len(at.selectbox) >= 2
        # Region selector has 6 Taiwan regions
        assert len(at.selectbox[0].options) == 6
        # Date selector has available forecast dates (7 days)
        assert len(at.selectbox[1].options) == 7
        assert len(at.dataframe) >= 1
    finally:
        os.environ.pop("WEATHER_DB_PATH", None)
def test_endpoint_is_fc0032_003():
    """Verify primary API URL points to live F-C0032-003 dataset."""
    from weather_service import CWA_API_URL
    assert "F-C0032-003" in CWA_API_URL
    assert "opendata.cwa.gov.tw" in CWA_API_URL


def test_api_failure_does_not_silently_fallback(monkeypatch, temp_db):
    """Verify that when API call fails, pipeline exits with error code 1."""
    from main import run_pipeline

    def mock_fetch_fail(api_key=None):
        raise RuntimeError("CWA API HTTP error (status code: 500) for dataset F-C0032-003")

    monkeypatch.setattr("main.fetch_cwa_forecast", mock_fetch_fail)
    monkeypatch.setattr("main.get_api_key", lambda k: "dummy_valid_key")

    exit_code = run_pipeline(api_key="dummy_valid_key", db_path=temp_db)
    assert exit_code == 1, "Pipeline must return non-zero exit code on API failure and not fall back silently"


def test_map_representative_coordinates():
    """Verify all 6 Taiwan regions have accurate representative coordinates in app.py."""
    import app
    assert hasattr(app, "REGION_COORDS")
    coords = app.REGION_COORDS
    assert len(coords) == 6
    expected_regions = ["北部地區", "中部地區", "南部地區", "東北部地區", "東部地區", "東南部地區"]
    for r in expected_regions:
        assert r in coords
        assert "lat" in coords[r]
        assert "lon" in coords[r]
        # Taiwan latitude roughly 21 to 26 N, longitude 119 to 122 E
        assert 21.0 <= coords[r]["lat"] <= 26.0
        assert 119.0 <= coords[r]["lon"] <= 123.0


def test_avgt_calculation_and_color_bins():
    """Verify daily average temperature calculation AvgT=(MinT+MaxT)/2 and 4-bin color mapping."""
    # Test formula: AvgT = (MinT + MaxT) / 2
    assert calculate_avg_temp(20, 24) == 22.0
    assert calculate_avg_temp(25, 30) == 27.5
    assert calculate_avg_temp(18, 21) == 19.5
    assert calculate_avg_temp(31, 33) == 32.0

    # Test bin boundary resolution:
    # 1. < 20°C -> Blue
    assert get_temp_bin(15.0) == "< 20°C"
    assert get_temp_bin(19.9) == "< 20°C"
    assert get_temp_color(19.9) == TEMP_BIN_COLORS["< 20°C"]

    # 2. 20°C <= AvgT < 25°C -> Green
    assert get_temp_bin(20.0) == "20–25°C"
    assert get_temp_bin(22.5) == "20–25°C"
    assert get_temp_bin(24.9) == "20–25°C"
    assert get_temp_color(20.0) == TEMP_BIN_COLORS["20–25°C"]

    # 3. 25°C <= AvgT <= 30°C -> Yellow
    assert get_temp_bin(25.0) == "25–30°C"
    assert get_temp_bin(27.5) == "25–30°C"
    assert get_temp_bin(30.0) == "25–30°C"
    assert get_temp_color(25.0) == TEMP_BIN_COLORS["25–30°C"]
    assert get_temp_color(30.0) == TEMP_BIN_COLORS["25–30°C"]

    # 4. > 30°C -> Red
    assert get_temp_bin(30.1) == "> 30°C"
    assert get_temp_bin(35.0) == "> 30°C"
    assert get_temp_color(30.1) == TEMP_BIN_COLORS["> 30°C"]




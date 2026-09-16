"""Streamlit Web Application for Temperature Forecast Visualization.

Fulfills HW10-4 (40%) & Advanced Features:
- Dropdown selectbox for choosing Taiwan forecast region (10%)
- Interactive line chart and data table displaying 7-day forecast (15%)
- Direct SQL querying from SQLite database 'data.db' (10%)
- Interactive Taiwan regional forecast map with representative coordinates (Plotly mapbox/map)
- Daily average temperature color bins (<20°C blue, 20–25°C green, 25–30°C yellow, >30°C red)
- Clean code architecture and readability (5%)
"""

import os
import sqlite3
import pandas as pd
import streamlit as st

from weather_service import (
    calculate_avg_temp,
    get_temp_bin,
    TEMP_BIN_COLORS,
)

try:
    import plotly.express as px
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# Fixed representative coordinates for the 6 forecast regions (central reference points)
REGION_COORDS = {
    "北部地區": {"lat": 25.0330, "lon": 121.5654, "city": "臺北 Taipei"},
    "中部地區": {"lat": 24.1477, "lon": 120.6736, "city": "臺中 Taichung"},
    "南部地區": {"lat": 22.6273, "lon": 120.3014, "city": "高雄 Kaohsiung"},
    "東北部地區": {"lat": 24.7570, "lon": 121.7530, "city": "宜蘭 Yilan"},
    "東部地區": {"lat": 23.9872, "lon": 121.6015, "city": "花蓮 Hualien"},
    "東南部地區": {"lat": 22.7583, "lon": 121.1444, "city": "臺東 Taitung"},
}

# Page configuration
st.set_page_config(
    page_title="Temperature Forecast Web App",
    page_icon="🌤️",
    layout="centered",
)

# App Title & Subtitle
st.title("Temperature Forecast Web App")
st.caption("AIoT 課程 HW10: 台灣一週氣溫預報視覺化 (CWA F-C0032-003 + SQLite + Streamlit + 均溫分級地圖)")

DB_PATH = os.environ.get("WEATHER_DB_PATH", "data.db")


def check_and_prepare_db(db_path: str = DB_PATH) -> bool:
    """Check if SQLite database and TemperatureForecasts table exist with data."""
    if not os.path.exists(db_path):
        return False
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='TemperatureForecasts'"
        )
        table_exists = cursor.fetchone()[0] > 0
        if not table_exists:
            conn.close()
            return False
        cursor.execute("SELECT count(*) FROM TemperatureForecasts")
        row_count = cursor.fetchone()[0]
        conn.close()
        return row_count > 0
    except Exception:
        return False


def resolve_cwa_api_key() -> str | None:
    """Retrieve CWA API key without exposing secret.
    
    Checks:
    1. Environment variable CWA_API_KEY (Streamlit Community Cloud root-level secrets become env vars)
    2. Streamlit secrets st.secrets["CWA_API_KEY"]
    3. weather_service.get_api_key fallback (local api_key.txt)
    """
    # 1. Environment variable
    env_key = os.environ.get("CWA_API_KEY", "").strip()
    if env_key:
        return env_key

    # 2. Streamlit secrets (safely handle environments without secrets.toml)
    try:
        if hasattr(st, "secrets") and "CWA_API_KEY" in st.secrets:
            sec_key = str(st.secrets["CWA_API_KEY"]).strip()
            if sec_key:
                return sec_key
    except Exception:
        pass

    # 3. weather_service helper (supports local api_key.txt)
    try:
        from weather_service import get_api_key
        return get_api_key()
    except Exception:
        pass

    return None


def bootstrap_database(db_path: str = DB_PATH) -> str:
    """Automatically bootstrap SQLite database when data.db is missing or empty.
    
    Tries live CWA API (F-C0032-003) if CWA_API_KEY is configured.
    Falls back to fixtures/cwa_sample.json if live call fails or key is missing.
    Returns a concise non-secret data source description.
    """
    from weather_service import (
        fetch_cwa_forecast,
        parse_temperature_forecasts,
        save_to_db,
    )
    import json
    from pathlib import Path

    key = resolve_cwa_api_key()
    if key:
        try:
            raw_data = fetch_cwa_forecast(api_key=key)
            records = parse_temperature_forecasts(raw_data)
            if records:
                save_to_db(records, db_path=db_path, drop_existing=True)
                return "LIVE CWA (F-C0032-003)"
        except Exception:
            # Fall back to offline fixture if live fetch encounters network/HTTP issues
            pass

    # Offline sample fallback for zero-configuration public cloud deployment
    fixture_file = Path(__file__).parent / "fixtures" / "cwa_sample.json"
    if fixture_file.exists():
        with open(fixture_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        records = parse_temperature_forecasts(raw_data)
        save_to_db(records, db_path=db_path, drop_existing=True)
        return "Offline Sample (fixtures/cwa_sample.json)"

    raise RuntimeError("無法初始化資料庫：未設定 API 金鑰且找不到範例資料 (fixtures/cwa_sample.json)。")


def ensure_database_ready(db_path: str = DB_PATH) -> str:
    """Ensure database exists and is populated, returning non-secret source string."""
    if not check_and_prepare_db(db_path):
        source = bootstrap_database(db_path)
        st.session_state["data_source"] = source
        return source

    if "data_source" in st.session_state:
        return st.session_state["data_source"]

    # If DB already exists on disk, determine if it originated from sample fixture or live API
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT MIN(dataDate) FROM TemperatureForecasts")
        row = cur.fetchone()
        conn.close()
        min_date = row[0] if row else ""
        if min_date and min_date.startswith("2024"):
            source = "Offline Sample (fixtures/cwa_sample.json)"
        else:
            source = "LIVE CWA (F-C0032-003)"
    except Exception:
        source = "SQLite Database (data.db)"

    st.session_state["data_source"] = source
    return source


# Automatic database bootstrapping on first page load (no button click required)
current_data_source = ensure_database_ready(DB_PATH)

# Sidebar with data source status & optional manual refresh
with st.sidebar:
    st.header("⚙️ 資料來源與管理")
    st.write(f"**當前模式**：\n`{current_data_source}`")
    if st.button("🔄 重新整理氣象資料 (Refresh Data)"):
        new_source = bootstrap_database(DB_PATH)
        st.session_state["data_source"] = new_source
        st.rerun()

# Concise non-secret status badge on the main page
if "LIVE" in current_data_source.upper():
    st.success(f"🟢 **資料來源 (Data Source)**：{current_data_source}（即時預報連線中）")
else:
    st.info(f"📦 **資料來源 (Data Source)**：{current_data_source}（示範展示模式）")



# 1. Connect to SQLite database and query distinct regions & forecast dates
conn = sqlite3.connect(DB_PATH)

query_regions = "SELECT DISTINCT regionName FROM TemperatureForecasts ORDER BY id ASC"
region_names = pd.read_sql_query(query_regions, conn)

query_dates = "SELECT DISTINCT dataDate FROM TemperatureForecasts ORDER BY dataDate ASC"
df_dates = pd.read_sql_query(query_dates, conn)
available_dates = df_dates["dataDate"].tolist() if not df_dates.empty else []

# 2. Controls: Select Region and Select Forecast Date
col_ctrl1, col_ctrl2 = st.columns(2)
with col_ctrl1:
    selected_region = st.selectbox(
        "Select a Region (請選擇預報地區)",
        region_names["regionName"],
        index=0,
    )
with col_ctrl2:
    selected_date = st.selectbox(
        "Select Forecast Date (選擇地圖預報日期)",
        available_dates,
        index=0 if available_dates else None,
    )

# 3. Query MaxT and MinT for the selected region (HW10-4)
query_weather = """
SELECT dataDate, mint AS MinT, maxt AS MaxT
FROM TemperatureForecasts
WHERE regionName = ?
ORDER BY dataDate ASC
"""
df_weather = pd.read_sql_query(query_weather, conn, params=(selected_region,))

# Ensure column names are standardized to MinT and MaxT regardless of SQLite column casing
col_map = {col: "MinT" if col.lower() == "mint" else "MaxT" if col.lower() == "maxt" else col for col in df_weather.columns}
df_weather = df_weather.rename(columns=col_map)

# 4. Query all 6 regions for the selected date to power the interactive map
query_map_data = """
SELECT regionName, mint AS MinT, maxt AS MaxT
FROM TemperatureForecasts
WHERE dataDate = ?
ORDER BY id ASC
"""
df_map_raw = pd.read_sql_query(query_map_data, conn, params=(selected_date,)) if selected_date else pd.DataFrame()

# Close the database connection
conn.close()

# Key metrics display for the selected region
if not df_weather.empty:
    avg_min = df_weather["MinT"].mean()
    avg_max = df_weather["MaxT"].mean()
    lowest_t = df_weather["MinT"].min()
    highest_t = df_weather["MaxT"].max()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("一週最高溫", f"{highest_t} °C")
    col2.metric("一週最低溫", f"{lowest_t} °C")
    col3.metric("平均最高溫", f"{avg_max:.1f} °C")
    col4.metric("平均最低溫", f"{avg_min:.1f} °C")

# 5. Interactive Taiwan Regional Forecast Map
st.subheader(f"🗺️ 台灣六大分區氣溫預報地圖 ({selected_date})")

if not df_map_raw.empty:
    map_rows = []
    for _, row in df_map_raw.iterrows():
        rname = row["regionName"]
        mint_val = int(row["MinT"])
        maxt_val = int(row["MaxT"])
        avg_t = calculate_avg_temp(mint_val, maxt_val)
        temp_bin = get_temp_bin(avg_t)
        coords = REGION_COORDS.get(rname, {"lat": 23.7, "lon": 120.95, "city": ""})
        is_sel = (rname == selected_region)
        map_rows.append({
            "regionName": rname,
            "lat": coords["lat"],
            "lon": coords["lon"],
            "city": coords["city"],
            "selected_date": selected_date,
            "MinT": mint_val,
            "MaxT": maxt_val,
            "AvgT": avg_t,
            "temp_bin": temp_bin,
            "預報日期 Date": str(selected_date),
            "平均氣溫 AvgT": f"{avg_t:.1f} °C",
            "最低氣溫 MinT": f"{mint_val} °C",
            "最高氣溫 MaxT": f"{maxt_val} °C",
            "代表城市 City": coords["city"],
            "均溫分級 Category": temp_bin,
            "選取狀態 Selection": f"★ 目前選取 ({rname})" if is_sel else f"其他地區 ({rname})",
            # Selected region is emphasized purely by size, never overriding the temperature color
            "標記大小 Marker Size": 28 if is_sel else 15,
        })
    df_map = pd.DataFrame(map_rows)

    # Visible temperature color legend matching the 4 bins
    st.markdown(
        """
        <div style="background-color: rgba(128,128,128,0.08); padding: 10px 14px; border-radius: 8px; margin-bottom: 12px; border: 1px solid rgba(128,128,128,0.2);">
            <div style="font-weight: 600; margin-bottom: 6px; font-size: 14px;">🌡️ 均溫分級色階圖例 (Daily AvgT Color Legend)：</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; font-size: 13px;">
                <span style="background-color: #1f77b4; color: white; padding: 4px 10px; border-radius: 6px; font-weight: 500;">🔵 &lt; 20°C (低溫 / Blue)</span>
                <span style="background-color: #2ecc71; color: white; padding: 4px 10px; border-radius: 6px; font-weight: 500;">🟢 20–25°C (舒適 / Green)</span>
                <span style="background-color: #f1c40f; color: #222; padding: 4px 10px; border-radius: 6px; font-weight: 500;">🟡 25–30°C (溫暖 / Yellow)</span>
                <span style="background-color: #e74c3c; color: white; padding: 4px 10px; border-radius: 6px; font-weight: 500;">🔴 &gt; 30°C (炎熱 / Red)</span>
            </div>
            <div style="font-size: 12px; color: gray; margin-top: 6px;">
                公式：<code>AvgT = (MinT + MaxT) / 2</code>；分界標準：<code>&lt;20°C</code>（藍）、<code>20°C &le; AvgT &lt; 25°C</code>（綠）、<code>25°C &le; AvgT &le; 30°C</code>（黃）、<code>&gt;30°C</code>（紅）。
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if HAS_PLOTLY:
        try:
            common_kwargs = dict(
                data_frame=df_map,
                lat="lat",
                lon="lon",
                hover_name="regionName",
                hover_data={
                    "預報日期 Date": True,
                    "平均氣溫 AvgT": True,
                    "最低氣溫 MinT": True,
                    "最高氣溫 MaxT": True,
                    "代表城市 City": True,
                    "均溫分級 Category": True,
                    "選取狀態 Selection": True,
                    "lat": False,
                    "lon": False,
                    "AvgT": False,
                    "MinT": False,
                    "MaxT": False,
                    "temp_bin": False,
                    "city": False,
                    "selected_date": False,
                    "標記大小 Marker Size": False,
                },
                size="標記大小 Marker Size",
                color="均溫分級 Category",
                color_discrete_map=TEMP_BIN_COLORS,
                category_orders={"均溫分級 Category": ["< 20°C", "20–25°C", "25–30°C", "> 30°C"]},
                zoom=6.2,
                center={"lat": 23.7, "lon": 120.95},
            )
            if hasattr(px, "scatter_map"):
                fig_map = px.scatter_map(**common_kwargs)
                fig_map.update_layout(
                    map_style="open-street-map",
                    margin={"r": 0, "t": 20, "l": 0, "b": 0},
                    height=450,
                    legend_title_text="均溫分級 (AvgT)",
                )
            elif hasattr(px, "scatter_mapbox"):
                fig_map = px.scatter_mapbox(**common_kwargs, mapbox_style="open-street-map")
                fig_map.update_layout(
                    margin={"r": 0, "t": 20, "l": 0, "b": 0},
                    height=450,
                    legend_title_text="均溫分級 (AvgT)",
                )
            else:
                raise NotImplementedError("Plotly scatter map is unavailable")
            st.plotly_chart(fig_map, use_container_width=True)
        except Exception:
            # Graceful fallback to Streamlit native map
            st.map(df_map[["lat", "lon"]], zoom=6)
    else:
        # Fallback to native map if Plotly is not installed
        st.map(df_map[["lat", "lon"]], zoom=6)

    st.caption("📍 **說明**：各分區標記顏色嚴格由當日平均氣溫 `AvgT = (MinT + MaxT) / 2` 之四級色階驅動；較大標記點為當前下拉選單所選之分區。座標點為代表性座標中心點（北部: 臺北、中部: 臺中、南部: 高雄、東北部: 宜蘭、東部: 花蓮、東南部: 臺東），非官方行政邊界邊線。")

# 6. Plot the temperature data (HW10-4)
st.subheader(f"📈 {selected_region} 一週氣溫趨勢圖")

if HAS_PLOTLY and not df_weather.empty:
    fig = px.line(
        df_weather,
        x="dataDate",
        y=["MinT", "MaxT"],
        title=f"Temperature Trends for {selected_region}",
        labels={"value": "Temperature (°C)", "dataDate": "Date", "variable": "指標"},
        markers=True,
        color_discrete_map={"MinT": "#1f77b4", "MaxT": "#ff7f0e"},
    )
    fig.update_layout(
        xaxis_title="預報日期 (Date)",
        yaxis_title="氣溫 (°C)",
        legend_title_text="氣溫指標",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    # Fallback to Streamlit native line chart if Plotly is unavailable
    if not df_weather.empty:
        df_chart = df_weather.set_index("dataDate")[["MinT", "MaxT"]]
        st.line_chart(df_chart)

# 7. Display the data table (HW10-4)
st.subheader(f"📋 {selected_region} 氣溫預報詳細資料")
st.write(f"Temperature Data for {selected_region}")
st.dataframe(
    df_weather.rename(
        columns={
            "dataDate": "預報日期 (Date)",
            "MinT": "最低氣溫 MinT (°C)",
            "MaxT": "最高氣溫 MaxT (°C)",
        }
    ),
    use_container_width=True,
)

# AIoT 第二週作業：台灣一週氣溫預報視覺化 Web App

本專案為 **AIoT-DA 課程第二週作業（HW10 / HW4）** 之完整實作，使用中央氣象署（CWA）官方開放資料 API **`F-C0032-003`（臺灣各分區一週天氣預報）**，並對應評分標準與各項要求。

專案具備即時 API 連線串接、離線測試資料、自動化單元測試、安全金鑰管理機制（金鑰讀自 `api_key.txt` 或環境變數，無硬編碼）、SQLite 資料庫管線（`data.db` / `TemperatureForecasts`）以及互動式 Streamlit Web 應用程式。專案完全獨立自足（self-contained），支援標準 Python / pip 以及 uv 工具，適合部署或複製到任何 Windows 電腦執行。

---

## 評分標準與程式碼對照表 (Rubric Mapping)

| 評分項目 | 滿分佔比 | 目的與要求 | 對應程式碼位置 / 實作功能 |
| :--- | :---: | :--- | :--- |
| **HW10-1 獲取天氣預報資料** | **20%** | 調用 CWA API（`F-C0032-003`）獲取台灣六大區域一週預報（JSON 格式），並能以 `json.dumps` 觀察資料。 | - [`weather_service.py`](weather_service.py) -> `fetch_cwa_forecast()`<br>- [`main.py`](main.py) -> `--inspect` 參數調用 `json.dumps(..., indent=4)`<br>- 支援從 `api_key.txt`、環境變數或命令列傳入 API Key，安全無硬編碼。 |
| **HW10-2 分析資料，提取氣溫** | **20%** | 分析 JSON 階層，精確定位並提取北部、中部、南部、東北部、東部、東南部六大地區每日最高溫（`MaxT`）與最低溫（`MinT`）。 | - [`weather_service.py`](weather_service.py) -> `parse_temperature_forecasts()`<br>- 遍歷 `Dataset -> Locations -> Location`<br>- 輸出 42 筆標準化字典資料（6 區 × 7 天），欄位包含 `regionName`, `dataDate`, `mint`, `maxt`。 |
| **HW10-3 儲存至 SQLite3 資料庫** | **20%** | 建立 `data.db` 與 `TemperatureForecasts` 資料表（欄位包含 `id`, `regionName`, `dataDate`, `mint`, `maxt`），並執行檢查查詢：<br>1. 列出所有地區名稱（`SELECT DISTINCT regionName`）<br>2. 列出中部地區氣溫（`WHERE regionName = '中部地區'`） | - [`weather_service.py`](weather_service.py) -> `init_db()`, `save_to_db()`, `get_distinct_regions()`, `get_central_region_forecast()`<br>- [`main.py`](main.py) -> `run_verification()` 自動執行並格式化印出兩大查詢結果。 |
| **HW10-4 實作氣溫預報 Web App 與互動地圖** | **40%** | 1. 使用 Streamlit 建立 Web App<br>2. 提供下拉選單選擇地區<br>3. 從 SQLite3 `data.db` 讀取資料<br>4. 使用折線圖與資料表格呈現一週氣溫趨勢<br>5. **互動式台灣分區氣溫地圖**（Plotly Map + 代表性分區座標 + 預報日期切換） | - [`app.py`](app.py)<br>- `st.selectbox` 動態綁定資料庫 Distinct 地區與預報日期<br>- 參數化 SQL 查詢該區氣溫（`mint AS MinT, maxt AS MaxT` 相容大小寫）<br>- Plotly 互動式折線圖（雙線 `MinT` / `MaxT`、Hover 提示、圖例）<br>- **互動式台灣六大分區氣溫地圖**（支援 hover 資訊卡、紅點突出選定分區、日期即時連動，遇異常自動降級 `st.map`）<br>- `st.dataframe` 格式化表格展示 |

---

## 專案目錄結構

```text
homework-cwa-forecast/
├── requirements.txt          # 標準 pip 相依套件清單（跨平台可移植）
├── pyproject.toml            # PEP 621 標準元資料與測試設定
├── .env.example              # 安全環境變數設定範本（無憑證）
├── .gitignore                # 排除 .env、api_key.txt、data.db、__pycache__ 等
├── README.md                 # 專案中文說明文件與評分對照
├── weather_service.py        # CWA F-C0032-003 API 串接、JSON 解析、SQLite 讀寫核心
├── main.py                   # 後端管線 CLI（即時 API 抓取、離線測試資料匯入、資料庫驗證）
├── app.py                    # Streamlit 視覺化前端 Web 應用程式
├── fixtures/
│   └── cwa_sample.json       # F-C0032-003 離線範例資料（供離線測試與演示使用）
└── tests/
    └── test_weather_pipeline.py # 自動化單元測試（包含解析、資料庫、查詢、CLI 與 Streamlit 冒煙測試）
```

---

## 執行環境建置與套件安裝（標準 Python / pip 方式）

在任何安裝有 Python 3.9+ 的 Windows 電腦上，打開 PowerShell 或命令提示字元進入本專案資料夾：

```powershell
# 1. 建立虛擬環境
python -m venv .venv

# 2. 啟動虛擬環境 (PowerShell)
.\.venv\Scripts\Activate.ps1
# 若在 CMD 執行： .\.venv\Scripts\activate.bat

# 3. 安裝相依套件
pip install -r requirements.txt
```

*(若電腦環境有安裝 `uv`，亦可使用 `uv pip install -r requirements.txt` 或直接執行 `uv run ...`)*

---

## 設定 API 金鑰

1. 打開專案根目錄的 `api_key.txt`。
2. 填入向中央氣象署申請的 API 授權碼（例如：`CWA-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX`）。
3. 存檔關閉。
   > **安全提醒**：`api_key.txt` 已被 `.gitignore` 忽略保護，不會隨 Git 提交。請勿將金鑰複製到程式碼或其他公開檔案。

---

## 執行後端管線與生成資料庫（HW10-1 ~ HW10-3）

### 1. 執行即時連線管線（讀取 `api_key.txt` 呼叫 CWA API）
```powershell
python main.py --inspect
```
- 程式會自動讀取 `api_key.txt`，向 CWA 官方 `F-C0032-003` 端點發送請求。
- 提取 6 個地區 7 天氣溫預報（42 筆），寫入 `data.db`（`TemperatureForecasts` 表）。
- 自動印出 JSON 觀察樣本，並執行兩大驗證查詢（列出所有地區、列出中部地區氣溫）。

### 2. 離線演示模式（無需聯網）
```powershell
python main.py --from-fixture fixtures/cwa_sample.json --inspect
```

### 3. 單獨執行資料庫檢查驗證查詢
```powershell
python main.py --verify-only
```

---

## 啟動 Streamlit 氣溫預報 Web App（HW10-4）

在已啟動虛擬環境的終端中執行：

```powershell
streamlit run app.py
```

- 啟動後在瀏覽器開啟 `http://localhost:8501`。
- **功能特色**：
  - **地區下拉選單**：即時從 SQLite `SELECT DISTINCT regionName` 載入 6 大地區（北部地區、中部地區、南部地區、東北部地區、東部地區、東南部地區）。
  - **預報日期下拉選單**：即時從 SQLite `SELECT DISTINCT dataDate` 載入預報日期，驅動互動地圖即時呈現當日全台分區氣溫。
  - **即時指標數據卡**：動態計算所選地區的一週最高溫、一週最低溫、平均最高溫、平均最低溫。
  - **互動式台灣分區氣溫地圖（依每日均溫四級色階）**：
    - 使用 Plotly OpenStreetMap 呈現台灣六大分區氣溫預報。
    - **均溫計算與四級色階**：標記顏色由所選日期當日平均氣溫 `AvgT = (MinT + MaxT) / 2` 驅動，嚴格依教授要求四級分類：
      - 🔵 `< 20°C`：低溫（藍色 `#1f77b4`）
      - 🟢 `20°C <= AvgT < 25°C`：舒適（綠色 `#2ecc71`）
      - 🟡 `25°C <= AvgT <= 30°C`：溫暖（黃色 `#f1c40f`）
      - 🔴 `> 30°C`：炎熱（紅色 `#e74c3c`）
      *(邊界歧義處理標準：`< 20` 藍、`20 <= AvgT < 25` 綠、`25 <= AvgT <= 30` 黃、`> 30` 紅)*
    - **常駐視覺化圖例**：於地圖上方提供四色色塊圖例卡與計算公式說明。
    - **選區強調不覆蓋顏色**：下拉選單所選分區以**放大標記（Size 28 vs 15）**進行視覺強調，絕不覆蓋溫級顏色。
    - **豐富浮動資訊卡（Hover）**：滑鼠懸浮完整顯示分區名稱、預報日期、平均氣溫（AvgT）、最低氣溫（MinT）、最高氣溫（MaxT）、代表城市、溫級分類及選取狀態。
    - **代表性座標中心點**：北部: 臺北 `25.0330, 121.5654`；中部: 臺中 `24.1477, 120.6736`；南部: 高雄 `22.6273, 120.3014`；東北部: 宜蘭 `24.7570, 121.7530`；東部: 花蓮 `23.9872, 121.6015`；東南部: 臺東 `22.7583, 121.1444`（清楚註明為分區代表點，非官方行政邊界邊線）。
    - **優雅降級保護**：若環境異常自動平滑降級為 Streamlit 原生 `st.map`。
  - **互動式趨勢折線圖**：Plotly 雙色折線圖（最高溫/最低溫），支援 Hover 懸浮提示、圖例點擊切換。
  - **詳細預報表格**：完整列出日期、最低氣溫、最高氣溫。
  - **雲端與離線自動引導 (Auto Bootstrap)**：初次載入或雲端部署環境下若無 `data.db`，系統全自動初始化載入氣象資料，無需使用者手動點擊按鈕，即開即用。

---

## Streamlit Community Cloud 雲端部署指南

本專案已最佳化以支援 **Streamlit Community Cloud** 快速一鍵部署，並具備初次造訪自動初始化機制（因 `data.db` 依安全規範不納入版本控制）：

### 1. 部署基本設定 (App Settings)
- **Repository**：`https://github.com/prometheans152/0916-2.git`（或您的 fork 儲存庫）
- **Branch**：`main`
- **Main file path**：`app.py`
- **Python version**：`3.11`（或 `3.10+`）
- **相依套件管理**：Streamlit Cloud 會自動偵測並以標準 pip 安裝 `requirements.txt`（包含 `streamlit`, `pandas`, `plotly`, `requests` 等，**無須 uv**）。

### 2. 設定 API 金鑰 (Secrets Management)
在 Streamlit Community Cloud 的 App 儀表板中，點選 **Settings -> Secrets**，填入您的中央氣象署 API 金鑰：

```toml
# Streamlit Community Cloud Secrets (根層級變數會自動注入為環境變數)
CWA_API_KEY = "CWA-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"
```

> **安全與自動適配機制說明**：
> 1. **即時連線優先**：若設定了 `CWA_API_KEY`，雲端應用在初次載入時會自動呼叫中央氣象署官方 `F-C0032-003` 即時開放資料 API，解析後寫入暫存 SQLite 資料庫，並在頁面上標示 `🟢 資料來源：LIVE CWA (F-C0032-003)`。
> 2. **零設定離線展示保護**：若未填寫金鑰或中央氣象署網路異常，雲端應用會**自動平滑降級**載入 `fixtures/cwa_sample.json` 範例資料，並標示 `📦 資料來源：Offline Sample (fixtures/cwa_sample.json)`。**全站圖表與互動地圖依舊能完整渲染運作，不會當機，亦無須訪客手動點擊初始化按鈕**。
> 3. **金鑰保密防護**：金鑰永遠不會被暴露、記錄或輸出至前端畫面。

---

## 自動化單元測試

執行全部 13 項自動化測試（包含解析、資料庫生命週期、欄位大小寫、CLI 流程、前端語法、代表性座標檢驗、均溫與四色階邏輯驗證、Streamlit AppTest 冒煙測試、雲端自動初始化與金鑰解析測試）：

```powershell
# 使用虛擬環境執行 pytest
.\.venv\Scripts\pytest -v
```
*(使用 uv 時為 `uv run pytest -v`)*


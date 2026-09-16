/**
 * GitHub Pages Static Dashboard Application
 * Replicates all professor-required features:
 * - 6-region Taiwan map with OpenStreetMap & Leaflet
 * - AvgT = (MinT + MaxT) / 2
 * - 4 temperature bins: <20°C (Blue), 20-25°C (Green), 25-30°C (Yellow), >30°C (Red)
 * - Selected region emphasized visually WITHOUT overriding temperature color
 * - Hover / Tooltip with Region, Date, AvgT, MinT, MaxT, City, Category, Selection state
 * - 7-day MinT/MaxT line chart (Chart.js)
 * - Detailed 7-day forecast table
 * - Summary metrics (highest, lowest, avg max, avg min)
 */

let forecastData = null;
let leafletMap = null;
let mapMarkers = [];
let chartInstance = null;

let currentRegion = "北部地區";
let currentDate = "";

async function init() {
  try {
    const response = await fetch("data/forecast.json");
    if (!response.ok) {
      throw new Error(`Failed to load forecast data (HTTP ${response.status})`);
    }
    forecastData = await response.json();
    setupUI();
  } catch (err) {
    console.error(err);
    document.getElementById("statusBadge").textContent = `⚠️ 資料載入失敗: ${err.message}`;
    document.getElementById("statusBadge").className = "status-badge";
  }
}

function setupUI() {
  const meta = forecastData.metadata;
  const statusEl = document.getElementById("statusBadge");

  const isLive = meta.source && meta.source.toLowerCase().includes("live");
  statusEl.textContent = `${isLive ? "🟢" : "📦"} 資料來源: ${meta.source} (更新: ${meta.generated_at.slice(0, 10)})`;
  statusEl.className = isLive ? "status-badge live" : "status-badge";

  // Setup Date and Region options
  const regionSelect = document.getElementById("regionSelect");
  regionSelect.innerHTML = "";
  forecastData.regions.forEach(r => {
    const opt = document.createElement("option");
    opt.value = r;
    opt.textContent = r;
    regionSelect.appendChild(opt);
  });

  const dateSelect = document.getElementById("dateSelect");
  dateSelect.innerHTML = "";
  forecastData.dates.forEach(d => {
    const opt = document.createElement("option");
    opt.value = d;
    opt.textContent = d;
    dateSelect.appendChild(opt);
  });

  currentRegion = forecastData.regions[0] || "北部地區";
  currentDate = forecastData.dates[0] || "";

  regionSelect.value = currentRegion;
  dateSelect.value = currentDate;

  regionSelect.addEventListener("change", (e) => {
    currentRegion = e.target.value;
    updateAll();
  });

  dateSelect.addEventListener("change", (e) => {
    currentDate = e.target.value;
    updateAll();
  });

  initMap();
  updateAll();
}

function initMap() {
  const mapContainer = document.getElementById("mapContainer");
  if (!mapContainer) return;

  leafletMap = L.map("mapContainer", {
    center: [23.7, 120.95],
    zoom: 7,
    scrollWheelZoom: false,
  });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(leafletMap);
}

function updateAll() {
  updateMetrics();
  updateMap();
  updateChart();
  updateTable();
  document.getElementById("mapSectionTitle").textContent = `🗺️ 台灣六大分區氣溫預報地圖 (${currentDate})`;
  document.getElementById("chartSectionTitle").textContent = `📈 ${currentRegion} 一週氣溫趨勢圖`;
  document.getElementById("tableSectionTitle").textContent = `📋 ${currentRegion} 氣溫預報詳細資料`;
}

function updateMetrics() {
  const regionRecords = forecastData.records.filter(r => r.regionName === currentRegion);
  if (!regionRecords.length) return;

  const maxts = regionRecords.map(r => r.maxt);
  const mints = regionRecords.map(r => r.mint);

  const highestT = Math.max(...maxts);
  const lowestT = Math.min(...mints);
  const avgMax = (maxts.reduce((a, b) => a + b, 0) / maxts.length).toFixed(1);
  const avgMin = (mints.reduce((a, b) => a + b, 0) / mints.length).toFixed(1);

  document.getElementById("metricHighest").textContent = `${highestT} °C`;
  document.getElementById("metricLowest").textContent = `${lowestT} °C`;
  document.getElementById("metricAvgMax").textContent = `${avgMax} °C`;
  document.getElementById("metricAvgMin").textContent = `${avgMin} °C`;
}

function updateMap() {
  if (!leafletMap) return;

  // Clear existing markers
  mapMarkers.forEach(m => leafletMap.removeLayer(m));
  mapMarkers = [];

  const dateRecords = forecastData.records.filter(r => r.dataDate === currentDate);

  dateRecords.forEach(r => {
    const isSelected = (r.regionName === currentRegion);

    // Visual emphasis without overriding temperature color:
    // Selected marker is noticeably larger and has a distinct prominent outer ring
    const markerRadius = isSelected ? 18 : 10;
    const strokeWidth = isSelected ? 4 : 2;
    const strokeColor = isSelected ? "#0f172a" : "#ffffff";

    const marker = L.circleMarker([r.lat, r.lon], {
      radius: markerRadius,
      fillColor: r.temp_color,
      color: strokeColor,
      weight: strokeWidth,
      opacity: 1,
      fillOpacity: 0.9,
    }).addTo(leafletMap);

    // Rich hover tooltip showing all required fields
    const tooltipContent = `
      <div style="font-family: inherit; font-size: 13px; line-height: 1.45; padding: 2px;">
        <div style="font-weight: 700; font-size: 14px; margin-bottom: 4px;">
          ${r.regionName} <span style="font-weight: normal; color: #64748b;">(${r.city})</span>
        </div>
        <div>預報日期 Date: <strong>${r.dataDate}</strong></div>
        <div>平均氣溫 AvgT: <strong>${r.avg_t.toFixed(1)} °C</strong></div>
        <div>最低氣溫 MinT: <strong>${r.mint} °C</strong></div>
        <div>最高氣溫 MaxT: <strong>${r.maxt} °C</strong></div>
        <div>均溫分級 Category: <span style="color: ${r.temp_color}; font-weight: 700;">${r.temp_bin}</span></div>
        <div style="margin-top: 4px; font-weight: 600; color: ${isSelected ? '#1e40af' : '#64748b'};">
          ${isSelected ? '★ 目前選取' : '點擊切換至此分區'}
        </div>
      </div>
    `;

    marker.bindTooltip(tooltipContent, {
      direction: "top",
      offset: [0, -10],
      opacity: 0.98,
    });

    // Clicking marker selects that region
    marker.on("click", () => {
      currentRegion = r.regionName;
      document.getElementById("regionSelect").value = currentRegion;
      updateAll();
    });

    mapMarkers.push(marker);
  });
}

function updateChart() {
  const regionRecords = forecastData.records.filter(r => r.regionName === currentRegion);
  if (!regionRecords.length) return;

  const labels = regionRecords.map(r => r.dataDate);
  const mintData = regionRecords.map(r => r.mint);
  const maxtData = regionRecords.map(r => r.maxt);

  const ctx = document.getElementById("trendChart").getContext("2d");

  if (chartInstance) {
    chartInstance.destroy();
  }

  chartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "最高氣溫 MaxT",
          data: maxtData,
          borderColor: "#ff7f0e",
          backgroundColor: "#ff7f0e",
          tension: 0.2,
          pointRadius: 6,
          pointHoverRadius: 8,
          borderWidth: 2.5,
        },
        {
          label: "最低氣溫 MinT",
          data: mintData,
          borderColor: "#1f77b4",
          backgroundColor: "#1f77b4",
          tension: 0.2,
          pointRadius: 6,
          pointHoverRadius: 8,
          borderWidth: 2.5,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: {
          position: "top",
          labels: {
            font: { size: 13, weight: "bold" },
            usePointStyle: true,
          },
        },
        tooltip: {
          callbacks: {
            afterBody: function(context) {
              const idx = context[0].dataIndex;
              const rec = regionRecords[idx];
              return `當日均溫 AvgT: ${rec.avg_t} °C (${rec.temp_bin})`;
            }
          }
        }
      },
      scales: {
        x: {
          title: {
            display: true,
            text: "預報日期 (Date)",
            font: { size: 12, weight: "bold" },
          },
          grid: { display: false },
        },
        y: {
          title: {
            display: true,
            text: "氣溫 (°C)",
            font: { size: 12, weight: "bold" },
          },
          suggestedMin: 15,
          suggestedMax: 35,
        },
      },
    },
  });
}

function updateTable() {
  const regionRecords = forecastData.records.filter(r => r.regionName === currentRegion);
  const tbody = document.getElementById("forecastTableBody");
  tbody.innerHTML = "";

  regionRecords.forEach(r => {
    const tr = document.createElement("tr");

    let pillStyle = `background-color: ${r.temp_color};`;
    if (r.temp_bin === "25–30°C") {
      pillStyle += " color: #111827;";
    }

    tr.innerHTML = `
      <td style="font-weight: 600;">${r.dataDate}</td>
      <td style="color: #1f77b4; font-weight: 600;">${r.mint} °C</td>
      <td style="color: #ea580c; font-weight: 600;">${r.maxt} °C</td>
      <td style="font-weight: 700;">${r.avg_t.toFixed(1)} °C</td>
      <td><span class="pill" style="${pillStyle}">${r.temp_bin}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

// Start application
window.addEventListener("DOMContentLoaded", init);

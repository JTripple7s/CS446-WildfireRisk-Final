let map;
let activeFireMarkers = [];
let predictionMarkers = [];
let allPredictions = [];

const API_BASE = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
  ? "http://localhost:8000"
  : "https://wildfire-api-653947415430.us-west1.run.app";
const CALFIRE_API = "https://www.fire.ca.gov/umbraco/api/IncidentApi/List?inactive=false";

const loadBtn = document.getElementById("loadBtn");
const statusDiv = document.getElementById("status");
const tableBody = document.querySelector("#predictionsTable tbody");
const toggleActiveFires = document.getElementById("toggleActiveFires");
const togglePredictions = document.getElementById("togglePredictions");
const filterHigh = document.getElementById("filterHigh");
const filterMedium = document.getElementById("filterMedium");
const filterLow = document.getElementById("filterLow");

function initMap() {
  try {
    // Initialize Leaflet map targeting the 'map' div
    map = L.map('map').setView([37.5, -120.5], 6);

    // Add dark themed map tiles to match our premium aesthetic
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: 'abcd',
      maxZoom: 20
    }).addTo(map);

    console.log("Leaflet dark map initialized.");

    // Load active fires immediately
    fetchActiveFires();
  } catch (error) {
    console.error("Map failed to load:", error);
  }
}

async function fetchActiveFires() {
  statusDiv.textContent = "Fetching active fires...";
  try {
    const url = `${API_BASE}/calfire`;
    const response = await fetch(url);
    if (!response.ok) throw new Error("Internal Proxy unavailable");

    const fires = await response.json();

    clearMarkers(activeFireMarkers);
    const bounds = L.latLngBounds();

    fires.forEach(fire => {
      if (fire.Latitude && fire.Longitude) {
        // High-end glowing fire emoji icon
        const fireIcon = L.divIcon({
          html: `<div style="font-size: 20px; filter: drop-shadow(0 0 6px rgba(239, 68, 68, 0.6)); text-align: center;">🔥</div>`,
          className: 'custom-fire-icon',
          iconSize: [24, 24],
          iconAnchor: [12, 12]
        });

        const lat = parseFloat(fire.Latitude);
        const lng = parseFloat(fire.Longitude);

        const fireUrl = fire.Url && fire.Url.startsWith("http") ? fire.Url : `https://www.fire.ca.gov${fire.Url || ''}`;

        const marker = L.marker([lat, lng], {
          icon: fireIcon,
          title: fire.Name
        });

        marker.bindPopup(`
          <div style="color: #1e293b; font-family: sans-serif; font-size: 13px; line-height: 1.4;">
            <h3 style="margin: 0 0 6px 0; color: #e11d48; font-size: 14px; font-weight: 700;">${fire.Name}</h3>
            <p style="margin: 2px 0;"><strong>Location:</strong> ${fire.Location}</p>
            <p style="margin: 2px 0;"><strong>Acres:</strong> ${fire.AcresBurned || 'Unknown'}</p>
            <p style="margin: 2px 0;"><strong>Contained:</strong> ${fire.PercentContained || 0}%</p>
            <p style="margin: 2px 0;"><strong>Started:</strong> ${new Date(fire.Started).toLocaleDateString()}</p>
            <a href="${fireUrl}" target="_blank" style="display: inline-block; margin-top: 6px; color: #0284c7; font-weight: 600; text-decoration: none;">View on CAL FIRE →</a>
          </div>
        `);

        if (toggleActiveFires.checked) {
          marker.addTo(map);
        }

        activeFireMarkers.push(marker);
        bounds.extend([lat, lng]);
      }
    });

    if (activeFireMarkers.length > 0) {
      map.fitBounds(bounds);
      statusDiv.textContent = `Loaded ${activeFireMarkers.length} active fires from CAL FIRE.`;
    }
  } catch (error) {
    console.error(error);
    statusDiv.textContent = "Error loading real fire data.";
  }
}

async function fetchPredictions() {
  statusDiv.textContent = "Loading AI predictions...";
  try {
    const response = await fetch(`${API_BASE}/predictions`);
    if (!response.ok) throw new Error(`HTTP error ${response.status}`);

    const data = await response.json();
    allPredictions = data.items;

    renderData();
  } catch (error) {
    statusDiv.textContent = `Error: ${error.message}`;
  }
}

function renderData() {
  clearMarkers(predictionMarkers);
  tableBody.innerHTML = "";

  const selectedRisks = [];
  if (filterHigh.checked) selectedRisks.push("HIGH");
  if (filterMedium.checked) selectedRisks.push("MEDIUM");
  if (filterLow.checked) selectedRisks.push("LOW");

  const filtered = allPredictions.filter(p => selectedRisks.includes(p.risk_level));
  const bounds = L.latLngBounds();

  let boundsExtended = false;

  // Include active fires in bounds if they are visible
  if (toggleActiveFires.checked) {
    activeFireMarkers.forEach(m => {
      bounds.extend(m.getLatLng());
      boundsExtended = true;
    });
  }

  filtered.forEach(item => {
    const lat = parseFloat(item.center_lat);
    const lon = parseFloat(item.center_lon);

    // Table Row
    const row = document.createElement("tr");
    const riskClass = item.risk_level.toLowerCase();
    row.className = `${riskClass}-row`;
    row.innerHTML = `
      <td>${item.prediction_date}</td>
      <td><span class="${riskClass}-label">${item.risk_level}</span></td>
      <td>${lat.toFixed(2)}, ${lon.toFixed(2)}</td>
    `;
    tableBody.appendChild(row);

    // Custom Glowing Dot Marker for predictions
    const color = getRiskColor(item.risk_level);
    const riskIcon = L.divIcon({
      html: `<div style="
        width: 12px; 
        height: 12px; 
        background-color: ${color}; 
        border: 2px solid #fff; 
        border-radius: 50%; 
        box-shadow: 0 0 8px ${color};
      "></div>`,
      className: 'custom-prediction-icon',
      iconSize: [16, 16],
      iconAnchor: [8, 8]
    });

    const marker = L.marker([lat, lon], { icon: riskIcon });

    marker.bindPopup(`
      <div style="color: #1e293b; font-family: sans-serif; font-size: 13px; line-height: 1.4;">
        <h3 style="margin: 0 0 6px 0; color: #0f172a; font-size: 14px; font-weight: 700;">AI Wildfire Risk Prediction</h3>
        <p style="margin: 2px 0;"><strong>Risk Level:</strong> <span style="color: ${color}; font-weight: 700;">${item.risk_level}</span></p>
        <p style="margin: 2px 0;"><strong>Risk Score:</strong> ${(item.risk_score * 100).toFixed(1)}%</p>
        <p style="margin: 2px 0;"><strong>Grid ID:</strong> ${item.grid_id}</p>
        <p style="margin: 2px 0;"><strong>Date:</strong> ${item.prediction_date}</p>
      </div>
    `);

    if (togglePredictions.checked) {
      marker.addTo(map);
    }

    predictionMarkers.push(marker);
    bounds.extend([lat, lon]);
    boundsExtended = true;
  });

  if (boundsExtended) {
    map.fitBounds(bounds, { padding: [30, 30] });
  }

  if (filtered.length > 0) {
    statusDiv.textContent = `Displaying ${filtered.length} predictions.`;
  } else {
    statusDiv.textContent = `No predictions found matching filters (loaded ${allPredictions.length} total).`;
  }
}

function getRiskColor(level) {
  if (level === "HIGH") return "#ef4444";
  if (level === "MEDIUM") return "#f59e0b";
  return "#10b981";
}

function clearMarkers(markerArray) {
  markerArray.forEach(m => map.removeLayer(m));
  markerArray.length = 0;
}

// Event Listeners
loadBtn.addEventListener("click", fetchPredictions);

[toggleActiveFires, togglePredictions, filterHigh, filterMedium, filterLow].forEach(el => {
  el.addEventListener("change", () => {
    // Show/hide active fires
    activeFireMarkers.forEach(m => {
      if (toggleActiveFires.checked) {
        m.addTo(map);
      } else {
        map.removeLayer(m);
      }
    });

    // Show/hide predictions
    predictionMarkers.forEach(m => {
      if (togglePredictions.checked) {
        m.addTo(map);
      } else {
        map.removeLayer(m);
      }
    });

    // Re-render to update filters
    renderData();
  });
});

initMap();
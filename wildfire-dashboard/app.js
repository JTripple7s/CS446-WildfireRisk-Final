let map;
let infoWindow;
let activeFireMarkers = [];
let predictionMarkers = [];
let allPredictions = [];

const API_BASE = "https://wildfire-api-808815635798.us-west1.run.app";
const CALFIRE_API = "https://www.fire.ca.gov/umbraco/api/IncidentApi/List?inactive=false";

const loadBtn = document.getElementById("loadBtn");
const statusDiv = document.getElementById("status");
const tableBody = document.querySelector("#predictionsTable tbody");
const toggleActiveFires = document.getElementById("toggleActiveFires");
const togglePredictions = document.getElementById("togglePredictions");
const filterHigh = document.getElementById("filterHigh");
const filterMedium = document.getElementById("filterMedium");
const filterLow = document.getElementById("filterLow");

async function initMap() {
  try {
    const { Map } = await google.maps.importLibrary("maps");
    const { AdvancedMarkerElement, PinElement } = await google.maps.importLibrary("marker");
    infoWindow = new google.maps.InfoWindow();

    map = new Map(document.getElementById("map"), {
      center: { lat: 37.5, lng: -120.5 },
      zoom: 6,
      mapId: "DEMO_MAP_ID", 
    });

    window.AdvancedMarkerElement = AdvancedMarkerElement;
    window.PinElement = PinElement;

    console.log("Map initialized.");
    
    // Load active fires immediately
    fetchActiveFires();
  } catch (error) {
    console.error("Map failed to load:", error);
  }
}

async function fetchActiveFires() {
  statusDiv.textContent = "Fetching active fires...";
  try {
    // Fetch from our own API proxy instead of third-party CORS proxies
    const url = `${API_BASE}/calfire`;
    
    const response = await fetch(url);
    if (!response.ok) throw new Error("Internal Proxy unavailable");
    
    const fires = await response.json();
    
    clearMarkers(activeFireMarkers);
    const bounds = new google.maps.LatLngBounds();

    fires.forEach(fire => {
      if (fire.Latitude && fire.Longitude) {
        const firePin = new window.PinElement({
          glyphText: "🔥",
          background: "#FF4500",
          borderColor: "#8B0000",
        });

        const marker = new window.AdvancedMarkerElement({
          position: { lat: parseFloat(fire.Latitude), lng: parseFloat(fire.Longitude) },
          map: toggleActiveFires.checked ? map : null,
          title: fire.Name,
          content: firePin.element,
        });

        marker.addListener("click", () => {
          const content = `
            <div style="color: #333;">
              <h3 style="margin: 0 0 5px;">${fire.Name}</h3>
              <p><strong>Location:</strong> ${fire.Location}</p>
              <p><strong>Acres:</strong> ${fire.AcresBurned || 'Unknown'}</p>
              <p><strong>Contained:</strong> ${fire.PercentContained || 0}%</p>
              <p><strong>Started:</strong> ${new Date(fire.Started).toLocaleDateString()}</p>
              <a href="https://www.fire.ca.gov${fire.Url}" target="_blank">View on CAL FIRE</a>
            </div>
          `;
          infoWindow.setContent(content);
          infoWindow.open(map, marker);
        });

        activeFireMarkers.push(marker);
        bounds.extend(marker.position);
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
  const bounds = new google.maps.LatLngBounds();
  
  // Include active fires in bounds if they are visible
  if (toggleActiveFires.checked) {
    activeFireMarkers.forEach(m => bounds.extend(m.position));
  }

  filtered.forEach(item => {
    // Table Row
    const row = document.createElement("tr");
    const riskClass = item.risk_level.toLowerCase();
    row.className = `${riskClass}-row`;
    row.innerHTML = `
      <td>${item.prediction_date}</td>
      <td class="${riskClass}-label">${item.risk_level}</td>
      <td>${parseFloat(item.center_lat).toFixed(2)}, ${parseFloat(item.center_lon).toFixed(2)}</td>
    `;
    tableBody.appendChild(row);

    // Marker
    const pin = new window.PinElement({
      background: getRiskColor(item.risk_level),
      borderColor: "#333",
      glyphColor: "white",
    });

    const marker = new window.AdvancedMarkerElement({
      position: { lat: parseFloat(item.center_lat), lng: parseFloat(item.center_lon) },
      map: togglePredictions.checked ? map : null,
      title: `Risk: ${item.risk_level}`,
      content: pin.element,
    });

    marker.addListener("click", () => {
      const content = `
        <div style="color: #333;">
          <h3 style="margin: 0 0 5px;">AI Prediction</h3>
          <p><strong>Risk Level:</strong> <span class="${riskClass}-label">${item.risk_level}</span></p>
          <p><strong>Risk Score:</strong> ${item.risk_score}</p>
          <p><strong>Grid ID:</strong> ${item.grid_id}</p>
          <p><strong>Date:</strong> ${item.prediction_date}</p>
        </div>
      `;
      infoWindow.setContent(content);
      infoWindow.open(map, marker);
    });

    predictionMarkers.push(marker);
    bounds.extend(marker.position);
  });

  if (filtered.length > 0 || (toggleActiveFires.checked && activeFireMarkers.length > 0)) {
    map.fitBounds(bounds);
    if (filtered.length > 0) statusDiv.textContent = `Displaying ${filtered.length} predictions.`;
  }
}

function getRiskColor(level) {
  if (level === "HIGH") return "#b00020";
  if (level === "MEDIUM") return "#d97706";
  return "#15803d";
}

function clearMarkers(markerArray) {
  markerArray.forEach(m => m.setMap(null));
  markerArray.length = 0;
}

// Event Listeners
loadBtn.addEventListener("click", fetchPredictions);

[toggleActiveFires, togglePredictions, filterHigh, filterMedium, filterLow].forEach(el => {
  el.addEventListener("change", () => {
    activeFireMarkers.forEach(m => m.setMap(toggleActiveFires.checked ? map : null));
    predictionMarkers.forEach(m => m.setMap(togglePredictions.checked ? map : null));
    
    // Re-render everything to apply risk filters correctly
    renderData();
  });
});

initMap();
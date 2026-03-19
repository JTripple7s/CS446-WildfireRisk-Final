const API_BASE =
  "https://wildfire-api-808815635798.us-west1.run.app";

const loadBtn = document.getElementById("loadBtn");
const statusDiv = document.getElementById("status");
const tableBody = document.querySelector("#predictionsTable tbody");

function riskClass(level) {
  if (level === "HIGH") return "high";
  if (level === "MEDIUM") return "medium";
  return "low";
}

async function loadPredictions() {
  statusDiv.textContent = "Loading predictions...";
  tableBody.innerHTML = "";

  try {
    const response = await fetch(`${API_BASE}/predictions`);
    if (!response.ok) {
      throw new Error(`HTTP error ${response.status}`);
    }

    const data = await response.json();

    statusDiv.textContent = `Loaded ${data.count} predictions.`;

    data.items.forEach((item) => {
      const row = document.createElement("tr");

      row.innerHTML = `
        <td>${item.prediction_date}</td>
        <td>${item.grid_id}</td>
        <td>${item.risk_score}</td>
        <td class="${riskClass(item.risk_level)}">${item.risk_level}</td>
        <td>${item.center_lat}</td>
        <td>${item.center_lon}</td>
        <td>${item.model_version ?? ""}</td>
      `;

      tableBody.appendChild(row);
    });
  } catch (error) {
    console.error(error);
    statusDiv.textContent = `Failed to load predictions: ${error.message}`;
  }
}

loadBtn.addEventListener("click", loadPredictions);
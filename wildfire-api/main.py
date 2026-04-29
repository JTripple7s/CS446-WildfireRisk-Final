from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import bigquery
import os
import requests

app = FastAPI(title="Wildfire Risk API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ID = os.getenv("PROJECT_ID", "wildfirecs446")
DATASET = os.getenv("BQ_DATASET", "wildfire_mvp")
TABLE = os.getenv("BQ_TABLE", "predictions")

client = bigquery.Client()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/calfire")
def get_calfire_data():
    url = "https://www.fire.ca.gov/umbraco/api/IncidentApi/List?inactive=false"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch CAL FIRE data: {str(e)}")


@app.get("/predictions")
def get_predictions(date: str | None = None):
    table_ref = f"{PROJECT_ID}.{DATASET}.{TABLE}"

    if date:
        query = f"""
            SELECT
              prediction_date,
              grid_id,
              risk_score,
              risk_level,
              center_lat,
              center_lon,
              model_version
            FROM `{table_ref}`
            WHERE prediction_date = @prediction_date
            ORDER BY risk_score DESC
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(
                    "prediction_date", "DATE", date
                )
            ]
        )
    else:
        query = f"""
            SELECT
              prediction_date,
              grid_id,
              risk_score,
              risk_level,
              center_lat,
              center_lon,
              model_version
            FROM `{table_ref}`
            ORDER BY prediction_date DESC, risk_score DESC
            LIMIT 100
        """
        job_config = None

    results = client.query(query, job_config=job_config).result()
    items = [dict(row.items()) for row in results]

    return {"count": len(items), "items": items}


@app.get("/risk")
def get_risk(grid_id: str):
    table_ref = f"{PROJECT_ID}.{DATASET}.{TABLE}"

    query = f"""
        SELECT
          prediction_date,
          grid_id,
          risk_score,
          risk_level,
          center_lat,
          center_lon,
          model_version
        FROM `{table_ref}`
        WHERE grid_id = @grid_id
        ORDER BY prediction_date DESC
        LIMIT 1
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("grid_id", "STRING", grid_id)
        ]
    )

    results = list(client.query(query, job_config=job_config).result())

    if not results:
        raise HTTPException(status_code=404, detail="Grid cell not found")

    return dict(results[0].items())
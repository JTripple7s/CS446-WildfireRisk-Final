# predict_and_write.py (fixed)
import os
import json
import logging
from joblib import load
import pandas as pd
from google.cloud import bigquery
from google.cloud import aiplatform

# Config
PROJECT = os.environ.get("PROJECT", "wildfirecs446")
LOCATION = os.environ.get("LOCATION", "us-central1")
ENDPOINT_ID = os.environ.get("ENDPOINT_ID", "100963754732158976")
BQ_DATASET = os.environ.get("BQ_DATASET", "wildfire_mvp")
BQ_TABLE = os.environ.get("BQ_TABLE", "predictions_ml")

logging.basicConfig(level=logging.INFO)

def predict_json(instances):
    aiplatform.init(project=PROJECT, location=LOCATION)
    endpoint = aiplatform.Endpoint(endpoint_name=ENDPOINT_ID)
    # endpoint.predict returns a PredictionResponse-like object
    response = endpoint.predict(instances=instances)
    return response.predictions

def get_risk_level(score):
    if score > 0.7: return "HIGH"
    if score > 0.3: return "MEDIUM"
    return "LOW"

def main():
    try:
        bq = bigquery.Client(project=PROJECT)

        # 1. Read minimal columns from grid table
        df = bq.query(f"""
            SELECT grid_id, center_lat, center_lon
            FROM `{PROJECT}.{BQ_DATASET}.grid_cells`
        """).to_dataframe()

        if df.empty:
            logging.info("No grid cells found; exiting.")
            return

        # 2. Add features (placeholder or simulated)
        df["temp_c"] = 28.5
        df["humidity"] = 35.0
        df["wind_speed_kmh"] = 15.0
        df["wind_dir_deg"] = 210.0
        df["vegetation_index"] = 0.6
        df["slope_deg"] = 8.0
        df["elevation_m"] = 450.0

        # 3. Build instances
        feature_columns = ["center_lat", "center_lon", "temp_c", "humidity", "wind_speed_kmh", "wind_dir_deg", "vegetation_index", "slope_deg", "elevation_m"]
        instances = df[feature_columns].values.tolist()

        # 4. Call Vertex AI
        logging.info("Calling Vertex AI endpoint %s...", ENDPOINT_ID)
        preds = predict_json(instances)

        # 5. Process predictions
        flat_preds = [float(p[0]) if isinstance(p, (list, tuple)) else float(p) for p in preds]
        df["risk_score"] = flat_preds
        df["risk_level"] = df["risk_score"].apply(get_risk_level)

        # 6. Align with BigQuery schema
        df["prediction_date"] = pd.Timestamp.utcnow().date().isoformat()
        df["model_version"] = "wildfire-vertex-xgb-v1"

        out_df = df[[
            "prediction_date",
            "grid_id",
            "risk_score",
            "risk_level",
            "center_lat",
            "center_lon",
            "model_version"
        ]]

        # 7. Write to BigQuery
        table_id = f"{PROJECT}.{BQ_DATASET}.{BQ_TABLE}"
        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
        job = bq.load_table_from_dataframe(out_df, table_id, job_config=job_config)
        job.result()
        logging.info("Success! Wrote %d rows to %s", len(out_df), table_id)

    except Exception as e:
        logging.exception("Job failed: %s", e)
        raise

if __name__ == "__main__":
    main()

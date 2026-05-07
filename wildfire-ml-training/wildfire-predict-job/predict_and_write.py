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
ENDPOINT_ID = os.environ.get("ENDPOINT_ID", "8097762950837698560")
BQ_DATASET = os.environ.get("BQ_DATASET", "wildfire_mvp")
BQ_TABLE = os.environ.get("BQ_TABLE", "predictions_ml")

logging.basicConfig(level=logging.INFO)

def predict_json(instances):
    aiplatform.init(project=PROJECT, location=LOCATION)
    endpoint = aiplatform.Endpoint(endpoint_name=ENDPOINT_ID)
    # endpoint.predict returns a PredictionResponse-like object
    response = endpoint.predict(instances=instances)
    return response.predictions

def main():
    try:
        bq = bigquery.Client(project=PROJECT)

        # 1. Read minimal columns from grid table
        df = bq.query("""
            SELECT grid_id, center_lat, center_lon
            FROM `wildfirecs446.wildfire_mvp.grid_cells`
        """).to_dataframe()

        if df.empty:
            logging.info("No grid cells found; exiting.")
            return

        # 2. Add placeholder features (or compute real ones)
        df["temp_c"] = 25.0
        df["humidity"] = 40.0
        df["wind_speed_kmh"] = 10.0
        df["wind_dir_deg"] = 180.0
        df["vegetation_index"] = 0.5
        df["slope_deg"] = 5.0
        df["elevation_m"] = 300.0

        # 3. Build instances as list-of-lists (2D)
        feature_columns = [
            "center_lat",
            "center_lon",
            "temp_c",
            "humidity",
            "wind_speed_kmh",
            "wind_dir_deg",
            "vegetation_index",
            "slope_deg",
            "elevation_m"
        ]
        instances = df[feature_columns].values.tolist()

        # 4. Call Vertex AI
        preds = predict_json(instances)

        # 5. Normalize predictions to a flat list of floats
        # handle cases where preds is list of lists or list of scalars
        flat_preds = []
        for p in preds:
            if isinstance(p, (list, tuple)):
                # take first element if nested
                flat_preds.append(float(p[0]))
            else:
                flat_preds.append(float(p))

        if len(flat_preds) != len(df):
            raise RuntimeError(f"Prediction length {len(flat_preds)} != input rows {len(df)}")

        df["risk_score"] = flat_preds

        # 6. Select only columns that match your BigQuery table schema
        out_df = df[[
            "grid_id",
            "center_lat",
            "center_lon",
            "risk_score"
        ]].copy()

        # Add optional metadata columns if your table expects them
        out_df["prediction_date"] = pd.Timestamp.utcnow().date().isoformat()
        out_df["model_version"] = "wildfire-risk-xgb-v2-cpu"

        # 7. Write to BigQuery (append)
        table_id = f"{PROJECT}.{BQ_DATASET}.{BQ_TABLE}"
        job = bq.load_table_from_dataframe(out_df, table_id)
        job.result()  # wait
        logging.info("Wrote %d rows to %s", len(out_df), table_id)

    except Exception as e:
        logging.exception("Job failed: %s", e)
        raise

if __name__ == "__main__":
    main()

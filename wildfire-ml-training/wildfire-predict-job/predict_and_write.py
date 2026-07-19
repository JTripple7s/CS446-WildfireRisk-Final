# predict_and_write.py (fixed with local/sqlite support)
import os
import json
import logging
import pandas as pd
import sqlite3

# Config
PROJECT = os.environ.get("PROJECT", "wildfirecs446")
LOCATION = os.environ.get("LOCATION", "us-west2")
ENDPOINT_ID = os.environ.get("ENDPOINT_ID", "100963754732158976")
BQ_DATASET = os.environ.get("BQ_DATASET", "wildfire_mvp")
BQ_TABLE = os.environ.get("BQ_TABLE", "predictions")

DATABASE_TYPE = os.environ.get("DATABASE_TYPE", "sqlite")
SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", "wildfire.db")
INFERENCE_TYPE = os.environ.get("INFERENCE_TYPE", "local")

logging.basicConfig(level=logging.INFO)


def find_model_path():
    model_path = os.environ.get("MODEL_PATH")
    if model_path and os.path.exists(model_path):
        return model_path
    
    candidates = [
        "model/model.joblib",
        "../model/model.joblib",
        "/app/model/model.joblib",
        "wildfire-ml-training/model/model.joblib"
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "model.joblib"  # default fallback


def predict_local(df_features, feature_columns):
    import joblib
    model_path = find_model_path()
    logging.info("Loading local model from %s...", model_path)
    model = joblib.load(model_path)
    
    # Run prediction directly using the DataFrame (retaining feature names to avoid warnings)
    preds = model.predict(df_features[feature_columns])
    return preds


def predict_vertex(instances):
    from google.cloud import aiplatform
    aiplatform.init(project=PROJECT, location=LOCATION)
    endpoint = aiplatform.Endpoint(endpoint_name=ENDPOINT_ID)
    response = endpoint.predict(instances=instances)
    return response.predictions


def get_risk_level(score):
    if score > 0.7: return "HIGH"
    if score > 0.3: return "MEDIUM"
    return "LOW"


def main():
    try:
        logging.info("Starting prediction job in %s mode (database: %s)", INFERENCE_TYPE, DATABASE_TYPE)
        
        # Read minimal columns from grid table
        if DATABASE_TYPE == "sqlite":
            logging.info("Reading grid cells from SQLite database: %s", SQLITE_DB_PATH)
            conn = sqlite3.connect(SQLITE_DB_PATH)
            df = pd.read_sql_query("SELECT grid_id, center_lat, center_lon FROM grid_cells", conn)
            conn.close()
        else:
            from google.cloud import bigquery
            logging.info("Reading grid cells from BigQuery")
            bq = bigquery.Client(project=PROJECT)
            df = bq.query(f"""
                SELECT grid_id, center_lat, center_lon
                FROM `{PROJECT}.{BQ_DATASET}.grid_cells`
            """).to_dataframe()

        if df.empty:
            logging.info("No grid cells found; exiting.")
            return

        # Add features (simulated)
        df["temp_c"] = 28.5
        df["humidity"] = 35.0
        df["wind_speed_kmh"] = 15.0
        df["wind_dir_deg"] = 210.0
        df["vegetation_index"] = 0.6
        df["slope_deg"] = 8.0
        df["elevation_m"] = 450.0

        # Feature columns list
        feature_columns = ["center_lat", "center_lon", "temp_c", "humidity", "wind_speed_kmh", "wind_dir_deg", "vegetation_index", "slope_deg", "elevation_m"]

        # Predict
        if INFERENCE_TYPE == "local":
            preds = predict_local(df, feature_columns)
        else:
            instances = df[feature_columns].values.tolist()
            logging.info("Calling Vertex AI endpoint %s...", ENDPOINT_ID)
            preds = predict_vertex(instances)

        # Process predictions
        flat_preds = [float(p[0]) if isinstance(p, (list, tuple)) else float(p) for p in preds]
        df["risk_score"] = flat_preds
        df["risk_level"] = df["risk_score"].apply(get_risk_level)

        # Align schemas
        # For BigQuery, keeping datetime object. For SQLite we'll format it as string.
        df["prediction_date"] = pd.to_datetime(pd.Timestamp.utcnow().date())
        df["model_version"] = "wildfire-local-xgb-v1" if INFERENCE_TYPE == "local" else "wildfire-vertex-xgb-v1"

        out_df = df[[
            "prediction_date",
            "grid_id",
            "risk_score",
            "risk_level",
            "center_lat",
            "center_lon",
            "model_version"
        ]]

        # Write predictions to storage
        if DATABASE_TYPE == "sqlite":
            logging.info("Writing predictions to SQLite database: %s", SQLITE_DB_PATH)
            out_df_sqlite = out_df.copy()
            out_df_sqlite["prediction_date"] = out_df_sqlite["prediction_date"].dt.strftime("%Y-%m-%d")
            
            conn = sqlite3.connect(SQLITE_DB_PATH)
            cursor = conn.cursor()
            records = out_df_sqlite.values.tolist()
            cursor.executemany("""
                INSERT OR REPLACE INTO predictions 
                (prediction_date, grid_id, risk_score, risk_level, center_lat, center_lon, model_version)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, records)
            conn.commit()
            conn.close()
            logging.info("Success! Upserted %d rows into predictions table in SQLite", len(out_df_sqlite))
        else:
            from google.cloud import bigquery
            bq = bigquery.Client(project=PROJECT)
            table_id = f"{PROJECT}.{BQ_DATASET}.{BQ_TABLE}"
            job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
            job = bq.load_table_from_dataframe(out_df, table_id, job_config=job_config)
            job.result()
            logging.info("Success! Wrote %d rows to BigQuery table %s", len(out_df), table_id)

    except Exception as e:
        logging.exception("Job failed: %s", e)
        raise


if __name__ == "__main__":
    main()


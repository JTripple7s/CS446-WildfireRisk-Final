from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "sqlite")
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "wildfire.db")

client = None
if DATABASE_TYPE == "bigquery":
    try:
        from google.cloud import bigquery
        client = bigquery.Client()
    except Exception as e:
        print(f"Error initializing BigQuery client: {e}. Falling back to SQLite.")
        DATABASE_TYPE = "sqlite"


def init_sqlite_db():
    import sqlite3
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grid_cells (
            grid_id TEXT PRIMARY KEY,
            center_lat REAL,
            center_lon REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            prediction_date TEXT,
            grid_id TEXT,
            risk_score REAL,
            risk_level TEXT,
            center_lat REAL,
            center_lon REAL,
            model_version TEXT,
            PRIMARY KEY (prediction_date, grid_id)
        )
    """)
    conn.commit()
    
    # Seed grid cells if empty
    cursor.execute("SELECT COUNT(*) FROM grid_cells")
    if cursor.fetchone()[0] == 0:
        # Generate deterministic organic grid cells (scattered points in California fire risk zones)
        import random
        rng = random.Random(42)  # Fixed seed for reproducibility
        grid_data = []
        
        # Focus on high fire-risk areas: Northern forests, Sierra Nevada range, Southern CA hills
        for i in range(100):
            r = rng.random()
            if r < 0.4:
                # Northern California (Redding, Shasta, Lassen)
                lat = rng.uniform(38.5, 41.5)
                lon = rng.uniform(-123.0, -120.0)
            elif r < 0.7:
                # Central Sierra Nevada Range
                lat = rng.uniform(36.0, 38.5)
                lon = rng.uniform(-121.0, -119.0)
            else:
                # Southern California foothills
                lat = rng.uniform(33.5, 35.5)
                lon = rng.uniform(-118.5, -116.0)
                
            grid_id = f"cell_{i+1:03d}"
            grid_data.append((grid_id, round(lat, 4), round(lon, 4)))
            
        cursor.executemany("INSERT INTO grid_cells VALUES (?, ?, ?)", grid_data)
        conn.commit()
        print(f"Seeded {len(grid_data)} California grid cells in SQLite.")
        
        # Seed mock predictions as initial state
        from datetime import date
        today = date.today().isoformat()
        pred_data = []
        for grid_id, lat, lon in grid_data:
            # Deterministic but realistic score mapping
            score = round((lat * 12.34 + abs(lon) * 56.78) % 1.0, 2)
            level = "LOW"
            if score > 0.7:
                level = "HIGH"
            elif score > 0.3:
                level = "MEDIUM"
            pred_data.append((today, grid_id, score, level, lat, lon, "wildfire-mock-v1"))
        cursor.executemany("INSERT OR REPLACE INTO predictions VALUES (?, ?, ?, ?, ?, ?, ?)", pred_data)
        conn.commit()
        print(f"Seeded initial mock predictions in SQLite.")
        
    conn.close()


@app.on_event("startup")
def startup_event():
    if DATABASE_TYPE == "sqlite":
        init_sqlite_db()


@app.get("/health")
def health():
    return {"status": "ok", "database_type": DATABASE_TYPE}


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
    if DATABASE_TYPE == "sqlite":
        import sqlite3
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if date:
            cursor.execute("""
                SELECT prediction_date, grid_id, risk_score, risk_level, center_lat, center_lon, model_version
                FROM predictions
                WHERE prediction_date = ?
                ORDER BY risk_score DESC
            """, (date,))
        else:
            cursor.execute("""
                SELECT prediction_date, grid_id, risk_score, risk_level, center_lat, center_lon, model_version
                FROM predictions
                ORDER BY prediction_date DESC, risk_score DESC
                LIMIT 100
            """)
        rows = cursor.fetchall()
        items = [dict(row) for row in rows]
        conn.close()
        return {"count": len(items), "items": items}
    
    else:
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
            from google.cloud import bigquery
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
    if DATABASE_TYPE == "sqlite":
        import sqlite3
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT prediction_date, grid_id, risk_score, risk_level, center_lat, center_lon, model_version
            FROM predictions
            WHERE grid_id = ?
            ORDER BY prediction_date DESC
            LIMIT 1
        """, (grid_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Grid cell not found")
        return dict(row)

    else:
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
        from google.cloud import bigquery
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("grid_id", "STRING", grid_id)
            ]
        )

        results = list(client.query(query, job_config=job_config).result())

        if not results:
            raise HTTPException(status_code=404, detail="Grid cell not found")

        return dict(results[0].items())
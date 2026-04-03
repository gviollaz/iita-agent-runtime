"""IITA Agent Runtime — minimal startup for debugging."""
import os
from fastapi import FastAPI

app = FastAPI(title="IITA Agent Runtime")

@app.get("/health")
async def health():
    return {"status": "ok", "port": os.environ.get("PORT", "unknown")}

@app.get("/api/v1/db-test")
async def db_test():
    db_url = os.environ.get("DATABASE_URL", "not set")
    has_password = "PASSWORD" not in db_url and db_url != "not set"
    try:
        import asyncpg
        pool = await asyncpg.create_pool(db_url, min_size=1, max_size=2, timeout=10)
        row = await pool.fetchrow(
            "SELECT (SELECT count(*) FROM information_schema.tables WHERE table_schema='public') as tables"
        )
        await pool.close()
        return {"status": "connected", "tables": row["tables"]}
    except Exception as e:
        return {"status": "error", "detail": str(e), "has_real_password": has_password}

"""IITA Agent Runtime — FastAPI application."""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from src.config import settings

db_ok = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_ok
    print(f"Starting IITA Agent Runtime v{settings.VERSION}")
    print(f"Port: {os.environ.get('PORT', 'not set')}")
    print(f"Environment: {settings.ENVIRONMENT} | Shadow: {settings.SHADOW_MODE}")
    print(f"DATABASE_URL set: {bool(settings.DATABASE_URL and 'PASSWORD' not in settings.DATABASE_URL)}")
    if settings.DATABASE_URL and 'PASSWORD' not in settings.DATABASE_URL:
        try:
            from src.db import get_pool
            pool = await get_pool()
            print(f"DB connected OK: {pool.get_size()} connections")
            db_ok = True
        except Exception as e:
            print(f"DB connection failed (non-fatal): {e}")
    yield
    try:
        from src.db import _pool
        if _pool:
            await _pool.close()
    except Exception:
        pass

app = FastAPI(title="IITA Agent Runtime", version=settings.VERSION, lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.VERSION, "db": db_ok}

@app.get("/api/v1/db-test")
async def db_test():
    try:
        from src.db import fetch_one
        stats = await fetch_one(
            "SELECT (SELECT count(*) FROM information_schema.tables WHERE table_schema='public') as tables, "
            "(SELECT count(*) FROM agent_identities) as agents, "
            "pg_size_pretty(pg_database_size(current_database())) as db_size"
        )
        return {"status": "connected", **stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/agents")
async def list_agents():
    from src.db import fetch_all
    return {"agents": await fetch_all("SELECT agent_code, name, role, model FROM agent_identities ORDER BY agent_code")}

@app.post("/api/v1/generate-response")
async def generate_response(conversation_id: int, interaction_id: int):
    return {"status": "not_implemented", "conversation_id": conversation_id}

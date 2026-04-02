"""IITA Agent Runtime — FastAPI application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from src.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Starting IITA Agent Runtime v{settings.VERSION}")
    print(f"Environment: {settings.ENVIRONMENT} | Shadow: {settings.SHADOW_MODE}")
    if settings.DATABASE_URL and settings.DATABASE_URL != '' and 'PASSWORD' not in settings.DATABASE_URL:
        try:
            from src.db import get_pool
            pool = await get_pool()
            print(f"DB connected: {pool.get_size()} connections")
        except Exception as e:
            print(f"WARNING: DB connection failed (non-fatal): {e}")
    else:
        print("WARNING: DATABASE_URL not configured or has placeholder")
    yield
    try:
        from src.db import _pool
        if _pool:
            await _pool.close()
    except Exception:
        pass
    print("Shutting down IITA Agent Runtime")


app = FastAPI(
    title="IITA Agent Runtime",
    description="Platform v4 — LangGraph Agent Runtime",
    version=settings.VERSION,
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    """Health check — always responds, even without DB."""
    return {
        "status": "ok",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "shadow_mode": settings.SHADOW_MODE,
    }


@app.get("/api/v1/db-test")
async def db_test():
    """Test database connection."""
    try:
        from src.db import fetch_one
        stats = await fetch_one(
            "SELECT "
            "(SELECT count(*) FROM information_schema.tables WHERE table_schema='public') as tables, "
            "(SELECT count(*) FROM tenants) as tenants, "
            "(SELECT count(*) FROM agent_identities) as agents, "
            "(SELECT count(*) FROM system_settings) as settings, "
            "pg_size_pretty(pg_database_size(current_database())) as db_size"
        )
        return {"status": "connected", "database": "IITA Platform v4", **stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {str(e)}")


@app.get("/api/v1/agents")
async def list_agents():
    from src.db import fetch_all
    agents = await fetch_all(
        "SELECT agent_code, name, role, model, is_active FROM agent_identities ORDER BY agent_code"
    )
    return {"agents": agents}


@app.get("/api/v1/settings/{category}")
async def get_settings(category: str):
    from src.db import fetch_all
    rows = await fetch_all(
        "SELECT key, value_text, value_numeric, value_boolean, description "
        "FROM system_settings WHERE category = $1 AND tenant_id = 1 ORDER BY key", category,
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Category '{category}' not found")
    return {"category": category, "settings": rows}


@app.post("/api/v1/generate-response")
async def generate_response(conversation_id: int, interaction_id: int):
    return {"status": "not_implemented", "conversation_id": conversation_id, "shadow_mode": settings.SHADOW_MODE}

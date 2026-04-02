"""IITA Agent Runtime — FastAPI application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from src.config import settings
from src.db import get_pool, fetch_one, fetch_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB pool on startup, close on shutdown."""
    print(f"Starting IITA Agent Runtime v{settings.VERSION}")
    print(f"Environment: {settings.ENVIRONMENT} | Shadow: {settings.SHADOW_MODE}")
    if settings.DATABASE_URL:
        pool = await get_pool()
        print(f"DB connected: {pool.get_size()} connections")
    else:
        print("WARNING: DATABASE_URL not set — DB features disabled")
    yield
    from src.db import _pool
    if _pool:
        await _pool.close()
    print("Shutting down IITA Agent Runtime")


app = FastAPI(
    title="IITA Agent Runtime",
    description="Platform v4 — LangGraph Agent Runtime",
    version=settings.VERSION,
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "shadow_mode": settings.SHADOW_MODE,
    }


@app.get("/api/v1/db-test")
async def db_test():
    """Test database connection and show v4 DB stats."""
    try:
        stats = await fetch_one(
            "SELECT "
            "(SELECT count(*) FROM information_schema.tables WHERE table_schema='public') as tables, "
            "(SELECT count(*) FROM tenants) as tenants, "
            "(SELECT count(*) FROM agent_identities) as agents, "
            "(SELECT count(*) FROM system_settings) as settings, "
            "(SELECT count(*) FROM pipeline_stages WHERE pipeline_id=1) as pipeline_stages, "
            "pg_size_pretty(pg_database_size(current_database())) as db_size, "
            "version() as pg_version"
        )
        return {"status": "connected", "database": "IITA Platform v4", **stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB connection failed: {str(e)}")


@app.get("/api/v1/agents")
async def list_agents():
    """List all configured agents."""
    agents = await fetch_all(
        "SELECT agent_code, name, role, model, available_tools, is_active "
        "FROM agent_identities ORDER BY agent_code"
    )
    return {"agents": agents}


@app.get("/api/v1/settings/{category}")
async def get_settings(category: str):
    """Get system settings by category."""
    rows = await fetch_all(
        "SELECT key, value_text, value_numeric, value_boolean, description "
        "FROM system_settings WHERE category = $1 AND tenant_id = 1 ORDER BY key",
        category,
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Category '{category}' not found")
    return {"category": category, "settings": rows}


@app.post("/api/v1/generate-response")
async def generate_response(conversation_id: int, interaction_id: int):
    """Generate AI response — replaces Make.com RG scenario."""
    # TODO: Fase 1 — wire up LangGraph agent
    return {
        "status": "not_implemented",
        "conversation_id": conversation_id,
        "interaction_id": interaction_id,
        "shadow_mode": settings.SHADOW_MODE,
        "message": "Agent Core not yet implemented. Next: implement agent_reasoning node.",
    }


@app.post("/api/v1/webhook/meta")
async def meta_webhook():
    """Unified Meta webhook — replaces 7 INPUT scenarios."""
    # TODO: Fase 2
    return {"status": "not_implemented"}

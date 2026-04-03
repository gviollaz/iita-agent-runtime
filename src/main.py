"""IITA Agent Runtime."""
import os
from fastapi import FastAPI

app = FastAPI(title="IITA Agent Runtime")

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}

@app.get("/")
def root():
    return {"service": "iita-agent-runtime", "status": "ok"}

@app.get("/api/v1/db-test")
async def db_test():
    """Test DB connection to Supabase v4."""
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url or "PASSWORD" in db_url:
        return {"status": "error", "detail": "DATABASE_URL not configured or has placeholder"}
    try:
        import asyncpg
        conn = await asyncpg.connect(db_url, timeout=10)
        row = await conn.fetchrow(
            "SELECT "
            "(SELECT count(*) FROM information_schema.tables WHERE table_schema='public') as tables, "
            "(SELECT count(*) FROM agent_identities) as agents, "
            "(SELECT count(*) FROM system_settings) as settings, "
            "pg_size_pretty(pg_database_size(current_database())) as db_size"
        )
        await conn.close()
        return {"status": "connected", "database": "IITA Platform v4", **dict(row)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.get("/api/v1/agents")
async def list_agents():
    """List configured agents."""
    db_url = os.environ.get("DATABASE_URL", "")
    try:
        import asyncpg
        conn = await asyncpg.connect(db_url, timeout=10)
        rows = await conn.fetch("SELECT agent_code, name, role, model FROM agent_identities ORDER BY agent_code")
        await conn.close()
        return {"agents": [dict(r) for r in rows]}
    except Exception as e:
        return {"error": str(e)}

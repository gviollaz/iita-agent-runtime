"""IITA Agent Runtime — connects via Supabase REST API (bypasses pooler)."""
import os
import httpx
from fastapi import FastAPI

app = FastAPI(title="IITA Agent Runtime")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

def supabase_headers():
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }

@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "supabase_url": SUPABASE_URL[:30] + "..." if SUPABASE_URL else "not set",
        "anon_key_set": bool(SUPABASE_ANON_KEY),
    }

@app.get("/")
def root():
    return {"service": "iita-agent-runtime", "status": "ok"}

@app.get("/api/v1/db-test")
async def db_test():
    """Test connection via Supabase REST API."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return {"status": "error", "detail": "SUPABASE_URL or SUPABASE_ANON_KEY not set"}
    try:
        async with httpx.AsyncClient() as client:
            # Query agent_identities via REST
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/agent_identities?select=agent_code,name,role,model",
                headers=supabase_headers(),
                timeout=10,
            )
            if r.status_code == 200:
                agents = r.json()
                return {
                    "status": "connected",
                    "database": "IITA Platform v4",
                    "method": "Supabase REST API",
                    "agents_found": len(agents),
                    "agents": agents,
                }
            else:
                return {"status": "error", "http_code": r.status_code, "detail": r.text}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.get("/api/v1/agents")
async def list_agents():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/agent_identities?select=agent_code,name,role,model,is_active&order=agent_code",
                headers=supabase_headers(),
                timeout=10,
            )
            return {"agents": r.json() if r.status_code == 200 else [], "http_code": r.status_code}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/v1/settings/{category}")
async def get_settings(category: str):
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{SUPABASE_URL}/rest/v1/system_settings?select=key,value_text,value_numeric,value_boolean,description&category=eq.{category}&tenant_id=eq.1",
                headers=supabase_headers(),
                timeout=10,
            )
            return {"category": category, "settings": r.json() if r.status_code == 200 else [], "http_code": r.status_code}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/v1/generate-response")
async def generate_response(conversation_id: int, interaction_id: int):
    return {"status": "not_implemented", "conversation_id": conversation_id}

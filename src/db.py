"""Database helpers — Supabase v4 (config) + v3 (CRM data)."""
import os
import httpx

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_V3_URL = os.environ.get("SUPABASE_V3_URL", "")
SUPABASE_V3_KEY = os.environ.get("SUPABASE_V3_SERVICE_KEY", "")

def _v4h():
    return {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"}

def _v3h():
    return {"apikey": SUPABASE_V3_KEY, "Authorization": f"Bearer {SUPABASE_V3_KEY}", "Content-Type": "application/json"}

async def v4_query(table: str, select: str, filters: str = "") -> list:
    """Query v4 Supabase via REST."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}"
    if filters:
        url += f"&{filters}"
    async with httpx.AsyncClient() as c:
        r = await c.get(url, headers=_v4h(), timeout=10)
        return r.json() if r.status_code == 200 else []

async def v3_rpc(fn: str, params: dict, timeout: int = 15):
    """Call v3 CRM RPC function."""
    if not SUPABASE_V3_URL or not SUPABASE_V3_KEY:
        return None
    url = f"{SUPABASE_V3_URL}/rest/v1/rpc/{fn}"
    async with httpx.AsyncClient() as c:
        r = await c.post(url, headers=_v3h(), json=params, timeout=timeout)
        return r.json() if r.status_code == 200 else None

async def v3_query(table: str, select: str, filters: str = "") -> list:
    """Query v3 CRM table via REST."""
    if not SUPABASE_V3_URL or not SUPABASE_V3_KEY:
        return []
    url = f"{SUPABASE_V3_URL}/rest/v1/{table}?select={select}"
    if filters:
        url += f"&{filters}"
    async with httpx.AsyncClient() as c:
        r = await c.get(url, headers=_v3h(), timeout=10)
        return r.json() if r.status_code == 200 else []

def v3_available() -> bool:
    return bool(SUPABASE_V3_URL and SUPABASE_V3_KEY)

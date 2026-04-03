"""Database helpers — v4 (config/logging) + v3 (CRM data)."""
import os
import json
import httpx

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_V3_URL = os.environ.get("SUPABASE_V3_URL", "")
SUPABASE_V3_KEY = os.environ.get("SUPABASE_V3_SERVICE_KEY", "")

def _v4h():
    return {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}", "Content-Type": "application/json"}

def _v3h():
    return {"apikey": SUPABASE_V3_KEY, "Authorization": f"Bearer {SUPABASE_V3_KEY}", "Content-Type": "application/json"}

async def v4_query(table: str, select: str, filters: str = "") -> list:
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}"
    if filters: url += f"&{filters}"
    async with httpx.AsyncClient() as c:
        r = await c.get(url, headers=_v4h(), timeout=10)
        return r.json() if r.status_code == 200 else []

async def v4_insert(table: str, data: dict) -> dict | None:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {**_v4h(), "Prefer": "return=representation"}
    async with httpx.AsyncClient() as c:
        r = await c.post(url, headers=headers, json=data, timeout=10)
        if r.status_code in (200, 201):
            result = r.json()
            return result[0] if isinstance(result, list) and result else result
        return None

async def v3_rpc(fn: str, params: dict, timeout: int = 15):
    if not SUPABASE_V3_URL or not SUPABASE_V3_KEY: return None
    url = f"{SUPABASE_V3_URL}/rest/v1/rpc/{fn}"
    async with httpx.AsyncClient() as c:
        r = await c.post(url, headers=_v3h(), json=params, timeout=timeout)
        return r.json() if r.status_code == 200 else None

async def v3_query(table: str, select: str, filters: str = "") -> list:
    if not SUPABASE_V3_URL or not SUPABASE_V3_KEY: return []
    url = f"{SUPABASE_V3_URL}/rest/v1/{table}?select={select}"
    if filters: url += f"&{filters}"
    async with httpx.AsyncClient() as c:
        r = await c.get(url, headers=_v3h(), timeout=10)
        return r.json() if r.status_code == 200 else []

async def v3_insert(table: str, data: dict) -> dict | None:
    """Insert a row into v3 CRM DB via REST."""
    if not SUPABASE_V3_URL or not SUPABASE_V3_KEY: return None
    url = f"{SUPABASE_V3_URL}/rest/v1/{table}"
    headers = {**_v3h(), "Prefer": "return=representation"}
    async with httpx.AsyncClient() as c:
        r = await c.post(url, headers=headers, json=data, timeout=10)
        if r.status_code in (200, 201):
            result = r.json()
            return result[0] if isinstance(result, list) and result else result
        return None

async def v3_update(table: str, filters: str, data: dict) -> dict | None:
    """Update rows in v3 CRM DB via REST."""
    if not SUPABASE_V3_URL or not SUPABASE_V3_KEY: return None
    url = f"{SUPABASE_V3_URL}/rest/v1/{table}?{filters}"
    headers = {**_v3h(), "Prefer": "return=representation"}
    async with httpx.AsyncClient() as c:
        r = await c.patch(url, headers=headers, json=data, timeout=10)
        if r.status_code in (200, 204):
            result = r.json() if r.status_code == 200 else None
            return result
        return None

def v3_available() -> bool:
    return bool(SUPABASE_V3_URL and SUPABASE_V3_KEY)

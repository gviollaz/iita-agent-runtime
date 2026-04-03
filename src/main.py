"""IITA Agent Runtime v0.6.0 — Shadow Batch + Dashboard."""
import os
import json
from openai import AsyncOpenAI
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from src.agent import load_agent, build_system_prompt, get_person_context, get_conversation_history, run_agent, resolve_person_id
from src.db import v4_query, v3_available, v3_query, v4_insert

app = FastAPI(title="IITA Agent Runtime", version="0.6.0")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
SHADOW_MODE = os.environ.get("SHADOW_MODE", "true").lower() == "true"
oai = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


class TestMessage(BaseModel):
    message: str
    agent_code: str = "AG-01"
    person_context: str = ""
    conversation_history: list[dict] = []

class GenerateRequest(BaseModel):
    conversation_id: int
    interaction_id: int

class ShadowCompareRequest(BaseModel):
    conversation_id: int

class ShadowBatchRequest(BaseModel):
    hours: int = 6
    max_conversations: int = 5


# ═══ CORE ENDPOINTS ═══

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.6.0", "openai": bool(OPENAI_API_KEY),
            "v3_connected": v3_available(), "shadow_mode": SHADOW_MODE}

@app.get("/")
def root():
    return {"service": "iita-agent-runtime", "version": "0.6.0"}

@app.get("/api/v1/db-test")
async def db_test():
    agents = await v4_query("agent_identities", "agent_code,name,role,model")
    settings = await v4_query("system_settings", "key", "tenant_id=eq.1")
    fragments = await v4_query("prompt_fragments", "name", "is_active=eq.true")
    shadow = await v4_query("shadow_log", "id", "order=id.desc&limit=1")
    return {"status": "connected", "v3": v3_available(),
            "agents": len(agents), "settings": len(settings),
            "fragments": len(fragments),
            "shadow_entries": shadow[0]["id"] if shadow else 0}

@app.get("/api/v1/agents")
async def list_agents():
    return {"agents": await v4_query("agent_identities", "agent_code,name,role,model,available_tools,is_active")}

@app.get("/api/v1/settings/{category}")
async def get_settings(category: str):
    rows = await v4_query("system_settings", "key,value_text,value_numeric,value_boolean,description",
                          f"category=eq.{category}&tenant_id=eq.1")
    return {"category": category, "settings": rows}

@app.get("/api/v1/system-prompt")
async def preview_system_prompt(agent_code: str = "AG-01"):
    agent = await load_agent(agent_code)
    if not agent:
        return {"error": f"Agent {agent_code} not found"}
    prompt = await build_system_prompt(agent)
    return {"agent": agent_code, "length": len(prompt), "prompt": prompt}


# ═══ AGENT ENDPOINTS ═══

@app.post("/api/v1/test-agent")
async def test_agent(req: TestMessage):
    """Test Ana with a direct message. Supports tool calling."""
    if not oai:
        return {"status": "error", "detail": "OPENAI_API_KEY not configured"}
    agent = await load_agent(req.agent_code)
    if not agent:
        return {"status": "error", "detail": f"Agent {req.agent_code} not found"}

    system_prompt = await build_system_prompt(agent, req.person_context)
    messages = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in req.conversation_history]
    messages.append({"role": "user", "content": req.message})

    result = await run_agent(oai, agent, system_prompt, messages)
    return {"status": "ok", "agent": agent.get("agent_code"), "model": agent.get("model"),
            "response": result["response"], "usage": result["usage"],
            "latency_ms": result["latency_ms"], "tool_calls": result["tool_calls"],
            "rounds": result["rounds"], "shadow_mode": SHADOW_MODE,
            "system_prompt_length": len(system_prompt)}


@app.post("/api/v1/generate-response")
async def generate_response(req: GenerateRequest):
    """Generate AI response for a real v3 CRM conversation."""
    if not oai:
        return {"status": "error", "detail": "OPENAI_API_KEY not configured"}
    agent = await load_agent("AG-01")
    if not agent:
        return {"status": "error", "detail": "Agent AG-01 not found"}

    person_context = await get_person_context(req.conversation_id)
    history = await get_conversation_history(req.conversation_id, limit=20)
    system_prompt = await build_system_prompt(agent, person_context)
    messages = history if history else [{"role": "user", "content": "Hola"}]

    result = await run_agent(oai, agent, system_prompt, messages, {"conversation_id": req.conversation_id})
    return {"status": "ok", "conversation_id": req.conversation_id,
            "interaction_id": req.interaction_id, "response": result["response"],
            "model": agent.get("model"), "latency_ms": result["latency_ms"],
            "tokens": result["usage"].get("total_tokens", 0),
            "tool_calls": result["tool_calls"], "rounds": result["rounds"],
            "shadow_mode": SHADOW_MODE, "action": "shadow_logged" if SHADOW_MODE else "would_send"}


# ═══ SHADOW MODE ENDPOINTS ═══

@app.post("/api/v1/shadow-compare")
async def shadow_compare(req: ShadowCompareRequest):
    """Compare v4 vs Make.com for one conversation."""
    if not oai or not v3_available():
        return {"status": "error", "detail": "OpenAI or V3 not available"}
    agent = await load_agent("AG-01")
    if not agent:
        return {"status": "error", "detail": "Agent not found"}

    person_id = await resolve_person_id(req.conversation_id)
    history = await get_conversation_history(req.conversation_id, limit=20)
    if not history:
        return {"status": "error", "detail": "No messages"}

    last_user_msg = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    if not last_user_msg:
        return {"status": "error", "detail": "No inbound message"}

    # Get v3 response
    sc = await v3_query("system_conversation", "id", f"id_conversation=eq.{req.conversation_id}")
    v3_response = None
    if sc:
        out = await v3_query("interactions", "text", f"id_system_conversation=eq.{sc[0]['id']}&text=not.is.null&order=time_stamp.desc&limit=1")
        v3_response = out[0]["text"] if out else None

    # Generate v4
    person_context = await get_person_context(req.conversation_id)
    system_prompt = await build_system_prompt(agent, person_context)
    result = await run_agent(oai, agent, system_prompt, history, {"conversation_id": req.conversation_id})

    # Log
    await v4_insert("shadow_log", {
        "conversation_id": req.conversation_id, "person_id": person_id,
        "user_message": last_user_msg, "v3_response": v3_response,
        "v4_response": result["response"], "v4_model": agent.get("model"),
        "v4_latency_ms": result["latency_ms"],
        "v4_tokens": result["usage"].get("total_tokens", 0),
        "v4_tool_calls": json.dumps(result["tool_calls"]),
        "v4_rounds": result["rounds"], "v4_prompt_length": len(system_prompt),
    })

    return {"status": "ok", "conversation_id": req.conversation_id,
            "user_message": last_user_msg,
            "v3_make_response": v3_response, "v4_agent_response": result["response"],
            "v4_metrics": {"latency_ms": result["latency_ms"],
                           "tokens": result["usage"].get("total_tokens", 0),
                           "tool_calls": result["tool_calls"], "rounds": result["rounds"]}}


@app.post("/api/v1/shadow-batch")
async def shadow_batch(req: ShadowBatchRequest):
    """Run shadow comparison on recent conversations automatically.
    
    Finds conversations with inbound messages in the last N hours
    that haven't been shadow-tested yet, and runs comparisons.
    """
    if not oai or not v3_available():
        return {"status": "error", "detail": "OpenAI or V3 not available"}

    # 1. Get conversations already tested
    tested = await v4_query("shadow_log", "conversation_id", "order=id.desc&limit=200")
    tested_ids = {r["conversation_id"] for r in tested}

    # 2. Find recent conversations with inbound messages from v3
    from src.db import v3_rpc
    recent = await v3_rpc("get_recent_conversations_for_shadow", {
        "p_hours": req.hours, "p_limit": req.max_conversations * 3
    })
    
    # Fallback: query directly if RPC doesn't exist
    if recent is None:
        recent_convs = await v3_query(
            "conversations", "id,last_activity_at",
            f"last_activity_at=gte.now()-{req.hours}*interval'1 hour'"
            f"&order=last_activity_at.desc&limit={req.max_conversations * 3}"
        )
        if not recent_convs:
            # Simpler query
            recent_convs = await v3_query(
                "conversations", "id",
                f"order=last_activity_at.desc&limit={req.max_conversations * 3}"
            )
        recent = [{"conversation_id": c["id"]} for c in recent_convs]

    if not recent:
        return {"status": "ok", "message": "No recent conversations found", "tested": 0}

    # 3. Filter out already tested
    candidates = []
    for r in recent:
        cid = r.get("conversation_id") or r.get("id")
        if cid and cid not in tested_ids:
            candidates.append(cid)
    candidates = candidates[:req.max_conversations]

    if not candidates:
        return {"status": "ok", "message": "All recent conversations already tested", "tested": 0}

    # 4. Run comparisons
    results = []
    for cid in candidates:
        try:
            compare_req = ShadowCompareRequest(conversation_id=cid)
            result = await shadow_compare(compare_req)
            results.append({"conversation_id": cid, "status": result.get("status", "error")})
        except Exception as e:
            results.append({"conversation_id": cid, "status": "error", "detail": str(e)})

    return {
        "status": "ok",
        "tested": len([r for r in results if r["status"] == "ok"]),
        "errors": len([r for r in results if r["status"] != "ok"]),
        "results": results,
    }


@app.get("/api/v1/shadow-log")
async def get_shadow_log(limit: int = 20):
    rows = await v4_query("shadow_log",
        "id,conversation_id,user_message,v3_response,v4_response,v4_latency_ms,v4_tokens,v4_tool_calls,v4_rounds,quality_score,quality_notes,created_at",
        f"order=id.desc&limit={limit}")
    return {"count": len(rows), "entries": rows}


# ═══ DASHBOARD ═══

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Visual dashboard for shadow mode comparison results."""
    rows = await v4_query("shadow_log",
        "id,conversation_id,user_message,v3_response,v4_response,v4_latency_ms,v4_tokens,v4_tool_calls,v4_rounds,quality_score,created_at",
        "order=id.desc&limit=50")
    
    stats = await v4_query("shadow_log", "id", "")
    total = len(stats)
    avg_latency = sum(r.get("v4_latency_ms", 0) for r in rows) // max(len(rows), 1) if rows else 0
    avg_tokens = sum(r.get("v4_tokens", 0) for r in rows) // max(len(rows), 1) if rows else 0
    tool_usage = sum(1 for r in rows if r.get("v4_rounds", 1) > 1)

    entries_html = ""
    for r in rows:
        tc = r.get("v4_tool_calls")
        if isinstance(tc, str):
            try: tc = json.loads(tc)
            except: tc = []
        tools_str = ", ".join([t.get("tool","?") for t in (tc or [])]) or "ninguna"
        
        v3_text = (r.get("v3_response") or "N/A")[:300]
        v4_text = (r.get("v4_response") or "N/A")[:300]
        user_text = (r.get("user_message") or "")[:150]
        
        q_score = r.get("quality_score")
        q_badge = f'<span style="background:#22c55e;color:white;padding:2px 8px;border-radius:4px">{q_score}/5</span>' if q_score else '<span style="background:#94a3b8;color:white;padding:2px 8px;border-radius:4px">sin evaluar</span>'
        
        entries_html += f"""
        <div style="border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:16px;background:white">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px">
                <strong>Conv #{r.get('conversation_id')} — Shadow #{r.get('id')}</strong>
                <span>{q_badge} | {r.get('v4_latency_ms',0)}ms | {r.get('v4_tokens',0)} tok | Tools: {tools_str}</span>
            </div>
            <div style="background:#f1f5f9;padding:8px;border-radius:4px;margin-bottom:8px">
                <strong>Usuario:</strong> {user_text}
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                <div style="background:#fef3c7;padding:10px;border-radius:4px;border-left:4px solid #f59e0b">
                    <strong>Make.com (v3):</strong><br>{v3_text}
                </div>
                <div style="background:#dbeafe;padding:10px;border-radius:4px;border-left:4px solid #3b82f6">
                    <strong>Agent Runtime (v4):</strong><br>{v4_text}
                </div>
            </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html><head><title>IITA Agent Runtime — Shadow Dashboard</title>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{font-family:system-ui;margin:0;padding:20px;background:#f8fafc}}
h1{{color:#1e3a5f}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}}
.stat{{background:white;border:1px solid #e2e8f0;border-radius:8px;padding:16px;text-align:center}}
.stat .n{{font-size:28px;font-weight:bold;color:#1a56db}}
.stat .l{{color:#64748b;font-size:13px}}</style></head>
<body>
<h1>IITA Agent Runtime — Shadow Dashboard</h1>
<div class="stats">
    <div class="stat"><div class="n">{total}</div><div class="l">Comparaciones totales</div></div>
    <div class="stat"><div class="n">{avg_latency}ms</div><div class="l">Latencia promedio v4</div></div>
    <div class="stat"><div class="n">{avg_tokens}</div><div class="l">Tokens promedio v4</div></div>
    <div class="stat"><div class="n">{tool_usage}/{len(rows)}</div><div class="l">Usaron tools</div></div>
</div>
<h2>Comparaciones recientes</h2>
{entries_html if entries_html else '<p style="color:#94a3b8">No hay comparaciones todavia. Usa POST /api/v1/shadow-batch para generar.</p>'}
</body></html>"""

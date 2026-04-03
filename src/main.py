"""IITA Agent Runtime v0.8.1 — CORS fix for frontend."""
import os
import json
from datetime import datetime
from openai import AsyncOpenAI
from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from src.agent import load_agent, build_system_prompt, get_person_context, get_conversation_history, run_agent, resolve_person_id
from src.db import v4_query, v3_available, v3_query, v4_insert
from src.webhook import parse_webhook, verify_webhook, MessageType
from src.channels import (resolve_channel_id, find_or_create_person,
    create_inbound_interaction, create_outbound_interaction,
    send_response, log_webhook_event)

app = FastAPI(title="IITA Agent Runtime", version="0.8.1")

# CORS — allow CRM frontend (Vercel) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://iitacrm.vercel.app",
        "https://iitacrm-*.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


# ═══ META WEBHOOK ═══

@app.get("/webhook/meta")
async def webhook_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    result = verify_webhook(hub_mode or "", hub_verify_token or "", hub_challenge or "")
    if result: return PlainTextResponse(content=result)
    return PlainTextResponse(content="Verification failed", status_code=403)

@app.post("/webhook/meta")
async def webhook_receive(request: Request):
    body = await request.json()
    messages = parse_webhook(body)
    if not messages: return {"status": "ok", "messages": 0}
    results = []
    for msg in messages:
        t0 = datetime.now(); status = "received"; error = None
        try:
            channel_id = resolve_channel_id(msg)
            if not channel_id:
                await log_webhook_event(msg, None, None, "error", f"Unknown recipient {msg.recipient_id}")
                results.append({"status": "error"}); continue
            conv_info = await find_or_create_person(msg, channel_id)
            if not conv_info:
                await log_webhook_event(msg, channel_id, None, "error", "No person/conv")
                results.append({"status": "error"}); continue
            if msg.message_type != MessageType.TEXT or not msg.text:
                await log_webhook_event(msg, channel_id, conv_info, "received_non_text")
                results.append({"status": "received_non_text"}); continue
            if SHADOW_MODE:
                status = "shadow_logged"
                latency = int((datetime.now() - t0).total_seconds() * 1000)
                await log_webhook_event(msg, channel_id, conv_info, status, latency_ms=latency)
                results.append({"status": status, "conversation_id": conv_info["conversation_id"]})
            else:
                await create_inbound_interaction(msg, conv_info)
                agent = await load_agent("AG-01")
                if agent and oai:
                    person_context = await get_person_context(conv_info["conversation_id"])
                    history = await get_conversation_history(conv_info["conversation_id"], limit=20)
                    system_prompt = await build_system_prompt(agent, person_context)
                    agent_result = await run_agent(oai, agent, system_prompt, history + [{"role": "user", "content": msg.text}], {"conversation_id": conv_info["conversation_id"]})
                    reply = agent_result["response"]
                    sr = await send_response(msg, reply, conv_info, channel_id)
                    await create_outbound_interaction(reply, conv_info)
                    status = "response_sent" if (sr and not sr.get("error")) else "response_via_makecom"
                latency = int((datetime.now() - t0).total_seconds() * 1000)
                await log_webhook_event(msg, channel_id, conv_info, status, error, latency)
                results.append({"status": status, "conversation_id": conv_info["conversation_id"], "latency_ms": latency})
        except Exception as e:
            await log_webhook_event(msg, None, None, "error", str(e))
            results.append({"status": "error", "detail": str(e)})
    return {"status": "ok", "messages": len(results), "shadow_mode": SHADOW_MODE, "results": results}


# ═══ CORE ═══

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.8.1", "openai": bool(OPENAI_API_KEY),
            "v3_connected": v3_available(), "shadow_mode": SHADOW_MODE}

@app.get("/")
def root():
    return {"service": "iita-agent-runtime", "version": "0.8.1"}

@app.get("/api/v1/db-test")
async def db_test():
    agents = await v4_query("agent_identities", "agent_code,name,role,model")
    settings = await v4_query("system_settings", "key", "tenant_id=eq.1")
    fragments = await v4_query("prompt_fragments", "name", "is_active=eq.true")
    shadow = await v4_query("shadow_log", "id", "order=id.desc&limit=1")
    webhook = await v4_query("webhook_events", "id", "order=id.desc&limit=1")
    return {"status": "connected", "v3": v3_available(),
            "agents": len(agents), "settings": len(settings), "fragments": len(fragments),
            "shadow_entries": shadow[0]["id"] if shadow else 0,
            "webhook_events": webhook[0]["id"] if webhook else 0}

@app.get("/api/v1/agents")
async def list_agents():
    return {"agents": await v4_query("agent_identities", "agent_code,name,role,model,available_tools,is_active")}

@app.get("/api/v1/settings/{category}")
async def get_settings(category: str):
    return {"category": category, "settings": await v4_query("system_settings",
        "key,value_text,value_numeric,value_boolean,description", f"category=eq.{category}&tenant_id=eq.1")}

@app.get("/api/v1/system-prompt")
async def preview_system_prompt(agent_code: str = "AG-01"):
    agent = await load_agent(agent_code)
    if not agent: return {"error": f"Agent {agent_code} not found"}
    prompt = await build_system_prompt(agent)
    return {"agent": agent_code, "length": len(prompt), "prompt": prompt}

@app.post("/api/v1/test-agent")
async def test_agent(req: TestMessage):
    if not oai: return {"status": "error", "detail": "OPENAI_API_KEY not configured"}
    agent = await load_agent(req.agent_code)
    if not agent: return {"status": "error", "detail": f"Agent {req.agent_code} not found"}
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
    if not oai: return {"status": "error", "detail": "OPENAI_API_KEY not configured"}
    agent = await load_agent("AG-01")
    if not agent: return {"status": "error", "detail": "Agent AG-01 not found"}
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


# ═══ SHADOW MODE ═══

@app.post("/api/v1/shadow-compare")
async def shadow_compare(req: ShadowCompareRequest):
    if not oai or not v3_available(): return {"status": "error", "detail": "OpenAI or V3 not available"}
    agent = await load_agent("AG-01")
    if not agent: return {"status": "error", "detail": "Agent not found"}
    person_id = await resolve_person_id(req.conversation_id)
    history = await get_conversation_history(req.conversation_id, limit=20)
    if not history: return {"status": "error", "detail": "No messages"}
    last_user_msg = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    if not last_user_msg: return {"status": "error", "detail": "No inbound message"}
    sc = await v3_query("system_conversation", "id", f"id_conversation=eq.{req.conversation_id}")
    v3_response = None
    if sc:
        out = await v3_query("interactions", "text", f"id_system_conversation=eq.{sc[0]['id']}&text=not.is.null&order=time_stamp.desc&limit=1")
        v3_response = out[0]["text"] if out else None
    person_context = await get_person_context(req.conversation_id)
    system_prompt = await build_system_prompt(agent, person_context)
    result = await run_agent(oai, agent, system_prompt, history, {"conversation_id": req.conversation_id})
    await v4_insert("shadow_log", {"conversation_id": req.conversation_id, "person_id": person_id,
        "user_message": last_user_msg, "v3_response": v3_response,
        "v4_response": result["response"], "v4_model": agent.get("model"),
        "v4_latency_ms": result["latency_ms"], "v4_tokens": result["usage"].get("total_tokens", 0),
        "v4_tool_calls": json.dumps(result["tool_calls"]),
        "v4_rounds": result["rounds"], "v4_prompt_length": len(system_prompt)})
    return {"status": "ok", "conversation_id": req.conversation_id, "user_message": last_user_msg,
            "v3_make_response": v3_response, "v4_agent_response": result["response"],
            "v4_metrics": {"latency_ms": result["latency_ms"], "tokens": result["usage"].get("total_tokens", 0),
                           "tool_calls": result["tool_calls"], "rounds": result["rounds"]}}

@app.post("/api/v1/shadow-batch")
async def shadow_batch(req: ShadowBatchRequest):
    if not oai or not v3_available(): return {"status": "error", "detail": "OpenAI or V3 not available"}
    tested = await v4_query("shadow_log", "conversation_id", "order=id.desc&limit=200")
    tested_ids = {r["conversation_id"] for r in tested}
    recent = await v3_query("conversations", "id", f"order=last_activity_at.desc&limit={req.max_conversations * 3}")
    candidates = [c["id"] for c in recent if c["id"] not in tested_ids][:req.max_conversations]
    if not candidates: return {"status": "ok", "message": "No untested conversations", "tested": 0}
    results = []
    for cid in candidates:
        try:
            r = await shadow_compare(ShadowCompareRequest(conversation_id=cid))
            results.append({"conversation_id": cid, "status": r.get("status", "error")})
        except Exception as e:
            results.append({"conversation_id": cid, "status": "error", "detail": str(e)})
    return {"status": "ok", "tested": len([r for r in results if r["status"] == "ok"]),
            "errors": len([r for r in results if r["status"] != "ok"]), "results": results}

@app.get("/api/v1/shadow-log")
async def get_shadow_log(limit: int = 20):
    entries = await v4_query("shadow_log",
        "id,conversation_id,user_message,v3_response,v4_response,v4_latency_ms,v4_tokens,v4_tool_calls,v4_rounds,quality_score,created_at",
        f"order=id.desc&limit={limit}")
    return {"count": len(entries), "entries": entries}

@app.get("/api/v1/webhook-events")
async def get_webhook_events(limit: int = 50):
    return {"events": await v4_query("webhook_events",
        "id,platform,sender_id,channel_id,conversation_id,message_type,message_preview,processing_status,error_detail,latency_ms,created_at",
        f"order=id.desc&limit={limit}")}


# ═══ DASHBOARD ═══

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    rows = await v4_query("shadow_log",
        "id,conversation_id,user_message,v3_response,v4_response,v4_latency_ms,v4_tokens,v4_tool_calls,v4_rounds,quality_score,created_at",
        "order=id.desc&limit=50")
    total = len(await v4_query("shadow_log", "id", ""))
    wh = len(await v4_query("webhook_events", "id", ""))
    al = sum(r.get("v4_latency_ms",0) for r in rows)//max(len(rows),1) if rows else 0
    at = sum(r.get("v4_tokens",0) for r in rows)//max(len(rows),1) if rows else 0
    tu = sum(1 for r in rows if r.get("v4_rounds",1)>1)
    eh = ""
    for r in rows:
        tc = r.get("v4_tool_calls"); 
        if isinstance(tc,str):
            try: tc=json.loads(tc)
            except: tc=[]
        ts=", ".join([t.get("tool","?") for t in (tc or [])]) or "-"
        eh+=f'<div style="border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:12px;background:white"><div style="display:flex;justify-content:space-between;margin-bottom:6px"><strong>#{r.get("id")} Conv {r.get("conversation_id")}</strong><span style="font-size:11px;color:#64748b">{r.get("v4_latency_ms",0)}ms | {r.get("v4_tokens",0)}tok | {ts}</span></div><div style="background:#f1f5f9;padding:8px;border-radius:4px;margin-bottom:8px;font-size:13px"><b>User:</b> {(r.get("user_message") or "")[:150]}</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><div style="background:#fef3c7;padding:8px;border-radius:4px;border-left:3px solid #f59e0b;font-size:12px"><b>v3:</b> {(r.get("v3_response") or "N/A")[:250]}</div><div style="background:#dbeafe;padding:8px;border-radius:4px;border-left:3px solid #3b82f6;font-size:12px"><b>v4:</b> {(r.get("v4_response") or "N/A")[:250]}</div></div></div>'
    return f'<!DOCTYPE html><html><head><title>IITA Dashboard</title><meta charset="utf-8"><style>body{{font-family:system-ui;margin:0;padding:20px;background:#f8fafc}}h1{{color:#1e3a5f}}.s{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:20px}}.c{{background:white;border:1px solid #e2e8f0;border-radius:8px;padding:14px;text-align:center}}.c .n{{font-size:26px;font-weight:800;color:#1a56db}}.c .l{{color:#64748b;font-size:12px}}</style></head><body><h1>IITA Agent Runtime v0.8.1</h1><div class="s"><div class="c"><div class="n">{total}</div><div class="l">Shadow</div></div><div class="c"><div class="n">{wh}</div><div class="l">Webhooks</div></div><div class="c"><div class="n">{al}ms</div><div class="l">Latencia</div></div><div class="c"><div class="n">{at}</div><div class="l">Tokens</div></div><div class="c"><div class="n">{tu}/{len(rows)}</div><div class="l">Tools</div></div></div>{eh or "<p>Sin datos</p>"}</body></html>'

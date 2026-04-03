"""IITA Agent Runtime v0.5.0 — FastAPI + OpenAI Tools + Shadow Mode."""
import os
import json
from openai import AsyncOpenAI
from fastapi import FastAPI
from pydantic import BaseModel
from src.agent import load_agent, build_system_prompt, get_person_context, get_conversation_history, run_agent, resolve_person_id
from src.db import v4_query, v3_available, v3_query, v4_insert

app = FastAPI(title="IITA Agent Runtime", version="0.5.0")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
SHADOW_MODE = os.environ.get("SHADOW_MODE", "true").lower() == "true"
oai = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# --- Models ---

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


# --- Endpoints ---

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.5.0", "openai": bool(OPENAI_API_KEY),
            "v3_connected": v3_available(), "shadow_mode": SHADOW_MODE}

@app.get("/")
def root():
    return {"service": "iita-agent-runtime", "version": "0.5.0"}

@app.get("/api/v1/db-test")
async def db_test():
    agents = await v4_query("agent_identities", "agent_code,name,role,model")
    settings = await v4_query("system_settings", "key", "tenant_id=eq.1")
    fragments = await v4_query("prompt_fragments", "name", "is_active=eq.true")
    patterns = await v4_query("response_evaluation_patterns", "pattern_text", "is_active=eq.true")
    shadow = await v4_query("shadow_log", "id", "order=id.desc&limit=1")
    return {"status": "connected", "v3": v3_available(),
            "agents": len(agents), "settings": len(settings),
            "fragments": len(fragments), "patterns": len(patterns),
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


@app.post("/api/v1/test-agent")
async def test_agent(req: TestMessage):
    """Test Ana with a direct message. Supports tool calling."""
    if not oai:
        return {"status": "error", "detail": "OPENAI_API_KEY not configured"}
    agent = await load_agent(req.agent_code)
    if not agent:
        return {"status": "error", "detail": f"Agent {req.agent_code} not found"}

    system_prompt = await build_system_prompt(agent, req.person_context)
    messages = []
    for msg in req.conversation_history:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": req.message})

    result = await run_agent(oai, agent, system_prompt, messages)
    return {
        "status": "ok", "agent": agent.get("agent_code"), "model": agent.get("model"),
        "response": result["response"], "usage": result["usage"],
        "latency_ms": result["latency_ms"], "tool_calls": result["tool_calls"],
        "rounds": result["rounds"], "shadow_mode": SHADOW_MODE,
        "system_prompt_length": len(system_prompt),
    }


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

    context = {"conversation_id": req.conversation_id}
    result = await run_agent(oai, agent, system_prompt, messages, context)

    return {
        "status": "ok", "conversation_id": req.conversation_id,
        "interaction_id": req.interaction_id, "response": result["response"],
        "model": agent.get("model"), "latency_ms": result["latency_ms"],
        "tokens": result["usage"].get("total_tokens", 0),
        "tool_calls": result["tool_calls"], "rounds": result["rounds"],
        "shadow_mode": SHADOW_MODE,
        "action": "shadow_logged" if SHADOW_MODE else "would_send",
        "v3_context": bool(person_context), "history_messages": len(messages),
    }


@app.post("/api/v1/shadow-compare")
async def shadow_compare(req: ShadowCompareRequest):
    """Compare v4 response vs Make.com (v3) for a real conversation.
    
    Reads the conversation history, gets the last user message,
    generates v4 response, fetches the existing Make.com response,
    logs the comparison to shadow_log, and returns both side by side.
    """
    if not oai:
        return {"status": "error", "detail": "OPENAI_API_KEY not configured"}
    if not v3_available():
        return {"status": "error", "detail": "V3 CRM not connected"}

    agent = await load_agent("AG-01")
    if not agent:
        return {"status": "error", "detail": "Agent AG-01 not found"}

    # 1. Resolve person
    person_id = await resolve_person_id(req.conversation_id)

    # 2. Get conversation history
    history = await get_conversation_history(req.conversation_id, limit=20)
    if not history:
        return {"status": "error", "detail": f"No messages found for conversation {req.conversation_id}"}

    # Find last user message
    last_user_msg = ""
    for msg in reversed(history):
        if msg["role"] == "user":
            last_user_msg = msg["content"]
            break
    if not last_user_msg:
        return {"status": "error", "detail": "No inbound message found"}

    # 3. Get the existing Make.com (v3) response for this message
    pc = await v3_query("person_conversation", "id", f"id_conversation=eq.{req.conversation_id}")
    sc = await v3_query("system_conversation", "id", f"id_conversation=eq.{req.conversation_id}")
    v3_response = None
    if sc:
        outbound = await v3_query("interactions", "text,time_stamp",
            f"id_system_conversation=eq.{sc[0]['id']}&text=not.is.null&order=time_stamp.desc&limit=1")
        if outbound:
            v3_response = outbound[0]["text"]

    # 4. Generate v4 response
    person_context = await get_person_context(req.conversation_id)
    system_prompt = await build_system_prompt(agent, person_context)
    result = await run_agent(oai, agent, system_prompt, history, {"conversation_id": req.conversation_id})

    # 5. Log to shadow_log in v4 DB
    log_entry = {
        "conversation_id": req.conversation_id,
        "person_id": person_id,
        "user_message": last_user_msg,
        "v3_response": v3_response,
        "v4_response": result["response"],
        "v4_model": agent.get("model"),
        "v4_latency_ms": result["latency_ms"],
        "v4_tokens": result["usage"].get("total_tokens", 0),
        "v4_tool_calls": json.dumps(result["tool_calls"]),
        "v4_rounds": result["rounds"],
        "v4_prompt_length": len(system_prompt),
    }
    await v4_insert("shadow_log", log_entry)

    return {
        "status": "ok",
        "conversation_id": req.conversation_id,
        "user_message": last_user_msg,
        "v3_make_response": v3_response,
        "v4_agent_response": result["response"],
        "v4_metrics": {
            "model": agent.get("model"),
            "latency_ms": result["latency_ms"],
            "tokens": result["usage"].get("total_tokens", 0),
            "tool_calls": result["tool_calls"],
            "rounds": result["rounds"],
        },
        "person_context_loaded": bool(person_context),
        "history_messages": len(history),
    }


@app.get("/api/v1/shadow-log")
async def get_shadow_log(limit: int = 20):
    """View recent shadow mode comparisons."""
    rows = await v4_query("shadow_log",
        "id,conversation_id,user_message,v3_response,v4_response,v4_latency_ms,v4_tokens,v4_tool_calls,v4_rounds,quality_score,quality_notes,created_at",
        f"order=id.desc&limit={limit}")
    return {"count": len(rows), "entries": rows}

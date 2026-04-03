"""IITA Agent Runtime v0.4.0 — FastAPI + OpenAI Tools + Supabase."""
import os
from openai import AsyncOpenAI
from fastapi import FastAPI
from pydantic import BaseModel
from src.agent import load_agent, build_system_prompt, get_person_context, get_conversation_history, run_agent
from src.db import v4_query, v3_available

app = FastAPI(title="IITA Agent Runtime", version="0.4.0")

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


# --- Endpoints ---

@app.get("/health")
def health():
    return {
        "status": "ok", "version": "0.4.0",
        "openai": bool(OPENAI_API_KEY),
        "v3_connected": v3_available(),
        "shadow_mode": SHADOW_MODE,
    }

@app.get("/")
def root():
    return {"service": "iita-agent-runtime", "version": "0.4.0"}

@app.get("/api/v1/db-test")
async def db_test():
    agents = await v4_query("agent_identities", "agent_code,name,role,model")
    settings = await v4_query("system_settings", "key", "tenant_id=eq.1")
    fragments = await v4_query("prompt_fragments", "name", "is_active=eq.true")
    patterns = await v4_query("response_evaluation_patterns", "pattern_text", "is_active=eq.true")
    return {
        "status": "connected", "v3": v3_available(),
        "agents": len(agents), "settings": len(settings),
        "fragments": len(fragments), "patterns": len(patterns),
    }

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
    """Test Ana with a direct message. Supports tool calling.

    Example:
        {"message": "Qué horarios tienen de robótica para un nene de 8 años?"}
    """
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
        "status": "ok",
        "agent": agent.get("agent_code"),
        "model": agent.get("model"),
        "response": result["response"],
        "usage": result["usage"],
        "latency_ms": result["latency_ms"],
        "tool_calls": result["tool_calls"],
        "rounds": result["rounds"],
        "shadow_mode": SHADOW_MODE,
        "system_prompt_length": len(system_prompt),
    }


@app.post("/api/v1/generate-response")
async def generate_response(req: GenerateRequest):
    """Generate AI response for a real v3 CRM conversation.
    
    1. Loads agent config from v4 DB
    2. Gets person context from v3 CRM
    3. Reads conversation history from v3
    4. Calls LLM with tool support
    5. In shadow mode: logs but doesn't send
    """
    if not oai:
        return {"status": "error", "detail": "OPENAI_API_KEY not configured"}

    agent = await load_agent("AG-01")
    if not agent:
        return {"status": "error", "detail": "Agent AG-01 not found"}

    # Get person context from v3
    person_context = await get_person_context(req.conversation_id)

    # Get conversation history from v3
    history = await get_conversation_history(req.conversation_id, limit=20)

    # Build prompt
    system_prompt = await build_system_prompt(agent, person_context)

    # Use history as messages (already in OpenAI format)
    messages = history if history else [{"role": "user", "content": "Hola"}]

    # Run agent with tools
    context = {"conversation_id": req.conversation_id}
    result = await run_agent(oai, agent, system_prompt, messages, context)

    return {
        "status": "ok",
        "conversation_id": req.conversation_id,
        "interaction_id": req.interaction_id,
        "response": result["response"],
        "model": agent.get("model"),
        "latency_ms": result["latency_ms"],
        "tokens": result["usage"].get("total_tokens", 0),
        "tool_calls": result["tool_calls"],
        "rounds": result["rounds"],
        "shadow_mode": SHADOW_MODE,
        "action": "shadow_logged" if SHADOW_MODE else "would_send",
        "v3_context": bool(person_context),
        "history_messages": len(messages),
    }

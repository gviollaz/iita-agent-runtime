"""IITA Agent Runtime v4 — FastAPI + OpenAI + Supabase REST."""
import os
import json
from datetime import datetime
import httpx
from openai import AsyncOpenAI
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="IITA Agent Runtime", version="0.3.0")

# Config from env
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_V3_URL = os.environ.get("SUPABASE_V3_URL", "")
SUPABASE_V3_KEY = os.environ.get("SUPABASE_V3_SERVICE_KEY", os.environ.get("SUPABASE_V3_ANON_KEY", ""))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
SHADOW_MODE = os.environ.get("SHADOW_MODE", "true").lower() == "true"

oai = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# --- Supabase helpers ---

def v4_headers():
    return {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"}

def v3_headers():
    return {"apikey": SUPABASE_V3_KEY, "Authorization": f"Bearer {SUPABASE_V3_KEY}"}

async def v4_query(table: str, select: str, filters: str = ""):
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}"
    if filters:
        url += f"&{filters}"
    async with httpx.AsyncClient() as c:
        r = await c.get(url, headers=v4_headers(), timeout=10)
        return r.json() if r.status_code == 200 else []

async def v3_rpc(function_name: str, params: dict):
    if not SUPABASE_V3_URL or not SUPABASE_V3_KEY:
        return None
    url = f"{SUPABASE_V3_URL}/rest/v1/rpc/{function_name}"
    async with httpx.AsyncClient() as c:
        r = await c.post(url, headers={**v3_headers(), "Content-Type": "application/json"},
                         json=params, timeout=15)
        return r.json() if r.status_code == 200 else None


# --- Agent Core ---

async def load_agent(agent_code: str = "AG-01") -> dict:
    agents = await v4_query("agent_identities",
        "agent_code,name,role,personality,model,temperature,max_tokens,available_tools",
        f"agent_code=eq.{agent_code}")
    return agents[0] if agents else {}

async def build_system_prompt(agent: dict, person_context: str = "") -> str:
    """Build system prompt from agent identity + DB fragments + context."""
    personality = agent.get("personality", {})
    if isinstance(personality, str):
        personality = json.loads(personality)

    name = agent.get("name", "Ana")
    traits = personality.get("traits", [])
    origin = personality.get("origin", "Salta")
    age = personality.get("age", 24)

    # Load anti-hallucination patterns
    patterns = await v4_query("response_evaluation_patterns",
        "pattern_text,description",
        "pattern_type=eq.forbidden_phrase&is_active=eq.true")
    forbidden = "\n".join([f'- NO mencionar "{p["pattern_text"]}" ({p["description"]})' for p in patterns])

    # Load prompt fragments (course catalog, etc.)
    fragments = await v4_query("prompt_fragments",
        "name,content",
        "is_active=eq.true&tenant_id=eq.1&order=sort_order")
    fragments_text = "\n\n".join([f["content"] for f in fragments])

    # Load pricing settings
    settings = await v4_query("system_settings",
        "key,value_text,value_numeric",
        "category=eq.pricing&tenant_id=eq.1")
    pricing_info = ""
    for s in settings:
        if s["key"] == "usd_ars_rate":
            pricing_info += f"Tasa USD/ARS: {int(s['value_numeric'])}\n"
        elif s["key"] == "course_price_usd":
            pricing_info += f"Precio referencial cursos internacionales: ~USD {int(s['value_numeric'])}\n"

    prompt = f"""Sos {name}, tenés {age} años, sos de {origin}.
Sos asesora del IITA (Instituto de Innovación y Tecnología Aplicada) en Salta, Argentina.

Tu personalidad: {', '.join(traits)}.
Usá voseo salteño (vos tenés, vos querés). Mantené respuestas cortas y directas (máximo 3-4 oraciones).
Siempre respondé en español.

Sedes:
- Salta Centro: Buenos Aires 135, Oficina 102, 1er piso
- San Lorenzo Chico: Av. San Martín esquina Los Ceibos

{fragments_text}

{pricing_info}

REGLAS ABSOLUTAS:
{forbidden}
- NO inventes cursos, precios, horarios ni fechas que no tengas confirmados.
- Si no sabés algo, decí "no tengo esa info ahora, pero averiguo y te cuento".
- Cuando alguien pregunte precios, usá SIEMPRE los precios del catálogo de arriba.
"""

    if person_context:
        prompt += f"\n--- CONTEXTO DE LA PERSONA ---\n{person_context}\n"

    return prompt


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
    return {"status": "ok", "version": "0.3.0", "openai": bool(OPENAI_API_KEY), "shadow_mode": SHADOW_MODE}

@app.get("/")
def root():
    return {"service": "iita-agent-runtime", "version": "0.3.0"}

@app.get("/api/v1/db-test")
async def db_test():
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return {"status": "error", "detail": "SUPABASE_URL or SUPABASE_ANON_KEY not set"}
    agents = await v4_query("agent_identities", "agent_code,name,role,model")
    settings = await v4_query("system_settings", "key", "tenant_id=eq.1")
    fragments = await v4_query("prompt_fragments", "name", "is_active=eq.true")
    patterns = await v4_query("response_evaluation_patterns", "pattern_text", "is_active=eq.true")
    return {"status": "connected", "agents": len(agents), "settings": len(settings),
            "fragments": len(fragments), "patterns": len(patterns)}

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
    """Preview the full system prompt that gets sent to the LLM."""
    agent = await load_agent(agent_code)
    if not agent:
        return {"error": f"Agent {agent_code} not found"}
    prompt = await build_system_prompt(agent)
    return {"agent": agent_code, "prompt_length": len(prompt), "prompt": prompt}


@app.post("/api/v1/test-agent")
async def test_agent(req: TestMessage):
    """Test Ana with a direct message. Loads real course data from DB."""
    if not oai:
        return {"status": "error", "detail": "OPENAI_API_KEY not configured"}

    agent = await load_agent(req.agent_code)
    if not agent:
        return {"status": "error", "detail": f"Agent {req.agent_code} not found"}

    system_prompt = await build_system_prompt(agent, req.person_context)

    messages = [{"role": "system", "content": system_prompt}]
    for msg in req.conversation_history:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": req.message})

    model = agent.get("model", "gpt-4o")

    try:
        t0 = datetime.now()
        response = await oai.chat.completions.create(
            model=model,
            messages=messages,
            temperature=float(agent.get("temperature", 0.7)),
            max_tokens=int(agent.get("max_tokens", 500)),
        )
        latency_ms = int((datetime.now() - t0).total_seconds() * 1000)

        reply = response.choices[0].message.content
        usage = response.usage

        return {
            "status": "ok",
            "agent": agent.get("agent_code"),
            "model": model,
            "response": reply,
            "usage": {
                "input_tokens": usage.prompt_tokens,
                "output_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            },
            "latency_ms": latency_ms,
            "shadow_mode": SHADOW_MODE,
            "system_prompt_length": len(system_prompt),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/api/v1/generate-response")
async def generate_response(req: GenerateRequest):
    """Generate AI response for a real conversation from v3 CRM."""
    if not oai:
        return {"status": "error", "detail": "OPENAI_API_KEY not configured"}

    agent = await load_agent("AG-01")
    if not agent:
        return {"status": "error", "detail": "Agent AG-01 not found"}

    person_context = None
    if SUPABASE_V3_URL and SUPABASE_V3_KEY:
        person_context = await v3_rpc("get_person_context_for_ai", {
            "p_person_id": 0,
            "p_conversation_id": req.conversation_id,
        })

    system_prompt = await build_system_prompt(agent, person_context or "")
    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": "Hola"})

    try:
        t0 = datetime.now()
        response = await oai.chat.completions.create(
            model=agent.get("model", "gpt-4o"),
            messages=messages,
            temperature=float(agent.get("temperature", 0.7)),
            max_tokens=int(agent.get("max_tokens", 500)),
        )
        latency_ms = int((datetime.now() - t0).total_seconds() * 1000)
        reply = response.choices[0].message.content

        return {
            "status": "ok",
            "conversation_id": req.conversation_id,
            "interaction_id": req.interaction_id,
            "response": reply,
            "model": agent.get("model"),
            "latency_ms": latency_ms,
            "tokens": response.usage.total_tokens,
            "shadow_mode": SHADOW_MODE,
            "action": "shadow_logged" if SHADOW_MODE else "would_send",
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}

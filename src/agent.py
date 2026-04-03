"""Agent Core — prompt building, LLM call with tool loop."""
import json
from datetime import datetime
from openai import AsyncOpenAI
from src.db import v4_query, v3_rpc, v3_query, v3_available
from src.tools import TOOL_DEFINITIONS, execute_tool


async def load_agent(agent_code: str = "AG-01") -> dict:
    agents = await v4_query("agent_identities",
        "agent_code,name,role,personality,model,temperature,max_tokens,available_tools",
        f"agent_code=eq.{agent_code}")
    return agents[0] if agents else {}


async def build_system_prompt(agent: dict, person_context: str = "") -> str:
    personality = agent.get("personality", {})
    if isinstance(personality, str):
        personality = json.loads(personality)

    name = agent.get("name", "Ana")
    traits = personality.get("traits", [])
    origin = personality.get("origin", "Salta")
    age = personality.get("age", 24)

    patterns = await v4_query("response_evaluation_patterns",
        "pattern_text,description", "pattern_type=eq.forbidden_phrase&is_active=eq.true")
    fragments = await v4_query("prompt_fragments",
        "name,content", "is_active=eq.true&tenant_id=eq.1&order=sort_order")
    settings = await v4_query("system_settings",
        "key,value_text,value_numeric", "category=eq.pricing&tenant_id=eq.1")

    forbidden = "\n".join([f'- NO: "{p["pattern_text"]}" ({p["description"]})' for p in patterns])
    fragments_text = "\n\n".join([f["content"] for f in fragments])
    pricing = ""
    for s in settings:
        if s["key"] == "usd_ars_rate":
            pricing += f"Tasa USD/ARS: {int(s['value_numeric'])}\n"

    prompt = f"""Sos {name}, tenés {age} años, sos de {origin}.
Sos asesora del IITA (Instituto de Innovación y Tecnología Aplicada) en Salta, Argentina.
Tu personalidad: {', '.join(traits)}.
Usá voseo salteño. Respuestas cortas y directas (máximo 3-4 oraciones). Siempre en español.

Sedes: Salta Centro (Buenos Aires 135, Of. 102, 1er piso) | San Lorenzo Chico (Av. San Martín esq. Los Ceibos)

{fragments_text}

{pricing}

REGLAS:
{forbidden}
- NO inventes datos. Si no sabés, decí "voy a consultar y te confirmo".
- Usá SIEMPRE la tool search_courses para consultar horarios y disponibilidad real.
- Usá los precios del catálogo de arriba.
"""
    if person_context:
        prompt += f"\n--- CONTEXTO DE LA PERSONA ---\n{person_context}\n"
    return prompt


async def resolve_person_id(conversation_id: int) -> int:
    if not v3_available():
        return 0
    pc = await v3_query("person_conversation", "id_person", f"id_conversation=eq.{conversation_id}&limit=1")
    return pc[0]["id_person"] if pc else 0


async def get_person_context(conversation_id: int) -> str:
    if not v3_available():
        return ""
    person_id = await resolve_person_id(conversation_id)
    if not person_id:
        return ""
    result = await v3_rpc("get_person_context_for_ai", {
        "p_person_id": person_id,
        "p_conversation_id": conversation_id,
    })
    if result and isinstance(result, str):
        return result
    return ""


async def get_conversation_history(conversation_id: int, limit: int = 20) -> list:
    """Read last N messages from a v3 CRM conversation.
    
    V3 schema: interactions has 'text' (not 'content'), 'time_stamp' (not 'timestamp').
    Direction is inferred: id_person_conversation = inbound, id_system_conversation = outbound.
    """
    if not v3_available():
        return []
    pc = await v3_query("person_conversation", "id", f"id_conversation=eq.{conversation_id}")
    sc = await v3_query("system_conversation", "id", f"id_conversation=eq.{conversation_id}")
    if not pc and not sc:
        return []
    
    pc_id = pc[0]["id"] if pc else -1
    sc_id = sc[0]["id"] if sc else -1
    
    # Query inbound (person → system) messages
    inbound = await v3_query(
        "interactions",
        "id,text,time_stamp,id_person_conversation",
        f"id_person_conversation=eq.{pc_id}&text=not.is.null&order=time_stamp.desc&limit={limit}"
    ) if pc_id > 0 else []
    
    # Query outbound (system → person) messages
    outbound = await v3_query(
        "interactions",
        "id,text,time_stamp,id_system_conversation",
        f"id_system_conversation=eq.{sc_id}&text=not.is.null&order=time_stamp.desc&limit={limit}"
    ) if sc_id > 0 else []
    
    # Merge, tag direction, sort by timestamp
    all_msgs = []
    for ix in inbound:
        if ix.get("text"):
            all_msgs.append({"role": "user", "content": ix["text"], "ts": ix["time_stamp"]})
    for ix in outbound:
        if ix.get("text"):
            all_msgs.append({"role": "assistant", "content": ix["text"], "ts": ix["time_stamp"]})
    
    # Sort chronologically and take last N
    all_msgs.sort(key=lambda x: x["ts"])
    all_msgs = all_msgs[-limit:]
    
    # Remove ts before returning
    return [{"role": m["role"], "content": m["content"]} for m in all_msgs]


async def run_agent(
    oai: AsyncOpenAI,
    agent: dict,
    system_prompt: str,
    messages: list,
    context: dict = None,
    max_tool_rounds: int = 3,
) -> dict:
    context = context or {}
    model = agent.get("model", "gpt-4o")
    temperature = float(agent.get("temperature", 0.7))
    max_tokens = int(agent.get("max_tokens", 500))
    
    all_messages = [{"role": "system", "content": system_prompt}] + messages
    total_tokens = 0
    tool_calls_log = []
    t0 = datetime.now()

    for round_num in range(max_tool_rounds + 1):
        response = await oai.chat.completions.create(
            model=model,
            messages=all_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=TOOL_DEFINITIONS if round_num < max_tool_rounds else None,
        )
        total_tokens += response.usage.total_tokens
        choice = response.choices[0]

        if choice.finish_reason != "tool_calls" or not choice.message.tool_calls:
            latency_ms = int((datetime.now() - t0).total_seconds() * 1000)
            return {
                "response": choice.message.content or "",
                "usage": {
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                    "total_tokens": total_tokens,
                },
                "latency_ms": latency_ms,
                "tool_calls": tool_calls_log,
                "rounds": round_num + 1,
            }

        all_messages.append(choice.message)
        for tc in choice.message.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)
            
            result = await execute_tool(fn_name, fn_args, context)
            tool_calls_log.append({
                "tool": fn_name,
                "args": fn_args,
                "result_length": len(result),
            })
            
            all_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    latency_ms = int((datetime.now() - t0).total_seconds() * 1000)
    return {
        "response": "Lo siento, tuve un problema procesando tu consulta.",
        "usage": {"total_tokens": total_tokens},
        "latency_ms": latency_ms,
        "tool_calls": tool_calls_log,
        "rounds": max_tool_rounds + 1,
        "error": "max_tool_rounds_exceeded",
    }

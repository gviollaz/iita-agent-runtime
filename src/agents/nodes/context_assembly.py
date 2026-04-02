"""Context Assembly — loads person, conversation, directives."""
from src.agents.state import AgentState, PersonContext, ConversationContext, AgentConfig
from src.db import fetch_one, fetch_all


async def context_assembly(state: AgentState) -> dict:
    """Assemble all context for the agent. Replaces get_person_context_for_ai()."""
    interaction = await fetch_one(
        "SELECT i.id, i.text, pc.id_person, pc.id_conversation, sc.id_channel "
        "FROM interactions i "
        "LEFT JOIN person_conversation pc ON pc.id = i.id_person_conversation "
        "LEFT JOIN system_conversation sc ON sc.id_conversation = pc.id_conversation "
        "WHERE i.id = $1",
        state.interaction_id,
    )
    if not interaction:
        return {"error": f"Interaction {state.interaction_id} not found"}

    pid = interaction["id_person"]
    cid = interaction["id_conversation"]
    ch = interaction.get("id_channel", 10)

    ctx = await fetch_one("SELECT get_person_context_for_ai($1, $2) as context", pid, cid)

    msgs = await fetch_all(
        "SELECT i.text, CASE WHEN i.id_person_conversation IS NOT NULL THEN 'in' ELSE 'out' END as dir, "
        "i.time_stamp FROM interactions i "
        "LEFT JOIN person_conversation pc ON pc.id = i.id_person_conversation "
        "LEFT JOIN system_conversation sc ON sc.id = i.id_system_conversation "
        "WHERE COALESCE(pc.id_conversation, sc.id_conversation) = $1 AND i.text IS NOT NULL "
        "ORDER BY i.time_stamp DESC LIMIT 20", cid,
    )

    person = await fetch_one("SELECT id, first_name FROM persons WHERE id = $1", pid)

    return {
        "person": PersonContext(person_id=pid, first_name=person["first_name"] if person else None),
        "conversation": ConversationContext(
            conversation_id=cid, channel_id=ch, channel_provider="whatsapp",
            last_messages=[dict(m) for m in reversed(msgs)],
        ),
        "sales_directives": ctx["context"] if ctx else "",
        "agent_config": AgentConfig(agent_id="AG-01", model="gpt-4o"),
    }

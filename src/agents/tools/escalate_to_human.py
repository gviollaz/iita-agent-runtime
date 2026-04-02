"""Tool: Escalate to human via Slack. Replaces Make scenario 4399426."""
from src.db import execute


async def escalate_to_human(conversation_id: int, person_id: int, reason: str) -> dict:
    await execute("UPDATE conversations SET ai_mode = 'manual' WHERE id = $1", conversation_id)
    # TODO: send Slack webhook notification
    return {"status": "escalated", "conversation_id": conversation_id, "reason": reason}

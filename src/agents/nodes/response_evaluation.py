"""Response Evaluation — quality check before sending."""
from src.agents.state import AgentState


async def response_evaluation(state: AgentState) -> dict:
    """Evaluate response quality. Replaces coherence check in Edge Function."""
    r = state.response_text
    if not r or len(r) < 10:
        return {"evaluation_passed": False, "evaluation_notes": "too_short"}
    if len(r) > 2000:
        return {"evaluation_passed": False, "evaluation_notes": "monologue"}
    return {"evaluation_passed": True, "should_send": not state.shadow_mode}

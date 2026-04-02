"""Agent Reasoning — calls LLM with context and tools."""
from src.agents.state import AgentState


async def agent_reasoning(state: AgentState) -> dict:
    """Call LLM to generate response. Replaces Make.com AI Agent module."""
    # TODO: Fase 1 — implement LLM call
    # 1. Build system prompt from agent_config + sales_directives
    # 2. Build message history
    # 3. Call OpenAI/Claude with tools
    # 4. Handle tool calls loop
    # 5. Return final text
    return {"response_text": "[TODO: agent_reasoning]", "tools_used": []}

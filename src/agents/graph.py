"""LangGraph agent graph: context → reasoning → evaluation."""
from langgraph.graph import StateGraph, END
from src.agents.state import AgentState
from src.agents.nodes.context_assembly import context_assembly
from src.agents.nodes.agent_reasoning import agent_reasoning
from src.agents.nodes.response_evaluation import response_evaluation


def should_send(state: AgentState) -> str:
    if state.error:
        return "error"
    if not state.evaluation_passed:
        return "retry"
    if state.shadow_mode:
        return "log_only"
    return "send"


def build_agent_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("context_assembly", context_assembly)
    graph.add_node("agent_reasoning", agent_reasoning)
    graph.add_node("response_evaluation", response_evaluation)

    graph.set_entry_point("context_assembly")
    graph.add_edge("context_assembly", "agent_reasoning")
    graph.add_edge("agent_reasoning", "response_evaluation")
    graph.add_conditional_edges(
        "response_evaluation", should_send,
        {"send": END, "log_only": END, "retry": "agent_reasoning", "error": END},
    )
    return graph.compile()


agent = build_agent_graph()

"""LangGraph agent state."""
from typing import Annotated
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class PersonContext(BaseModel):
    person_id: int
    first_name: str | None = None
    country: str | None = None
    dialect: str | None = None
    currency: str = "ARS"
    etapa_funnel: str = "sin_clasificar"
    curso_interes: str | None = None


class ConversationContext(BaseModel):
    conversation_id: int
    channel_id: int
    channel_provider: str
    ai_mode: str = "auto"
    last_messages: list[dict] = Field(default_factory=list)


class AgentConfig(BaseModel):
    agent_id: str = "AG-01"
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 500
    system_prompt: str = ""


class AgentState(BaseModel):
    """Full state for the LangGraph agent."""
    interaction_id: int
    inbound_text: str
    inbound_media: dict | None = None

    person: PersonContext | None = None
    conversation: ConversationContext | None = None
    agent_config: AgentConfig = Field(default_factory=AgentConfig)
    sales_directives: str = ""

    response_text: str = ""
    tools_used: list[str] = Field(default_factory=list)

    evaluation_passed: bool = False
    should_send: bool = False
    shadow_mode: bool = True
    error: str | None = None

    messages: Annotated[list, add_messages] = Field(default_factory=list)

# IITA Agent Runtime

**IITA Platform v4** — Agent Runtime: FastAPI + LangGraph

Reemplaza Make.com (39 scenarios) con 5 servicios Python unificados.

## Stack

- **Python 3.12** + FastAPI + LangGraph
- **Supabase** — PostgreSQL, Auth, Storage
- **Railway** — Deployment
- **LangSmith** — Observabilidad
- **OpenAI / Anthropic** — LLM providers

## Setup local

```bash
git clone https://github.com/gviollaz/iita-agent-runtime.git
cd iita-agent-runtime
pip install -e ".[dev]"
cp .env.example .env
uvicorn src.main:app --reload --port 8000
```

## Estructura

```
src/
├── main.py              # FastAPI app
├── config.py            # Settings/env vars
├── db.py                # PostgreSQL connection pool
├── agents/
│   ├── state.py         # LangGraph AgentState
│   ├── graph.py         # Agent graph definition
│   ├── nodes/
│   │   ├── context_assembly.py
│   │   ├── agent_reasoning.py
│   │   └── response_evaluation.py
│   └── tools/
│       ├── search_courses.py
│       └── escalate_to_human.py
├── channels/
│   ├── gateway.py       # Unified webhook handler (Fase 2)
│   └── sender.py        # Unified message sender (Fase 2)
└── media/
    └── processor.py     # Whisper + Vision (Fase 2)
```

## Documentación

Ver `gviollaz/iita-system` → `docs/architecture/platform-v4/`

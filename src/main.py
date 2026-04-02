"""IITA Agent Runtime — FastAPI application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Starting IITA Agent Runtime v{settings.VERSION}")
    print(f"Environment: {settings.ENVIRONMENT} | Shadow: {settings.SHADOW_MODE}")
    yield
    print("Shutting down IITA Agent Runtime")


app = FastAPI(
    title="IITA Agent Runtime",
    description="Platform v4 — LangGraph Agent Runtime",
    version=settings.VERSION,
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "shadow_mode": settings.SHADOW_MODE,
    }


@app.post("/api/v1/generate-response")
async def generate_response(conversation_id: int, interaction_id: int):
    """Generate AI response — replaces Make.com RG scenario."""
    # TODO: Fase 1 — wire up LangGraph agent
    return {"status": "not_implemented", "conversation_id": conversation_id}


@app.post("/api/v1/webhook/meta")
async def meta_webhook():
    """Unified Meta webhook — replaces 7 INPUT scenarios."""
    # TODO: Fase 2
    return {"status": "not_implemented"}

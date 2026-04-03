"""Management API — endpoints for frontend CRUD operations.

Self-registering: import this module after creating the app to add routes.
"""
from pydantic import BaseModel
from src.db import v4_query, v4_update


class FragmentUpdate(BaseModel):
    content: str

class ShadowScore(BaseModel):
    quality_score: int
    quality_notes: str = ""


def register(app):
    """Register management routes on the given FastAPI app."""

    @app.get("/api/v1/prompt-fragments")
    async def list_fragments():
        rows = await v4_query("prompt_fragments",
            "id,name,category,content,sort_order,is_active",
            "tenant_id=eq.1&order=sort_order")
        return {"fragments": rows}

    @app.put("/api/v1/prompt-fragments/{name}")
    async def update_fragment(name: str, body: FragmentUpdate):
        result = await v4_update("prompt_fragments",
            f"name=eq.{name}&tenant_id=eq.1",
            {"content": body.content})
        if result:
            return {"status": "ok", "name": name, "length": len(body.content)}
        return {"status": "error", "detail": f"Fragment '{name}' not found"}

    @app.patch("/api/v1/shadow-log/{entry_id}/score")
    async def score_shadow(entry_id: int, body: ShadowScore):
        if body.quality_score < 1 or body.quality_score > 5:
            return {"status": "error", "detail": "Score must be 1-5"}
        result = await v4_update("shadow_log",
            f"id=eq.{entry_id}",
            {"quality_score": body.quality_score, "quality_notes": body.quality_notes})
        if result:
            return {"status": "ok", "id": entry_id, "score": body.quality_score}
        return {"status": "error", "detail": f"Shadow entry {entry_id} not found"}

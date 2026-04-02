"""Tool: Search courses. Replaces Make scenarios 4409119 + 3614175 + 3794184."""
from src.db import fetch_all


async def search_courses(query: str, modality: str | None = None) -> list[dict]:
    """Search courses by name, group, or modality."""
    results = await fetch_all(
        "SELECT id, name, registration_price, quota_price, curso_group, min_age, max_age "
        "FROM courses WHERE name ILIKE '%' || $1 || '%' OR curso_group ILIKE '%' || $1 || '%' "
        "ORDER BY name LIMIT 10", query,
    )
    return results

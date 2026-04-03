"""IITA Agent Runtime — App factory with all routes registered."""
from src.main import app
from src.management import router as mgmt_router

# Register management routes (prompt editing, shadow scoring)
app.include_router(mgmt_router)

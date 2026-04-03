"""Entry point — imports app and registers all route modules."""
from src.main import app
from src.management import register
register(app)

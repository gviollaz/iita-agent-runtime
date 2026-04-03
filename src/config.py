"""Configuration — loaded from environment."""
import os

class Settings:
    VERSION = "0.4.0"
    ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
    SHADOW_MODE = os.environ.get("SHADOW_MODE", "true").lower() == "true"
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

settings = Settings()

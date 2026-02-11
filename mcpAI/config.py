"""Configuration management for the application.

All configuration is loaded from environment variables with sensible defaults.
"""

import os
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Centralized configuration management."""

    # Security Configuration
    API_KEYS: List[str] = [
        key.strip()
        for key in os.getenv("API_KEYS", "").split(",")
        if key.strip()
    ]
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
    ALLOWED_ORIGINS: List[str] = [
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
        if origin.strip()
    ]
    ALLOWED_URL_PATTERNS: List[str] = [
        pattern.strip()
        for pattern in os.getenv("ALLOWED_URL_PATTERNS", "").split(",")
        if pattern.strip()
    ]

    # Browser Configuration
    HEADLESS_MODE: bool = os.getenv("HEADLESS_MODE", "true").lower() == "true"
    BROWSER_SLOW_MO: int = int(os.getenv("BROWSER_SLOW_MO", "0"))

    # LLM Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # MCP Configuration
    MCP_SSE_URL: str = os.getenv("MCP_SSE_URL", "http://127.0.0.1:4375")

    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Application Configuration
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration values."""
        if not cls.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is required. Set it in your environment or .env file."
            )


# Create a singleton instance
config = Config()

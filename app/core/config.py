"""
Application settings loaded from environment variables.

Uses pydantic-settings to read from .env or environment.
Only settings required for container startup are defined here.
Later tasks will extend this as needed.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_NAME = "ai-ceo-layer1"
SERVICE_VERSION = "0.1.0"


class Settings(BaseSettings):
    """Layer 1 application settings. Values come from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- PostgreSQL ---
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ai_ceo_layer1"
    postgres_user: str = "ai_ceo"
    postgres_password: str = "changeme"
    database_url: str | None = None

    # --- FastAPI ---
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_log_level: str = "INFO"
    # json (one object per line) or text; see app.core.logging.
    log_format: str = "json"
    app_debug: bool = False

    # --- Mock Source ---
    mock_source_base_url: str = "http://mock-source:8080"

    @property
    def effective_database_url(self) -> str:
        """Return the DATABASE_URL if set explicitly, otherwise construct it."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()

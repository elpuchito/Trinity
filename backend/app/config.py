"""
TriageForge — Configuration
Pydantic Settings for environment variable management.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # --- Application ---
    app_name: str = "TriageForge"
    app_version: str = "1.0.0"
    debug: bool = True

    # --- Google Gemini ---
    google_api_key: str = ""

    # --- Database ---
    postgres_user: str = "triageforge"
    postgres_password: str = "triageforge_secret_change_me"
    postgres_db: str = "triageforge"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    database_url: str = ""

    # --- Redis ---
    redis_url: str = "redis://redis:6379/0"

    # --- ChromaDB ---
    chromadb_host: str = "chromadb"
    chromadb_port: int = 8000

    # --- OpenTelemetry ---
    otel_service_name: str = "triageforge-backend"
    otel_exporter_otlp_endpoint: str = "http://otel-collector:4317"

    # --- Frontend ---
    frontend_url: str = "http://localhost:3000"

    # --- Mocked Integrations ---
    linear_api_key: str = "mock-linear-api-key"
    linear_team_id: str = "mock-team-id"
    slack_webhook_url: str = "http://backend:8000/mock/slack/webhook"
    email_smtp_host: str = "backend"
    email_smtp_port: int = 1025
    email_from: str = "triageforge@example.com"

    @property
    def async_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()

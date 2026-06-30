"""Pydantic Settings for environment-driven configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings

# Repo root (.../Code Workspace) holds the gitignored .env. Resolve it absolutely so
# the API loads secrets whether it's launched from api/ or the repo root.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Application configuration from environment variables.

    REDIS_URL: Redis connection string (e.g., redis://localhost:6379).
    DATABASE_URL: Database connection string (e.g., postgresql://...).
    GITHUB_WEBHOOK_SECRET: Webhook HMAC secret.
    GITHUB_APP_ID: GitHub App ID.
    GITHUB_APP_PRIVATE_KEY: GitHub App private key (PEM format).
    DISABLED_ANALYZERS: Comma-separated analyzer IDs to disable (kill-switch).
    """

    redis_url: str = "redis://localhost:6379"
    database_url: str = "sqlite:///./app.db"
    github_webhook_secret: str = ""
    github_app_id: str = ""
    github_app_private_key: str = ""
    github_app_private_key_path: str = ""
    disabled_analyzers: str = ""
    environment: str = "development"
    dashboard_url: str = ""
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    llm_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_model: str = "minimaxai/minimax-m3"
    llm_api_key: str = ""
    # Scan-API protection. API_KEY empty => open (dev/demo); set it to require an
    # X-API-Key header on scan creation. RATE_LIMIT_PER_MINUTE bounds requests per
    # client IP even in open mode (<=0 disables).
    api_key: str = ""
    rate_limit_per_minute: int = 60

    class Config:
        env_file = str(_ENV_FILE)
        case_sensitive = False

    @property
    def disabled_analyzer_ids(self) -> set[str]:
        """Rule IDs (SQG001..SQG007) the kill-switch disables, parsed from the
        comma-separated DISABLED_ANALYZERS env var (case-insensitive)."""
        return {x.strip().upper() for x in self.disabled_analyzers.split(",") if x.strip()}


settings = Settings()

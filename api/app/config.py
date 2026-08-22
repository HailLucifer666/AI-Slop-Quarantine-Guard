"""Pydantic Settings for environment-driven configuration."""

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings
from sqlalchemy.engine import make_url

# Repo root (.../Code Workspace) holds the gitignored .env. Resolve it absolutely so
# the API loads secrets whether it's launched from api/ or the repo root.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# api/ — where app.db has always actually lived. A relative sqlite URL is resolved
# against THIS, not the process CWD (see _resolve_sqlite_path).
_API_ROOT = Path(__file__).resolve().parents[1]


def _resolve_sqlite_path(url_str: str) -> str:
    """Make a relative sqlite path absolute against api/, leaving other URLs alone.

    ``sqlite:///./app.db`` is resolved against the process working directory, so the
    API launched from api/ and a worker launched from the repo root silently read and
    write two DIFFERENT database files — the worker completes scans into one while the
    dashboard reads stale rows from the other. This already happened here: api/app.db
    is the live 660KB database, and a second 0-byte app.db sits at the repo root.

    Parsed with ``make_url`` rather than counting slashes, because an absolute Windows
    path (``sqlite:///C:/db/app.db``) has the same three slashes as a relative POSIX one.
    """
    try:
        url = make_url(url_str)
    except Exception:  # noqa: BLE001 — let create_async_engine raise its own clearer error
        return url_str
    if not url.drivername.startswith("sqlite"):
        return url_str
    database = url.database
    if not database or database == ":memory:" or Path(database).is_absolute():
        return url_str
    return url.set(database=str((_API_ROOT / database).resolve())).render_as_string(hide_password=False)


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
    # Defaults to production so a deploy that forgets ENVIRONMENT fails closed. The
    # secrets check below keys off this field, so defaulting it to "development" made
    # the guard depend on the operator setting the very variable that says this IS
    # production — and a miss meant forgeable webhooks, an open scan API, and
    # local-folder scans, all silently. You opt IN to development (.env.example does).
    environment: str = "production"
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

    @model_validator(mode="after")
    def _anchor_sqlite_to_api_dir(self) -> "Settings":
        """Resolve a relative sqlite path so every launch method uses one database."""
        self.database_url = _resolve_sqlite_path(self.database_url)
        return self

    @model_validator(mode="after")
    def _require_secrets_outside_development(self) -> "Settings":
        """Fail fast rather than silently run wide open outside development.

        An empty GITHUB_WEBHOOK_SECRET makes ``hmac.new(b"", body)`` trivially
        forgeable — any well-formed signature validates, so anyone could forge a
        PR webhook and drive the worker with attacker-chosen data. An empty
        API_KEY leaves scan creation/reads open to anyone. Both are fine in
        development/demo (the default), never outside it.
        """
        if self.environment != "development":
            if not self.github_webhook_secret:
                raise ValueError("GITHUB_WEBHOOK_SECRET must be set outside development")
            if not self.api_key:
                raise ValueError("API_KEY must be set outside development")
        return self


settings = Settings()

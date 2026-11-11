"""Settings: fail fast outside development if the webhook secret or API key is
unset — an empty GITHUB_WEBHOOK_SECRET makes signature verification trivially
forgeable, and an empty API_KEY leaves the scan API wide open."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_development_allows_empty_secrets():
    s = Settings(environment="development", github_webhook_secret="", api_key="")
    assert s.environment == "development"


def test_production_requires_webhook_secret():
    with pytest.raises(ValidationError, match="GITHUB_WEBHOOK_SECRET"):
        Settings(environment="production", github_webhook_secret="", api_key="k")


def test_production_requires_api_key():
    with pytest.raises(ValidationError, match="API_KEY"):
        Settings(environment="production", github_webhook_secret="s", api_key="")


def test_production_with_both_secrets_set_is_valid():
    s = Settings(environment="production", github_webhook_secret="s", api_key="k")
    assert s.environment == "production"


# --- the default itself -------------------------------------------------------
# The guard above only fires when ENVIRONMENT says "not development". Defaulting that
# field to "development" meant the check depended on the operator remembering to set
# the very variable that says this is production. Forgetting it on a deploy gave, all
# at once: forgeable webhooks (hmac.new(b"", body) validates anything), an
# unauthenticated scan API, and POST /api/scans {"source":"local","path":"/"} reading
# arbitrary host directories — with nothing in the logs saying so.


def _clean_env(monkeypatch):
    """Ignore the developer's own .env and shell so the DEFAULT is what's under test."""
    for var in ("ENVIRONMENT", "GITHUB_WEBHOOK_SECRET", "API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_unset_environment_defaults_to_production_and_demands_secrets(monkeypatch):
    _clean_env(monkeypatch)
    with pytest.raises(ValidationError, match="GITHUB_WEBHOOK_SECRET"):
        Settings(_env_file=None)


def test_unset_environment_still_demands_an_api_key(monkeypatch):
    _clean_env(monkeypatch)
    with pytest.raises(ValidationError, match="API_KEY"):
        Settings(_env_file=None, github_webhook_secret="s")


def test_opting_in_to_development_still_runs_open(monkeypatch):
    # The dev affordance is deliberate and must keep working — you now opt IN to it.
    _clean_env(monkeypatch)
    s = Settings(_env_file=None, environment="development")
    assert s.environment == "development"
    assert s.github_webhook_secret == "" and s.api_key == ""

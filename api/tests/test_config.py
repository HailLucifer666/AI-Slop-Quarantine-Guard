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

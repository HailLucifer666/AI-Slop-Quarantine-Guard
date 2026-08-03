"""Test the webhook spine: HMAC verify → dedupe → enqueue → 202.

Redis-backed helpers (already_seen, enqueue_webhook_delivery) are monkeypatched
so the tests run with no live Redis. This proves the handler's control flow.
"""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import settings

SECRET = "test_secret"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def client(monkeypatch):
    """TestClient with a fixed secret and fake (in-memory) queue helpers."""
    monkeypatch.setattr(settings, "github_webhook_secret", SECRET)

    seen: set[str] = set()
    enqueued: list[dict] = []

    async def fake_already_seen(guid: str) -> bool:
        if guid in seen:
            return True
        seen.add(guid)
        return False

    async def fake_enqueue(guid: str, event: str, payload: dict) -> None:
        enqueued.append({"delivery_guid": guid, "event": event, "payload": payload})

    monkeypatch.setattr(main, "already_seen", fake_already_seen)
    monkeypatch.setattr(main, "enqueue_webhook_delivery", fake_enqueue)

    c = TestClient(main.app)
    c.enqueued = enqueued  # expose for assertions
    return c


def _post(client, body: bytes, *, sig: str | None = None, guid: str = "guid-1", event: str = "pull_request"):
    headers = {
        "X-Hub-Signature-256": _sign(body) if sig is None else sig,
        "X-GitHub-Delivery": guid,
        "X-GitHub-Event": event,
    }
    return client.post("/webhooks/github", content=body, headers=headers)


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_valid_event_enqueued_202(client):
    body = json.dumps({"action": "opened", "number": 1}).encode()
    resp = _post(client, body)
    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted"}
    assert len(client.enqueued) == 1
    job = client.enqueued[0]
    assert job["delivery_guid"] == "guid-1"
    assert job["event"] == "pull_request"
    assert job["payload"]["action"] == "opened"


def test_bad_signature_rejected_401(client):
    body = b'{"action": "opened"}'
    resp = _post(client, body, sig="sha256=deadbeef")
    assert resp.status_code == 401
    assert client.enqueued == []


def test_malformed_signature_header_401(client):
    body = b'{"action": "opened"}'
    resp = _post(client, body, sig="garbage_no_equals")
    assert resp.status_code == 401
    assert client.enqueued == []


def test_missing_delivery_guid_400(client):
    body = json.dumps({"action": "opened"}).encode()
    headers = {"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "pull_request"}
    resp = client.post("/webhooks/github", content=body, headers=headers)
    assert resp.status_code == 400
    assert client.enqueued == []


def test_duplicate_delivery_deduped(client):
    body = json.dumps({"action": "opened"}).encode()
    first = _post(client, body, guid="dup-guid")
    second = _post(client, body, guid="dup-guid")
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate"}


def test_malformed_json_body_400_not_500(client):
    # A validly-signed but malformed body must return a clean 400, not an
    # uncaught JSONDecodeError surfacing as a 500.
    body = b"not json at all"
    resp = _post(client, body, guid="malformed-guid")
    assert resp.status_code == 400
    assert client.enqueued == []

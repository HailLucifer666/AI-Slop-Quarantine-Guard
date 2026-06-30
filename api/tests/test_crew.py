"""The Crew (Phase 7): explainer helpers + explain_finding + router.

No live LLM — httpx is faked, and the router's explain_finding is monkeypatched.
"""

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app import crew_router, main
from app.config import settings
from app.crew import explainer

FINDING = {
    "rule_id": "SQG003",
    "category": "placeholder",
    "confidence": "HIGH",
    "file_path": "x.py",
    "line_start": 1,
    "message": "TODO left in code",
}


# ---- pure helpers ----

def test_coerce_flattens_list():
    assert explainer._coerce(["do A", "do B", "   "]) == "1. do A\n2. do B"


def test_coerce_scalar_and_none():
    assert explainer._coerce("just this") == "just this"
    assert explainer._coerce(None) == ""


def test_parse_strips_markdown_fence():
    content = '```json\n{"explanation":"e","why_it_matters":"w","how_to_fix":"h"}\n```'
    assert explainer._parse(content) == {"explanation": "e", "why_it_matters": "w", "how_to_fix": "h"}


def test_parse_coerces_list_how_to_fix():
    content = '{"explanation":"e","why_it_matters":"w","how_to_fix":["a","b"]}'
    assert explainer._parse(content)["how_to_fix"] == "1. a\n2. b"


# ---- explain_finding with a faked httpx transport ----

class _FakeResp:
    def __init__(self, data, exc=None):
        self._data, self._exc = data, exc

    def raise_for_status(self):
        if self._exc:
            raise self._exc

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self, resp=None, post_exc=None):
        self._resp, self._post_exc = resp, post_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        if self._post_exc:
            raise self._post_exc
        return self._resp


@pytest.mark.asyncio
async def test_explain_no_key_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    assert await explainer.explain_finding(FINDING) is None


@pytest.mark.asyncio
async def test_explain_http_error_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "k")
    monkeypatch.setattr(
        explainer.httpx, "AsyncClient", lambda **k: _FakeClient(post_exc=httpx.ConnectError("down"))
    )
    assert await explainer.explain_finding(FINDING) is None


@pytest.mark.asyncio
async def test_explain_bad_shape_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "k")
    monkeypatch.setattr(explainer.httpx, "AsyncClient", lambda **k: _FakeClient(resp=_FakeResp({})))
    assert await explainer.explain_finding(FINDING) is None


@pytest.mark.asyncio
async def test_explain_success_flattens_list(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "k")
    content = '{"explanation":"e","why_it_matters":"w","how_to_fix":["a","b"]}'
    data = {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 10}}
    monkeypatch.setattr(explainer.httpx, "AsyncClient", lambda **k: _FakeClient(resp=_FakeResp(data)))
    out = await explainer.explain_finding(FINDING)
    assert out["explanation"] == "e"
    assert out["how_to_fix"] == "1. a\n2. b"


# ---- POST /api/crew/explain ----

@pytest.mark.asyncio
async def test_route_bad_body_400():
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/crew/explain", content="not json", headers={"content-type": "application/json"}
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_route_missing_rule_id_400():
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/crew/explain", json={"message": "no rule"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_route_503_when_unavailable(monkeypatch):
    async def fake_none(_f):
        return None

    monkeypatch.setattr(crew_router, "explain_finding", fake_none)
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/crew/explain", json=FINDING)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_route_success_200(monkeypatch):
    async def fake_ok(_f):
        return {"explanation": "e", "why_it_matters": "w", "how_to_fix": "h"}

    monkeypatch.setattr(crew_router, "explain_finding", fake_ok)
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/crew/explain", json=FINDING)
    assert resp.status_code == 200
    assert resp.json()["explanation"] == "e"

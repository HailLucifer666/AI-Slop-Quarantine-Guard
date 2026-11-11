"""GitHub client: fetch_file_content, create_check_run, and update_check_run all
retry transient errors rather than giving up (or crashing) on the first blip —
never retries a genuine 404, and returns a safe fallback once retries exhaust."""

import httpx
import pytest

from app import github_client

_RealAsyncClient = httpx.AsyncClient  # captured before any monkeypatching


def _patch_client(monkeypatch, handler):
    def factory(*args, **kwargs):
        return _RealAsyncClient(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(github_client.httpx, "AsyncClient", factory)


async def _noop(*_args):
    return None


@pytest.mark.asyncio
async def test_fetch_file_content_200_returns_text(monkeypatch):
    _patch_client(monkeypatch, lambda req: httpx.Response(200, text="hello"))
    assert await github_client.fetch_file_content("o/r", "a.py", "sha", "tok") == "hello"


@pytest.mark.asyncio
async def test_fetch_file_content_404_returns_none_without_retry(monkeypatch):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(404)

    _patch_client(monkeypatch, handler)
    monkeypatch.setattr(github_client.asyncio, "sleep", _noop)

    assert await github_client.fetch_file_content("o/r", "a.py", "sha", "tok") is None
    assert calls["n"] == 1  # a genuine 404 is not transient — must not retry


@pytest.mark.asyncio
async def test_fetch_file_content_transient_error_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectError("down")
        return httpx.Response(200, text="recovered")

    _patch_client(monkeypatch, handler)
    monkeypatch.setattr(github_client.asyncio, "sleep", _noop)

    assert await github_client.fetch_file_content("o/r", "a.py", "sha", "tok") == "recovered"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_fetch_file_content_5xx_retries_then_gives_up(monkeypatch):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503)

    _patch_client(monkeypatch, handler)
    monkeypatch.setattr(github_client.asyncio, "sleep", _noop)

    assert await github_client.fetch_file_content("o/r", "a.py", "sha", "tok") is None
    assert calls["n"] == 3  # initial attempt + 2 retries, all exhausted


@pytest.mark.asyncio
async def test_create_check_run_transient_error_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(503)
        return httpx.Response(201, json={"id": 42})

    _patch_client(monkeypatch, handler)
    monkeypatch.setattr(github_client.asyncio, "sleep", _noop)

    assert await github_client.create_check_run("o/r", "sha", "tok") == 42
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_create_check_run_exhausted_retries_returns_none(monkeypatch):
    _patch_client(monkeypatch, lambda req: httpx.Response(503))
    monkeypatch.setattr(github_client.asyncio, "sleep", _noop)
    assert await github_client.create_check_run("o/r", "sha", "tok") is None


@pytest.mark.asyncio
async def test_update_check_run_transient_error_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectError("down")
        return httpx.Response(200)

    _patch_client(monkeypatch, handler)
    monkeypatch.setattr(github_client.asyncio, "sleep", _noop)

    ok = await github_client.update_check_run("o/r", 42, "success", "all clear", "tok")
    assert ok is True
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_update_check_run_exhausted_retries_returns_false(monkeypatch):
    _patch_client(monkeypatch, lambda req: httpx.Response(503))
    monkeypatch.setattr(github_client.asyncio, "sleep", _noop)
    ok = await github_client.update_check_run("o/r", 42, "success", "all clear", "tok")
    assert ok is False

"""Test registry existence clients: 200->EXISTS, 404->MISSING, errors->UNKNOWN."""

import httpx
import pytest

from app import registries
from app.registries import Existence, check_exists, normalize_pypi


def test_normalize_pypi():
    assert normalize_pypi("Foo.Bar_Baz") == "foo-bar-baz"
    assert normalize_pypi("requests") == "requests"


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_exists_200():
    async with _client(lambda req: httpx.Response(200)) as c:
        assert await check_exists("pypi", "requests", c) is Existence.EXISTS


@pytest.mark.asyncio
async def test_missing_404():
    async with _client(lambda req: httpx.Response(404)) as c:
        assert await check_exists("npm", "totally-fake-pkg", c) is Existence.MISSING


@pytest.mark.asyncio
async def test_transport_error_is_unknown(monkeypatch):
    monkeypatch.setattr(registries.asyncio, "sleep", lambda *_: _noop())

    def boom(req):
        raise httpx.ConnectError("down")

    async with _client(boom) as c:
        assert await check_exists("crates", "serde", c) is Existence.UNKNOWN


@pytest.mark.asyncio
async def test_server_error_retries_then_unknown(monkeypatch):
    monkeypatch.setattr(registries.asyncio, "sleep", lambda *_: _noop())
    async with _client(lambda req: httpx.Response(503)) as c:
        assert await check_exists("pypi", "flaky", c) is Existence.UNKNOWN


@pytest.mark.asyncio
async def test_scoped_npm_name_encoded():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        return httpx.Response(200)

    async with _client(handler) as c:
        await check_exists("npm", "@scope/pkg", c)
    assert "%2F" in seen["url"]


async def _noop():
    return None

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


# --- first-release parsing (SQG007 established-package gate, ADR-025) --------

def test_parse_iso_normalizes_offsetless_pypi_timestamp():
    # PyPI upload_time carries no offset; a NAIVE datetime reaching the gate's
    # aware subtraction raises TypeError (2026-11-13 probe) — the parser must
    # attach UTC so the shape PyPI actually serves can never crash the analyzer.
    dt = registries._parse_iso("2018-04-27T09:43:02")
    assert dt is not None and dt.tzinfo is not None and dt.year == 2018


def test_parse_iso_handles_z_offset_and_garbage():
    assert registries._parse_iso("2010-12-29T19:38:25.450Z").tzinfo is not None
    assert registries._parse_iso("2015-01-01T00:00:00+00:00").tzinfo is not None
    assert registries._parse_iso("not a date") is None
    assert registries._parse_iso(None) is None
    assert registries._parse_iso("") is None


@pytest.mark.asyncio
async def test_created_at_pypi_takes_earliest_release():
    body = {"releases": {
        "0.2": [{"upload_time": "2020-05-05T10:00:00"}],
        "0.1": [{"upload_time": "2018-04-27T09:43:02"}],
    }}
    async with _client(lambda req: httpx.Response(200, json=body)) as c:
        dt = await registries.registry_created_at("pypi", "bleak", c)
    assert dt is not None and dt.year == 2018 and dt.tzinfo is not None


@pytest.mark.asyncio
async def test_created_at_npm_packument_created():
    body = {"time": {"created": "2010-12-29T19:38:25.450Z"}}
    async with _client(lambda req: httpx.Response(200, json=body)) as c:
        dt = await registries.registry_created_at("npm", "express", c)
    assert dt is not None and dt.year == 2010


@pytest.mark.asyncio
async def test_created_at_missing_releases_field_is_none():
    # PyPI has deprecated the project-level `releases` key; its absence must
    # yield None (age unknown → keep the finding), never a guess or a crash.
    async with _client(lambda req: httpx.Response(200, json={"info": {}})) as c:
        assert await registries.registry_created_at("pypi", "futurepkg", c) is None


@pytest.mark.asyncio
async def test_created_at_404_is_none():
    async with _client(lambda req: httpx.Response(404)) as c:
        assert await registries.registry_created_at("pypi", "never-published", c) is None


@pytest.mark.asyncio
async def test_created_at_outage_is_none(monkeypatch):
    monkeypatch.setattr(registries.asyncio, "sleep", lambda *_: _noop())

    def boom(req):
        raise httpx.ConnectError("down")

    async with _client(boom) as c:
        assert await registries.registry_created_at("pypi", "anything", c) is None

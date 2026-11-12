"""Live package-registry existence clients (Phase 3, SQG001).

One job: answer "does this package exist in its registry?" with three outcomes —
EXISTS, MISSING (clean 404), or UNKNOWN (registry unreachable/timeout/429 after
retries). The analyzer maps MISSING → CERTAIN block, UNKNOWN → HIGH advisory.
Never block on UNKNOWN: a registry outage must not fail a PR.
"""

import asyncio
import re
from datetime import datetime
from enum import Enum
from typing import Optional

import httpx

_USER_AGENT = "ai-slop-quarantine-guard (registry existence check)"
_TIMEOUT = 8.0
_RETRIES = 2


class Existence(str, Enum):
    EXISTS = "EXISTS"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


def normalize_pypi(name: str) -> str:
    """PEP 503 normalization: lowercase, runs of -_. collapsed to a single dash."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _registry_url(ecosystem: str, name: str) -> Optional[str]:
    if ecosystem == "pypi":
        return f"https://pypi.org/pypi/{normalize_pypi(name)}/json"
    if ecosystem == "npm":
        # Scoped names (@org/name) must have the slash percent-encoded.
        return f"https://registry.npmjs.org/{name.replace('/', '%2F')}"
    if ecosystem == "crates":
        return f"https://crates.io/api/v1/crates/{name}"
    return None


async def check_exists(
    ecosystem: str, name: str, client: httpx.AsyncClient
) -> Existence:
    """Query the ecosystem's registry for a package name.

    200 → EXISTS, 404 → MISSING. Any transport error, 429, or 5xx is retried
    with backoff and downgraded to UNKNOWN if it never resolves cleanly.
    """
    url = _registry_url(ecosystem, name)
    if url is None:
        return Existence.UNKNOWN

    for attempt in range(_RETRIES + 1):
        try:
            resp = await client.get(
                url, headers={"User-Agent": _USER_AGENT}, follow_redirects=True
            )
        except httpx.HTTPError:
            await asyncio.sleep(0.5 * (attempt + 1))
            continue
        if resp.status_code == 200:
            return Existence.EXISTS
        if resp.status_code == 404:
            return Existence.MISSING
        # 429 / 5xx / unexpected → transient; back off and retry.
        await asyncio.sleep(0.5 * (attempt + 1))

    return Existence.UNKNOWN


def _parse_iso(value) -> Optional[datetime]:
    """Parse an ISO-8601 registry timestamp, or None. Registries disagree on format
    (PyPI drops the offset, npm suffixes Z, crates carries a numeric offset); fromisoformat
    plus a Z→+00:00 swap covers all three without a dateutil dependency."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


async def registry_created_at(
    ecosystem: str, name: str, client: httpx.AsyncClient
) -> Optional[datetime]:
    """First-release timestamp for a package name, from the SAME registry bodies the
    existence check already downloads (full PyPI JSON / full npm packument / crates
    doc) — no new endpoint, no extra round trip beyond this call's own.

    Returns None when the registry is unreachable, the name is unknown (404), or the
    body lacks the field — note PyPI has announced deprecating the project-level
    ``releases`` key, so its absence is an expected future shape, not an error.
    Callers MUST treat None as "age unknown" and keep any finding: age data going
    quietly missing must never turn suppression on (ADR-025).

    npm note: this relies on the FULL packument, which is what this client fetches
    (no ``Accept: application/vnd.npm.install-v1+json`` header is sent anywhere in
    this module — the abbreviated install format drops ``time.created``). If that
    header is ever added for bandwidth, this parser breaks loudly in the corpus
    contract test, not silently.
    """
    url = _registry_url(ecosystem, name)
    if url is None:
        return None

    for attempt in range(_RETRIES + 1):
        try:
            resp = await client.get(
                url, headers={"User-Agent": _USER_AGENT}, follow_redirects=True
            )
        except httpx.HTTPError:
            await asyncio.sleep(0.5 * (attempt + 1))
            continue
        if resp.status_code == 404:
            return None  # never published — "how old?" is meaningless; caller keeps any finding
        if resp.status_code != 200:
            await asyncio.sleep(0.5 * (attempt + 1))  # 429 / 5xx → transient, retry
            continue
        try:
            body = resp.json()
        except ValueError:
            return None
        if ecosystem == "pypi":
            releases = body.get("releases") if isinstance(body, dict) else None
            times: list[datetime] = []
            if isinstance(releases, dict):
                for files_ in releases.values():
                    if isinstance(files_, list):
                        for file_ in files_:
                            parsed = _parse_iso(file_.get("upload_time")) if isinstance(file_, dict) else None
                            if parsed is not None:
                                times.append(parsed)
            return min(times) if times else None
        if ecosystem == "npm":
            time_block = body.get("time") if isinstance(body, dict) else None
            return _parse_iso(time_block.get("created")) if isinstance(time_block, dict) else None
        if ecosystem == "crates":
            crate = body.get("crate") if isinstance(body, dict) else None
            return _parse_iso(crate.get("created_at")) if isinstance(crate, dict) else None
        return None
    return None

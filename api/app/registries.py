"""Live package-registry existence clients (Phase 3, SQG001).

One job: answer "does this package exist in its registry?" with three outcomes —
EXISTS, MISSING (clean 404), or UNKNOWN (registry unreachable/timeout/429 after
retries). The analyzer maps MISSING → CERTAIN block, UNKNOWN → HIGH advisory.
Never block on UNKNOWN: a registry outage must not fail a PR.
"""

import asyncio
import re
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

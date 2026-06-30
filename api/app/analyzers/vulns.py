"""SQG004 — known-vulnerable dependency detector (Phase 3, OSV.dev API).

Asks OSV.dev "is this exact pinned version known-vulnerable?" for dependencies
the PR introduces. No Trivy binary, no Docker — one HTTP client, same shape as
the SQG001 registry checks.

Hard rules (product constraints):
* Advisory only. A CVE's *presence* is not proof of *exploitability*, so a
  vulnerability finding is always HIGH / never block-eligible.
* Fail-safe. OSV unreachable / timeout / 429 → return None → the dep is silently
  skipped. A vuln-feed outage must never fail a PR.

Scope (MVP): only *exactly pinned* versions are checkable —
* pip ``name==1.2.3`` (requirements.txt)
* npm exact semver values (package.json)
Range/caret specs (``^1.2``, ``>=1.0``, Cargo bare versions, pyproject ranges)
need a real resolver to know the installed version; querying the declared spec
would be misleading, so they are skipped. Resolver + crates/pyproject → backlog.

Like SQG001, only versions appearing on *added* lines are queried — the PR is
judged on what it introduced, not what was already there.
"""

import asyncio
import logging
import re
from typing import Callable, Dict, List, Optional, Tuple

import httpx

from app.diff import parse_diff
from app.manifests import (
    extract_pinned_lockfile,
    lockfile_ecosystem,
    manifest_ecosystem,
    parse_package_json,
)

from .base import Confidence, Evidence, Finding

logger = logging.getLogger("analyzers.vulns")

RULE_ID = "SQG004"

_OSV_URL = "https://api.osv.dev/v1/query"
_OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
# Our ecosystem key → OSV ecosystem name. Manifests pin only pypi/npm exactly;
# lockfiles add crates.io + Go (fully resolved, exact versions — see manifests.py).
_OSV_ECOSYSTEM = {"pypi": "PyPI", "npm": "npm", "crates": "crates.io", "go": "Go"}
_TIMEOUT = 8.0
_RETRIES = 2
_BATCH_SIZE = 1000   # OSV /v1/querybatch accepts up to 1000 queries per request
_MAX_PINS = 2000     # safety cap on unique deps queried per scan (logged if exceeded)

# A (ecosystem, name, version) dependency pin.
Pin = Tuple[str, str, str]

# pip exact pin: name == version (ignores ~=, >=, extras, markers).
_PIP_PIN = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([A-Za-z0-9][A-Za-z0-9.\-+]*)\s*$"
)
# A bare, exact semver — no range operators, no wildcard, no "latest".
_EXACT_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")


async def query_osv(
    ecosystem: str, name: str, version: str, client: httpx.AsyncClient
) -> Optional[list]:
    """Query OSV.dev for vulns affecting an exact version.

    Returns the (possibly empty) list of vuln records, or None if OSV could not
    be reached after retries — callers treat None as "skip silently".
    """
    osv_eco = _OSV_ECOSYSTEM.get(ecosystem)
    if osv_eco is None:
        return None
    body = {"package": {"name": name, "ecosystem": osv_eco}, "version": version}
    for attempt in range(_RETRIES + 1):
        try:
            resp = await client.post(_OSV_URL, json=body)
        except httpx.HTTPError:
            await asyncio.sleep(0.5 * (attempt + 1))
            continue
        if resp.status_code == 200:
            return resp.json().get("vulns", []) or []
        # 429 / 5xx / unexpected → transient; back off and retry.
        await asyncio.sleep(0.5 * (attempt + 1))
    return None


async def _post_batch(queries: list, client: httpx.AsyncClient) -> Optional[list]:
    """POST one chunk to OSV /v1/querybatch; return the index-aligned results list or None."""
    for attempt in range(_RETRIES + 1):
        try:
            resp = await client.post(_OSV_BATCH_URL, json={"queries": queries})
        except httpx.HTTPError:
            await asyncio.sleep(0.5 * (attempt + 1))
            continue
        if resp.status_code == 200:
            return resp.json().get("results", [])
        await asyncio.sleep(0.5 * (attempt + 1))
    return None


async def query_osv_batch(pins: List[Pin], client: httpx.AsyncClient) -> Dict[Pin, Optional[list]]:
    """Resolve many pins in one shot via OSV's batch endpoint.

    Returns ``{pin: vulns}`` where vulns is the (possibly empty) advisory list, or
    ``None`` when OSV couldn't be reached for that pin — callers treat ``None`` as
    "skip silently" (fail-safe; a feed outage never produces or blocks a finding).
    """
    results: Dict[Pin, Optional[list]] = {}
    # Pins in an ecosystem OSV doesn't know are unanswerable → None (skipped).
    queryable = [p for p in pins if p[0] in _OSV_ECOSYSTEM]
    for p in pins:
        if p[0] not in _OSV_ECOSYSTEM:
            results[p] = None

    for i in range(0, len(queryable), _BATCH_SIZE):
        chunk = queryable[i : i + _BATCH_SIZE]
        body = [
            {"package": {"name": name, "ecosystem": _OSV_ECOSYSTEM[eco]}, "version": version}
            for eco, name, version in chunk
        ]
        data = await _post_batch(body, client)
        if data is None or len(data) != len(chunk):
            for p in chunk:
                results[p] = None  # whole chunk unresolved → fail-safe skip
            continue
        for p, entry in zip(chunk, data):
            results[p] = (entry.get("vulns") or []) if isinstance(entry, dict) else []
    return results


def _pinned_deps(filename: str, content: str) -> List[Tuple[str, str, str]]:
    """Return (ecosystem, name, version) for every exactly-pinned dependency."""
    base = filename.rsplit("/", 1)[-1]
    if base == "requirements.txt":
        pins: List[Tuple[str, str, str]] = []
        for raw in content.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            m = _PIP_PIN.match(line)
            if m:
                pins.append(("pypi", m.group(1), m.group(2)))
        return pins
    if base == "package.json":
        return [
            ("npm", name, version.strip())
            for name, version in parse_package_json(content).items()
            if _EXACT_SEMVER.match(version.strip())
        ]
    return []


def _find_line(name: str, version: str, added: List[Tuple[int, str]]) -> Optional[int]:
    """First added line that mentions this pinned dependency, else None."""
    for line_no, text in added:
        if name in text and version in text:
            return line_no
    return None


def _find_lock_line(name: str, version: str, added: List[Tuple[int, str]]) -> Optional[int]:
    """Locate a lockfile pin in the added lines.

    Unlike a manifest, a lockfile puts the name and the resolved version on
    *separate* lines (e.g. poetry.lock / package-lock.json), so we require the
    name to appear somewhere in the added block and report the version's line.
    The (name, version) pair itself comes from an authoritative parse, so the
    finding is real even though the reported line is approximate.
    """
    if not any(name in text for _, text in added):
        return None
    for line_no, text in added:
        if version in text:
            return line_no
    return None


def _vuln_finding(
    name: str, version: str, vulns: list, path: str, line: int
) -> Finding:
    ids = [v.get("id", "?") for v in vulns]
    shown = ", ".join(ids[:3]) + ("…" if len(ids) > 3 else "")
    first = ids[0] if ids else ""
    return Finding(
        category="vulnerability",
        confidence=Confidence.HIGH,
        block_eligible=False,
        file_path=path,
        line_start=line,
        line_end=line,
        message=f"{name}=={version} has {len(vulns)} known advisory(ies): {shown}",
        evidence=Evidence(snippet=f"{name}=={version}"),
        tool="osv",
        rule_id=RULE_ID,
        fix_suggestion=(
            f"Upgrade to a patched release; see https://osv.dev/vulnerability/{first}"
            if first
            else "Upgrade to a patched release."
        ),
    )


def _default_fetch(repo: str, path: str, ref: str, token: str):
    from app.github_client import fetch_file_content

    return fetch_file_content(repo, path, ref, token)


async def check_vulnerabilities(
    diff: str,
    repo_context: dict,
    *,
    fetch_file: Optional[Callable] = None,
    query_batch: Callable = query_osv_batch,
) -> List[Finding]:
    """Flag PR-introduced dependencies pinned to known-vulnerable versions (advisory).

    Every pin found on an added line is collected, deduped to a unique set, and
    resolved in ONE batched OSV call (``query_batch``) — so a 1000-package lockfile
    costs one request, not a thousand serial ones. A finding is emitted per location
    whose pin has advisories. Fail-safe throughout: an unresolved pin (``None``) is
    skipped silently, never a finding, never a block.
    """
    fetch_file = fetch_file or _default_fetch
    repo = repo_context.get("repo")
    head_sha = repo_context.get("head_sha")
    token = repo_context.get("token")

    added_by_file: dict[str, List[Tuple[int, str]]] = {}
    for path, line, content in parse_diff(diff):
        added_by_file.setdefault(path, []).append((line, content))

    # Collect every (path, line, pin) occurrence introduced on an added line.
    occurrences: List[Tuple[str, int, Pin]] = []
    async with httpx.AsyncClient(timeout=10) as client:
        for path, added in added_by_file.items():
            lock_eco = lockfile_ecosystem(path)
            is_lock = lock_eco in _OSV_ECOSYSTEM
            if not is_lock and manifest_ecosystem(path) not in _OSV_ECOSYSTEM:
                continue
            content = await fetch_file(repo, path, head_sha, token)
            if content is None:
                continue  # unfetchable manifest → silent (protects zero-FP)

            if is_lock:
                # Lockfile: the fully resolved tree, all pinned exactly.
                pins = [(lock_eco, n, v) for n, v in extract_pinned_lockfile(path, content)]
                locate = _find_lock_line
            else:
                pins = _pinned_deps(path, content)
                locate = _find_line

            for dep_eco, name, version in pins:
                line = locate(name, version, added)
                if line is None:
                    continue  # pin wasn't introduced by this PR
                occurrences.append((path, line, (dep_eco, name, version)))

        # Dedupe to unique pins (lockfiles repeat heavily); cap + log so a giant tree
        # can never silently drop coverage or stall the scan.
        keys = sorted({pin for _p, _l, pin in occurrences})
        if len(keys) > _MAX_PINS:
            logger.warning(
                "SQG004: %d unique deps exceed cap %d — scanning first %d, %d skipped",
                len(keys), _MAX_PINS, _MAX_PINS, len(keys) - _MAX_PINS,
            )
            keys = keys[:_MAX_PINS]
        results = await query_batch(keys, client) if keys else {}

    queried = set(keys)
    findings: List[Finding] = []
    for path, line, pin in occurrences:
        if pin not in queried:
            continue  # dropped by the cap
        vulns = results.get(pin)
        if vulns:  # non-empty list; None (outage) or [] (clean) → no finding
            _eco, name, version = pin
            findings.append(_vuln_finding(name, version, vulns, path, line))
    return findings

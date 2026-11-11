"""SQG004 — known-vulnerable dependency detector (Phase 3, OSV.dev API).

Asks OSV.dev "is this exact pinned version known-vulnerable?" for dependencies
the PR introduces. No Trivy binary, no Docker — one HTTP client, same shape as
the SQG001 registry checks.

Hard rules (product constraints):
* Advisory only. A CVE's *presence* is not proof of *exploitability*, so a
  vulnerability finding is always HIGH / never block-eligible.
* Fail-safe. OSV unreachable / timeout / 429 → return None → the dep is silently
  skipped. A vuln-feed outage must never fail a PR.

Scope: only *exactly pinned* versions are checkable. Those come from
* pip ``name==1.2.3`` (requirements.txt) and npm exact semver (package.json);
* every supported lockfile, which pins the whole resolved tree (manifests.py);
* the Go / Maven / NuGet manifests parsed by ``app.pinned``, which carry literal
  versions of their own.
Range/caret specs (``^1.2``, ``>=1.0``, Cargo bare versions, pyproject ranges) and
unresolvable references (a Gradle version catalog, an inherited Maven property)
need a resolver to know the installed version; querying the declared spec would be
misleading, so they are skipped — and counted, so coverage reports the file as
partially read rather than fully checked.

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
    parse_pins,
    versioned_manifest_ecosystem,
)

from .base import (
    REMEDIATION_GUIDANCE,
    REMEDIATION_PATCH,
    Advisory,
    Confidence,
    Evidence,
    Finding,
    Remediation,
)

logger = logging.getLogger("analyzers.vulns")

RULE_ID = "SQG004"

_OSV_URL = "https://api.osv.dev/v1/query"
_OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
# Our ecosystem key → OSV ecosystem name. Manifests pin only pypi/npm exactly;
# lockfiles add crates.io + Go (fully resolved, exact versions — see manifests.py).
_OSV_ECOSYSTEM = {
    "pypi": "PyPI", "npm": "npm", "crates": "crates.io", "go": "Go",
    # Added once app.pinned could read exact versions out of these ecosystems'
    # manifests and lockfiles. Names must use OSV's spelling for the ecosystem —
    # "groupId:artifactId" for Maven, "vendor/package" for Packagist — or the query
    # silently returns "no known vulnerabilities" for a package that has plenty.
    "maven": "Maven", "rubygems": "RubyGems", "packagist": "Packagist", "nuget": "NuGet",
}
_TIMEOUT = 8.0
_RETRIES = 2
_BATCH_SIZE = 1000   # OSV /v1/querybatch accepts up to 1000 queries per request
_MAX_PINS = 2000     # safety cap on unique deps queried per scan (logged if exceeded)

# A (ecosystem, name, version) dependency pin.
Pin = Tuple[str, str, str]

# pip exact pin: name == version (ignores ~=, >=, extras). Allows the specific
# trailing shapes pip itself supports on an exact pin — an environment marker
# (`; python_version>="3.8"`) and/or one or more `--hash=` flags (hash-pinned
# requirements — the security-conscious style — used to be invisible here since
# the fully-anchored `$` rejected any trailing content at all. NOT a bare
# unanchored match: "package==1.2.*" must still be rejected as a range, not an
# exact pin, so only these specific trailing shapes are permitted.
_PIP_PIN = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([A-Za-z0-9][A-Za-z0-9.\-+]*)"
    r"\s*(?:;[^#]*)?"
    r"(?:\s+--hash=\S+)*"
    r"\s*\\?\s*$"
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


def _find_versioned_line(name: str, version: str, added: List[Tuple[int, str]]) -> Optional[int]:
    """Locate a pin from a Go / Maven / NuGet manifest in the added lines.

    These formats vary in layout: go.mod, Gradle and .csproj put the coordinate and its
    version on one line, while a Maven POM spreads groupId, artifactId and version over
    three. So try the whole coordinate on one line first, then the artifact name alone,
    and only then report the line the version sits on. The (name, version) pair itself
    came from an authoritative parse, so the finding is real even when the reported line
    is the version's rather than the declaration's.
    """
    same_line = next((ln for ln, text in added if name in text and version in text), None)
    if same_line is not None:
        return same_line

    # Last path/coordinate segment: "org.foo:bar" → "bar", "github.com/pkg/errors" → "errors".
    token = name.rsplit(":", 1)[-1].rsplit("/", 1)[-1]
    same_line = next((ln for ln, text in added if token in text and version in text), None)
    if same_line is not None:
        return same_line
    if not any(token in text for _, text in added):
        return None
    return next((ln for ln, text in added if version in text), None)


def _fixed_versions(vulns: list) -> List[str]:
    """Versions OSV names as the first patched release, in the order encountered.

    Read strictly from OSV's ``affected[].ranges[].events[].fixed`` — the only place a
    fixed version is authoritative. If OSV doesn't say, we don't either: no upper-bound
    guessing, no "probably the next minor".
    """
    fixed: List[str] = []
    for vuln in vulns:
        for affected in vuln.get("affected") or []:
            for rng in affected.get("ranges") or []:
                for event in rng.get("events") or []:
                    value = event.get("fixed")
                    if value and value not in fixed:
                        fixed.append(value)
    return fixed


def _severity_of(vulns: list) -> Optional[str]:
    """Highest severity OSV reports, or None when OSV reports none.

    Never computed from the advisory count or our own judgement — an absent severity is
    reported as absent so nobody mistakes silence for "low".
    """
    ranking = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2, "MEDIUM": 2, "LOW": 3}
    best: Optional[str] = None
    for vuln in vulns:
        label = (vuln.get("database_specific") or {}).get("severity")
        if not isinstance(label, str):
            continue
        label = label.upper()
        if label not in ranking:
            continue
        if best is None or ranking[label] < ranking[best]:
            best = label
    return best.lower() if best else None


def _replacement_line(snippet: str, name: str, version: str, fixed: str) -> Optional[str]:
    """The manifest line rewritten to the patched version, or None if not derivable.

    Only a literal substitution of the version token inside the original line. If the
    version string doesn't appear verbatim (lockfile layouts spread name and version
    across lines), there is no honest one-line patch and we return None rather than
    constructing a line the file never had.
    """
    if not snippet or version not in snippet:
        return None
    if name not in snippet:
        return None
    return snippet.replace(version, fixed, 1)


def _vuln_finding(
    name: str, version: str, vulns: list, path: str, line: int, snippet: Optional[str] = None
) -> Finding:
    ids = [v.get("id", "?") for v in vulns]
    shown = ", ".join(ids[:3]) + ("…" if len(ids) > 3 else "")
    evidence_snippet = snippet.strip() if snippet else f"{name}=={version}"

    advisories = [
        Advisory(id=vuln_id, url=f"https://osv.dev/vulnerability/{vuln_id}")
        for vuln_id in ids if vuln_id and vuln_id != "?"
    ]
    fixed = _fixed_versions(vulns)
    # CVE aliases carried by GHSA entries, so a reader searching by CVE finds it.
    cve_ids = sorted({
        alias for vuln in vulns for alias in (vuln.get("aliases") or [])
        if isinstance(alias, str) and alias.startswith("CVE-")
    })
    for cve in cve_ids:
        if all(a.id != cve for a in advisories):
            advisories.append(Advisory(id=cve, url=f"https://nvd.nist.gov/vuln/detail/{cve}"))

    remediation: Optional[Remediation] = None
    if fixed:
        replacement = _replacement_line(evidence_snippet, name, version, fixed[0])
        if replacement:
            # A concrete, checkable rewrite: OSV named the version, and we only swapped
            # that token in the line that is already there.
            remediation = Remediation(
                kind=REMEDIATION_PATCH,
                text=f"Upgrade {name} to {fixed[0]}.",
                suggested_replacement=replacement,
                basis=f"OSV lists {fixed[0]} as a patched release for {ids[0] if ids else 'this advisory'}",
            )
        else:
            remediation = Remediation(
                kind=REMEDIATION_GUIDANCE,
                text=f"Upgrade {name} to {fixed[0]} or later.",
                basis="OSV names a patched version, but this file's layout has no single "
                      "line to rewrite (lockfiles record the version separately)",
            )
    else:
        remediation = Remediation(
            kind=REMEDIATION_GUIDANCE,
            text="Check the advisory for a patched release.",
            basis="OSV does not name a fixed version for this advisory",
        )

    return Finding(
        category="vulnerability",
        confidence=Confidence.HIGH,
        block_eligible=False,
        file_path=path,
        line_start=line,
        line_end=line,
        message=f"{name}=={version} has {len(vulns)} known advisory(ies): {shown}",
        evidence=Evidence(snippet=evidence_snippet),
        tool="osv",
        rule_id=RULE_ID,
        advisories=advisories,
        severity=_severity_of(vulns),
        fix_versions=fixed,
        remediation=remediation,
        fix_suggestion=remediation.text if remediation else None,
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
            versioned_eco = versioned_manifest_ecosystem(path)
            is_versioned = not is_lock and versioned_eco in _OSV_ECOSYSTEM
            if not is_lock and not is_versioned and manifest_ecosystem(path) not in _OSV_ECOSYSTEM:
                continue
            content = await fetch_file(repo, path, head_sha, token)
            if content is None:
                continue  # unfetchable manifest → silent (protects zero-FP)

            if is_lock:
                # Lockfile: the fully resolved tree, all pinned exactly.
                pins = [(lock_eco, n, v) for n, v in extract_pinned_lockfile(path, content)]
                locate = _find_lock_line
            elif is_versioned:
                # go.mod / pom.xml / build.gradle / *.csproj — literal versions only;
                # whatever the parser could not resolve is simply absent here.
                pins = [(versioned_eco, n, v) for n, v in parse_pins(path, content).pins]
                locate = _find_versioned_line
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
            # The real added line, so a suggested upgrade rewrites what is actually
            # in the file rather than a reconstruction of it.
            snippet = next(
                (text for ln, text in added_by_file.get(path, []) if ln == line), None
            )
            findings.append(_vuln_finding(name, version, vulns, path, line, snippet))
    return findings

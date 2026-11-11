"""SQG005 — risky-license detector (Phase 3, registry-metadata MVP).

For each dependency the PR introduces, ask the package registry what license it
ships under and flag copyleft licenses (GPL / AGPL / LGPL / SSPL) that carry
distribution obligations a reviewer should weigh. No Trivy, no Syft — just the
registry JSON we already fetch, same shape as the SQG001 existence checks.

Hard rules (product constraints):
* Advisory only. License *compatibility* is a legal/business judgement, not a
  build error — findings are MEDIUM and never block-eligible.
* Fail-safe. Registry unreachable / no license declared → silent. A metadata
  gap must never fail a PR.

Scope: PyPI + npm, whose registry JSON exposes license metadata directly, plus
Packagist — Composer writes each resolved package's license into composer.lock, so
that ecosystem needs no network call at all and is read straight from the file.

RubyGems, Maven and NuGet remain uncovered: their licenses are only obtainable one
HTTP request per package, and a Gemfile.lock routinely holds 200 gems. Doing that
serially inside the analyzer's wall-clock budget would time the check out — which
coverage would then report as `timed_out`, a worse outcome than an honest
`not_covered`. Bounded-concurrency registry fetching → backlog.

crates.io and range-spec resolution → backlog. Only dependencies appearing on
*added* lines are checked — the PR is judged on what it introduced.
"""

import re
from typing import Callable, List, Optional

import httpx

from app.diff import parse_diff
from app.manifests import extract_dependency_names, lockfile_ecosystem, manifest_ecosystem
from app.pinned import composer_lock_licenses
from app.registries import normalize_pypi

from .base import Confidence, Evidence, Finding

RULE_ID = "SQG005"

# Ecosystems whose registry JSON we can read a license from.
_SUPPORTED = {"pypi", "npm"}

# Lockfiles that record the license themselves — no registry lookup needed.
_DECLARED_LICENSE_LOCKFILES = {"packagist"}

# Copyleft / network-copyleft families worth a human glance.
_COPYLEFT = re.compile(
    r"\b(?:A?GPL|LGPL|GPL-?\d|SSPL|GNU\s+(?:Lesser\s+|Affero\s+)?General\s+Public)",
    re.IGNORECASE,
)


def _pypi_license_label(info: dict) -> str:
    """Best-effort license label from a PyPI ``info`` block.

    Only trusts STRUCTURED signals — the trove ``classifiers`` and the SPDX
    ``license_expression`` — plus the free-text ``license`` field when it is a
    short, single-line identifier (e.g. "GPL-3.0-only"). PyPI's ``license`` field
    is frequently the FULL license document (pandas, scipy, matplotlib paste the
    entire BSD/PSF text, which merely *mentions* "GPL" in a clause); substring-
    matching that body produced false copyleft hits, so a multi-line / long body
    is ignored here. Real copyleft packages still carry a GPL/LGPL/AGPL trove
    classifier or SPDX expression, so detection is preserved.
    """
    classifiers = " ".join(c for c in info.get("classifiers", []) if "License" in c)
    raw = (info.get("license") or "").strip()
    short_license = raw if (len(raw) <= 80 and "\n" not in raw) else ""
    expr = info.get("license_expression") or ""
    return f"{short_license} {expr} {classifiers}".strip()


def _npm_license_text(data: dict) -> str:
    """Pull a license label out of an npm registry document (several shapes)."""
    lic = data.get("license")
    if isinstance(lic, str):
        return lic
    if isinstance(lic, dict):
        return str(lic.get("type", ""))
    licenses = data.get("licenses")
    if isinstance(licenses, list):
        return " ".join(
            str(item.get("type", "")) if isinstance(item, dict) else str(item)
            for item in licenses
        )
    return ""


async def fetch_license(
    ecosystem: str, name: str, client: httpx.AsyncClient
) -> Optional[str]:
    """Return a best-effort license label for a package, or None if unreachable."""
    if ecosystem == "pypi":
        url = f"https://pypi.org/pypi/{normalize_pypi(name)}/json"
    elif ecosystem == "npm":
        url = f"https://registry.npmjs.org/{name.replace('/', '%2F')}"
    else:
        return None

    try:
        resp = await client.get(url, follow_redirects=True)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None

    data = resp.json()
    if ecosystem == "pypi":
        return _pypi_license_label(data.get("info", {}))
    return _npm_license_text(data)


def _name_present(name: str, added: list[tuple[int, str]]) -> Optional[int]:
    """First added line where `name` appears as a whole token (mirrors SQG001).
    A bare substring test would match e.g. npm "ms" or PyPI "six" inside an
    unrelated word, running the license check against a package the PR never
    actually touched."""
    pattern = re.compile(rf"(?<![\w@/.-]){re.escape(name)}(?![\w.-])")
    for line, content in added:
        if pattern.search(content):
            return line
    return None


def _finding(
    name: str, license_label: str, match: str, path: str, line: int, source: str = "registry"
) -> Finding:
    return Finding(
        category="license",
        confidence=Confidence.MEDIUM,
        block_eligible=False,
        file_path=path,
        line_start=line,
        line_end=line,
        message=f"Dependency '{name}' is copyleft-licensed ({match}) — review distribution obligations",
        evidence=Evidence(snippet=f"{name}: {license_label[:120]}"),
        # Names where the label came from, because "the lockfile says GPL" and "the
        # registry says GPL" are different claims a reviewer may want to re-check.
        tool=source,
        rule_id=RULE_ID,
        fix_suggestion="Confirm the license is compatible with your project's license and distribution model.",
    )


def _default_fetch(repo: str, path: str, ref: str, token: str):
    from app.github_client import fetch_file_content

    return fetch_file_content(repo, path, ref, token)


async def check_licenses(
    diff: str,
    repo_context: dict,
    *,
    fetch_file: Optional[Callable] = None,
    fetch_license: Callable = fetch_license,
) -> List[Finding]:
    """Flag PR-introduced dependencies under copyleft licenses (advisory)."""
    fetch_file = fetch_file or _default_fetch
    repo = repo_context.get("repo")
    head_sha = repo_context.get("head_sha")
    token = repo_context.get("token")
    # repo_context values come from a plain dict; narrow before using them as str.
    assert isinstance(repo, str)
    assert isinstance(head_sha, str)
    assert isinstance(token, str)

    added_by_file: dict[str, List[tuple[int, str]]] = {}
    for path, line, content in parse_diff(diff):
        added_by_file.setdefault(path, []).append((line, content))

    findings: List[Finding] = []
    async with httpx.AsyncClient(timeout=10) as client:
        for path, added in added_by_file.items():
            if lockfile_ecosystem(path) in _DECLARED_LICENSE_LOCKFILES:
                content = await fetch_file(repo, path, head_sha, token)
                if content is None:
                    continue
                for name, label in composer_lock_licenses(content):
                    lock_line = _name_present(name, added)
                    if lock_line is None:
                        continue  # not introduced by this PR
                    m = _COPYLEFT.search(label)
                    if m:
                        findings.append(
                            _finding(name, label, m.group(0), path, lock_line, source="lockfile")
                        )
                continue

            ecosystem = manifest_ecosystem(path)
            if ecosystem not in _SUPPORTED:
                continue
            content = await fetch_file(repo, path, head_sha, token)
            if content is None:
                continue  # unfetchable manifest → silent (protects zero-FP)
            for name in extract_dependency_names(path, content):
                manifest_line = _name_present(name, added)
                if manifest_line is None:
                    continue  # not introduced by this PR
                label = await fetch_license(ecosystem, name, client)
                if not label:
                    continue  # unreachable or no license → silent
                m = _COPYLEFT.search(label)
                if m:
                    findings.append(_finding(name, label, m.group(0), path, manifest_line))
    return findings

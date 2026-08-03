"""SQG001 — non-existent / hallucinated dependency detector (Phase 3).

The defensible core: for every dependency *newly added* in this PR's manifests,
ask the real registry whether it exists. A clean 404 from a reachable registry is
a CERTAIN, block-eligible finding. A registry we can't reach is downgraded to a
HIGH advisory — an outage must never block a PR.

Calibrated for zero false positives: only registry-checkable names from a real
manifest parse are queried (local/git/url/workspace specs are filtered upstream
in manifests.py), and a dependency is only considered "new" when its name appears
on an added diff line.
"""

import re
from typing import Awaitable, Callable, List, Optional

import httpx

from app import github_client
from app.diff import parse_diff
from app.manifests import (
    extract_dependency_names,
    has_pip_extra_index,
    manifest_ecosystem,
    npmrc_private_scopes,
)
from app.registries import Existence, check_exists

from .base import Confidence, Evidence, Finding

RULE_ID = "SQG001"


def _added_lines_by_file(diff: str) -> dict[str, list[tuple[int, str]]]:
    """Group a diff's added lines into {file_path: [(line_number, content), ...]}."""
    grouped: dict[str, list[tuple[int, str]]] = {}
    for path, line, content in parse_diff(diff):
        grouped.setdefault(path, []).append((line, content))
    return grouped


def _name_present(name: str, added: list[tuple[int, str]]) -> Optional[int]:
    """Return the first added line number where `name` appears as a whole token."""
    pattern = re.compile(rf"(?<![\w@/.-]){re.escape(name)}(?![\w.-])")
    for line, content in added:
        if pattern.search(content):
            return line
    return None


def _missing_finding(name: str, ecosystem: str, path: str, line: int, snippet: str) -> Finding:
    return Finding(
        category="dependency",
        confidence=Confidence.CERTAIN,
        block_eligible=True,
        file_path=path,
        line_start=line,
        line_end=line,
        message=f"Package '{name}' does not exist in {ecosystem} (404)",
        evidence=Evidence(snippet=snippet.strip()),
        tool=f"registry:{ecosystem}",
        rule_id=RULE_ID,
        fix_suggestion=f"Remove '{name}' or correct the package name; it is not published on {ecosystem}.",
    )


def _unknown_finding(name: str, ecosystem: str, path: str, line: int, snippet: str) -> Finding:
    return Finding(
        category="dependency",
        confidence=Confidence.HIGH,
        block_eligible=False,
        file_path=path,
        line_start=line,
        line_end=line,
        message=f"Could not verify '{name}' against {ecosystem} (registry unreachable) — advisory only",
        evidence=Evidence(snippet=snippet.strip()),
        tool=f"registry:{ecosystem}",
        rule_id=RULE_ID,
    )


def _private_index_finding(name: str, ecosystem: str, path: str, line: int, snippet: str) -> Finding:
    """A public-registry 404 that ISN'T proof of a hallucinated package: this repo
    declares a private/custom index, so the name may be a real internal package the
    public registry has simply never heard of. Advisory only — never block on an
    absence we can't actually prove (G3)."""
    return Finding(
        category="dependency",
        confidence=Confidence.HIGH,
        block_eligible=False,
        file_path=path,
        line_start=line,
        line_end=line,
        message=(
            f"'{name}' was not found on the public {ecosystem} registry, but this project "
            f"declares a private/custom index — it may be a real internal package. Advisory only."
        ),
        evidence=Evidence(snippet=snippet.strip()),
        tool=f"registry:{ecosystem}",
        rule_id=RULE_ID,
    )


async def check_dependencies(diff: str, repo_context: dict) -> List[Finding]:
    """Flag hallucinated dependencies added in this PR.

    repo_context keys:
        repo, head_sha, token   — used to fetch full manifest content.
        fetch_file (optional)   — async (path) -> content|None, for injection/tests.
        check_exists (optional) — async (ecosystem, name, client) -> Existence.
    """
    added_by_file = _added_lines_by_file(diff)

    repo = repo_context.get("repo", "")
    head_sha = repo_context.get("head_sha", "")
    token = repo_context.get("token", "")

    fetch_file: Callable[[str], Awaitable[Optional[str]]] = repo_context.get(
        "fetch_file",
        lambda path: github_client.fetch_file_content(repo, path, head_sha, token),
    )
    exists_fn = repo_context.get("check_exists", check_exists)

    findings: List[Finding] = []
    npmrc_scopes: Optional[set[str]] = None  # lazy, fetched at most once per scan
    async with httpx.AsyncClient(timeout=10) as client:
        for path, added in added_by_file.items():
            ecosystem = manifest_ecosystem(path)
            if ecosystem is None:
                continue

            content = await fetch_file(path)
            if not content:
                continue  # can't parse → stay silent (protects zero-FP bar)

            # A repo-declared private index means a public-registry 404 is NOT proof
            # of a hallucinated package (see manifests.has_pip_extra_index/
            # npmrc_private_scopes) — never block on an absence we can't prove (G3).
            pip_private = ecosystem == "pypi" and has_pip_extra_index(content)
            if ecosystem == "npm" and npmrc_scopes is None:
                npmrc_content = await fetch_file(".npmrc")
                npmrc_scopes = npmrc_private_scopes(npmrc_content) if npmrc_content else set()

            seen: set[str] = set()
            for name in extract_dependency_names(path, content):
                if name in seen:
                    continue
                line = _name_present(name, added)
                if line is None:
                    continue  # declared but not touched in this PR
                seen.add(name)

                snippet = next(c for ln, c in added if ln == line)
                result = await exists_fn(ecosystem, name, client)
                if result is Existence.MISSING:
                    is_private = pip_private or (
                        ecosystem == "npm"
                        and npmrc_scopes
                        and any(name.startswith(f"{scope}/") for scope in npmrc_scopes)
                    )
                    if is_private:
                        findings.append(_private_index_finding(name, ecosystem, path, line, snippet))
                    else:
                        findings.append(_missing_finding(name, ecosystem, path, line, snippet))
                elif result is Existence.UNKNOWN:
                    findings.append(_unknown_finding(name, ecosystem, path, line, snippet))

    return findings

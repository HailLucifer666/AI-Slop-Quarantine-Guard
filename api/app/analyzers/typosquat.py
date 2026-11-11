"""SQG007 — typosquatting advisory (Phase 3).

Flags a PR-introduced dependency whose name is 1–2 edits away from a well-known
popular package (``reqeusts`` → ``requests``). The look-alike usually *does* exist
on the registry, so this is a **suspicion, not a provable fact** — the honesty rule
forbids calling it CERTAIN or blocking on it. Findings are therefore always HIGH,
advisory, never block-eligible; the evidence names the look-alike target and asks
the author to verify.

Pure string comparison against a bundled curated list (popular_packages.py) — no
network, so it is deterministic and fail-safe by construction. False positives are
suppressed by three guards: the name must not itself be a popular package, must be
long enough that a 2-edit collision is unlikely (MIN_LEN), and must land within
MAX_DISTANCE edits of exactly the closest popular name.
"""

import re
from typing import Awaitable, Callable, List, Optional

from app import github_client
from app.diff import parse_diff
from app.manifests import extract_dependency_names, manifest_ecosystem

from .base import Confidence, Evidence, Finding
from .popular_packages import POPULAR_BY_ECOSYSTEM

RULE_ID = "SQG007"

# A name below this floor is too short for edit distance to mean anything at all
# (nearly everything is within 2 edits of a 1-2 char string).
MIN_LEN = 3
MAX_DISTANCE = 2
# The allowed edit distance SCALES with the popular target's length rather than
# using one flat floor — a flat MIN_LEN=5 floor let genuinely short squats
# ("flsk" vs "flask") evade detection just by staying under it, while a flat
# ratio alone would flood short real names with coincidental matches. A short
# target (e.g. "six") only tolerates a 1-edit neighbour; a longer one tolerates
# up to MAX_DISTANCE.
MAX_DISTANCE_RATIO = 0.3


def _max_allowed_distance(candidate_len: int) -> int:
    return max(1, min(MAX_DISTANCE, round(candidate_len * MAX_DISTANCE_RATIO)))


def _normalize(ecosystem: str, name: str) -> str:
    """Canonical comparison form: lower-case; PyPI treats ``_`` and ``-`` alike."""
    name = name.lower()
    return name.replace("_", "-") if ecosystem == "pypi" else name


def _edit_distance_within(a: str, b: str, max_d: int) -> Optional[int]:
    """Levenshtein distance between a and b, or None if it exceeds max_d.

    Length gap alone can rule a pair out before the (small) DP runs.
    """
    if abs(len(a) - len(b)) > max_d:
        return None
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            val = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            cur.append(val)
            row_min = min(row_min, val)
        if row_min > max_d:
            return None  # whole row already past the bound → give up early
        prev = cur
    return prev[-1] if prev[-1] <= max_d else None


def _closest_popular(ecosystem: str, name: str) -> Optional[str]:
    """Return the nearest popular package within MAX_DISTANCE edits, else None.

    Returns None when the name *is* a popular package (distance 0) — that's the
    real thing, not a typo of it.
    """
    popular = POPULAR_BY_ECOSYSTEM.get(ecosystem)
    if not popular or len(name) < MIN_LEN or name in popular:
        return None
    best: Optional[str] = None
    best_d = MAX_DISTANCE + 1
    for candidate in popular:
        allowed = _max_allowed_distance(len(candidate))
        d = _edit_distance_within(name, candidate, allowed)
        if d is not None and 1 <= d < best_d:
            best, best_d = candidate, d
            if best_d == 1:
                break  # can't get closer
    return best


def _name_present(name: str, added: list[tuple[int, str]]) -> Optional[int]:
    """First added line where `name` appears as a whole token (mirrors SQG001)."""
    pattern = re.compile(rf"(?<![\w@/.-]){re.escape(name)}(?![\w.-])")
    for line, content in added:
        if pattern.search(content):
            return line
    return None


def _finding(name: str, target: str, path: str, line: int, snippet: str) -> Finding:
    return Finding(
        category="dependency",
        confidence=Confidence.HIGH,
        block_eligible=False,
        file_path=path,
        line_start=line,
        line_end=line,
        message=(
            f"Dependency '{name}' is a near look-alike of the popular package "
            f"'{target}' — possible typosquat. Verify it's the package you intended."
        ),
        evidence=Evidence(snippet=snippet.strip()),
        tool="typosquat",
        rule_id=RULE_ID,
        fix_suggestion=(
            f"If you meant '{target}', correct the name. Otherwise confirm '{name}' "
            f"is a package you trust — advisory only, not a block."
        ),
    )


async def check_typosquat(diff: str, repo_context: dict) -> List[Finding]:
    """Flag PR-introduced dependencies that look like typos of popular packages.

    repo_context keys mirror SQG001: repo, head_sha, token, and an optional
    ``fetch_file`` async (path) -> content|None for injection/tests.
    """
    added_by_file: dict[str, list[tuple[int, str]]] = {}
    for path, line, content in parse_diff(diff):
        added_by_file.setdefault(path, []).append((line, content))

    repo = repo_context.get("repo", "")
    head_sha = repo_context.get("head_sha", "")
    token = repo_context.get("token", "")
    fetch_file: Callable[[str], Awaitable[Optional[str]]] = repo_context.get(
        "fetch_file",
        lambda path: github_client.fetch_file_content(repo, path, head_sha, token),
    )

    findings: List[Finding] = []
    for path, added in added_by_file.items():
        ecosystem = manifest_ecosystem(path)
        if ecosystem not in POPULAR_BY_ECOSYSTEM:
            continue
        body = await fetch_file(path)
        if not body:
            continue  # can't parse → stay silent (protects zero-FP bar)

        seen: set[str] = set()
        for name in extract_dependency_names(path, body):
            if name in seen:
                continue
            line_no = _name_present(name, added)
            if line_no is None:
                continue  # declared but not touched in this PR
            seen.add(name)
            target = _closest_popular(ecosystem, _normalize(ecosystem, name))
            if target is None:
                continue
            snippet = next(c for ln, c in added if ln == line_no)
            findings.append(_finding(name, target, path, line_no, snippet))

    return findings

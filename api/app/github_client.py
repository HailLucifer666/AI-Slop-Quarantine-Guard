"""GitHub API client with httpx (Phase 2 + Phase 4)."""

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

import httpx

GITHUB_API = "https://api.github.com"
CHECK_RUN_NAME = "PR Quality & Security Gate"

# Retry budget for every GitHub call in this module — mirrors
# app.registries.check_exists. A transient blip (429/5xx/connection error) must
# not silently disable an analyzer (fetch_file_content — indistinguishable from
# "file deleted" without a retry), drop a PR job (create_check_run), or leave a
# Check Run stuck "in_progress" forever (update_check_run) — and an uncaught
# httpx.HTTPError would otherwise crash the whole scan/job, not just this call.
_FETCH_RETRIES = 2

# GitHub accepts more, but a review that posts hundreds of inline comments is spam, not
# review. The Check Run summary still accounts for every finding, so this caps noise
# without hiding anything.
MAX_REVIEW_COMMENTS = 25
# Bound the existing-comment scan on a long-running PR.
_MAX_COMMENT_PAGES = 5

_CHECK_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def fetch_pr_diff(
    repo: str, pr_number: int, token: str
) -> Optional[str]:
    """Fetch the unified diff for a PR.

    Uses the `application/vnd.github.diff` media type so GitHub returns the raw
    unified diff in one call. Returns None if the PR can't be fetched.

    Args:
        repo: Repository (org/name).
        pr_number: PR number.
        token: GitHub installation token.

    Returns:
        Raw unified diff text, or None.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.diff"},
        )
    if resp.status_code == 200:
        return resp.text
    return None


async def fetch_file_content(
    repo: str, path: str, ref: str, token: str
) -> Optional[str]:
    """Fetch a single file's raw content at a given ref (Phase 3).

    Uses the `application/vnd.github.raw` media type so the Contents API returns
    the file body directly. Returns None if the file can't be fetched (deleted,
    too large for the raw endpoint, etc.).

    Args:
        repo: Repository (org/name).
        path: File path within the repo.
        ref: Commit SHA or branch.
        token: GitHub installation token.

    Returns:
        Raw file content, or None.
    """
    for attempt in range(_FETCH_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{GITHUB_API}/repos/{repo}/contents/{path}",
                    params={"ref": ref},
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw"},
                )
        except httpx.HTTPError:
            await asyncio.sleep(0.5 * (attempt + 1))
            continue
        if resp.status_code == 200:
            return resp.text
        if resp.status_code == 404:
            return None  # genuinely missing/deleted — not transient, don't retry
        # 429 / 5xx / unexpected → transient; back off and retry.
        await asyncio.sleep(0.5 * (attempt + 1))
    return None


async def fetch_review_comment_bodies(repo: str, pr_number: int, token: str) -> List[str]:
    """Bodies of review comments already on this PR, for idempotency.

    Re-running the gate (a new push, a re-request) must not stack a second copy of the
    same comment on the same line. Each body we post carries a fingerprint marker, so
    reading existing bodies is enough to know what has already been said.

    Returns [] on failure — which errs toward posting a possible duplicate rather than
    staying silent about a real finding.
    """
    bodies: List[str] = []
    page = 1
    while page <= _MAX_COMMENT_PAGES:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/comments",
                    params={"per_page": 100, "page": page},
                    headers={"Authorization": f"Bearer {token}", **_CHECK_HEADERS},
                )
        except httpx.HTTPError:
            return bodies
        if resp.status_code != 200:
            return bodies
        batch = resp.json()
        if not isinstance(batch, list) or not batch:
            return bodies
        bodies.extend(c.get("body", "") for c in batch if isinstance(c, dict))
        if len(batch) < 100:
            return bodies
        page += 1
    return bodies


async def create_review(
    repo: str,
    pr_number: int,
    commit_sha: str,
    comments: List[dict],
    token: str,
    body: str = "",
) -> bool:
    """Post inline review comments in one review.

    ``comments`` entries are GitHub's shape: ``path``, ``line`` (and optional
    ``start_line``), ``side``, ``body``. Posted as event=COMMENT — the gate comments, it
    never approves or requests changes, which would be an authority it hasn't earned.

    A comment anchored to a line outside the diff makes GitHub reject the WHOLE review
    (422), so on 422 we retry once with the comments dropped, preserving the summary body
    rather than losing the entire review.
    """
    payload: dict = {"commit_id": commit_sha, "event": "COMMENT"}
    if body:
        payload["body"] = body
    if comments:
        payload["comments"] = comments[:MAX_REVIEW_COMMENTS]

    for attempt in range(_FETCH_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/reviews",
                    headers={"Authorization": f"Bearer {token}", **_CHECK_HEADERS},
                    json=payload,
                )
        except httpx.HTTPError:
            await asyncio.sleep(0.5 * (attempt + 1))
            continue
        if resp.status_code in (200, 201):
            return True
        if resp.status_code == 422 and payload.get("comments"):
            # An unanchorable comment poisoned the batch. Drop the inline comments and
            # post the summary alone rather than saying nothing at all.
            payload.pop("comments")
            if not payload.get("body"):
                return False
            continue
        if resp.status_code in (401, 403, 404):
            return False  # permissions/missing PR — retrying cannot help
        await asyncio.sleep(0.5 * (attempt + 1))
    return False


async def create_check_run(repo: str, head_sha: str, token: str) -> Optional[int]:
    """Open an in-progress Check Run so the gate shows as "running" immediately.

    Args:
        repo: Repository (org/name).
        head_sha: Commit SHA the run is attached to.
        token: GitHub installation token.

    Returns:
        The new check run's id, or None if creation failed (never fatal — the
        worker falls back to a single create-with-conclusion call).
    """
    for attempt in range(_FETCH_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{GITHUB_API}/repos/{repo}/check-runs",
                    headers={"Authorization": f"Bearer {token}", **_CHECK_HEADERS},
                    json={
                        "name": CHECK_RUN_NAME,
                        "head_sha": head_sha,
                        "status": "in_progress",
                        "started_at": _now_iso(),
                    },
                )
        except httpx.HTTPError:
            await asyncio.sleep(0.5 * (attempt + 1))
            continue
        if resp.status_code == 201:
            return resp.json().get("id")
        # 429 / 5xx / unexpected → transient; back off and retry.
        await asyncio.sleep(0.5 * (attempt + 1))
    return None


async def update_check_run(
    repo: str,
    check_run_id: int,
    conclusion: str,
    summary: str,
    token: str,
    annotations: Optional[List[dict]] = None,
    title: str = CHECK_RUN_NAME,
) -> bool:
    """Complete a Check Run with a conclusion, summary, and inline annotations.

    Args:
        repo: Repository (org/name).
        check_run_id: The id returned by ``create_check_run``.
        conclusion: "success" or "action_required" (Phase 4 — never "failure").
        summary: Markdown summary (truncation-safe).
        token: GitHub installation token.
        annotations: Inline line markers (GitHub caps each request at 50).
        title: Output title.

    Returns:
        True on success.
    """
    output: dict = {"title": title, "summary": summary}
    if annotations:
        output["annotations"] = annotations[:50]
    for attempt in range(_FETCH_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.patch(
                    f"{GITHUB_API}/repos/{repo}/check-runs/{check_run_id}",
                    headers={"Authorization": f"Bearer {token}", **_CHECK_HEADERS},
                    json={
                        "status": "completed",
                        "conclusion": conclusion,
                        "completed_at": _now_iso(),
                        "output": output,
                    },
                )
        except httpx.HTTPError:
            await asyncio.sleep(0.5 * (attempt + 1))
            continue
        if resp.status_code == 200:
            return True
        # 429 / 5xx / unexpected → transient; back off and retry.
        await asyncio.sleep(0.5 * (attempt + 1))
    return False

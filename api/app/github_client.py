"""GitHub API client with httpx (Phase 2 + Phase 4)."""

from datetime import datetime, timezone
from typing import List, Optional

import httpx

GITHUB_API = "https://api.github.com"
CHECK_RUN_NAME = "PR Quality & Security Gate"

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
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/contents/{path}",
            params={"ref": ref},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw"},
        )
    if resp.status_code == 200:
        return resp.text
    return None


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
    if resp.status_code == 201:
        return resp.json().get("id")
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
    return resp.status_code == 200

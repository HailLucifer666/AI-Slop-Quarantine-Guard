"""Startup advisories about database files that are NOT the live one.

A relative sqlite URL used to resolve against the process working directory, so
launching the API and the worker from different directories created two unrelated
`app.db` files — one accumulating scans, the other being read by the dashboard.
`config._resolve_sqlite_path` closes that hole going forward, but the files it already
produced are still on disk and are still confusing: an operator who finds `app.db` at
the repo root reasonably assumes it is the database.

This module only ever LOGS. Deleting or restoring a database is the operator's call —
copying a `.bak-*` over the live file would resurrect old scans as if they were current
results, which is exactly the failure mode this codebase is trying to eliminate.
"""

import logging
from pathlib import Path

logger = logging.getLogger("db.diagnostics")

# api/ holds the live app.db; its parent is the repo root, where a stray copy landed.
_API_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _API_ROOT.parent


def find_stray_databases(live_path: str = "") -> list[tuple[Path, int]]:
    """Database-looking files that are not the live database, as (path, size_bytes).

    Args:
        live_path: absolute path of the database actually in use, so it is never
            reported as stray.
    """
    live = Path(live_path).resolve() if live_path else None
    candidates: list[Path] = [_REPO_ROOT / "app.db"]
    candidates.extend(sorted(_API_ROOT.glob("app.db.bak-*")))

    stray: list[tuple[Path, int]] = []
    for path in candidates:
        if not path.is_file():
            continue
        if live is not None and path.resolve() == live:
            continue
        stray.append((path, path.stat().st_size))
    return stray


def log_stray_databases() -> None:
    """Warn about stray database files, naming each path and size."""
    from .session import engine

    live_path = engine.url.database or ""
    if not live_path:
        return  # non-file backend (Postgres, :memory:) — nothing to confuse

    for path, size in find_stray_databases(live_path):
        logger.warning(
            "stray database file present and NOT in use: %s (%d bytes). The live "
            "database is %s. Delete the stray one manually if it is causing confusion; "
            "never copy a .bak-* over the live file — that would make old scans look "
            "like current results.",
            path, size, live_path,
        )

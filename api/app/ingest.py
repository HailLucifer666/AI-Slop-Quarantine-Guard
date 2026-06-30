"""Codebase ingestion for whole-repo scans.

Three safe ways to get a codebase into an in-memory {path: content} map:
- `clone_repo(url)`  — shallow `git clone` of a public forge URL (read-only; code never executed).
- `read_zip(data)`   — entries read directly from the archive (no extraction → no zip-slip on disk).
- `walk_dir(path)`   — a local folder (dev only; gated by the caller).

Every path runs through the same guards: ignore-dirs, binary skip, and hard caps (per-file,
total bytes, file count). Over budget → the file is skipped and recorded, never silently dropped —
honoring the product's "never lie / fail-safe" promise.
"""

import io
import os
import shutil
import subprocess
import tempfile
import zipfile
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import pathspec

# Hard caps (free-tier safe). Over budget → skip + record.
MAX_FILES = 5000
MAX_TOTAL_BYTES = 50 * 1024 * 1024  # 50 MB of text
MAX_FILE_BYTES = 1 * 1024 * 1024    # 1 MB per file
CLONE_TIMEOUT_S = 60

# Directories never worth scanning (vendored / generated / VCS). Findings inside
# build output, framework caches, and bundled dependency code are not the user's
# source — scanning them floods false positives (and duplicates each bundled lib
# across every serverless-function copy).
IGNORE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", "dist", "build", "out",
    ".venv", "venv", "env", "__pycache__", ".next", ".nuxt", "target",
    ".idea", ".vscode", "coverage", ".pytest_cache", ".mypy_cache", "bin", "obj",
    # Framework build output / caches / serverless bundles.
    ".vercel", ".output", "nitro-output", "dev-runtime", ".svelte-kit", ".turbo",
    ".cache", ".parcel-cache", ".serverless", ".terraform", ".angular", ".expo",
    ".docusaurus", ".astro", ".gradle",
}

# Ignore-spec files whose patterns we honor (the project's own declared ignores).
_IGNORE_SPEC_FILENAMES = {".gitignore", ".dockerignore"}


def _build_ignore_spec(lines: List[str]) -> Optional["pathspec.PathSpec"]:
    """Compile collected ignore-file patterns into a matcher (None on failure).

    Honoring the project's own .gitignore/.dockerignore is what real scanners do:
    it excludes build output, local env files (.env*.local), and bespoke cache dirs
    a hardcoded denylist can't anticipate. Patterns from ignore files anywhere in the
    tree are pooled; gitignore's non-anchored patterns match at any depth, which is
    what we want. A malformed file degrades to None → denylist still applies.
    """
    if not lines:
        return None
    # "gitignore" is the modern factory name; "gitwildmatch" is the long-standing
    # one (pathspec <=0.12). Prefer the former, fall back to the latter.
    for style in ("gitignore", "gitwildmatch"):
        try:
            return pathspec.PathSpec.from_lines(style, lines)
        except Exception:  # noqa: BLE001 — bad patterns/unknown style must never break a scan
            continue
    return None


def _ignored_by_spec(spec: "Optional[pathspec.PathSpec]", rel_path: str) -> bool:
    return spec is not None and spec.match_file(rel_path.replace("\\", "/"))

# Binary / non-source extensions to skip outright.
BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svg", ".pdf",
    ".zip", ".gz", ".tar", ".rar", ".7z", ".jar", ".war", ".class", ".exe",
    ".dll", ".so", ".dylib", ".o", ".a", ".bin", ".wasm", ".woff", ".woff2",
    ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".mov", ".avi", ".webm", ".wav",
    ".db", ".sqlite", ".sqlite3", ".pyc", ".lock",
}

# Public forge hosts allowed for clone (SSRF guard — no internal/arbitrary hosts).
ALLOWED_CLONE_HOSTS = {"github.com", "www.github.com", "gitlab.com", "bitbucket.org"}


class IngestError(ValueError):
    """Raised when a source can't be safely ingested (bad URL, clone failure)."""


def _is_ignored(rel_path: str) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    return any(part in IGNORE_DIRS for part in parts[:-1])


def _is_binary_name(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in BINARY_EXTS


def _decode(data: bytes) -> Optional[str]:
    """Decode bytes to text; return None if it looks binary."""
    if b"\x00" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def _accumulate(
    files: Dict[str, str], skipped: List[str], total: List[int],
    rel_path: str, raw: bytes, declared_size: int,
) -> None:
    """Apply caps + binary check, then add to the map or record as skipped."""
    rel_path = rel_path.replace("\\", "/")
    if _is_ignored(rel_path) or _is_binary_name(rel_path):
        return  # quietly ignored (not user-meaningful "skipped")
    if len(files) >= MAX_FILES:
        skipped.append(f"{rel_path} (file-count cap {MAX_FILES} reached)")
        return
    if declared_size > MAX_FILE_BYTES:
        skipped.append(f"{rel_path} (exceeds {MAX_FILE_BYTES // 1024}KB file cap)")
        return
    if total[0] + len(raw) > MAX_TOTAL_BYTES:
        skipped.append(f"{rel_path} (total-size cap {MAX_TOTAL_BYTES // (1024*1024)}MB reached)")
        return
    text = _decode(raw)
    if text is None:
        return  # binary by content
    files[rel_path] = text
    total[0] += len(raw)


def _collect_dir_ignore_spec(root: str) -> "Optional[pathspec.PathSpec]":
    """Light pre-pass: pool every .gitignore/.dockerignore in the tree into one spec."""
    lines: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            if name in _IGNORE_SPEC_FILENAMES:
                try:
                    with open(os.path.join(dirpath, name), "r", encoding="utf-8", errors="ignore") as fh:
                        lines.extend(fh.read().splitlines())
                except OSError:
                    pass
    return _build_ignore_spec(lines)


def walk_dir(root: str) -> Tuple[Dict[str, str], List[str]]:
    """Read a local directory tree into a {path: content} map (+ skipped list)."""
    if not os.path.isdir(root):
        raise IngestError(f"not a directory: {root}")
    files: Dict[str, str] = {}
    skipped: List[str] = []
    total = [0]
    spec = _collect_dir_ignore_spec(root)
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune by the built-in denylist AND the project's own ignore rules.
        dirnames[:] = [
            d for d in dirnames
            if d not in IGNORE_DIRS
            and not _ignored_by_spec(spec, os.path.relpath(os.path.join(dirpath, d), root) + "/")
        ]
        for name in filenames:
            abs_path = os.path.join(dirpath, name)
            rel = os.path.relpath(abs_path, root)
            if _ignored_by_spec(spec, rel):
                continue  # quietly ignored (project's .gitignore) — not a "skipped" file
            try:
                size = os.path.getsize(abs_path)
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                _accumulate(files, skipped, total, rel, b"", size)
                continue
            try:
                with open(abs_path, "rb") as fh:
                    raw = fh.read()
            except OSError:
                continue
            _accumulate(files, skipped, total, rel, raw, size)
    return files, skipped


def _common_prefix(names: List[str]) -> str:
    """If every entry sits under one top-level folder (e.g. `repo-main/`), return it."""
    normed = [n.replace("\\", "/") for n in names]
    tops = {n.split("/", 1)[0] for n in normed if "/" in n}
    if len(tops) == 1 and all("/" in n for n in normed):
        return next(iter(tops)) + "/"
    return ""


def read_zip(data: bytes) -> Tuple[Dict[str, str], List[str]]:
    """Read a zip archive's entries directly into a {path: content} map.

    Entries are read from the archive, never written to disk, so path traversal
    ("zip-slip") cannot escape anywhere — but absolute / `..` names are still
    rejected defensively. A common single top-level folder is stripped.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise IngestError(f"not a valid zip archive: {exc}") from exc

    files: Dict[str, str] = {}
    skipped: List[str] = []
    total = [0]
    with zf:
        names = [i for i in zf.infolist() if not i.is_dir()]
        prefix = _common_prefix([i.filename for i in names])

        def _rel(fname: str) -> str:
            return fname[len(prefix):] if prefix and fname.startswith(prefix) else fname

        # Pool the archive's own .gitignore/.dockerignore patterns first.
        ignore_lines: List[str] = []
        for info in names:
            if _rel(info.filename).replace("\\", "/").rsplit("/", 1)[-1] in _IGNORE_SPEC_FILENAMES:
                try:
                    ignore_lines.extend(zf.read(info).decode("utf-8", errors="ignore").splitlines())
                except (RuntimeError, zipfile.BadZipFile):
                    pass
        spec = _build_ignore_spec(ignore_lines)

        for info in names:
            name = info.filename
            if os.path.isabs(name) or ".." in name.replace("\\", "/").split("/"):
                skipped.append(f"{name} (unsafe path rejected)")
                continue
            rel = _rel(name)
            if not rel:
                continue
            if _ignored_by_spec(spec, rel):
                continue  # quietly ignored (project's .gitignore) — not a "skipped" file
            if info.file_size > MAX_FILE_BYTES:
                _accumulate(files, skipped, total, rel, b"", info.file_size)
                continue
            try:
                raw = zf.read(info)
            except (RuntimeError, zipfile.BadZipFile):
                skipped.append(f"{rel} (unreadable: encrypted or corrupt)")
                continue
            _accumulate(files, skipped, total, rel, raw, info.file_size)
    return files, skipped


def validate_clone_url(url: str) -> str:
    """Validate a clone URL: https only, public forge host only (SSRF guard)."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise IngestError("only https:// repository URLs are allowed")
    if "@" in parsed.netloc:
        raise IngestError("credentials in the URL are not allowed")
    if parsed.hostname not in ALLOWED_CLONE_HOSTS:
        raise IngestError(
            f"host '{parsed.hostname}' not allowed; use github.com, gitlab.com, or bitbucket.org"
        )
    return url.strip()


def clone_repo(url: str) -> Tuple[Dict[str, str], List[str]]:
    """Shallow-clone a public repo into a temp dir, read it, then clean up.

    Read-only: we clone and parse text. The repo's code is never executed.
    """
    url = validate_clone_url(url)
    tmp = tempfile.mkdtemp(prefix="slopscan-")
    try:
        proc = subprocess.run(
            ["git", "clone", "--depth", "1", "--filter=blob:none", "--quiet", url, tmp],
            capture_output=True, text=True, timeout=CLONE_TIMEOUT_S,
        )
        if proc.returncode != 0:
            raise IngestError(f"git clone failed: {proc.stderr.strip()[:200]}")
        return walk_dir(tmp)
    except subprocess.TimeoutExpired as exc:
        raise IngestError(f"clone timed out after {CLONE_TIMEOUT_S}s") from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

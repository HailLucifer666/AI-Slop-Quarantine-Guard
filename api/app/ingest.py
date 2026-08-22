"""Codebase ingestion for whole-repo scans.

Three safe ways to get a codebase into an in-memory {path: content} map:
- `clone_repo(url)`  — shallow `git clone` of a public forge URL (read-only; code never executed).
- `read_zip(data)`   — entries read directly from the archive (no extraction → no zip-slip on disk).
- `walk_dir(path)`   — a local folder (dev only; gated by the caller).

Every path runs through the same guards: ignore-dirs, binary skip, and hard caps (per-file,
total bytes, file count). Over budget → the file is skipped and recorded, never silently dropped —
honoring the product's "never lie / fail-safe" promise.
"""

import hashlib
import io
import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import urlparse

import pathspec


@dataclass
class IngestResult:
    """Everything one ingestion produced, and everything it did NOT read.

    The three sources previously returned bare tuples of differing arity — walk_dir and
    read_zip gave (files, skipped) while clone_repo gave (files, skipped, sha) — which
    left nowhere to report a fourth fact without changing every caller again.

    ``skipped`` and ``suppressed`` are deliberately separate: they have different causes
    and need different wording in the report. Skipped means we looked and could not take
    it (size/count cap, unreadable). Suppressed means the scanned repository's own ignore
    rules excluded it. Both mean "not examined", which is what disqualifies a clean
    verdict — see coverage.summarize.
    """

    files: Dict[str, str]
    skipped: List[str] = field(default_factory=list)
    suppressed: List[str] = field(default_factory=list)
    resolved_sha: Optional[str] = None

    @property
    def unexamined_count(self) -> int:
        """Files the scan did not read, for any reason. Never claim clean while > 0."""
        return len(self.skipped) + len(self.suppressed)


# Hard caps (free-tier safe). Over budget → skip + record.
MAX_FILES = 5000
MAX_TOTAL_BYTES = 50 * 1024 * 1024  # 50 MB of text
MAX_FILE_BYTES = 1 * 1024 * 1024    # 1 MB per file
CLONE_TIMEOUT_S = 60
# Reading the checked-out commit is a local, instant operation; a short cap means a
# hung git can never delay a scan for provenance metadata.
_REV_PARSE_TIMEOUT_S = 10

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
    # AI/agent tooling scratch space. Real scans were reporting findings inside
    # `.claude/worktrees/<branch>/src/...` — a coding agent's checkout of the repo,
    # not the user's code, and often a stale copy of it. Counting those is both a
    # false positive and a duplicate of the same file in the real tree.
    ".claude", ".cursor", ".aider", "graphify-out", "strix_runs", ".codeium",
    # More language/tool caches that are never user source.
    ".ruff_cache", ".tox", ".nox", "site-packages", "Pods", ".dart_tool",
    ".terragrunt-cache", "htmlcov", ".nyc_output", ".sass-cache",
}

# Generated/bundled single files that aren't user source. Findings in these are noise:
# the code came from a build step, and the same issue (if real) lives in the source the
# bundle was built from.
_GENERATED_SUFFIXES = (
    ".min.js", ".min.css", ".bundle.js", ".chunk.js", ".map",
    ".pb.go", "_pb2.py", ".g.dart", ".freezed.dart", ".generated.ts", ".d.ts.map",
)

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
    ".db", ".sqlite", ".sqlite3", ".pyc",
}

# Lockfiles must reach the analyzers: they are the ONLY place a dependency's exact
# resolved version is written down, and SQG004 needs an exact version to ask OSV
# whether it is known-vulnerable (see manifests.LOCKFILE_ECOSYSTEM).
#
# ".lock" used to sit in BINARY_EXTS, which silently dropped yarn.lock, poetry.lock
# and Cargo.lock from every scan — manifests.py registered parsers for all three and
# was never fed a single one. That is why a 794-file repo returned one vulnerability
# finding. They are also routinely larger than MAX_FILE_BYTES, so they are exempt from
# the per-file cap (bounded instead by LOCKFILE_MAX_BYTES) rather than being "skipped"
# at exactly the moment they matter most.
LOCKFILE_NAMES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "npm-shrinkwrap.json",
    "poetry.lock", "Pipfile.lock", "uv.lock",
    "Cargo.lock", "go.sum", "Gemfile.lock", "composer.lock", "packages.lock.json",
})
LOCKFILE_MAX_BYTES = 8 * 1024 * 1024  # a lockfile this large is pathological, not normal

# Public forge hosts allowed for clone (SSRF guard — no internal/arbitrary hosts).
ALLOWED_CLONE_HOSTS = {"github.com", "www.github.com", "gitlab.com", "bitbucket.org"}


class IngestError(ValueError):
    """Raised when a source can't be safely ingested (bad URL, clone failure)."""


def _is_ignored(rel_path: str) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    return any(part in IGNORE_DIRS for part in parts[:-1])


def _is_binary_name(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in BINARY_EXTS


def _is_generated_name(base: str) -> bool:
    """True for minified/bundled/code-generated files (see _GENERATED_SUFFIXES)."""
    low = base.lower()
    return any(low.endswith(suffix) for suffix in _GENERATED_SUFFIXES)


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
    base = rel_path.rsplit("/", 1)[-1]
    is_lockfile = base in LOCKFILE_NAMES
    if _is_ignored(rel_path) or (not is_lockfile and _is_binary_name(rel_path)):
        return  # quietly ignored (not user-meaningful "skipped")
    if not is_lockfile and _is_generated_name(base):
        return  # minified/bundled output — not the user's source
    if len(files) >= MAX_FILES:
        skipped.append(f"{rel_path} (file-count cap {MAX_FILES} reached)")
        return
    # Lockfiles get a larger cap: dropping one costs the whole vulnerability check for
    # that ecosystem, which is a far worse outcome than reading a few extra MB.
    cap = LOCKFILE_MAX_BYTES if is_lockfile else MAX_FILE_BYTES
    if declared_size > cap:
        skipped.append(f"{rel_path} (exceeds {cap // 1024}KB file cap)")
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


def _within(real_root: str, path: str) -> bool:
    """True if `path` resolves to somewhere inside `real_root`.

    The scanned tree is attacker-controlled: `clone_repo` restores whatever mode-120000
    entries the repository committed as real symlinks. ``os.walk`` defaults to
    ``followlinks=False``, which prunes symlinked *directories* — but a symlinked FILE is
    yielded as an ordinary name and ``open()`` resolves it, so a committed
    ``notes.txt -> /root/.ssh/id_rsa`` would read the scanner host's own files into the
    scan set, where a secret match lands in Evidence.snippet and is served straight back
    out by GET /api/scans/{id}.

    Compares resolved paths rather than testing ``os.path.islink`` on the leaf, because a
    plain file reached *through* a symlinked parent is not itself a link and would pass
    that check.
    """
    try:
        resolved = os.path.realpath(path)
    except OSError:
        return False
    return resolved == real_root or resolved.startswith(real_root + os.sep)


def walk_dir(root: str) -> IngestResult:
    """Read a local directory tree into an IngestResult."""
    if not os.path.isdir(root):
        raise IngestError(f"not a directory: {root}")
    files: Dict[str, str] = {}
    skipped: List[str] = []
    suppressed: List[str] = []
    total = [0]
    spec = _collect_dir_ignore_spec(root)
    real_root = os.path.realpath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune by the built-in denylist, the project's own ignore rules, AND anything
        # resolving outside the tree we were handed.
        dirnames[:] = [
            d for d in dirnames
            if d not in IGNORE_DIRS
            and not _ignored_by_spec(spec, os.path.relpath(os.path.join(dirpath, d), root) + "/")
            and _within(real_root, os.path.join(dirpath, d))
        ]
        for name in filenames:
            abs_path = os.path.join(dirpath, name)
            rel = os.path.relpath(abs_path, root)
            if not _within(real_root, abs_path):
                # A link escaping the repository is not repository content at all, so it
                # is neither "skipped" nor "suppressed" — there was nothing of the user's
                # to examine. Dropped silently, like a binary file.
                continue
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
    return IngestResult(files=files, skipped=skipped, suppressed=suppressed)


_READ_CHUNK = 65536


def _read_entry_capped(zf: zipfile.ZipFile, info: zipfile.ZipInfo, cap: int) -> Optional[bytes]:
    """Read one zip entry, aborting the instant decompressed bytes exceed `cap`.

    Streams via ``zf.open()`` and counts real bytes as they're produced, rather
    than trusting ``info.file_size`` (the archive's own declared uncompressed
    size — attacker-controlled zip metadata) and then pulling the whole entry in
    one ``zf.read()`` call. The cap is enforced against what decompression
    actually produces, so it can't be bypassed by a size field that disagrees
    with the real content, and memory use during the read is bounded to one
    chunk at a time rather than the full entry at once.

    Returns None if the cap was exceeded (caller records it as skipped).
    """
    chunks: List[bytes] = []
    total = 0
    with zf.open(info) as fh:
        while True:
            chunk = fh.read(_READ_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > cap:
                return None
            chunks.append(chunk)
    return b"".join(chunks)


def _common_prefix(names: List[str]) -> str:
    """If every entry sits under one top-level folder (e.g. `repo-main/`), return it."""
    normed = [n.replace("\\", "/") for n in names]
    tops = {n.split("/", 1)[0] for n in normed if "/" in n}
    if len(tops) == 1 and all("/" in n for n in normed):
        return next(iter(tops)) + "/"
    return ""


def read_zip(data: bytes) -> IngestResult:
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
    suppressed: List[str] = []
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
            try:
                raw = _read_entry_capped(zf, info, MAX_FILE_BYTES)
            except (RuntimeError, zipfile.BadZipFile):
                skipped.append(f"{rel} (unreadable: encrypted or corrupt)")
                continue
            if raw is None:
                skipped.append(f"{rel} (exceeds {MAX_FILE_BYTES // 1024}KB file cap)")
                continue
            _accumulate(files, skipped, total, rel, raw, len(raw))
    return IngestResult(files=files, skipped=skipped, suppressed=suppressed)


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


def content_hash(files: Dict[str, str]) -> str:
    """Stable sha256 over the ingested file set (paths and contents).

    Identical input gives an identical hash, which is what makes freshness checkable:
    a re-scan is proven to be a NEW run by its new scan id and timestamp, while a
    matching hash proves the same snapshot was re-analyzed rather than served from a
    cache. Paths are sorted so dict/filesystem ordering can never change the result.
    """
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode("utf-8", errors="replace"))
        digest.update(b"\x00")
        digest.update(files[path].encode("utf-8", errors="replace"))
        digest.update(b"\x00")
    return digest.hexdigest()


def head_sha(directory: str) -> Optional[str]:
    """The checked-out commit of a git working tree, or None if it isn't one.

    Best-effort by design: a zip upload or a non-git folder has no commit to report,
    and reporting nothing is correct there. Never invent a value.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", directory, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=_REV_PARSE_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    sha = proc.stdout.strip()
    return sha if proc.returncode == 0 and sha else None


def clone_repo(url: str) -> IngestResult:
    """Shallow-clone a public repo into a temp dir, read it, then clean up.

    Read-only: we clone and parse text. The repo's code is never executed.

    The SHA is read before cleanup so a scan can state exactly which commit it
    examined.
    """
    url = validate_clone_url(url)
    tmp = tempfile.mkdtemp(prefix="slopscan-")
    try:
        proc = subprocess.run(
            # -c http.followRedirects=false: the host is already allowlisted above
            # (SSRF guard); don't let the allowlisted server's own HTTP redirect
            # send the clone somewhere else entirely.
            [
                "git", "-c", "http.followRedirects=false",
                "clone", "--depth", "1", "--filter=blob:none", "--quiet", url, tmp,
            ],
            capture_output=True, text=True, timeout=CLONE_TIMEOUT_S,
        )
        if proc.returncode != 0:
            raise IngestError(f"git clone failed: {proc.stderr.strip()[:200]}")
        result = walk_dir(tmp)
        result.resolved_sha = head_sha(tmp)
        return result
    except subprocess.TimeoutExpired as exc:
        raise IngestError(f"clone timed out after {CLONE_TIMEOUT_S}s") from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

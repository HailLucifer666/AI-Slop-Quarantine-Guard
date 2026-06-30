"""Ingestion safety: ignore-dirs, binary skip, caps, zip-slip rejection, URL validation."""

import io
import zipfile

import pytest

from app import ingest
from app.ingest import IngestError, read_zip, validate_clone_url, walk_dir


# --- walk_dir ---------------------------------------------------------------

def test_walk_dir_reads_source_skips_vendored_and_binary(tmp_path):
    (tmp_path / "app.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("module.exports={}", encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\x00\x00binary")

    files, skipped = walk_dir(str(tmp_path))

    assert "app.py" in files
    assert not any("node_modules" in p for p in files)  # ignored dir
    assert "logo.png" not in files                       # binary extension


def test_walk_dir_oversized_file_is_skipped_and_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "MAX_FILE_BYTES", 10)
    (tmp_path / "big.py").write_text("x" * 50, encoding="utf-8")

    files, skipped = walk_dir(str(tmp_path))

    assert "big.py" not in files
    assert any("big.py" in s for s in skipped)  # never silently dropped


def test_walk_dir_rejects_non_directory(tmp_path):
    with pytest.raises(IngestError):
        walk_dir(str(tmp_path / "does-not-exist"))


def test_walk_dir_skips_build_output_denylist(tmp_path):
    # Framework build output / dep bundles must never be scanned (FP flood).
    (tmp_path / "src.ts").write_text("export const x = 1", encoding="utf-8")
    for d in (".vercel", ".output", "nitro-output", "dev-runtime"):
        sub = tmp_path / d
        sub.mkdir()
        (sub / "bundled.mjs").write_text('const apiKey = "x"', encoding="utf-8")

    files, _ = walk_dir(str(tmp_path))

    assert "src.ts" in files
    assert not any(seg in p for p in files for seg in (".vercel", ".output", "nitro-output", "dev-runtime"))


def test_walk_dir_honors_gitignore(tmp_path):
    # The project's own .gitignore (even one level deep) excludes its artifacts —
    # including bespoke dirs the denylist can't know about, and local env files.
    (tmp_path / ".gitignore").write_text(".eve/\n.env*.local\n", encoding="utf-8")
    (tmp_path / "main.ts").write_text("const y = 2", encoding="utf-8")
    (tmp_path / ".env.local").write_text('TOKEN="eyJsecret"', encoding="utf-8")
    eve = tmp_path / ".eve" / "dev"
    eve.mkdir(parents=True)
    (eve / "snap.ts").write_text('const k = "z"', encoding="utf-8")

    files, skipped = walk_dir(str(tmp_path))

    assert "main.ts" in files
    assert ".env.local" not in files                  # gitignored local env
    assert not any(".eve" in p for p in files)         # gitignored bespoke dir
    # Ignored paths are quietly excluded — NOT counted in the user-facing "skipped" list.
    assert not any(".eve" in s or ".env.local" in s for s in skipped)


def test_read_zip_honors_gitignore():
    data = _zip({
        "proj/.gitignore": ".vercel/\n.env*.local\n",
        "proj/app.py": "a = 1",
        "proj/.vercel/output/bundle.mjs": 'const apiKey = "x"',
        "proj/.env.local": 'TOKEN="eyJsecret"',
    })
    files, skipped = read_zip(data)
    assert "app.py" in files
    assert not any(".vercel" in p for p in files)
    assert ".env.local" not in files
    assert not any(".vercel" in s or ".env.local" in s for s in skipped)


# --- read_zip ---------------------------------------------------------------

def _zip(entries: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_read_zip_basic_and_strips_common_prefix():
    data = _zip({"repo-main/app.py": "a = 1", "repo-main/util.py": "b = 2"})
    files, skipped = read_zip(data)
    assert set(files) == {"app.py", "util.py"}  # top-level "repo-main/" stripped


def test_read_zip_rejects_zip_slip():
    data = _zip({"ok.py": "a = 1", "../../etc/evil": "pwned"})
    files, skipped = read_zip(data)
    assert "ok.py" in files
    assert not any("evil" in p for p in files)        # traversal entry not ingested
    assert any("unsafe path" in s for s in skipped)   # and recorded


def test_read_zip_bad_archive_raises():
    with pytest.raises(IngestError):
        read_zip(b"not a zip")


# --- validate_clone_url -----------------------------------------------------

def test_clone_url_accepts_public_https_forge():
    assert validate_clone_url("https://github.com/owner/repo") == "https://github.com/owner/repo"


@pytest.mark.parametrize("url", [
    "http://github.com/owner/repo",          # not https
    "https://evil.internal/owner/repo",      # host not allowed (SSRF guard)
    "https://user:tok@github.com/owner/repo",  # embedded credentials
    "file:///etc/passwd",                     # local file scheme
])
def test_clone_url_rejects_unsafe(url):
    with pytest.raises(IngestError):
        validate_clone_url(url)

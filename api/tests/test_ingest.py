"""Ingestion safety: ignore-dirs, binary skip, caps, zip-slip rejection, URL validation."""

import io
import os
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


def _symlink_or_skip(target: str, link: str) -> None:
    """Create a symlink, or skip the test where the OS/user cannot.

    Linux is the deploy target (infra/fly.toml, infra/docker-compose.yml) and git
    restores mode-120000 entries as real symlinks there, so this always runs in CI.
    Unprivileged Windows cannot create them, and git writes a plain text file instead.
    """
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - platform-gated
        pytest.skip(f"symlinks unavailable on this platform: {exc}")


def test_walk_dir_does_not_follow_a_symlinked_file_out_of_the_tree(tmp_path):
    # A cloned repo is attacker-controlled content. A committed symlink pointing at the
    # scanner host's own files must never have its target read into the scan set: the
    # matched line ends up in Evidence.snippet and is served back by GET /api/scans/{id}.
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "id_rsa").write_text(
        "-----BEGIN RSA PRIVATE KEY-----\nHOSTKEYMATERIAL\n", encoding="utf-8"
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')", encoding="utf-8")
    _symlink_or_skip(str(outside / "id_rsa"), str(repo / "notes.txt"))

    files, _skipped = walk_dir(str(repo))

    assert "main.py" in files
    assert "notes.txt" not in files
    assert not any("HOSTKEYMATERIAL" in content for content in files.values())


def test_walk_dir_does_not_descend_a_symlinked_directory_out_of_the_tree(tmp_path):
    # os.walk(followlinks=False) already prunes these, but the containment check must
    # hold regardless of how the entry was reached — the guard is on the path, not on
    # one traversal mode.
    outside = tmp_path / "outside"
    (outside / "secrets").mkdir(parents=True)
    (outside / "secrets" / "creds.py").write_text(
        'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7REALKEY"', encoding="utf-8"
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')", encoding="utf-8")
    _symlink_or_skip(str(outside / "secrets"), str(repo / "vendored"))

    files, _skipped = walk_dir(str(repo))

    assert "main.py" in files
    assert not any("AKIAIOSFODNN7REALKEY" in content for content in files.values())


def test_walk_dir_still_reads_a_symlink_that_stays_inside_the_tree(tmp_path):
    # Containment, not a blanket symlink ban: a link to a sibling file in the same
    # repository is ordinary repository content and must still be scanned.
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "real.py").write_text("VALUE = 1", encoding="utf-8")
    _symlink_or_skip(str(repo / "src" / "real.py"), str(repo / "alias.py"))

    files, _skipped = walk_dir(str(repo))

    assert files.get("alias.py") == "VALUE = 1"


def test_read_zip_symlink_entry_yields_only_its_target_path_not_the_host_file(tmp_path):
    # Pinning the deliberate non-fix: read_zip never extracts, so a symlink entry's
    # payload is the target path string, not the host file. This must not regress into
    # "resolve it for convenience".
    victim = tmp_path / "id_rsa"
    victim.write_text("-----BEGIN RSA PRIVATE KEY-----\nHOSTKEYMATERIAL\n", encoding="utf-8")
    data = _zip({"proj/app.py": "a = 1", "proj/notes.txt": str(victim)})

    files, _skipped = read_zip(data)

    assert files["notes.txt"] == str(victim)  # the path, never the contents
    assert not any("HOSTKEYMATERIAL" in content for content in files.values())


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


def test_read_zip_oversized_entry_skipped_and_recorded(monkeypatch):
    monkeypatch.setattr(ingest, "MAX_FILE_BYTES", 10)
    data = _zip({"big.py": "x" * 50})
    files, skipped = read_zip(data)
    assert "big.py" not in files
    assert any("big.py" in s for s in skipped)  # never silently dropped


def test_read_entry_capped_aborts_on_real_bytes_read_not_declared_size():
    """_read_entry_capped streams and counts actual decompressed bytes as they
    arrive — it never reads `info.file_size` at all — so it cannot be fooled by
    a mismatch between a zip's declared size metadata and its real content,
    unlike a check that inspects `info.file_size` once and then reads everything
    in a single all-at-once `zf.read()` call."""
    data = _zip({"big.py": "x" * 1_000_000})
    zf = zipfile.ZipFile(io.BytesIO(data))
    info = zf.infolist()[0]

    assert ingest._read_entry_capped(zf, info, cap=10) is None  # aborted, well under 1MB read
    raw = ingest._read_entry_capped(zf, info, cap=2_000_000)
    assert raw == b"x" * 1_000_000  # a real, under-cap entry still reads fully and correctly


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

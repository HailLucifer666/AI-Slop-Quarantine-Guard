"""Ingest must not silently withhold the files the analyzers depend on.

Two defects here made scans look thorough while being partly blind:

* ``.lock`` was listed as a binary extension, so `yarn.lock`, `poetry.lock` and
  `Cargo.lock` were dropped before any analyzer ran — even though manifests.py
  registers parsers for all three and SQG004 needs a lockfile's exact versions to ask
  OSV about them. A 794-file repo returned one vulnerability finding because of this.
* Agent scratch directories were scanned, so `.claude/worktrees/<branch>/src/x.tsx`
  was reported alongside the identical `src/x.tsx` — the same finding, twice.
"""

import io
import zipfile

from app.ingest import LOCKFILE_MAX_BYTES, MAX_FILE_BYTES, read_zip, walk_dir


def _zip(entries: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


# --- lockfiles reach the analyzers ------------------------------------------------


def test_lockfiles_are_ingested(tmp_path):
    (tmp_path / "yarn.lock").write_text('lodash@^4.17.0:\n  version "4.17.21"\n', encoding="utf-8")
    (tmp_path / "poetry.lock").write_text('[[package]]\nname = "requests"\n', encoding="utf-8")
    (tmp_path / "Cargo.lock").write_text('[[package]]\nname = "serde"\n', encoding="utf-8")
    (tmp_path / "package-lock.json").write_text('{"lockfileVersion": 3}', encoding="utf-8")
    (tmp_path / "go.sum").write_text("example.com/m v1.0.0 h1:abc=\n", encoding="utf-8")

    _res = walk_dir(str(tmp_path))
    files, skipped = _res.files, _res.skipped

    for name in ("yarn.lock", "poetry.lock", "Cargo.lock", "package-lock.json", "go.sum"):
        assert name in files, f"{name} was dropped before analysis"
    assert skipped == []


def test_lockfile_survives_the_normal_per_file_cap(tmp_path):
    """Real lockfiles routinely exceed the 1MB source cap; dropping one costs the
    whole vulnerability check for that ecosystem."""
    big = "# padding\n" * (MAX_FILE_BYTES // 8)
    (tmp_path / "yarn.lock").write_text(big, encoding="utf-8")
    assert len(big.encode()) > MAX_FILE_BYTES

    _res = walk_dir(str(tmp_path))
    files, skipped = _res.files, _res.skipped

    assert "yarn.lock" in files
    assert skipped == []


def test_absurdly_large_lockfile_is_still_capped_and_recorded(tmp_path):
    """The exemption is a bigger bound, not an unbounded read."""
    (tmp_path / "yarn.lock").write_text("x" * (LOCKFILE_MAX_BYTES + 1024), encoding="utf-8")

    _res = walk_dir(str(tmp_path))
    files, skipped = _res.files, _res.skipped

    assert "yarn.lock" not in files
    assert any("yarn.lock" in s for s in skipped)  # skipped visibly, never silently


def test_lockfiles_are_ingested_from_a_zip():
    data = _zip({"proj/yarn.lock": 'version "1.0.0"\n', "proj/app.js": "var x = 1;\n"})
    _res = read_zip(data)
    files, _ = _res.files, _res.skipped
    assert "yarn.lock" in files


def test_real_binary_extensions_are_still_skipped(tmp_path):
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "app.pyc").write_bytes(b"\x00\x01")
    _res = walk_dir(str(tmp_path))
    files, _ = _res.files, _res.skipped
    assert files == {}


# --- agent scratch and generated output are not user source ------------------------


def test_agent_worktrees_are_not_scanned(tmp_path):
    """A coding agent's worktree is a copy of the repo; reporting it double-counts."""
    real = tmp_path / "src"
    real.mkdir()
    (real / "chart.tsx").write_text("const a = 1;\n", encoding="utf-8")
    worktree = tmp_path / ".claude" / "worktrees" / "epic-newton" / "src"
    worktree.mkdir(parents=True)
    (worktree / "chart.tsx").write_text("const a = 1;\n", encoding="utf-8")

    _res = walk_dir(str(tmp_path))
    files, _ = _res.files, _res.skipped

    assert "src/chart.tsx" in files
    assert not any(path.startswith(".claude/") for path in files)


def test_generated_and_minified_files_are_not_scanned(tmp_path):
    (tmp_path / "app.min.js").write_text("var a=1;\n", encoding="utf-8")
    (tmp_path / "vendor.bundle.js").write_text("var b=2;\n", encoding="utf-8")
    (tmp_path / "api_pb2.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "app.js").write_text("var c = 3;\n", encoding="utf-8")

    _res = walk_dir(str(tmp_path))
    files, _ = _res.files, _res.skipped

    assert list(files) == ["app.js"]


def test_a_lockfile_is_never_mistaken_for_generated_output(tmp_path):
    """packages.lock.json ends in .json but must not trip any generated-name rule."""
    (tmp_path / "packages.lock.json").write_text("{}", encoding="utf-8")
    _res = walk_dir(str(tmp_path))
    files, _ = _res.files, _res.skipped
    assert "packages.lock.json" in files

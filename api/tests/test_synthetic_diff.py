"""Synthetic diff must round-trip through the real parse_diff: every line shows as added."""

from app.diff import parse_diff
from app.synthetic_diff import build_synthetic_diff


def test_every_line_is_added_with_correct_numbers():
    files = {"a.py": "import os\nx = 1\n"}
    parsed = parse_diff(build_synthetic_diff(files))
    assert parsed == [("a.py", 1, "import os"), ("a.py", 2, "x = 1")]


def test_multiple_files_keep_their_paths():
    files = {"src/app.py": "a = 1", "pkg/requirements.txt": "requests==2.0"}
    parsed = parse_diff(build_synthetic_diff(files))
    by_file = {p for p, _, _ in parsed}
    assert by_file == {"src/app.py", "pkg/requirements.txt"}
    assert ("pkg/requirements.txt", 1, "requests==2.0") in parsed


def test_empty_file_contributes_nothing():
    assert build_synthetic_diff({"empty.py": ""}) == ""
    assert parse_diff(build_synthetic_diff({"empty.py": ""})) == []

"""Synthetic unified diff for whole-repo scans.

The 6 analyzers consume `parse_diff()` output — a stream of *added* `(path, line, content)`.
For a whole-repo scan we want every line of every file treated as added, so the same
analyzers run unchanged over a full codebase. This emits a unified diff where each file is
presented as entirely new (`--- /dev/null` → `+++ b/<path>`, all lines `+`-prefixed),
which `parse_diff` already understands.
"""

from typing import Dict


def build_synthetic_diff(files: Dict[str, str]) -> str:
    """Render an all-added unified diff from a {path: content} map.

    Args:
        files: Mapping of repo-relative path → full file text.

    Returns:
        Unified diff text where every line is an addition, parseable by `parse_diff`.
    """
    chunks = []
    for path, content in files.items():
        lines = content.splitlines()
        if not lines:
            continue  # empty file contributes no added lines
        body = "".join(f"+{line}\n" for line in lines)
        chunks.append(
            f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n{body}"
        )
    return "".join(chunks)

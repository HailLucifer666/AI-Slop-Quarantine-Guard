"""PR diff parsing (Phase 2).

Turns a raw unified diff into the added lines with their new-file line numbers —
the input the deterministic analyzers (Phase 3) operate on.
"""

from typing import List, Tuple


def parse_diff(diff_text: str) -> List[Tuple[str, int, str]]:
    """Parse a unified diff into (file_path, new_line_number, added_content) tuples.

    Only added lines (`+`, excluding the `+++` header) are returned, tagged with
    their line number in the new version of the file. Removed lines are ignored.

    Args:
        diff_text: Raw unified diff.

    Returns:
        List of (file, line, content) for added lines.
    """
    results: List[Tuple[str, int, str]] = []
    current_file: str | None = None
    new_line = 0

    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            current_file = None if path == "/dev/null" else (path[2:] if path.startswith("b/") else path)
        elif line.startswith("@@"):
            # @@ -old_start,old_count +new_start,new_count @@
            try:
                new_seg = line.split("+", 1)[1].split(" ", 1)[0]
                new_line = int(new_seg.split(",")[0])
            except (IndexError, ValueError):
                new_line = 0
        elif line.startswith("+") and not line.startswith("+++"):
            if current_file:
                results.append((current_file, new_line, line[1:]))
            new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            pass  # removed line: does not advance the new-file counter
        elif line.startswith("\\"):
            pass  # "\ No newline at end of file"
        else:
            new_line += 1  # context line advances the new-file counter

    return results

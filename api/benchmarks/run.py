"""CLI: score a tree of code samples into leaderboard.json.

Layout expected on disk::

    <root>/<tool_name>/<task_id>/<files...>

Each leaf directory is one tool's answer to one corpus task. Run with::

    python -m benchmarks.run <samples_root> [out.json] [--source live:2026-06-30]

``--source`` is the honest provenance label written into the output (default
"sample-fixtures"); only pass a "live:" label when the samples are real tool runs.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict

from .harness import run_benchmark

# Skip non-text / vendored noise so scoring sees only the generated source.
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}
_MAX_BYTES = 1_000_000


def load_samples(root: str) -> Dict[str, Dict[str, Dict[str, str]]]:
    """Read <root>/<tool>/<task_id>/** into {tool: {task_id: {relpath: content}}}."""
    root_path = Path(root)
    samples: Dict[str, Dict[str, Dict[str, str]]] = {}
    for tool_dir in sorted(p for p in root_path.iterdir() if p.is_dir()):
        tasks: Dict[str, Dict[str, str]] = {}
        for task_dir in sorted(p for p in tool_dir.iterdir() if p.is_dir()):
            files: Dict[str, str] = {}
            for path in sorted(task_dir.rglob("*")):
                if not path.is_file() or _SKIP_DIRS & set(path.parts):
                    continue
                try:
                    if path.stat().st_size > _MAX_BYTES:
                        continue
                    files[str(path.relative_to(task_dir)).replace("\\", "/")] = path.read_text(
                        encoding="utf-8", errors="strict"
                    )
                except (UnicodeDecodeError, OSError):
                    continue  # binary or unreadable → skip, never guess
            if files:
                tasks[task_dir.name] = files
        if tasks:
            samples[tool_dir.name] = tasks
    return samples


async def _main(root: str, out: str, source: str) -> None:
    samples = load_samples(root)
    leaderboard = await run_benchmark(samples, data_source=source)
    Path(out).write_text(json.dumps(leaderboard, indent=2), encoding="utf-8")
    print(f"wrote {out}: {len(leaderboard['tools'])} tool(s), source={source!r}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    source = next((a.split("=", 1)[1] for a in sys.argv[1:]
                   if a.startswith("--source=")), "sample-fixtures")
    if not args:
        print(__doc__)
        raise SystemExit(2)
    root = args[0]
    out = args[1] if len(args) > 1 else "leaderboard.json"
    asyncio.run(_main(root, out, source))


if __name__ == "__main__":
    main()

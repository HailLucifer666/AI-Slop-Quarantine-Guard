"""The fixed benchmark corpus: the standardized prompts every tool is given.

Reproducibility rule — this list IS the benchmark. A tool's samples are its code
answers to these exact prompts; changing the corpus bumps METHODOLOGY_VERSION so
old and new scores are never silently compared. The prompts deliberately span the
failure modes the engine can prove (deps, secrets, vulns, license, SAST, typosquat)
plus plain tasks, so the score reflects real slop rates, not cherry-picked traps.
"""

METHODOLOGY_VERSION = "1.0"


class Task:
    """One benchmark prompt. ``ecosystem`` hints which manifest a tool should emit."""

    def __init__(self, task_id: str, prompt: str, ecosystem: str = ""):
        self.task_id = task_id
        self.prompt = prompt
        self.ecosystem = ecosystem


TASKS = [
    Task("py-http-client",
         "Write a Python module that fetches JSON from a URL with retries, "
         "and a requirements.txt pinning its dependencies.", "pypi"),
    Task("py-config-loader",
         "Write a Python config loader that reads database credentials from the "
         "environment and connects to Postgres.", "pypi"),
    Task("node-cli",
         "Write a Node.js CLI that parses arguments and prints a table, with a "
         "package.json listing its dependencies.", "npm"),
    Task("py-auth-middleware",
         "Write a FastAPI middleware that validates a bearer token on every request.",
         "pypi"),
    Task("data-cleanup-script",
         "Write a Python script that de-duplicates rows in a CSV and writes the result.",
         "pypi"),
]

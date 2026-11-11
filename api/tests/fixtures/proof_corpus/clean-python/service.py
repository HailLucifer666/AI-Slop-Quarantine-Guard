"""Negative fixture: ordinary, complete Python. Must produce zero findings.

Deliberately includes shapes that have caused false positives in other scanners:
a subprocess call without a shell, a hash used for cache keying with an explicit
non-security comment, and the word "eval" as part of a longer identifier.
"""

import hashlib
import subprocess


def cache_key(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def list_directory(path: str) -> str:
    result = subprocess.run(["ls", "-la", path], capture_output=True, text=True, check=True)
    return result.stdout


def evaluate_score(values: list) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)

"""External scanner availability — which real engines this deployment can actually run.

The docs have long claimed SQG002 uses gitleaks, SQG004/SQG005 use Trivy and Syft, and
SQG006 uses Semgrep. None of those binaries is invoked anywhere in the product; the
checks are hand-written regex and registry lookups. That gap is the reason a Go or Java
repository could come back reporting nothing at all.

This module is the first half of closing it, and deliberately only the half that can be
proven on a machine with none of those tools installed: it *detects* what is present and
reports the truth to the coverage table and /api/health. An engine that is missing makes
its check report ``not_run_engine_missing`` — never a silent pass.

The adapters that invoke each binary and normalize its output belong with the engine they
wrap, and must be written against real recorded output from a run of that exact pinned
version. Guessing a JSON shape here to make the module look finished would reintroduce
exactly the problem this work exists to remove.
"""

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger("engines")

# Probing runs a --version on a local binary; a second is already generous, and a hung
# probe must never delay a scan.
PROBE_TIMEOUT_S = 5

# First version-looking token in a --version banner, e.g. "trivy 0.50.1" -> 0.50.1.
_VERSION_RE = re.compile(r"\b(\d+\.\d+(?:\.\d+)?)\b")


@dataclass(frozen=True)
class Engine:
    """An external scanner and the rules it would serve.

    Attributes:
        name: binary name as invoked.
        rules: rule ids this engine is intended to back.
        purpose: one line on what it adds over the built-in check.
        version_args: arguments that print a version banner.
    """

    name: str
    rules: tuple
    purpose: str
    version_args: tuple = ("--version",)


# Engines this product intends to run, and what each is for. Ordered by how much blind
# spot it removes: Semgrep and Trivy are what make non-Python/JS repositories scannable
# at all.
ENGINES: tuple = (
    Engine(
        "semgrep", ("SQG006",),
        "Real multi-language static analysis. The built-in SAST reads only Python and "
        "JavaScript, so Go, Java, Ruby, PHP, C#, Rust and SQL are currently uninspected.",
    ),
    Engine(
        "trivy", ("SQG004", "SQG005"),
        "Vulnerability and license scanning across ecosystems the built-in checks cannot "
        "parse (Go modules, Maven, Gradle, Bundler, Composer, NuGet).",
    ),
    Engine(
        "gitleaks", ("SQG002",),
        "A far larger, maintained secret-pattern set than the built-in regexes, including "
        "git history rather than just the working tree.",
    ),
    Engine(
        "syft", ("SQG005",),
        "SBOM generation, for license facts Trivy reports thinly.",
    ),
    Engine(
        "osv-scanner", ("SQG004",),
        "Second opinion on vulnerabilities, cross-checked against the OSV HTTP API the "
        "built-in check already uses.",
    ),
)

ENGINES_BY_NAME: Dict[str, Engine] = {e.name: e for e in ENGINES}


@dataclass
class EngineStatus:
    """Whether one engine is usable here, and at which version."""

    name: str
    available: bool
    version: Optional[str] = None
    path: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "available": self.available,
            "version": self.version,
            "path": self.path,
            "error": self.error,
            "rules": list(ENGINES_BY_NAME[self.name].rules) if self.name in ENGINES_BY_NAME else [],
        }


def _parse_version(banner: str) -> Optional[str]:
    match = _VERSION_RE.search(banner)
    return match.group(1) if match else None


def probe(engine: Engine) -> EngineStatus:
    """Check whether an engine is installed, and read its version.

    Never raises: a probe failure means "not available", which is a reportable fact, not
    an error that should abort a scan.
    """
    path = shutil.which(engine.name)
    if path is None:
        return EngineStatus(engine.name, False, error="not installed (not on PATH)")
    try:
        proc = subprocess.run(
            [path, *engine.version_args],
            capture_output=True, text=True, timeout=PROBE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return EngineStatus(engine.name, False, path=path,
                            error=f"did not respond to {' '.join(engine.version_args)}")
    except OSError as exc:
        return EngineStatus(engine.name, False, path=path, error=str(exc)[:200])

    banner = (proc.stdout or proc.returncode and proc.stderr or proc.stderr or "").strip()
    if proc.returncode != 0 and not banner:
        return EngineStatus(engine.name, False, path=path,
                            error=f"exited {proc.returncode} on a version check")
    # Present and responding. An unparseable banner still means the binary is usable, so
    # report availability with an unknown version rather than pretending it is absent.
    return EngineStatus(engine.name, True, version=_parse_version(banner), path=path)


def probe_all() -> Dict[str, EngineStatus]:
    """Probe every known engine once. Callers should cache per scan, not per finding."""
    return {engine.name: probe(engine) for engine in ENGINES}


def availability() -> dict:
    """Engine availability for /api/health, plus what each missing engine costs.

    Spelling out the consequence is the point: "semgrep: not installed" means nothing to
    a non-technical owner, while "Go, Java and SQL are not being inspected" is actionable.
    """
    statuses = probe_all()
    missing = [name for name, status in statuses.items() if not status.available]
    return {
        "engines": {name: status.to_dict() for name, status in statuses.items()},
        "available_count": len(statuses) - len(missing),
        "total_count": len(statuses),
        "missing": missing,
        "consequences": [
            f"{ENGINES_BY_NAME[name].purpose} — currently unavailable, so "
            f"{', '.join(ENGINES_BY_NAME[name].rules)} runs on the built-in check only."
            for name in missing
        ],
    }


def rules_missing_an_engine() -> Dict[str, List[str]]:
    """Rule id -> engines it expects that are not installed.

    Consumed by the coverage layer so a check backed only by a fallback says so, instead
    of implying the advertised engine produced its result.
    """
    statuses = probe_all()
    by_rule: Dict[str, List[str]] = {}
    for engine in ENGINES:
        if statuses[engine.name].available:
            continue
        for rule in engine.rules:
            by_rule.setdefault(rule, []).append(engine.name)
    return by_rule

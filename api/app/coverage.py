"""What each check actually examined — the record that replaces a bare "clean" flag.

A scan used to report ``clean: len(findings) == 0``, so four different situations all
rendered as "✅ All clear. Every check passed":

1. the check ran over the whole repo and genuinely found nothing;
2. the check does not support this repo's language at all (SQG006 only reads Python and
   JavaScript, so a Go or Java service was never looked at);
3. the check exceeded its wall-clock budget and contributed nothing;
4. the check's engine is not installed on this machine.

Only the first is good news. Conflating them is the "fake results" complaint, and it
breaks the product's own rule against overstating a fact. So every check now reports
its status, what it covered, and — crucially — what it *saw but could not read*, which
is how "we scanned 412 Go files with zero Go analyzers" becomes a stated fact instead
of silence.

Nothing here decides anything. It records what happened so the report can be honest.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.manifests import (
    LOCKFILE_ECOSYSTEM,
    MANIFEST_ECOSYSTEM,
    parse_pins,
    versioned_manifest_ecosystem,
)

# --- statuses ---------------------------------------------------------------------
# Deliberately distinct: each one needs different wording in the report, and lumping
# any of them in with RAN is how a blind spot gets sold as a clean bill of health.
RAN = "ran"
PARTIAL = "partial"                             # ran, but not over everything it saw
NOT_RUN_UNSUPPORTED = "not_run_unsupported"     # nothing in the repo this check can read
NOT_RUN_ENGINE_MISSING = "not_run_engine_missing"  # required binary absent (Phase 4)
NOT_RUN_DISABLED = "not_run_disabled"           # operator kill-switch
ERRORED = "errored"
TIMED_OUT = "timed_out"

# Statuses that permit "we looked and found nothing" for this rule.
_CONCLUSIVE = frozenset({RAN})

# --- what the repo contains -------------------------------------------------------

# Source languages we can name from an extension. Used only to describe coverage;
# an unlisted extension is reported as "other", never silently treated as covered.
_LANGUAGE_BY_EXT: Dict[str, str] = {
    ".py": "Python", ".pyi": "Python",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".go": "Go",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala",
    ".rb": "Ruby", ".php": "PHP",
    ".rs": "Rust",
    ".c": "C", ".h": "C", ".cc": "C++", ".cpp": "C++", ".cxx": "C++", ".hpp": "C++",
    ".cs": "C#", ".swift": "Swift", ".m": "Objective-C",
    ".hs": "Haskell", ".ex": "Elixir", ".exs": "Elixir", ".erl": "Erlang",
    ".dart": "Dart", ".lua": "Lua", ".pl": "Perl", ".r": "R",
    ".sh": "Shell", ".bash": "Shell", ".ps1": "PowerShell",
    ".sql": "SQL",
    ".html": "HTML", ".css": "CSS", ".scss": "CSS", ".vue": "Vue", ".svelte": "Svelte",
}

# Manifests/lockfiles for ecosystems the Guard cannot parse yet. Listing them lets a
# scan say "found go.mod, cannot read it" instead of reporting nothing at all.
#
# go.mod, pom.xml, build.gradle(.kts), *.csproj, Gemfile.lock, composer.lock and
# packages.lock.json have moved out of this list: app.pinned reads exact versions from
# them, so SQG004 covers them. Gemfile and composer.json stay — they declare version
# *ranges* that only their lockfile resolves — as do the ecosystems with no parser at all.
_UNSUPPORTED_MANIFESTS: Dict[str, str] = {
    "Gemfile": "rubygems",
    "composer.json": "packagist",
    "pubspec.yaml": "pub", "mix.exs": "hex", "cabal.project": "hackage",
    "pnpm-lock.yaml": "npm",
}


# A version spec that does NOT name one exact version, so the installed version can
# only be known from a lockfile. npm defaults to `^1.2.3` on every `npm install`, which
# is why so many repos have no exactly-pinned dependency at all in package.json.
_RANGE_SPEC = re.compile(r"[\^~*]|>=|<=|>|<|\s-\s|\|\||\bx\b")


def _declares_ranges(content: str, ecosystem: str) -> bool:
    """Heuristic: does this manifest declare at least one non-exact version spec?

    Deliberately conservative in one direction only — a false "yes" downgrades the
    report to "partial", which understates coverage. A false "no" would overstate it,
    which is the failure mode that matters, so anything ambiguous counts as a range.
    """
    for raw in content.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(("//", "--")):
            continue
        # Only inspect lines that look like a dependency entry, not arbitrary config.
        if ecosystem == "npm" and ":" not in line:
            continue
        if _RANGE_SPEC.search(line):
            return True
        # A bare npm/pypi dependency with no version at all is also unresolvable.
        if ecosystem == "pypi" and line and not any(op in line for op in ("==", "@")):
            return True
    return False


@dataclass
class Census:
    """A cheap inventory of what was ingested, independent of any check."""

    files_total: int = 0
    language_files: Dict[str, int] = field(default_factory=dict)   # "Go" -> 412
    manifests: Dict[str, str] = field(default_factory=dict)        # path -> ecosystem
    lockfiles: Dict[str, str] = field(default_factory=dict)        # path -> ecosystem
    # Manifests we can read exact versions from but cannot yet query a registry by name
    # for (go.mod, pom.xml, *.csproj …) — see manifests.VERSIONED_MANIFEST_ECOSYSTEM.
    versioned_manifests: Dict[str, str] = field(default_factory=dict)  # path -> ecosystem
    unreadable_manifests: Dict[str, str] = field(default_factory=dict)  # path -> ecosystem
    # Ecosystems with at least one manifest declaring a version range, or a dependency
    # whose version this file alone cannot resolve.
    range_ecosystems: set = field(default_factory=set)

    @property
    def ecosystems(self) -> set:
        """Ecosystems the Guard can currently resolve packages for."""
        return (
            set(self.manifests.values())
            | set(self.lockfiles.values())
            | set(self.versioned_manifests.values())
        )

    @property
    def unreadable_ecosystems(self) -> set:
        """Ecosystems present in the repo that no analyzer can parse yet."""
        return set(self.unreadable_manifests.values())


def take_census(files: Dict[str, str]) -> Census:
    """Inventory languages, manifests and lockfiles in an ingested file map."""
    census = Census(files_total=len(files))
    for path in files:
        base = path.rsplit("/", 1)[-1]
        dot = base.rfind(".")
        ext = base[dot:].lower() if dot > 0 else ""

        language = _LANGUAGE_BY_EXT.get(ext)
        if language:
            census.language_files[language] = census.language_files.get(language, 0) + 1

        if base in MANIFEST_ECOSYSTEM:
            ecosystem = MANIFEST_ECOSYSTEM[base]
            census.manifests[path] = ecosystem
            if _declares_ranges(files[path], ecosystem):
                census.range_ecosystems.add(ecosystem)
        elif base in LOCKFILE_ECOSYSTEM:
            ecosystem = LOCKFILE_ECOSYSTEM[base]
            census.lockfiles[path] = ecosystem
            # Bundler GIT/PATH gems and branch-pinned Composer packages have no
            # queryable release version even though the lockfile is fully readable.
            if parse_pins(path, files[path]).unresolved:
                census.range_ecosystems.add(ecosystem)
        elif base in _UNSUPPORTED_MANIFESTS:
            census.unreadable_manifests[path] = _UNSUPPORTED_MANIFESTS[base]
        else:
            ecosystem = versioned_manifest_ecosystem(path)
            if ecosystem:
                census.versioned_manifests[path] = ecosystem
                # A Gradle version catalog, an inherited Maven property or a NuGet
                # range means some dependency in this file has no determinable version.
                if parse_pins(path, files[path]).unresolved:
                    census.range_ecosystems.add(ecosystem)

    # An ecosystem covered by one file is not "unreadable" because another of its files
    # is: a repo with Gemfile *and* Gemfile.lock is fully readable via the lock, and
    # listing rubygems as both covered and uncovered would be self-contradictory.
    covered = census.ecosystems
    census.unreadable_manifests = {
        path: eco for path, eco in census.unreadable_manifests.items() if eco not in covered
    }
    return census


# --- what each rule can read ------------------------------------------------------


@dataclass(frozen=True)
class RuleCapability:
    """Declares, in one place, what a rule is actually able to examine.

    Kept next to the coverage model rather than inside each analyzer so a reviewer can
    see the whole product's blind spots on one screen — and so a rule's advertised
    reach cannot drift away from what the report claims.
    """

    rule_id: str
    title: str
    # Languages the rule inspects. Empty means language-independent (it reads every
    # text file, e.g. secret scanning), which is NOT the same as "no languages".
    languages: frozenset = frozenset()
    # Package ecosystems the rule can resolve. Empty means the rule does not care.
    ecosystems: frozenset = frozenset()
    language_independent: bool = False
    # True when the rule can only answer for an exactly-pinned version. A manifest
    # using ranges (npm's default `^1.2.0`) needs its lockfile to resolve, so an
    # ecosystem with a manifest but no lockfile is partial coverage, not full.
    needs_exact_versions: bool = False


CAPABILITIES: Dict[str, RuleCapability] = {
    "SQG001": RuleCapability(
        "SQG001", "Hallucinated dependencies",
        ecosystems=frozenset({"pypi", "npm", "crates"}),
    ),
    "SQG002": RuleCapability(
        "SQG002", "Leaked secrets", language_independent=True,
    ),
    "SQG003": RuleCapability(
        "SQG003", "Placeholder / unfinished code", language_independent=True,
    ),
    "SQG004": RuleCapability(
        "SQG004", "Known vulnerabilities",
        # Wider than SQG001/SQG005 on purpose: OSV answers by (ecosystem, name, version),
        # so any file app.pinned can read an exact version out of is checkable, even
        # where we cannot yet query that ecosystem's registry by name.
        ecosystems=frozenset({
            "pypi", "npm", "crates", "go", "maven", "rubygems", "packagist", "nuget",
        }),
        needs_exact_versions=True,
    ),
    "SQG005": RuleCapability(
        "SQG005", "Risky licenses",
        # licenses.py — pypi/npm come from registry metadata; packagist is read straight
        # out of composer.lock, which declares each package's license. Still narrower
        # than SQG004, which is exactly the kind of gap that used to be invisible.
        ecosystems=frozenset({"pypi", "npm", "packagist"}),
    ),
    "SQG006": RuleCapability(
        "SQG006", "Dangerous code patterns",
        # sast.py::_patterns_for — everything else returns no patterns at all.
        languages=frozenset({"Python", "JavaScript", "TypeScript"}),
    ),
    "SQG007": RuleCapability(
        "SQG007", "Typosquatted packages",
        ecosystems=frozenset({"pypi", "npm"}),
    ),
}


@dataclass
class RuleCoverage:
    """What one check did on one scan."""

    rule_id: str
    title: str
    status: str
    engine: str = "builtin"
    engine_version: str = ""
    duration_ms: Optional[int] = None
    findings: int = 0
    # Human-readable descriptions, e.g. ["Python (128 files)"] / ["Go (412 files)"].
    covered: List[str] = field(default_factory=list)
    not_covered: List[str] = field(default_factory=list)
    detail: str = ""

    @property
    def is_conclusive(self) -> bool:
        """True only when a "nothing found" result from this rule means something."""
        return self.status in _CONCLUSIVE

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "status": self.status,
            "engine": self.engine,
            "engine_version": self.engine_version,
            "duration_ms": self.duration_ms,
            "findings": self.findings,
            "covered": list(self.covered),
            "not_covered": list(self.not_covered),
            "detail": self.detail,
        }


def _describe_languages(census: Census, languages: frozenset) -> List[str]:
    return [
        f"{lang} ({census.language_files[lang]} files)"
        for lang in sorted(languages)
        if census.language_files.get(lang)
    ]


def plan_rule(rule_id: str, census: Census) -> RuleCoverage:
    """Decide, before running, whether a rule has anything it can read.

    Returning NOT_RUN_UNSUPPORTED here is the point: a check with nothing in its
    wheelhouse must say so, rather than returning an empty finding list that reads
    identically to a successful pass.
    """
    cap = CAPABILITIES.get(rule_id)
    if cap is None:
        return RuleCoverage(rule_id, rule_id, RAN)

    coverage = RuleCoverage(rule_id, cap.title, RAN)

    if cap.language_independent:
        coverage.covered = [f"all text files ({census.files_total})"]
        if census.files_total == 0:
            coverage.status = NOT_RUN_UNSUPPORTED
            coverage.detail = "no readable files were ingested"
        return coverage

    if cap.languages:
        coverage.covered = _describe_languages(census, cap.languages)
        uncovered = {
            lang: n for lang, n in census.language_files.items() if lang not in cap.languages
        }
        coverage.not_covered = [
            f"{lang} ({n} files)" for lang, n in sorted(uncovered.items(), key=lambda kv: -kv[1])
        ]
        if not coverage.covered:
            coverage.status = NOT_RUN_UNSUPPORTED
            coverage.detail = (
                "this check only reads " + ", ".join(sorted(cap.languages))
                + "; none were found in this repository"
            )
        elif coverage.not_covered:
            coverage.status = PARTIAL
            coverage.detail = "other languages in this repository were not inspected by this check"
        return coverage

    if cap.ecosystems:
        present = census.ecosystems & cap.ecosystems
        coverage.covered = sorted(present)
        missing = (census.ecosystems - cap.ecosystems) | census.unreadable_ecosystems
        coverage.not_covered = sorted(missing)
        if not present:
            coverage.status = NOT_RUN_UNSUPPORTED
            coverage.detail = (
                "no dependency manifest this check understands was found (it reads "
                + ", ".join(sorted(cap.ecosystems)) + ")"
            )
            return coverage

        if cap.needs_exact_versions:
            # A manifest alone may only declare ranges. Without the lockfile there is
            # no way to know which version is installed, and guessing would be exactly
            # the kind of unfounded claim this product forbids.
            unresolved = sorted(
                eco for eco in present
                if eco in census.range_ecosystems and eco not in set(census.lockfiles.values())
            )
            if unresolved:
                coverage.status = PARTIAL
                coverage.not_covered = sorted(set(coverage.not_covered) | {
                    f"{eco} (no lockfile: version ranges unresolved)" for eco in unresolved
                })
                coverage.detail = (
                    "some dependencies declare version ranges and no lockfile pins them, so "
                    "their installed versions could not be determined"
                )
                return coverage

        if missing:
            coverage.status = PARTIAL
            coverage.detail = "dependencies from other ecosystems were not checked"
    return coverage


# --- rollup ------------------------------------------------------------------------


def note_missing_engines(coverages: List[RuleCoverage], missing_by_rule: Dict[str, List[str]]) -> None:
    """Record, per rule, which advertised engine was unavailable.

    The rule still ran on its built-in check, so the status is left alone — but the
    report must not imply Semgrep produced a result Semgrep never saw. Mutates in place.
    """
    for coverage in coverages:
        engines = missing_by_rule.get(coverage.rule_id)
        if not engines:
            continue
        coverage.not_covered = list(coverage.not_covered) + [
            f"{name} not installed" for name in engines
        ]
        note = (
            "ran on the built-in check only; "
            + ", ".join(engines) + " " + ("is" if len(engines) == 1 else "are")
            + " not installed here"
        )
        coverage.detail = f"{coverage.detail}; {note}" if coverage.detail else note


def summarize(coverages: List[RuleCoverage]) -> dict:
    """Roll per-rule coverage into the numbers a report headline needs.

    ``clean`` is deliberately narrow: it is True only when every check reached a
    conclusive result AND found nothing. A scan where three checks could not run is
    not clean — it is inconclusive, and must say so.
    """
    total = len(coverages)
    conclusive = [c for c in coverages if c.is_conclusive]
    findings = sum(c.findings for c in coverages)
    return {
        "rules_total": total,
        "rules_ran": len(conclusive),
        "rules_incomplete": total - len(conclusive),
        "fully_covered": total > 0 and len(conclusive) == total,
        "clean": total > 0 and len(conclusive) == total and findings == 0,
        "rules": [c.to_dict() for c in coverages],
    }

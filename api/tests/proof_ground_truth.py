"""Known answers for the proof corpus — what the engine MUST and MUST NOT find.

Accuracy is only meaningful against facts established independently of the code under
test. Every network-dependent fact below was checked against the live registry on the
date recorded in ``VERIFIED_ON``, and the observed response is replayed here so CI stays
deterministic and offline. The date matters: when it goes stale, re-verify rather than
assuming the fact still holds.

Facts as verified on 2026-08-03:

* ``sqg-hallucinated-package-xyz789`` — HTTP 404 from pypi.org/pypi/<name>/json.
  Nothing by that name has ever been published, which is what makes SQG001 CERTAIN.
* ``requests`` — HTTP 200, license "Apache-2.0" (permissive).
* ``requests==2.19.0`` — OSV /v1/query returned 10 advisories, including
  GHSA-9hjg-9r4m-mvj7 (alias CVE-2024-47081, severity MODERATE, fixed in 2.32.4).
* ``requests==2.32.4`` — no advisories at that version.
* ``pyqt5`` — PyPI license field "GPL v3" (copyleft, distribution obligations).
* ``chardet`` — PyPI license "0BSD" (permissive).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from app.registries import Existence

VERIFIED_ON = "2026-08-03"

CORPUS_DIR = "tests/fixtures/proof_corpus"


# --- replayed registry state -------------------------------------------------------

# (ecosystem, normalized name) -> existence, as observed on VERIFIED_ON.
_EXISTENCE: Dict[tuple, Existence] = {
    ("pypi", "requests"): Existence.EXISTS,
    ("pypi", "chardet"): Existence.EXISTS,
    ("pypi", "pyqt5"): Existence.EXISTS,
    ("pypi", "sqg-hallucinated-package-xyz789"): Existence.MISSING,
    # Verified 2026-11-13 (live HTTP status): bleak 200, reqests 404.
    ("pypi", "bleak"): Existence.EXISTS,
    ("pypi", "reqests"): Existence.MISSING,
}

# (ecosystem, normalized name) -> first-release timestamp as observed on
# VERIFIED_ON_DATE (ISO, parsed with fromisoformat). An absent key returns None:
# "age unknown" — which keeps every SQG007 finding (fail-safe, ADR-025).
_CREATED: Dict[tuple, str] = {
    # bleak first upload, from the PyPI JSON `releases` timestamps (verified live).
    ("pypi", "bleak"): "2018-04-27T09:43:02",
}

VERIFIED_ON_DATE = "2026-11-13"

# (ecosystem, name) -> license label, verbatim from the registry JSON.
_LICENSES: Dict[tuple, str] = {
    ("pypi", "requests"): "Apache-2.0",
    ("pypi", "chardet"): "0BSD",
    ("pypi", "pyqt5"): "GPL v3",
}

# One real OSV advisory for requests 2.19.0, trimmed to the fields the analyzer reads.
_REQUESTS_2_19_0_ADVISORIES: List[dict] = [
    {
        "id": "GHSA-9hjg-9r4m-mvj7",
        "aliases": ["CVE-2024-47081", "PYSEC-2026-1872"],
        "database_specific": {"severity": "MODERATE"},
        "affected": [
            {"ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.32.4"}]}]}
        ],
    },
]

# (ecosystem, name, version) -> advisories. An absent key means "no data" (None),
# which the analyzer must treat as inconclusive rather than clean.
_ADVISORIES: Dict[tuple, List[dict]] = {
    ("pypi", "requests", "2.19.0"): _REQUESTS_2_19_0_ADVISORIES,
    ("pypi", "requests", "2.32.4"): [],
    ("pypi", "chardet", "5.2.0"): [],
    ("pypi", "pyqt5", "5.15.10"): [],
}


def _normalize(name: str) -> str:
    return name.lower().replace("_", "-")


async def replay_existence(ecosystem: str, name: str, _client=None) -> Existence:
    """Registry existence as observed on VERIFIED_ON.

    An unknown name returns UNKNOWN, not EXISTS: a fixture that forgot to record a fact
    must produce an inconclusive result, never a silently clean one.
    """
    return _EXISTENCE.get((ecosystem, _normalize(name)), Existence.UNKNOWN)


async def replay_osv_batch(pins, _client=None) -> Dict[tuple, Optional[List[dict]]]:
    """OSV advisories as observed on VERIFIED_ON; None for anything unrecorded."""
    return {
        pin: _ADVISORIES.get((pin[0], _normalize(pin[1]), pin[2]))
        for pin in pins
    }


async def replay_license(ecosystem: str, name: str, _client=None) -> Optional[str]:
    """Registry license label as observed on VERIFIED_ON; None when unrecorded."""
    return _LICENSES.get((ecosystem, _normalize(name)))


async def replay_created(ecosystem: str, name: str, _client=None):
    """Registry first-release date as observed on VERIFIED_ON_DATE; None when unrecorded.

    None means "age unknown", and the SQG007 gate treats unknown as keep-the-finding —
    the same honesty rule replay_existence applies to UNKNOWN existence.
    """
    from datetime import datetime

    raw = _CREATED.get((ecosystem, _normalize(name)))
    if raw is None:
        return None
    return datetime.fromisoformat(raw)


REPLAY_OVERRIDES = {
    "check_exists": replay_existence,
    "query_batch": replay_osv_batch,
    "fetch_license": replay_license,
    "created_fn": replay_created,
}


# --- expectations ------------------------------------------------------------------


@dataclass(frozen=True)
class Expectation:
    """What a fixture proves.

    Attributes:
        fixture: directory name under CORPUS_DIR.
        why: the fact being asserted, in plain language.
        must_find: rule id -> exact number of findings expected. Exact, not "at least":
            a rule that starts emitting three findings where one is correct has
            regressed, even though recall still looks fine.
        min_confidence: rule id -> the tier that rule must reach, where the fact is
            strong enough to demand it.
        must_not_find: rules that must produce nothing. Any hit is a false positive.
        expect_advisories: rules whose findings must carry at least one advisory link.
        expect_applicable_patch: rules whose findings must offer a commitable fix.
    """

    fixture: str
    why: str
    must_find: Dict[str, int] = field(default_factory=dict)
    min_confidence: Dict[str, str] = field(default_factory=dict)
    must_not_find: Set[str] = field(default_factory=frozenset)
    expect_advisories: Set[str] = field(default_factory=frozenset)
    expect_applicable_patch: Set[str] = field(default_factory=frozenset)


# Rules that every negative fixture must stay silent on.
ALL_RULES = frozenset({"SQG001", "SQG002", "SQG003", "SQG004", "SQG005", "SQG006", "SQG007"})


EXPECTATIONS: List[Expectation] = [
    Expectation(
        fixture="hallucinated-dependency",
        why="A package name that returns a clean 404 from a reachable PyPI does not "
            "exist, which is a reproducible fact and therefore block-eligible.",
        must_find={"SQG001": 1},
        min_confidence={"SQG001": "CERTAIN"},
        # The real pinned dependency alongside it must not be flagged as anything.
        must_not_find=frozenset({"SQG002", "SQG003", "SQG004", "SQG005", "SQG006"}),
    ),
    Expectation(
        fixture="leaked-aws-key",
        why="A format-valid AWS access key id in source is a verifiable pattern match, "
            "not a judgement call.",
        must_find={"SQG002": 1},
        min_confidence={"SQG002": "CERTAIN"},
        must_not_find=frozenset({"SQG001", "SQG003", "SQG004", "SQG005", "SQG006", "SQG007"}),
    ),
    Expectation(
        fixture="known-cve-pin",
        why="requests 2.19.0 has published advisories in OSV, with 2.32.4 named as a "
            "patched release — so the finding must carry the advisory and a fix.",
        must_find={"SQG004": 1},
        expect_advisories=frozenset({"SQG004"}),
        expect_applicable_patch=frozenset({"SQG004"}),
        must_not_find=frozenset({"SQG002", "SQG003", "SQG006", "SQG007"}),
    ),
    Expectation(
        fixture="copyleft-license",
        why="PyQt5 ships under GPL v3, a copyleft license with distribution "
            "obligations a reviewer should weigh.",
        must_find={"SQG005": 1},
        must_not_find=frozenset({"SQG001", "SQG002", "SQG003", "SQG004", "SQG006"}),
    ),
    Expectation(
        fixture="dangerous-eval",
        why="eval() on a parameter and subprocess(shell=True) are the two sinks this "
            "rule exists to surface; both are on real call lines.",
        must_find={"SQG006": 2},
        must_not_find=frozenset({"SQG001", "SQG002", "SQG004", "SQG005", "SQG007"}),
    ),
    Expectation(
        fixture="clean-python",
        why="Ordinary Python containing shapes that commonly cause false positives: a "
            "shell-free subprocess call, sha256 hashing, and 'eval' inside a longer name.",
        must_not_find=ALL_RULES,
    ),
    Expectation(
        fixture="clean-typescript",
        why="Ordinary TypeScript using textContent rather than innerHTML, with 'eval' "
            "appearing only inside an identifier.",
        must_not_find=ALL_RULES,
    ),
    Expectation(
        fixture="established-lookalike",
        why="bleak is the standard cross-platform BLE library (first PyPI release "
            "2018-04-27, verified live 2026-11-13), two edits from popular 'black' - "
            "the distance heuristic alone flagged it in scan #18. With registry age "
            "available the established-package gate must suppress the SQG007 finding.",
        must_not_find=ALL_RULES,
    ),
    Expectation(
        fixture="fresh-lookalike",
        why="'reqests' is a clean 404 (verified live 2026-11-13) with NO recorded "
            "first-release date - age unknown keeps the typosquat finding (fail-safe), "
            "and SQG001 independently blocks the hallucinated name. This is the "
            "positive control proving the age gate never switches the detector off.",
        must_find={"SQG001": 1, "SQG007": 1},
        min_confidence={"SQG001": "CERTAIN", "SQG007": "HIGH"},
        must_not_find=frozenset({"SQG003", "SQG004", "SQG005", "SQG006"}),
    ),
    Expectation(
        fixture="synthetic-token",
        why="A distinctive token whose own value carries a fake-marker word is fixture "
            "material — surfaced as an advisory, never CERTAIN/block-eligible (scan #20 "
            "blocked on a literal github_pat_SYNTHETIC_... token).",
        must_find={"SQG002": 1},
        min_confidence={"SQG002": "HIGH"},
        must_not_find=frozenset({"SQG001", "SQG003", "SQG004", "SQG005", "SQG006", "SQG007"}),
    ),
    Expectation(
        fixture="clean-dependencies",
        why="Two real, exactly-pinned, permissively-licensed packages with no "
            "advisories at those versions.",
        must_not_find=ALL_RULES,
    ),
]

EXPECTATIONS_BY_FIXTURE = {e.fixture: e for e in EXPECTATIONS}

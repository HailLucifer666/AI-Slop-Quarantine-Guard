"""The Finding record — the one currency every check reports in.

``Finding`` carries everything a report needs about a single result: where it is, how
confident we are, whether it may block, the advisories behind it, a remediation, and the
provenance (which analyzer and engine version produced it) that lets a reader re-check
the claim rather than trust it. ``finalize`` stamps the fingerprint and evidence hash on
the way out so no rule can forget to.
"""

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

# Revision of the built-in rule set. Bump on any change to detection logic so findings
# recorded by different revisions stay distinguishable in a stored scan.
# 1.1 — 2026-11-12: SQG002 key-material requirement + label-echo skip; SQG003 TODO marker forms.
RULE_VERSION = "1.1"


class Confidence(str, Enum):
    """Confidence level for findings."""
    CERTAIN = "CERTAIN"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


@dataclass
class Evidence:
    """Evidence for a finding."""
    snippet: str
    context_before: List[str] = field(default_factory=list)
    context_after: List[str] = field(default_factory=list)


@dataclass
class Advisory:
    """A published advisory backing a finding — an identifier plus where to read it.

    Advisory links used to be interpolated into the free-text ``fix_suggestion``, which
    made them unlinkable, unsortable and impossible to render as a proper reference.
    """
    id: str
    url: str


# How a finding can be remediated. "patch" is reserved for a replacement derived
# mechanically from an authoritative source (an OSV/Trivy fixed version, a Semgrep
# autofix) — never for something inferred. Anything else is "guidance": prose only.
REMEDIATION_PATCH = "patch"
REMEDIATION_GUIDANCE = "guidance"


@dataclass
class Remediation:
    """A proposed fix, and an honest statement of where it came from.

    ``kind == "patch"`` promises the replacement is machine-derived and safe to apply
    verbatim; that is what allows it to be offered as a one-click GitHub suggestion. A
    fabricated patch would be worse than no patch at all, so a finding with no
    authoritative fix gets ``kind == "guidance"`` and no replacement text.
    """
    kind: str
    text: str
    suggested_replacement: Optional[str] = None
    # Free-form note on provenance, e.g. "OSV reports 2.31.0 as the first patched
    # release" — so a reader can check the claim rather than trust it.
    basis: str = ""

    @property
    def is_applicable(self) -> bool:
        """True when there is a concrete replacement a reviewer could commit."""
        return self.kind == REMEDIATION_PATCH and bool(self.suggested_replacement)


@dataclass
class Finding:
    """A single finding (the universal currency).

    Attributes:
        category: e.g., "dependency", "secret", "sast", "placeholder", "license", "vulnerability".
        confidence: CERTAIN, HIGH, or MEDIUM.
        block_eligible: True if this finding can trigger a block (under user control).
        file_path: File where finding was detected.
        line_start: Starting line number.
        line_end: Ending line number.
        message: Human-readable description.
        evidence: Code evidence + context.
        tool: Tool that produced this (e.g., "gitleaks", "semgrep", "trivy").
        fix_suggestion: Optional fix (for advisories).
        rule_id: Stable rule ID (e.g., "SQG001").
    """
    category: str
    confidence: Confidence
    block_eligible: bool
    file_path: str
    line_start: int
    line_end: int
    message: str
    evidence: Evidence
    tool: str
    rule_id: str
    fix_suggestion: Optional[str] = None
    analyzer_version: str = "0.1"
    # Version of the detection logic for this specific rule. Bumped when a rule's
    # patterns or thresholds change, so a report states which revision of the rule
    # produced the finding and a result from an older scan stays interpretable.
    rule_version: str = RULE_VERSION
    tool_version: str = ""
    evidence_hash: str = ""
    # --- review-grade detail. Every field below is populated ONLY from a source that
    # actually states it; an empty list means "not known", never "none apply". -------
    # CWE identifiers, e.g. ["CWE-78"]. Set where the detection itself defines the
    # weakness class (a shell=True call IS command injection), or where a tool says so.
    cwe: List[str] = field(default_factory=list)
    # Published advisories (CVE/GHSA/OSV) with links.
    advisories: List[Advisory] = field(default_factory=list)
    # Severity as reported by the SOURCE, not computed by us. None when nothing
    # authoritative said one — inventing a severity would make the report less true.
    severity: Optional[str] = None
    cvss_score: Optional[float] = None
    cvss_vector: Optional[str] = None
    # Versions the source names as fixed, which is what makes a patch derivable.
    fix_versions: List[str] = field(default_factory=list)
    remediation: Optional[Remediation] = None
    # Documentation for the rule itself.
    rule_url: str = ""
    # Content-derived identity, stable across scans and across line moves. Used to
    # group duplicates and to avoid re-posting the same PR comment.
    fingerprint: str = ""


def compute_fingerprint(finding: "Finding") -> str:
    """Stable identity for a finding, from its content rather than its position.

    Line numbers are excluded deliberately: inserting an import above a vulnerable call
    must not turn one finding into a "new" one, or every unrelated edit would re-post the
    same PR comment. Identity is (rule, file, the matched text), with whitespace
    collapsed so reindentation is not a change either.
    """
    snippet = " ".join((finding.evidence.snippet or "").split())
    basis = "\x00".join((finding.rule_id, finding.file_path, snippet))
    return hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()[:16]


def finalize(findings: List["Finding"]) -> List["Finding"]:
    """Fill in derived fields every finding must carry before it is reported.

    Analyzers stay focused on detection; anything mechanically derivable is computed in
    one place so no rule can forget it and no two rules can disagree on how.
    """
    for finding in findings:
        if not finding.fingerprint:
            finding.fingerprint = compute_fingerprint(finding)
        if not finding.evidence_hash:
            snippet = (finding.evidence.snippet or "").encode("utf-8", errors="replace")
            finding.evidence_hash = hashlib.sha256(snippet).hexdigest()[:16]
    return findings

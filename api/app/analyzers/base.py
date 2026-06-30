"""Finding model and Analyzer protocol (real impl, universal currency).

ponytail: Finding is REAL, Analyzer protocol is stub signatures only.
"""

from dataclasses import dataclass, field
from typing import List, Protocol, Optional
from enum import Enum


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
    tool_version: str = ""
    evidence_hash: str = ""


class Analyzer(Protocol):
    """Analyzer protocol (stub signatures).

    ponytail: stub, implemented in Phase 3
    """

    async def analyze(self, diff: str, repo_context: dict) -> List[Finding]:
        """Run analysis on a PR diff.

        Args:
            diff: Unified diff text.
            repo_context: Repository context (manifest data, etc.).

        Returns:
            List of findings.
        """
        ...

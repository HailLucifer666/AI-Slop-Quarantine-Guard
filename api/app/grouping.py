"""Cluster related findings so volume cannot bury the important ones.

A real scan of simplex-chat returned 367 findings: 318 genuine `TODO` comments, and —
underneath them — 3 leaked secrets and 39 dangerous-code hits. Every one of the 318 was
true. The report was still bad, because a flat list sorted by severity still buries the
secrets once you scroll, and a "+N more" cutoff at 20 hid the rest entirely.

Grouping fixes that without discarding anything: "318 TODO markers across 216 files"
becomes one row that can be expanded, while the 3 secrets stay individually visible. No
finding is dropped, no count is rounded, and the group always reports its true size.

Deliberately NOT a severity filter. Suppressing low-severity findings would make the
report shorter by making it less true; this makes it shorter by making it structured.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List

from app.analyzers.base import Confidence, Finding

# Group only when a rule is genuinely repetitive across a codebase. A secret or a
# hallucinated dependency is a discrete incident and must always stand alone, however
# many there are — collapsing those would hide exactly what the reader came for.
GROUPABLE_RULES = frozenset({"SQG003", "SQG006"})

# Below this, a group costs more than a plain list of findings.
MIN_GROUP_SIZE = 3

_CONFIDENCE_ORDER = {Confidence.CERTAIN: 0, Confidence.HIGH: 1, Confidence.MEDIUM: 2}

# Strip the volatile tail analyzers append to messages ("at line 42: 'x = 1'") so the
# same underlying issue clusters regardless of where it occurred.
_LINE_SUFFIX = re.compile(r"\s+at line \d+:.*$", re.DOTALL)
# Versioned package mentions ("lodash==4.17.20") vary per occurrence.
_VERSION = re.compile(r"\b\d+\.\d+(?:\.\d+)?\b")


def issue_key(finding: Finding) -> str:
    """What makes two findings "the same issue" for grouping purposes."""
    label = _LINE_SUFFIX.sub("", finding.message).strip()
    label = _VERSION.sub("<version>", label)
    # A shared advisory is a stronger signal than message text: the same CVE across
    # three manifests is one problem, however differently each line is worded.
    if finding.advisories:
        return f"{finding.rule_id}::{finding.advisories[0].id}"
    return f"{finding.rule_id}::{label}"


@dataclass
class FindingGroup:
    """One issue and every place it occurs."""

    key: str
    rule_id: str
    title: str
    confidence: Confidence
    findings: List[Finding] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.findings)

    @property
    def file_count(self) -> int:
        return len({f.file_path for f in self.findings})

    @property
    def is_group(self) -> bool:
        """True when this collapses several occurrences rather than standing alone."""
        return self.count >= MIN_GROUP_SIZE and self.rule_id in GROUPABLE_RULES

    def to_dict(self, max_occurrences: int = 50) -> dict:
        """Serialize for the API. Occurrences are capped for payload size, but the
        true total is always reported so a cap can never read as the whole story."""
        return {
            "key": self.key,
            "rule_id": self.rule_id,
            "title": self.title,
            "confidence": self.confidence.value,
            "count": self.count,
            "file_count": self.file_count,
            "grouped": self.is_group,
            "occurrences_shown": min(self.count, max_occurrences),
            "occurrences": [
                {
                    "file_path": f.file_path,
                    "line_start": f.line_start,
                    "line_end": f.line_end,
                    "snippet": f.evidence.snippet,
                    "fingerprint": f.fingerprint,
                }
                for f in self.findings[:max_occurrences]
            ],
        }


def group_findings(findings: List[Finding]) -> List[FindingGroup]:
    """Cluster findings by issue, most severe (then largest) first.

    Every input finding lands in exactly one group, so the group counts always sum back
    to the total the user was told about.
    """
    groups: Dict[str, FindingGroup] = {}
    for finding in findings:
        key = issue_key(finding)
        group = groups.get(key)
        if group is None:
            groups[key] = FindingGroup(
                key=key,
                rule_id=finding.rule_id,
                title=_LINE_SUFFIX.sub("", finding.message).strip(),
                confidence=finding.confidence,
                findings=[finding],
            )
            continue
        group.findings.append(finding)
        # A group is only as reassuring as its worst member.
        if _CONFIDENCE_ORDER.get(finding.confidence, 9) < _CONFIDENCE_ORDER.get(group.confidence, 9):
            group.confidence = finding.confidence

    return sorted(
        groups.values(),
        key=lambda g: (_CONFIDENCE_ORDER.get(g.confidence, 9), -g.count, g.key),
    )


def summarize_groups(groups: List[FindingGroup]) -> dict:
    """Counts for the report headline."""
    return {
        "groups_total": len(groups),
        "findings_total": sum(g.count for g in groups),
        "collapsed_groups": sum(1 for g in groups if g.is_group),
        "groups": [g.to_dict() for g in groups],
    }

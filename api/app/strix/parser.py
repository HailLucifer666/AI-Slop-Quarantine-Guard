"""Map Strix's own findings into this product's advisory `Finding` currency.

WHAT'S REAL HERE: ``to_findings()`` — the safety-critical adapter — takes
already-parsed records (plain dicts, one per Strix finding) and enforces the
non-negotiable honesty invariants (see module-level constants below) no matter
what a record contains. This is fully implemented and tested.

WHAT'S DEFERRED, AND WHY: reading a completed ``strix_runs/<run-name>/`` tree
and producing those raw records. As of strix-agent 1.0.4, Strix's own output
format is not documented (no fixed JSON schema, no ``--format json`` flag, no
SARIF export — confirmed by reading the project's README before writing this
module; see the CI workflow's comment on the same point). Writing a file/schema
parser now would mean guessing at a structure this repo has never actually
observed — exactly the kind of "research, don't guess" violation this project's
own operating rules forbid. The real next step is to run
``strix -n --target <dir> --output <tmp>`` once (locally, with a real
``LLM_API_KEY``, deliberately — it costs API budget) and write ``load_run()``
against its ACTUAL output, or consult docs.strix.ai directly. Do not fabricate
a schema here to make this module "feel done."
"""

from typing import List

from app.analyzers.base import Confidence, Evidence, Finding

RULE_ID = "STRIX"
CATEGORY = "pentest"


def to_findings(records: List[dict]) -> List[Finding]:
    """Map raw Strix finding records to advisory `Finding`s.

    Each input record is treated defensively (arbitrary/unknown shape) — every
    field is read with a safe default, never assumed present. The invariants
    below are enforced unconditionally, regardless of what a record claims:

    * ``category`` is always "pentest" and ``rule_id`` is always "STRIX" — never
      mixed into a Guard rule id (SQG00x), so a Strix finding can never be
      mistaken for a deterministic fact in any downstream aggregation.
    * ``block_eligible`` is always False. Strix's output is an LLM's judgement,
      not a reproducible fact — G2 (block only on a provable fact) means it can
      never gate a merge, no matter how confident the record claims to be.
    * ``confidence`` is never CERTAIN — at most HIGH (when the record claims a
      working proof-of-concept) or MEDIUM otherwise. CERTAIN is reserved for
      the Guard's own deterministic checks.
    """
    findings: List[Finding] = []
    for record in records:
        has_poc = bool(record.get("proof_of_concept") or record.get("poc"))
        confidence = Confidence.HIGH if has_poc else Confidence.MEDIUM
        title = str(record.get("title") or record.get("name") or "Strix finding")
        location = str(record.get("location") or record.get("file") or "(dynamic)")
        line = record.get("line") or 0
        try:
            line = int(line)
        except (TypeError, ValueError):
            line = 0
        remediation = record.get("remediation") or record.get("fix_suggestion")

        findings.append(Finding(
            category=CATEGORY,
            confidence=confidence,
            block_eligible=False,  # non-negotiable — see docstring
            file_path=location,
            line_start=line,
            line_end=line,
            message=f"[AI pentest — advisory, verify before acting] {title}",
            evidence=Evidence(snippet=str(record.get("proof_of_concept") or record.get("poc") or "")),
            tool="strix",
            rule_id=RULE_ID,
            fix_suggestion=str(remediation) if remediation else None,
        ))
    return findings

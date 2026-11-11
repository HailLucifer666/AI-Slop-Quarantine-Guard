## What changed, and why (one sentence)

## Evidence

- [ ] Behaviour change ships a test that **fails on the parent commit** — name the test:
- [ ] Proof gate run — paste the command and its result (`api/scripts/prove.ps1` / `prove.sh`, or `pytest api/tests/test_accuracy.py`):
- [ ] If output from any LLM tool (Crew, Strix, codex-security) influenced this change: the executable PoC is attached, and nothing was added to `api/app/analyzers/` or `checks.py` without it.

CI is the enforcement layer (ruff, gitleaks, the accuracy corpus, coverage ≥ 80%). These checkboxes exist to make you produce that evidence, not to replace it.

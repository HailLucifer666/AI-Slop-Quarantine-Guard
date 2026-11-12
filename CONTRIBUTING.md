# Contributing — the review gate

This repo's promise is: *"we run every known check the best companies run, we catch everything
those checks can catch, and we never lie to you about a fact."* Contributing means keeping that
promise load-bearing. Three rules do it.

## Rule 1 — a fix without a test is a claim, not a fix

Every change that alters behaviour ships the test that **fails on the parent commit** and passes
on the new one. Not "a test that passes" — the test that would have caught this bug. If a test is
genuinely impossible, say so in the commit message and state what proof replaces it. Never omit
silently.

A test you have never seen fail is also just a claim. Write it, break the thing it guards, watch
it go red for the stated reason, restore, and only then trust it.

## Rule 2 — run the proof gate, not your optimism

The repo ships executable proof; use it instead of re-reading your own diff and agreeing with it:

| When you changed... | Run |
|---|---|
| anything under `api/app/` (analyzers, checks, scan, ingest) | `api/scripts/prove.ps1` (Windows) or `api/scripts/prove.sh` — accuracy corpus + a scan of the Guard's own code |
| a rule's precision or recall | `pytest api/tests/test_accuracy.py` — measured against the ground-truth corpus |
| anything at all | `pytest api/tests` — CI also enforces coverage ≥ 80% |

`main` is always the last known-good build: branch, test there, merge only green.

## Rule 3 — the firewall: LLM output never enters the Guard

Findings from any LLM-backed tool (the Crew, Strix, the codex-security bot) are hypotheses, not
facts. They never become blocks and never feed `api/app/analyzers/` or `checks.py` unless someone
first proves them with an executable PoC and ships that proof with the change. The deterministic
Guard blocks only on provable facts — that is the product (see `docs/DECISIONS.md` ADR-003 and
ADR-019, and the same firewall written into `.github/workflows/strix.yml` and
`.github/workflows/codex-security.yml`).

## What the maintainer adds on top

The maintainer applies these same rules through the `kee` harness (`/kee audit`, `/kee preflight`,
`/kee review`) — a local skill, not a requirement for contributors and not available in this repo.
The rules above are the portable substance; kee is one tool for applying them.

## Pull requests

The PR template asks for evidence, not assertions: name the test, paste the command you ran. The
checkboxes are prompts to produce that evidence — CI is the enforcement layer (ruff, gitleaks,
the accuracy corpus, coverage ≥ 80%).

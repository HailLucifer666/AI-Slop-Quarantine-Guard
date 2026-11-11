# AI Slop Quarantine Guard — Folded Roadmap (PLAN.md)

Prepared 2026-11-12 by folding the self-scan #15 response plan (line-verified against the code)
into the product roadmap. Implementing agents work one phase at a time with the prompt template at
the bottom. This document supersedes the earlier standalone plans; nothing in it has shipped
except where marked done.

## 0. Read this first

**Goal.** Make the Guard provable (anyone can check its claims), adoptable (one command to try it)
and hard to break (a failure never turns into a false green). The goal is not more features.

**Design principle (locked 2026-11-12, Arghya): the scanner adapts; scanned code never carries
annotations to silence it.** False alarms are detector bugs and get fixed by tuning the detector,
each change red-first tested with a keeper test proving no recall loss. The inline marker below is
an adoption feature for users' *accepted* findings only — the Guard's own repo never uses it for
false alarms.

**Working rules (never break these).**

1. One concern per branch and per PR. Write the failing test first, then the fix.
2. No LLM call anywhere in `api/app/analyzers/` or `checks.py`. The Crew explainer stays advisory.
3. Never widen the `block_eligible` set. A new rule never blocks.
4. Failing to examine something is never reported as clean. Unknown is its own state.
5. Secret values never appear in any output: logs, SARIF, JSON, dashboard, issues.
6. Anything that comes from the scanned code (config, suppression markers, baselines in a PR head)
   is attacker-controlled. For pull requests, read policy from the base branch.
7. No new dependency without a one-line justification in the PR.
8. A behavior change ships with its docs: update `CHECKS_CATALOG.md`, and add an ADR in
   `DECISIONS.md` for any design decision.
9. If a step is ambiguous, stop and ask the owner. Do not guess.

**Definition of done for every step.** The new test fails before the change and passes after; the
full suite is green; ruff and mypy are clean; docs are updated; the PR touches only the files the
step names.

**Verified facts the sketches below rely on (checked 2026-11-12):**

- The finalize chain is duplicated inline at `scan.py:312` AND `worker.py:254` (no shared
  function; `finalize` lives in `analyzers/base.py:148`). Any chain change = two edits.
- Fingerprints are deterministic sha256 (`base.py:135-145`), stamped by `finalize`.
- `[project.scripts]` is absent from `api/pyproject.toml`; pyyaml is not a dependency — both are
  additions, each with a one-line justification (rule 7).
- The boot validator (`config.py:93-108`) currently rejects only EMPTY secrets outside
  development; placeholder rejection is net-new.
- A failed diff fetch currently produces a green check: `fetch_pr_diff` returns None on any
  non-200 (`github_client.py:60`) and `worker.py:188-196` publishes a "success" check run.
- SQG008 is reserved ("NOT IMPLEMENTED", `CHECKS_CATALOG.md`) — never reuse the id.
- `test_accuracy.py` runs the real `scan.py` chain; every detector change must keep it 1.0/1.0.

## Phase 0 — stabilize ✅ (2026-11-12)

PRs opened for the pending branches: #20 `fix/findingcard-legacy-findings`,
#21 `fix/launcher-env-path`, #22 `docs/tooling-gates`. Worktree junk disposed; this PLAN.md,
LICENSE (MIT) and README honesty tweaks ship on `docs/honesty-plan`.

## Phase 1 — self-scan response (detector tuning only)

### Branch A: `fix/dashboard-deps` (the 11 real findings)

- `web/`: `npm install next@^15.5.28` (fixes GHSA-2464-fhr4-w9xw, Critical 9.5 unauth RCE in Next
  Image Optimization; stays in the declared `^15.0.0`), then `npm audit fix` (never `--force`).
  A surviving transitive advisory (minimatch 10.2.6→11.0.1 may be parent-capped) is reported
  honestly.
- Verify: npm audit before/after counts, `npx tsc --noEmit`, `npm run build`; rescan → the SQG004
  `next` finding is gone. Commit `package.json` + `package-lock.json`.

### Branch B: `fix/self-scan-false-positives`

1. **secrets.py — PEM with no key material is structurally not a secret (any path).** Rework the
   private-key-block branches (`secrets.py:309-317`): `has_body = _has_key_body(added, idx) or
   _has_inline_body(content)`, where `_has_inline_body` extracts the BEGIN→END segment within the
   physical line and requires ≥32 consecutive base64 chars with no `...`/`…`. No body → skip
   entirely (bare doc headers AND inline skeletons like `infra/docker-compose.yml:36,54` die) —
   and it must **never fall through to `_certain`**. Body present → existing branches unchanged
   (test → `_certain_in_test`, example → `_advisory`, placeholder window → `_advisory`, else
   `_certain`). **No widening:** an inline body alone never upgrades to CERTAIN. Red-first:
   rewrite `test_bare_pem_headers_no_body_are_advisory_not_blocked` (test_secrets.py:196-211) →
   0 findings; rewrite the pinned compose-skeleton expectation (~test_secrets.py:172) → 0
   findings. New keeper: inline PEM with a real base64 body in docker-compose → still HIGH
   advisory. Keepers untouched: `test_private_key_block_blocks`, `test_real_pem_in_normal_path_still_blocks`.
2. **secrets.py — quoted-assignment prose values are not credentials.** In the quoted
   `_ASSIGNMENT` tier only (before `_high`): skip when the value reads as an English phrase
   (contains a space, no digits, no symbols beyond apostrophe/hyphen) UNLESS the name is in the
   password family (`passwd|password|pwd|passphrase` — a subset of the name alternation already
   at `secrets.py:95`, derived from the existing selector, no new hand list). Kills
   `web/components/wall/panels/AnimatedScan.tsx:22` (`secrets: "Leaked secrets"`). Keepers
   pinned: `password = "correct horse battery staple"` → still HIGH; corpus AWS key → CERTAIN.
   (.env unquoted tier untouched.)
3. **base.py — delete the dead `Analyzer` Protocol** (base.py:163-189; zero importers), drop
   `Protocol` from the typing import, fix docstrings (base.py:9-10, `analyzers/__init__.py:3-4`).
4. **placeholders.py — TODO arm requires a colon** (line-42 alternation, TODO arm only →
   `TODO\s*:`; FIXME/XXX/IGNORECASE untouched). Kills the 5 prose TODO hits. Pinned positives
   (test_placeholders.py:16,90,105) all have colons.
5. **placeholders.py:39 — accept and pin.** Bare-XXX prose cannot be pattern-separated from slop
   XXX without breaking `test_bare_xxx_marker_still_flagged`, and the no-annotation principle
   forbids markers. The rescan keeps exactly ONE advisory self-hit on the detector's own source —
   pinned by a test and documented in `CHECKS_CATALOG.md` as a known self-scan advisory.
6. **Docs:** CHECKS_CATALOG.md — SQG002 "does not catch" gains bare PEM headers / skeleton keys /
   prose values; SQG003 notes the TODO-colon rule. DECISIONS.md — ADR: "the scanner adapts;
   scanned code never carries annotations to silence it."

**Expected rescan:** 25 → 1 known advisory (placeholders.py:39) + any honestly-reported surviving
transitive dep advisory; 0 block-eligible; `next` finding gone.

## Phase 2 — honesty bugs (highest priority after Phase 1)

### Step 2.1: a failed diff fetch must never produce a green check

New `api/app/gate.py`: `Verdict` enum (CLEAN / FLAGGED / BLOCKED / UNVERIFIED), pure `decide(GateInput)`,
`CONCLUSION` map (clean→success, flagged→action_required, blocked→failure, unverified→neutral).
Wire into the PR path replacing `determine_conclusion` (checks.py:48-54); fix the confirmed hole
at `worker.py:188-196`. The UNVERIFIED check-run summary reads: "Slop Guard could not examine
this change, so it makes no claim." Tests in `api/tests/test_gate.py` (failed fetch → neutral;
unexamined files → never success; proven finding beats unverified; blocking opt-in) plus one
integration test that monkeypatches the real diff fetch to fail.

### Step 2.2: the boot validator must reject placeholder secrets

Extend `config.py`'s `_require_secrets_outside_development` (:93-108): reject placeholder values
(marker tuple: changeme, your-, example, replace, placeholder, dummy, xxxx, todo …) and values
copied from `.env.example`, outside development only. Helpers pure and unit tested. Optional
switched-off features are not checked.

### Step 2.3: triage the 19 audit leads

One GitHub issue per lead (`docs/AUDIT_2026-11-11.md`, lead N). Fix the five most severe, one PR
each, regression test first; accepted risks recorded as ADR lines; false leads closed with reasons.

### Step 2.4: one file that states every honesty promise

`api/tests/test_honesty_invariants.py` — only dependency+secret can be block-eligible (via the
checks.py choke point); registry outage is advisory never CERTAIN; secret values never appear in
any field. After Phase 4, add the same secret check against SARIF and JSON outputs.

## Phase 3 — measurability

- **Step 3.1** `api/benchmarks/metrics.py`: Wilson 95% intervals + per-rule TP/FP/FN. Corpus size
  is always printed next to a percentage.
- **Step 3.2** grow the fixture corpus to ≥40 repos with an `expected.toml` per fixture
  (tomllib, no new dependency); 20 realistic clean + 20 poisoned across every rule. **Fold note:
  Phase 1's red-first negatives become corpus fixtures** (bare PEM header in docs, inline
  skeleton in compose, prose value, TODO-without-colon).
- **Step 3.3** real-world run: 50–100 pinned public repos (`api/benchmarks/real_world_repos.txt`,
  `real_world.py` — network, never in the offline suite), human triage by fingerprint,
  `benchmarks/REAL_WORLD.md` published with date + tags + Wilson interval.
- **Step 3.4** CI: python 3.12/3.13 matrix, pinned action SHAs, scheduled `real-world.yml`.

## Phase 4 — adoption

- **Step 4.1 CLI** `slopguard = 'app.cli:main'` (add `[project.scripts]` — absent today). Exit
  codes: 0 clean/advisory, 1 block-eligible finding, 2 incomplete, 3 usage. Explicit
  `allow_local` parameter for `walk_dir` that only the CLI passes; the server gate untouched.
- **Step 4.2 SARIF** `api/app/sarif.py`: 2.1.0, CERTAIN→error / HIGH→warning / MEDIUM→note,
  never a secret value anywhere in serialized output.
- **Step 4.3 reusable GitHub Action** `action.yml`: composite, inputs via `env`, pinned SHAs.
- **Step 4.4 policy file** `.slopguard.yml` read from the BASE branch on PRs (pyyaml added with
  justification; config can only narrow — the checks.py choke point still decides first;
  policy-excluded files reported, never counted examined-clean).
- **Step 4.5 baselines + inline suppression (grammar FROZEN 2026-11-12, confirmed by Arghya):**

```
slopguard: ignore SQG003 -- reason text of at least 8 characters
slopguard: ignore SQG003,SQG006 until=2027-03-01 -- reason text
```

  - Prefix `slopguard:` lowercase, case-sensitive; verb `ignore` only (unknown verb = malformed).
    One or more comma-separated `SQG\d{3}` ids; **no wildcard, no blanket** — a suppression you
    cannot take back must be explicit.
  - Optional lowercase `key=value` tokens between the rule list and the delimiter; unknown keys →
    warning + ignored, never fatal (free text comes last, so new keys can never be swallowed by
    the reason). Delimiter is whitespace-delimited ` -- `; reason runs to end of line; trailing
    comment terminators (`*/`, `-->`) stripped before reading; reason trimmed, ≥8 characters. At
    most one marker per line (a second occurrence is reason text).
  - `until=` semantics frozen with the grammar: ISO date `YYYY-MM-DD`; after that date the marker
    is not honored and the finding resurfaces with a "suppression expired" note.
  - **Scope:** the marker applies to a finding on its own line or the line directly above.
    **PR-path requirement:** the line lookup must include context lines from the diff hunks, not
    `parse_diff`'s added-lines-only output (`diff.py:10`) — otherwise line-above scope silently
    works in local scans and fails on PRs.
  - **Malformed marker** (bad rule id, unknown verb, missing/short reason) is never honored and
    is reported as an advisory finding under a reserved meta id (SQG010 proposed; SQG008 stays
    reserved) — a typo can neither silently suppress nor silently fail.
  - **Marker on a block-eligible finding:** recognized, not honored, reported with "needs a
    baseline entry" (author-controlled code cannot hide proven blockers — rule 6).
  - **No-comment formats** (package.json, lockfiles, binaries) use the baseline file.
    **Foreign markers** (`noqa`, `nosec`, `type: ignore`) are not honored — known pre-existing
    exception documented, not changed: SQG003's allowlist (placeholders.py:32), decision
    deferred to this phase.
  - **Receipts:** every suppression cites the exact marker (line + text), including the
    stacked-line case (a trailing marker also covers the line below) — visible, never silent.
    Unknown-key warnings surface in the receipts/summary stream (the Guard has no separate
    warning channel).
  - Known limitation documented: matching is line-text-based, not syntax-aware — a marker-shaped
    string literal also suppresses.
  - **Baselines:** stored fingerprints (`base.py:135-145`) + expiry, `slopguard baseline create`
    with 90-day default; every report prints suppressed/baselined counts. False alarms never
    route through any of this — they are detector bugs (Phase 1 principle).

## Phase 5 — slop-specific rules (all advisory, gate below)

**Gate for every new rule:** (1) PoC script; (2) ≥5 positive + ≥10 negative realistic fixtures;
(3) measured FP count on the real-world set; (4) CHECKS_CATALOG entry; (5) coverage.py
CAPABILITIES entry; (6) registration in BOTH runner lists; (7) kill-switch test via
`DISABLED_ANALYZERS`. A new rule starts HIGH/MEDIUM advisory and never blocks.

- **Step 5.1 undeclared imports** (best first rule) — reuse `app/manifests.py`; skip
  try/except-ImportError and TYPE_CHECKING guards; alias table for import-name vs distribution;
  HIGH advisory.
- **Step 5.2 vacuous tests** — only `test_*` in test files; respect self.assertX / pytest.raises /
  mock assert_called*.
- **Step 5.3 placeholder data + env-var drift** (MEDIUM advisory until measured).
- **Step 5.4 hallucinated APIs** (research, last) — stage one only: `import pkg.sub` where the
  pinned version's wheel RECORD lacks the module; artifact hash as evidence; advisory.

## Phase 6 — MCP server for AI coding agents

`api/app/mcp_server.py` (ADAPT to installed SDK): `package_exists(ecosystem, name)` →
exists / not_found / unknown (unknown is never evidence of a hallucination); `scan_snippet(files)`
enforcing the same size caps as ingestion. Document client setup per current client docs.

## Phase 7 — operational discipline

Registry cache that cannot create false CERTAIN findings (cache exists long, not-found short,
errors never); workflow `permissions: contents: read` + pinned SHAs + dependabot github-actions;
one structured log line per finished scan; tag v0.1.0 + CHANGELOG + Release.

## Phase 8 — credibility

README order: pitch, demo, one-command try-it, honesty table (promise → test file), measured
results with corpus size + 95% interval, rules docs (what it catches / does not / confidence /
blocking / measured precision / edge cases / how to suppress), decisions, limitations, license.
Write-up: scan N popular repos; sampling + triage process; report FPs openly; claim nothing
unprovable (the product's own rule).

## If time is short

Phase 0 → Phase 1 → Phase 2 → steps 3.3 + 4.1. Skip for now: SOC2, leaderboard, fuller SAST,
LLM tier inside the Guard, GitLab/Bitbucket.

## Prompt template for the implementing agent

```text
You are implementing step <ID> of docs/PLAN.md in the repo AI-Slop-Quarantine-Guard.
1. Read the working rules in section 0 and obey them.
2. Read these real files first: <list them>. Do not trust names in the sketches.
3. Write the failing test or tests first and show them failing.
4. Make the smallest change that passes them.
5. Run: cd api && python -m pytest -q  then ruff check and mypy app.
6. Update the docs named in the step.
7. Reply with: files changed, test summary, anything you adapted from the sketch, open questions.
Do not touch anything outside this step.
```

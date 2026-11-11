# ROADMAP — 11-Phase Build Plan (Living Checklist)

Status: **Phase 3 COMPLETE** — Phases 1–2 done (webhook spine + worker/auth/diff). All 6 analyzers built & wired into worker: SQG001 deps (CERTAIN/block), SQG002 secrets (CERTAIN/block), SQG003 placeholders, SQG004 CVE/OSV, SQG005 licenses, SQG006 SAST (all advisory). 84 tests green, zero-FP gated. All pure-Python/HTTP — no external binaries. Next: Phase 4 (Check Run output + block logic).

---

## Phase 0 — Validate + Foundations

**Goal:** Market signal + GitHub App registered + dev environment boots.

**Tasks:**
- [ ] Market validation: search HN, Reddit for "AI slop detection" / "hallucinated packages" pain.
- [ ] Check competitor status: `slopcheck`, `ai-slop-gate` (Qwen's research suggests `slopcheck` archived = opening).
- [ ] Register GitHub App (perms: PRs R/W, Checks R/W, Contents R, Metadata R; events: `pull_request`, `installation`).
- [ ] Create accounts: Supabase, Upstash, Fly, Vercel, Cloudflare.
- [ ] Scaffold repo: folder structure, `pyproject.toml`, `package.json`, `docker-compose.yml`, `.env.example`.
- [ ] Secrets in `.env.local` (gitignored).

**Verify:**
- [ ] Services reachable (test DB connection, Redis ping).
- [ ] GitHub App shows in org.
- [ ] `make dev` boots api + worker + db + redis without errors.

**Duration:** 2–3 days.

---

## Phase 1 — Webhook Spine + Foundations Baked In

**Goal:** Accept PRs, verify signature, dedupe, queue, return 202 <1s. Structured logs from day one.

**Tasks:**
- [ ] `POST /webhooks/github`: HMAC-SHA256 verify on raw body.
- [ ] Deduplication via `X-GitHub-Delivery` → DB lookup.
- [ ] Enqueue job to arq (Redis).
- [ ] Return 202 "Accepted" immediately.
- [ ] Structured logging (`structlog` JSON).
- [ ] Correlation ID on every request.
- [ ] `GET /healthz` (DB + Redis status).
- [ ] SQLite persistence (analyses + findings tables, Alembic migrations).
- [ ] Kill-switch env var (`DISABLED_ANALYZERS`).
- [ ] Graceful SIGTERM shutdown (worker finishes current job).

**Verify:**
- [ ] Real PR → 202 <1s.
- [ ] Job appears in Redis (inspect via `redis-cli`).
- [ ] Row in `analyses` table.
- [ ] Logs are JSON + traceable by delivery ID.
- [ ] Bad signature → 401.
- [ ] Redelivered webhook (same delivery ID) → 409.

**Duration:** 3–4 days.

---

## Phase 2 — Worker + GitHub Auth Chain

**Goal:** Worker turns PR into parsed diff. Token minting cached. Graceful failures.

**Tasks:**
- [ ] arq worker boots and picks up jobs.
- [ ] App-JWT → installation-token chain (cache until 5 min before expiry).
- [ ] Fetch PR diff via GitHub API (`/repos/{owner}/{repo}/pulls/{pr}/files`).
- [ ] Parse diff (manifest-aware: `requirements.txt`, `package.json`, `Cargo.toml`, `go.mod`, `Gemfile`).
- [ ] Graceful diff-size cap (e.g., >100 MB lockfile → skip, log as `degraded`).
- [ ] Retry logic with backoff (transient errors, rate-limit handling).
- [ ] Graceful SIGTERM (finish current job, don't orphan).

**Verify:**
- [ ] Real PR → worker fetches diff within 5s.
- [ ] Token minted once, reused for multiple API calls.
- [ ] Oversized diff degraded gracefully (no crash).
- [ ] Worker survives redeploy mid-job (idempotent by `(repo, pr, head_sha)`).

**Duration:** 3–5 days.

---

## Phase 3 — The Guard, One Analyzer at a Time (Calibrate)

**Goal:** SQG001 (dependencies) end-to-end, calibrated to zero FP. Then add others.

**Calibration discipline:**
- Build + test on 20 real public repos (5 Python, 5 JS, 5 Rust, 5 expected-clean).
- Fixture bank: positive set (fake packages), negative set (real packages, clean code, lockfiles, vendored dirs, monorepos).
- Each analyzer wrapped in try/except → structured `errored` finding (never silent skip).
- **Hard ceiling:** ship analyzer when fixture suite is green AND 20-repo sample yields zero unexpected CERTAIN findings. Remaining FPs → backlog.

**Tasks (Dependency SQG001):**
- [x] `manifests.py`: parse `requirements.txt`, `pyproject.toml`, `package.json`, `Cargo.toml` (real parsers via stdlib `tomllib`/`json`). _go.mod, Gemfile → backlog._
- [x] Registry clients: PyPI JSON API, npm, crates.io (httpx + error handling). _Go proxy → backlog._
- [x] Fail-safe: registry unreachable/timeout/429 → retry w/ backoff → downgrade to `HIGH` (never block).
- [x] Whitelist: local/VCS/url specs (`workspace:`, `file:`, `link:`, `git+`, paths) filtered in parser; scoped (`@org/*`) handled. _monorepo workspace files, private registries → backlog._
- [ ] Grace window: newly published pkgs (<72h) → `HIGH` (not `CERTAIN`).
- [ ] Analyzer wraps in try/except → `errored` Finding on crash. _(currently: unfetchable manifest → silent skip; worker catches analyzer exceptions)_
- [x] Test on fixture bank: zero FPs on negative set, 100% catch on positive set (20 tests green).
- [ ] Test on 20-repo sample: measure real-world FP rate.

**Then add (in order):**
- [x] SQG002 (secrets, offline): pure-regex MVP done — distinctive tokens (AWS AKIA, GitHub ghp_, Stripe sk_live_, Slack xox, Google AIza, PEM private keys) → CERTAIN/block-eligible; generic `secret=/password=/api_key=` assignments → HIGH advisory; allowlist kills EXAMPLE keys / env refs / placeholders; secret values redacted in findings. 10 tests green. _gitleaks/TruffleHog + checksum verification → backlog._
- [x] SQG004 (CVE): OSV.dev API MVP done — queries exact pins only (pip `==`, npm exact semver) for PR-introduced deps; HIGH advisory, never blocks; OSV outage → silent (fail-safe); secret-free. 8 tests green. _Now also reads go.mod, pom.xml, build.gradle(.kts), *.csproj, Gemfile.lock, composer.lock and packages.lock.json via `app/pinned.py`, covering Go, Maven, RubyGems, Packagist and NuGet — verified against live OSV. Trivy/Syft, range→version resolver, crates/pyproject → backlog._
- [x] SQG006 (SAST): pure-regex MVP done — curated P0/P1 sinks (Python: eval/exec/os.system/shell=True/pickle/unsafe yaml.load/weak hash; JS: eval/child_process.exec/dangerouslySetInnerHTML/innerHTML/document.write), language-gated by extension, HIGH/MEDIUM advisory never blocks, honours # nosec. 11 tests green. _Real Semgrep/OpenGrep subprocess + ruleset → backlog._
- [x] SQG005 (licenses): registry-metadata MVP done — reads PyPI/npm license fields for PR-introduced deps, flags copyleft (GPL/AGPL/LGPL/SSPL) MEDIUM advisory never blocks, registry outage/no-license → silent (fail-safe). 9 tests green. _Packagist added by reading the licenses `composer.lock` declares inline (no network). Trivy/Syft, crates, rubygems/maven/nuget registry lookups, transitive deps → backlog._
- [x] SQG003 (placeholders): regex MVP done — TODO/FIXME, NotImplementedError, ellipsis bodies, stub prose; advisory MEDIUM, skips doc files, allowlists noqa/type:ignore. _tree-sitter AST → backlog._

**Verify (per analyzer):**
- [ ] Fixture bank 100% green (zero FPs).
- [ ] 20-repo sample: no unexpected CERTAIN findings.
- [ ] Each planted issue caught at exact line.
- [ ] Timeout guards (e.g., Semgrep <2s).

**Duration:** 2 weeks (1 analyzer/day, then integration + calibration).

---

## Phase 4 — Results on the PR (Visible, Label-Only)

**Goal:** Create Check Run on PR, post findings (not blocking yet). **First demoable moment.**

**Tasks:**
- [ ] Worker creates Check Run (status `in_progress` at start).
- [ ] Collect all findings from analyzers.
- [ ] Truncation-safe summary (top-N findings + "X more in dashboard" link).
- [ ] Post Check Run with conclusion:
  - `success` if no findings.
  - `action_required` (orange, highly visible) if findings.
  - Never `neutral` (renders as green, findings invisible).
- [ ] Post PR review comments for top findings (anchored to line + code block).
- [ ] Reconciliation: any `in_progress` Check Run >5 min old → `action_required` "timed out".
- [ ] GitHub Checks API rate budget tracking (1000/hr/repo).

**Verify:**
- [ ] PR with fake package → orange check at the right line within seconds.
- [ ] Dashboard deep-link in summary.
- [ ] No blocking (only label).

**Duration:** 3 days.

---

## Phase 5 — Persistence & Audit (Postgres)

**Goal:** Migrate SQLite → Postgres. Full audit trail.

**Tasks:**
- [ ] Migrate DB schema: `analyses`, `findings`, `webhook_deliveries`, `audit_log`, `installations`, `settings`.
- [ ] Alembic versioning (every change tracked, rollback safe).
- [ ] Indexes (fast queries by timestamp, repo, rule, confidence).
- [ ] Retention policy: findings 90d, analyses 180d, webhook logs 30d, audit log 1y.
- [ ] Worker idempotency: refresh check run if already concluded (don't re-analyze).
- [ ] Audit log: every action (analysis started, setting changed, bypass approved).

**Verify:**
- [ ] History queryable with filters (by repo, PR, rule, date).
- [ ] Redelivery deduped at DB.
- [ ] No analysis lost.
- [ ] Alembic rollback tested.

**Duration:** 4 days.

---

## Phase 6 — Dashboard → ✅ Usable Product

**Goal:** Users can log in, see repos, drill into PRs, read findings. **Shippable to first users.**

**Tasks:**
- [ ] Next.js 15 + Tailwind + shadcn/ui scaffold.
- [ ] GitHub OAuth login via Supabase Auth.
- [ ] Screens:
  - Installations: list repos under this org.
  - PR history: per-repo, recent PRs + statuses.
  - Analysis detail: all findings, plain-language summary.
  - Settings: block mode, allowlists, retention.
- [ ] Reuse `.webp` mockups + `.txt` UI snippets from design phase.
- [ ] Link to GitHub PR + Check Run.
- [ ] Pagination + sorting (recent first).

**Verify:**
- [ ] Login → see repos → open a PR → read findings.
- [ ] Settings change takes effect on next PR.

**Duration:** 1 week.

---

## Phase 7 — The Crew (AI Explainer) — Advisory Only

**Goal:** Claude Haiku explains each finding in plain English + suggested fix. Never blocks.

**Tasks:**
- [ ] Claude Haiku 4.5 integration (`anthropic` SDK).
- [ ] Fallback: Gemini 2.5 Flash-Lite if Claude rate-limited.
- [ ] Per-finding prompt:
  - "Explain this finding to a non-technical founder."
  - "Why does it matter? (attack example, likelihood)"
  - "How to fix it? (code example, link to docs)"
- [ ] Diff context only (don't pass entire PR).
- [ ] Prompt caching to reduce cost.
- [ ] Cost logging (tokens + USD per PR).
- [ ] Strict rule: never change a check conclusion; never claim AI authorship.
- [ ] Dashboard UI: "Explain" tab per finding.

**Verify:**
- [ ] Flagged PR → clear explanation + fix appears.
- [ ] Cost <$0.001 per PR (fraction of a cent).
- [ ] Conclusion unchanged (Guard findings immutable).

**Duration:** 1 week.

---

## Phase 8 — Config & Multi-Tenant

**Goal:** Per-repo settings, org defaults, audit trail.

**Tasks:**
- [ ] `.slopguard.yml` per repo (version controlled):
  ```yaml
  block_mode: false
  blocked_rules: "SQG001,SQG002"
  ai_enabled: true
  ai_model: "claude-haiku-4-5"
  path_allowlist: ["test/", "docs/"]
  rule_allowlist: ["SQG003"]
  retain_findings_days: 90
  ```
- [ ] Org defaults (fallback if no `.slopguard.yml`).
- [ ] Dashboard editor → audit log every change.
- [ ] Per-analyzer kill switch: `DISABLED_ANALYZERS` env var + DB flag.

**Verify:**
- [ ] Flip a setting → takes effect next PR.
- [ ] Audit log shows who changed what.

**Duration:** 3 days.

---

## Phase 9 — Opt-In Blocking (Carefully)

**Goal:** Enable blocking ONLY for CERTAIN findings, ONLY if repo opted in, ONLY after measured FP <1%.

**Tasks:**
- [ ] Gate: setting `block_mode: true` required.
- [ ] Block only CERTAIN findings (SQG001, verified SQG002).
- [ ] Measure: track FP rate in production for N PRs (target <1%).
- [ ] Human-in-the-loop bypass: dashboard "Approve this finding" (logged in audit trail).
- [ ] PR comment: "This finding would block the merge. Override?" (with link).
- [ ] Conclusion: `failure` (red), merge blocked.

**Verify:**
- [ ] PR with verified secret + block on → blocked.
- [ ] Advisory-only PR (HIGH/MEDIUM) → never blocked.
- [ ] Bypass logged in audit.

**Duration:** 1 week.

---

## Phase 10 — Harden & Ship to Production

**Goal:** Distroless image, CI scan pipeline, secrets externalized, zero-downtime deploy, alerts, custom domain.

**Tasks:**
- [ ] Distroless multi-stage Dockerfile (non-root, <200 MB).
- [ ] CI scan pipeline (the app checks itself):
  - Run Guard on its own repo.
  - Semgrep scan.
  - Trivy scan.
  - gitleaks scan.
- [ ] Secrets externalized (never in image/code):
  - `fly secrets set`.
  - Vercel env vars.
- [ ] Cloudflare WAF + rate limiting in front of webhook.
- [ ] OTel tracing end-to-end by correlation ID.
- [ ] Alembic expand-contract migrations (safe, no downtime).
- [ ] Rollback: `fly releases rollback` instant.
- [ ] Alerts: ACK p95 >5s, queue depth >5000, failure rate >1%.
- [ ] Custom domain + TLS (Fly/Vercel auto-provision Let's Encrypt).
- [ ] Monitoring dashboard (Sentry, basic Prometheus).

**Verify:**
- [ ] Push to main → CI scans + zero-downtime deploy.
- [ ] Deliberately break a build → rollback restores.
- [ ] Trace one PR end-to-end by delivery ID.

**Duration:** 1 week.

---

## Phase 11 — Polish, Docs, Public Release

**Goal:** Full documentation, blog post, first users onboard.

**Tasks:**
- [ ] Finalize all 10 reference docs (this roadmap + BUILD_GUIDE, PRD).
- [ ] Record setup walkthrough video.
- [ ] Blog post: "We're building the safety net for AI-generated code."
- [ ] GitHub README (simple, feature list, quick start).
- [ ] API docs auto-generated (Swagger at `/docs`).
- [ ] Community Slack/Discord (optional, Phase 11+).

**Verify:**
- [ ] Docs complete + reviewed.
- [ ] First 10 beta users onboard without friction.

**Duration:** 1 week.

---

## Total Estimate

**~10–12 weeks** (Phase 0–11), parallel where possible:
- Phase 0: 2–3 days (parallel with Phase 1).
- Phase 1–2: 1 week.
- Phase 3: 2 weeks (the calibration is thorough).
- Phase 4–5: 1 week.
- Phase 6–7: 2 weeks.
- Phase 8–9: 1 week.
- Phase 10–11: 2 weeks.

**Accelerators:**
- Use the Qwen scaffold as reference (adjust, don't copy).
- Pre-generated mocks (design phase deliverables).
- Fixed testing discipline (fixture bank prevents FP spirals).

---

## Success Criteria (Definition of Done)

Phase 0: Repo boots locally.
Phase 1: Webhook accepted <1s.
Phase 3: One analyzer calibrated, zero FP.
Phase 4: **First demoable (PR findings visible).**
Phase 6: **First users onboardable.**
Phase 10: **Production ready (live without babysitting).**

---

## Living Updates

Phases are sequences; actual execution may reorder based on user feedback. Update this doc after each phase.

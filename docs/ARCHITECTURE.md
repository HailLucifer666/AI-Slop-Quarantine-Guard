# Architecture
## PR Quality & Security Gate

---

## 1. System Overview

The system has three moving parts:

1. **API server** — receives GitHub webhook events, verifies them, and queues jobs.
2. **Worker** — picks up queued jobs, runs all checks, writes results back to GitHub and the database.
3. **Dashboard** — a web app where users log in, see results, and configure settings.

These three parts are deployed separately and communicate through a queue (Redis) and a database (Postgres).

---

## 2. Top-Level Data Flow

```
GitHub                    Cloudflare Edge          API Server (Fly.io)
  │                            │                         │
  │  POST /webhooks/github      │                         │
  │ ──────────────────────────► │  WAF + rate-limit       │
  │                            │ ──────────────────────► │
  │                            │                         │  1. Verify HMAC-SHA256
  │                            │                         │     (raw body, constant-time)
  │                            │                         │  2. Dedupe on X-GitHub-Delivery
  │                            │                         │     (Redis + DB — from Phase 1)
  │                            │                         │  3. Enqueue job → Redis (arq)
  │                            │                         │  4. Return 202 Accepted
  │ ◄──────────────────────────────────────────────────── │
  │  (< 500 ms)                                           │
  │
  │         Worker (Fly.io, same app or separate process)
  │                   │
  │  1. Dequeue job   │
  │  2. Mint App-JWT (RS256 private key) → GitHub API
  │  3. Exchange JWT for installation token (cached, reused until 5 min pre-expiry)
  │  4. Fetch PR diff via GitHub REST API
  │  5. Parse diff → manifest-aware (requirements.txt, package.json, Cargo.toml, etc.)
  │  6. Create "in_progress" Check Run on the PR (user sees spinner immediately)
  │  7. Run The Guard (all analyzers in parallel, each in try/except)
  │  8. Run The Crew (AI explainer, Phase 7+)
  │  9. Write Check Run result to GitHub Checks API
  │  10. Persist analysis + findings to Postgres
  │
  │ ◄── GitHub Checks API posts result back to PR UI
```

---

## 3. The Guard / Crew Separation

This is the most important design constraint. These two layers must never be mixed.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Worker Job                               │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  THE GUARD  (deterministic — never guesses)              │  │
│  │                                                          │  │
│  │  Plugin Engine: each analyzer is a registered plugin     │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │  │
│  │  │ SQG001   │ │ SQG002   │ │ SQG004   │ │ SQG003   │   │  │
│  │  │ Fake pkg │ │ Secrets  │ │ CVEs     │ │Placeholdr│   │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐                │  │
│  │  │ SQG005   │ │ SQG006   │ │ SQG007   │                │  │
│  │  │ Licenses │ │ Outdated │ │ AI scrpad│                │  │
│  │  └──────────┘ └──────────┘ └──────────┘                │  │
│  │                                                          │  │
│  │  Each analyzer → list[Finding]                           │  │
│  │  confidence_resolver: (raw_output, context) → confidence │  │
│  │  Trust-status per analyzer: completed|degraded|failed    │  │
│  │                                                          │  │
│  │  Output: list[Finding], trust_status_map                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                         │                                       │
│                         │  findings flow ONE WAY →              │
│                         ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  THE CREW  (AI explainer — advisory only, Phase 7+)      │  │
│  │                                                          │  │
│  │  Input: list[Finding] (read-only — cannot modify)        │  │
│  │  LLM: Claude Haiku 4.5 (Gemini 2.5 Flash-Lite fallback)  │  │
│  │  Context: diff-only (not full repo) + prompt caching     │  │
│  │                                                          │  │
│  │  Per finding:                                            │  │
│  │    • Plain-English explanation                           │  │
│  │    • Why it matters (attack scenario, likelihood)        │  │
│  │    • How to fix (code example)                           │  │
│  │    • References                                          │  │
│  │                                                          │  │
│  │  RULES: never changes a finding's conclusion.            │  │
│  │         never asserts AI authorship.                     │  │
│  │         never blocks a PR.                               │  │
│  │         logs cost per PR.                                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                         │                                       │
│                         ▼                                       │
│  GitHub Checks API + Postgres persist                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Plugin Engine

Analyzers are registered plugins behind one interface. This means:
- Any analyzer can be enabled or disabled without touching other analyzers.
- New analyzers (custom rules, third-party tools) can be added without changing core code.
- Each analyzer has a per-analyzer kill switch: an environment variable (`DISABLED_ANALYZERS`) or database flag disables it instantly without redeployment.

**Analyzer interface (each plugin must implement):**

```
id: str                    # e.g., "SQG001"
version: str               # e.g., "1.0.0"
confidence_model: str      # "CERTAIN" | "HIGH" | "MEDIUM"
enabled: bool              # respects kill switch
analyze(diff, context) → list[Finding]
```

**Analyzer health tracking (per analyzer, visible in dashboard):**
- Success percentage
- Average and p95 runtime
- Last failure reason
- False-positive count (user-reported)
- Queue time

---

## 5. Forge Adapter Seams

The core engine is forge-agnostic. GitHub is the MVP adapter. The seams are defined now so adding GitLab/Bitbucket/Azure DevOps later = write a new adapter, not a rewrite.

```
GitHub Adapter          Core Engine              Output Adapter
─────────────           ────────────             ──────────────
Webhook parse     →     Diff parse           →   GitHub Checks API
Installation token      Analyzer orchestration   PR review comments
Rate limit handling     Finding normalization     Dashboard API
```

---

## 6. The Universal Finding Record

Every analyzer outputs findings in this single format. This is the "currency" of the system — everything downstream (Crew, GitHub output, dashboard, database) works with this record.

```python
Finding {
    # Identity
    rule_id: str              # "SQG001"
    category: str             # "fake_package" | "secret" | ...

    # Confidence (three-axis — these are different concepts)
    evidence_confidence: str  # how strong is the raw signal from the tool
    finding_confidence: str   # CERTAIN | HIGH | MEDIUM (after context applied)
    block_eligible: bool      # true only for CERTAIN + verified findings

    # Location
    file_path: str
    line_start: int
    line_end: int

    # Content
    message: str              # human-readable summary
    evidence: {
        snippet: str          # the exact code/text that triggered the finding
        context_before: list[str]
        context_after: list[str]
    }
    fix_suggestion: str | None

    # Immutability / audit
    analyzer_version: str     # version of the analyzer that produced this
    rule_version: str         # version of the rule definition
    tool_version: str         # version of the underlying tool (e.g., gitleaks 8.x)
    diff_sha256: str          # sha256 of the diff — ties finding to exact code state
    evidence_sha256: str      # sha256 of the evidence — cryptographically reproducible

    # Trust / status
    analyzer_trust_status: str  # "completed" | "degraded" | "failed" | "skipped"
}
```

**Immutability rule:** findings are never overwritten after creation. If an analyzer is re-run (e.g., after a bad deploy), a new record is created. The audit trail is append-only. This answers "why did this pass yesterday and fail today?"

---

## 7. Confidence Resolver

A single, small, unit-tested function: `confidence_resolver(raw_output, context) → final_confidence`

This is the most trust-critical code in the system. It centralizes the logic for:
- Is the registry actually reachable? (if not → never CERTAIN)
- Is the file path in the allowlist? (test fixtures, examples → downgrade or skip)
- Does the secret checksum verify? (if not → HIGH not CERTAIN)
- Is the package in a workspace/monorepo config? (whitelist → skip)
- Is the package brand new (< 72 hours)? (grace window → advisory)

---

## 8. Trust-Status State Machine

Each analysis has an overall trust status derived from all analyzer statuses. This is visible in the dashboard as a colored dot.

```
Per analyzer:
  completed  →  all checks ran, results reliable
  degraded   →  ran but with reduced reliability (e.g., registry timeout → some deps unchecked)
  failed     →  crashed or produced an error finding
  skipped    →  disabled via kill switch or over diff-size budget

Overall analysis status:
  Green  =  all analyzers: completed
  Yellow =  any analyzer: degraded  (findings may be incomplete — shown in UI)
  Red    =  any analyzer: failed
```

Yellow means "we checked what we could, but some checks were uncertain." This is honest — it differentiates the product from black-box tools that silently skip checks.

---

## 9. Webhook Security

The webhook handler applies these checks in order before any business logic runs:

1. **Max payload size check** — reject anything over 5 MB with 413 before JSON parsing (DoS guard).
2. **HMAC-SHA256 verification** — on the raw request body, constant-time comparison. 401 on mismatch.
3. **Dedupe on `X-GitHub-Delivery`** — checked in Redis (fast path) and Postgres (durable). Redeliveries are silently accepted with 202 but not re-queued.
4. **Cloudflare WAF** — locks webhook endpoint to GitHub's published IP ranges. Rate limiting at the edge before traffic reaches the API server.

**ACK target:** < 500 ms (p95) from receipt to 202 response. All heavy work happens in the worker, not the webhook handler.

---

## 10. GitHub Authentication Chain

```
API private key (RS256, stored in Fly.io secrets, never in repo or image)
  │
  ▼
App-JWT (minted fresh, valid 10 min, signed with private key)
  │
  ▼
GitHub API: POST /app/installations/{id}/access_tokens
  │
  ▼
Installation token (valid 1 hour, cached until 5 min pre-expiry)
  │
  ▼
All GitHub API calls for this job use this token
```

One token mint per hour per installation (cached). Many jobs reuse the same token.

---

## 11. Retry / Failure Classification

Failures are classified and retried differently:

| Type | Example | Retry behavior |
|------|---------|----------------|
| `permanent` | Registry returns clean 404 | Record finding, don't retry |
| `transient` | Network timeout | Exponential backoff, up to N attempts |
| `rate_limited` | HTTP 429 from registry or GitHub | Honor `Retry-After` header |
| `auth` | Installation token expired | Re-mint token, retry once |
| `config` | Missing required env var | Fail loudly, do not retry |
| `tool_crash` | gitleaks segfault | Retry N times, then emit `failed` trust status |

---

## 12. Performance Budgets

These are hard targets, tested in CI on every code change. Exceeded → degrade gracefully (skip the slow check with a `degraded` status), never hang.

| Operation | Budget |
|-----------|--------|
| Webhook ACK (202 response) | < 500 ms (p95) |
| Dependency existence check | < 2 seconds |
| Secret scan | < 4 seconds |
| Full analysis (all checks) | < 30 seconds (p95) |
| Dashboard page load | < 1 second |

**Diff size cap:** If a PR diff exceeds the configured size limit (sized to stay within Fly.io's 256 MB RAM budget given Trivy/OSV memory use), the analysis degrades gracefully with an advisory: "PR too large for deep scan — manual review recommended."

---

## 13. GitHub Checks API Output Rules

- Check Run created as `in_progress` when the job starts (user sees a spinner immediately).
- Completed with `action_required` (orange, highly visible) if any HIGH or CERTAIN finding exists.
- Completed with `success` (green) if no findings.
- **Never use `neutral`** — it renders as a green checkmark and makes findings invisible.
- Summary is truncated to fit GitHub's character limit: top-N findings + "X more findings — see dashboard."
- PR review comments are posted for the top findings, anchored to the exact line.
- **Reconciliation task:** any Check Run still `in_progress` after 5 minutes is automatically closed as `action_required` with message "analysis timed out." No orphaned spinners.
- **Rate budget:** GitHub Checks API allows 1,000 updates per hour per repo. The system does not double-update; one transition from `in_progress` to final state.

---

## 14. Database Schema (Summary)

Full schema in `DATA_MODEL.md`. Key tables:

| Table | Purpose |
|-------|---------|
| `webhook_deliveries` | Dedupe table. PK = `delivery_guid` (`X-GitHub-Delivery`). Written atomically before enqueue. |
| `analyses` | One row per PR analysis. Columns include: `repo`, `pr_number`, `head_sha`, `trust_status`, `started_at`, `completed_at`. Idempotent on `(repo, pr_number, head_sha)`. |
| `findings` | One row per Finding. Foreign key to `analyses`. Append-only; never updated. |
| `audit_log` | Config changes, bypass approvals, re-runs. Append-only. |
| `analyzer_health` | Rolling stats per analyzer: success %, p95 runtime, last failure. |

---

## 15. Cost Tracking

Cost is tracked from day one, even before the AI Crew ships:

| Metric | Target |
|--------|--------|
| Per PR | ~$0.003 |
| Per repo / month | ~$0.10 |
| Per user / month | ~$3.00 |

The Crew logs LLM cost per PR. This makes pricing decisions grounded in real data, not guesswork.

---

## 16. Observability

Every PR analysis is traceable end-to-end by a single `correlation_id` (the `X-GitHub-Delivery` value):

- **Structured logs:** `structlog` → JSON, includes `correlation_id` on every log line.
- **Distributed tracing:** OpenTelemetry — spans for webhook receive, enqueue, dequeue, each analyzer, GitHub API calls.
- **Error tracking:** Sentry — captures exceptions with full context.
- **Metrics:** Prometheus counters for webhook ACK time, analysis completion time, analyzer success/failure rates, queue depth.
- **Queue-depth alert:** alert fires if the worker queue exceeds a threshold (indicates worker is falling behind or crashed).

---

## 17. Repository Structure

```
Code Workspace/
├── api/
│   └── app/
│       ├── main.py              # FastAPI: POST /webhooks/github, GET /healthz
│       ├── security.py          # HMAC-SHA256 verify (raw body, constant-time)
│       ├── queue.py             # arq enqueue + worker settings
│       ├── github_auth.py       # App-JWT RS256 → installation token + cache
│       ├── github_client.py     # httpx client with retry + rate-limit handling
│       ├── diff.py              # fetch + parse PR diff (manifest-aware)
│       ├── manifests.py         # parse requirements/pyproject/package.json/Cargo
│       ├── analyzers/
│       │   ├── base.py          # Finding model + Analyzer protocol + try/except wrapper
│       │   ├── dependencies.py  # SQG001: registry existence + fail-safe + workspace whitelist
│       │   ├── secrets.py       # SQG002: gitleaks runner + path allowlist
│       │   ├── placeholders.py  # SQG003: regex + tree-sitter AST
│       │   ├── vulns.py         # SQG004: trivy / osv-scanner
│       │   ├── licenses.py      # SQG005: license check
│       │   └── sast.py          # Semgrep runner (P0/P1 rules only)
│       ├── checks.py            # GitHub Checks API output (truncation-safe)
│       ├── crew/                # Phase 7: AI explainer — prompts, router, caching
│       ├── db/                  # SQLAlchemy 2.0 models + Alembic migrations
│       ├── observability.py     # structlog + OTel + correlation-id
│       ├── config.py            # settings, DISABLED_ANALYZERS kill-switch
│       └── worker.py            # arq task: job → analyzers → check run → persist
│   └── tests/
│       └── fixtures/            # positive + negative fixture bank (8-10 cases each)
│   └── pyproject.toml
│   └── Dockerfile               # multi-stage, distroless, non-root
├── web/                         # Next.js 15 dashboard (App Router + Tailwind + shadcn/ui)
├── infra/
│   ├── fly.toml
│   └── docker-compose.yml       # local: postgres + redis + api + worker
├── .github/
│   └── workflows/
│       └── ci.yml               # test → semgrep → trivy → gitleaks → build → deploy
├── docs/                        # this document set
└── Makefile                     # `make dev` starts everything with one command
```

---

## 18. Deployment Topology

```
Internet
  │
  ▼
Cloudflare (WAF, rate-limit, DDoS, IP allowlist for GitHub hooks)
  │
  ├── /webhooks/github  ──►  Fly.io (API server, Python/FastAPI)
  │                              │
  │                              ▼
  │                          Upstash Redis (job queue + dedupe + rate-limit state)
  │                              │
  │                              ▼
  │                          Fly.io (Worker, same image or separate process)
  │                              │
  │                              ▼
  │                          Supabase (Postgres — analyses, findings, audit_log)
  │
  └── dashboard  ──────►  Vercel (Next.js 15, auto-deploy on git push)
                               │
                               ▼
                           Supabase Auth (GitHub OAuth, operator login)
```

**Secrets:** Never in the repository or Docker image. API private key and webhook secret injected at runtime via `fly secrets set`. Dashboard env vars set in Vercel dashboard.

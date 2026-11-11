# Build Guide
## PR Quality & Security Gate — Idea → Live in Production

> **Who this is for:** A non-technical founder who does not write code. Every step is numbered. Every command is copy-pasteable. Every phase ends with a verify check so you know it worked before moving on.
>
> **How to read this:** Work through phases in order. Do not skip a phase. Each phase has a "What you're doing and why" section, then the exact steps, then a verify check. Only advance when the verify check passes.
>
> **Where you type commands:** In the "terminal" (also called command prompt or shell). On Mac: open Terminal. On Windows: open PowerShell. Commands start with `$` — don't type the `$`, just what comes after it.

---

## Phases at a Glance

| Phase | What Happens | Who Acts |
|-------|-------------|----------|
| 0 | Create all accounts, scaffold repo | **You (manual)** |
| 1 | Webhook receives GitHub events | Dev |
| 2 | Worker fetches PR content | Dev |
| 3 | Checkers analyze the PR | Dev |
| 4 | Results appear on the PR | Dev — **first demoable moment** |
| 5 | History stored in Postgres | Dev |
| 6 | Dashboard live — **usable product** | Dev |
| 7 | AI Crew explains findings in plain English | Dev |
| 8 | Per-repo configuration | Dev |
| 9 | Opt-in blocking | Dev |
| 10 | Hardened, production-ready | Dev — **live** |

---

## Phase 0 — Accounts, Credentials, and Repo Scaffold

### What you're doing and why

Before any code runs, you need accounts on five services and a GitHub App registration. This phase is entirely manual — only you can create these accounts and generate the credentials. No developer can do this step for you.

The credentials you create here get injected into the app as "secrets" — they are never written into the code or the repository.

### Step 0.1 — Create a GitHub App

A GitHub App is different from a regular GitHub account. It's a bot identity that gets installed on repositories and can read pull requests, post check results, and react to webhooks.

1. Go to: **GitHub → Your account → Settings → Developer settings → GitHub Apps → New GitHub App**
2. Fill in:
   - **App name:** `pr-quality-gate` (or your chosen name)
   - **Homepage URL:** `https://yourproduct.com` (placeholder for now)
   - **Webhook URL:** leave blank for now — you'll fill it in Phase 1
   - **Webhook secret:** click "Generate" and save the value somewhere safe (e.g., a password manager)
3. **Permissions — set these exactly:**
   - Pull requests: Read & Write
   - Checks: Read & Write
   - Contents: Read
   - Metadata: Read (required, auto-checked)
4. **Subscribe to events:**
   - `pull_request`
   - `installation`
   - `check_run`
5. Click **Create GitHub App**
6. On the next page:
   - Note the **App ID** (a number)
   - Click **Generate a private key** — a `.pem` file downloads. Save it somewhere safe. This is your signing key.
7. Install the App on a test repository: **GitHub App page → Install App → choose a repo**

> **You must save:** App ID, Webhook Secret, the `.pem` private key file. These go into Fly.io secrets in Phase 1.

---

### Step 0.2 — Create a Supabase account (database + auth)

Supabase is a managed Postgres database. It also handles user login for the dashboard.

1. Go to **supabase.com** → Sign up (free)
2. Create a new project:
   - Name: `pr-quality-gate`
   - Region: choose closest to you
   - Generate a strong database password and save it
3. Once the project is created, go to **Settings → API**
4. Save:
   - **Project URL** (looks like `https://xxxx.supabase.co`)
   - **anon/public key**
   - **service_role key** (keep this secret)
5. Go to **Settings → Database** and save the **connection string** (the `postgres://...` URL)

---

### Step 0.3 — Create an Upstash account (Redis queue)

Upstash is a managed Redis service. It acts as the job queue between the webhook receiver and the worker.

1. Go to **upstash.com** → Sign up (free)
2. Create a Redis database:
   - Name: `pr-quality-gate-queue`
   - Region: same region as Supabase
3. Once created, go to the database details page and save:
   - **Redis URL** (the `redis://...` or `rediss://...` connection string)

---

### Step 0.4 — Create a Fly.io account (API + worker hosting)

Fly.io runs the backend. Your code runs in containers close to your users.

1. Go to **fly.io** → Sign up (free tier available)
2. Install the Fly CLI on your computer:
   - Mac: `$ brew install flyctl`
   - Windows: follow instructions at fly.io/docs/hands-on/install-flyctl/
3. Log in: `$ flyctl auth login`
4. No app created yet — that happens in Phase 10.

---

### Step 0.5 — Create a Vercel account (dashboard hosting)

Vercel hosts the Next.js dashboard. It deploys automatically whenever you push code.

1. Go to **vercel.com** → Sign up with GitHub
2. No project created yet — that happens in Phase 6.

---

### Step 0.6 — Create a Cloudflare account (edge security)

Cloudflare sits in front of your webhook and protects it from abuse.

1. Go to **cloudflare.com** → Sign up (free)
2. No configuration needed yet — that happens in Phase 10.

---

### Step 0.7 — Get an Anthropic API key (for the AI Crew)

The AI Crew uses Claude Haiku 4.5.

1. Go to **console.anthropic.com** → Sign up
2. Go to **API Keys** → Create key
3. Save the key (starts with `sk-ant-...`)
4. Also get a **Gemini API key** from **aistudio.google.com** as the fallback (free tier available)

---

### Step 0.8 — Scaffold the repository

The developer sets up the folder structure and wires everything together. You provide the credentials from above.

Create a `.env` file in the project root (this file is gitignored — it never goes into the repository):

```
# GitHub App
GITHUB_APP_ID=12345
GITHUB_WEBHOOK_SECRET=your_webhook_secret_here
GITHUB_PRIVATE_KEY_PATH=./github-app.pem

# Supabase
DATABASE_URL=postgres://postgres:password@db.xxxx.supabase.co:5432/postgres
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here

# Redis (Upstash)
REDIS_URL=rediss://your_upstash_url_here

# AI Crew (Phase 7)
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=your_gemini_key_here

# Kill switches (comma-separated rule IDs to disable)
DISABLED_ANALYZERS=
```

Copy your `.pem` file into the project root as `github-app.pem`.

### ✅ Verify Phase 0

- [ ] GitHub App exists and is installed on a test repo
- [ ] Supabase project is running, connection string saved
- [ ] Upstash Redis URL saved
- [ ] Fly CLI installed, logged in
- [ ] Vercel account created
- [ ] Cloudflare account created
- [ ] `.env` file populated with all credentials
- [ ] `make dev` command starts without errors (API + worker + local Postgres + local Redis all boot)

---

## Phase 1 — Webhook Spine

### What you're doing and why

The GitHub App needs a URL to send events to. When someone opens a pull request, GitHub POSTs a JSON payload to that URL. This phase builds the receiver: a small web server that verifies the payload is genuinely from GitHub, deduplicates retries, queues a job for the worker, and immediately responds with "got it" (HTTP 202).

Speed matters here. GitHub expects a response within a few seconds. All heavy work goes to the worker queue.

### Steps (developer executes)

1. Build `POST /webhooks/github` endpoint
2. Implement HMAC-SHA256 signature verification on the raw request body (constant-time comparison)
3. Check the `X-GitHub-Delivery` header against Redis (fast dedupe) and Postgres (durable dedupe) — reject duplicates silently with 202
4. Enqueue job to Redis (arq)
5. Return 202 immediately
6. Add `GET /healthz` endpoint (returns `{"status": "ok"}`)
7. Add `structlog` JSON logging with `correlation_id` = the `X-GitHub-Delivery` value on every log line
8. Wire the GitHub App webhook URL to the running server:
   - Use `ngrok` or `cloudflared tunnel` locally to get a public URL for your laptop
   - Paste it into: **GitHub App → Webhook URL**

### ✅ Verify Phase 1

- [ ] Open a PR on the test repo → server logs show the delivery ID within 1 second
- [ ] Server responds 202 in under 1 second
- [ ] Job appears in Redis queue
- [ ] Row appears in `webhook_deliveries` table in Postgres
- [ ] Redeliver the same webhook from GitHub App settings → second delivery is accepted (202) but not re-queued
- [ ] Send a request with a wrong signature → server returns 401
- [ ] `GET /healthz` returns 200 `{"status":"ok"}`

---

## Phase 2 — Worker + GitHub Auth

### What you're doing and why

The worker is a separate process that picks up jobs from the Redis queue. It needs to authenticate with GitHub using the App's private key, then fetch the actual code diff from the pull request.

The authentication is a two-step chain: the private key generates a short-lived "App JWT," which is exchanged for an "installation token" that allows reading the repository. The token is cached to avoid minting a new one for every job.

### Steps (developer executes)

1. Build the arq worker process
2. Implement App-JWT generation (RS256 signing with the private key)
3. Exchange JWT for installation token via GitHub API; cache it in Redis until 5 minutes before expiry
4. Build `github_client.py`: httpx async client with retry/backoff, rate-limit handling (`X-RateLimit-Remaining` header, `Retry-After` header)
5. Fetch the PR diff via GitHub REST API
6. Parse the diff (manifest-aware: identify `requirements.txt`, `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod` lines that add dependencies)
7. Enforce diff size cap: if diff exceeds budget, emit advisory finding and skip deep scan
8. Handle graceful SIGTERM shutdown (finish current job, don't abandon)

### ✅ Verify Phase 2

- [ ] Open a PR on the test repo → worker logs show it dequeued the job and fetched the diff
- [ ] Token is minted once and reused across multiple jobs within the same hour
- [ ] App survives a redeploy mid-job (SIGTERM → job finishes or re-queues cleanly)
- [ ] A PR that is too large → worker emits advisory, does not crash

---

## Phase 3 — The Guard (Analyzers)

### What you're doing and why

This is the core of the product. Each analyzer is built and calibrated one at a time. "Calibrated" means: tested against real public repositories and a fixture bank (deliberately crafted test cases) until the false-positive rate on clean code is zero.

Build order within this phase:
1. **SQG001 — fake package checker** (highest impact, build first, calibrate fully before moving on)
2. **SQG002 — secret scanner**
3. **SQG004 — CVE/vulnerable dependency**
4. **SQG005 — license check**
5. **SQG006 — outdated dependency**
6. **SQG003 — placeholder code**
7. **SQG007 — typosquatted package name** (always on, advisory only). The AI-scratchpad
   detector this number used to name is unimplemented and re-numbered SQG008.

### SQG001 — Fake Package Checker

**What it does:** For every package added in the diff, queries the public registry (PyPI, npm, crates.io) to verify the package exists. There is no Go proxy client — Go, Maven, RubyGems, Packagist and NuGet are covered by the CVE check (SQG004), not by this one; `docs/CHECKS_CATALOG.md` explains why a CERTAIN 404 is not safe in those ecosystems yet.

**False-positive controls (critical):**
- Registry unreachable / timeout / rate-limited → retry with backoff → if still failing, emit `degraded` status (never block)
- Package in a workspace config (`pnpm-workspace.yaml`, `turbo.json`, `Cargo.toml` workspace, `workspace:` / `file:` / `link:` prefixes) → skip (it's a local package)
- Scoped org package (`@myorg/something`) → check private registry config before querying public
- Package registered within last 72 hours → emit advisory (not CERTAIN), note the grace window

### SQG002 — Secret Scanner

**What it does (today):** runs a curated in-process pattern set with format validation over the diff — **not** gitleaks, which is not installed or invoked. Hits are mapped to lines added in this PR, never lines from history. Wrapping gitleaks is planned; until then the scan's coverage record states that this check ran on the built-in matcher only.

**False-positive controls:**
- Path allowlist: `*.example`, `test/`, `fixtures/`, `*.md` (documentation examples)
- Confidence: HIGH (offline pattern + entropy + format checksum). CERTAIN requires checksum match of a known secret format (e.g., `AKIA...` for AWS keys).
- Live secret verification (calling AWS with the key to test if it works) is **deferred post-v1** — legal/ethical risk.

### SQG004 — CVE Scanner

**What it does (today):** queries the OSV.dev HTTP API in batches for exactly-pinned dependencies. Trivy and osv-scanner are **not** installed or invoked, so ecosystems whose manifests the in-process parsers can't read (Go modules, Maven, Gradle, Bundler, Composer, NuGet) are reported as not covered rather than as clean.

**Confidence:** HIGH. The match to the CVE database is factual; whether your specific code is exploitable requires deeper analysis we don't do yet. Therefore CVEs are advisory, not block-eligible.

### SQG003, SQG005, SQG006, SQG007

Built similarly: each wrapped in try/except, each with positive and negative fixtures, each calibrated before shipping.

### The fixture bank

Every analyzer must have:
- **Positive fixtures** (deliberately broken cases that must be caught): fake package, real leaked secret format, stub with `pass` body, dep with known CVE, GPL license in proprietary project, `TODO:` in non-comment code, `<thinking>` block
- **Negative fixtures** (clean code that must not flag): real packages, test fixtures with fake-looking strings, lockfiles, generated code, README examples, monorepo workspace packages, vendored directories

### Steps (developer executes)

1. Build `analyzers/base.py`: Finding model, Analyzer protocol, try/except wrapper (any crash → structured `errored` finding, never a silent skip)
2. Build `confidence_resolver.py`: the single unit-tested function that maps raw tool output + context to final confidence
3. Build each analyzer per the order above
4. Calibrate SQG001 against ~20 real public repos (5 Python, 5 JS, 5 Rust, 5 expected-clean)
5. Gate: only move to the next analyzer when the clean fixture set produces zero unexpected CERTAIN findings
6. Build the benchmark repo (fixture bank in CI — runs on every code change)

### ✅ Verify Phase 3

- [ ] Every positive fixture caught at the exact line
- [ ] Clean fixture set (README, lockfiles, generated code, test fixtures, monorepo workspaces) produces zero false positives
- [ ] Any analyzer crash → `errored` finding in output, not a silent skip and not an exception that kills the job
- [ ] Registry unreachable → `degraded` trust status, not a block
- [ ] Benchmark CI job passes green

---

## Phase 4 — Results on the PR

### What you're doing and why

Right now the worker runs checks but the results are only in logs. This phase makes results visible directly on the pull request via GitHub's Checks API.

**This is the first demoable moment.** After this phase, you can show someone a PR with findings appearing automatically.

### Steps (developer executes)

1. Build `checks.py`: creates a Check Run as `in_progress` when the job starts (user sees a spinner on the PR immediately)
2. On completion: write `action_required` (orange, highly visible) if any finding exists; `success` (green) if clean
3. **Never use `neutral`** — it renders as green and hides findings
4. Truncate the summary to fit GitHub's character limit: show top-N findings + "X more — see dashboard [link]"
5. Post PR review comments for top findings, anchored to the exact diff line
6. Build the reconciliation task: any Check Run still `in_progress` after 5 minutes → automatically close as `action_required` "analysis timed out"

### ✅ Verify Phase 4

- [ ] Open a PR that adds a fake package → orange check appears at the exact line within 30 seconds
- [ ] PR is not blocked (blocking is Phase 9)
- [ ] Clean PR → green check
- [ ] Deliberately kill the worker mid-job → after 5 minutes, the Check Run closes with "timed out" message (not an orphaned spinner forever)
- [ ] **Show this to a real person.** Does the finding make sense? Is the line reference correct? This is your first user feedback loop.

---

## Phase 5 — Persistence (Postgres)

### What you're doing and why

Until now, the database used for local development is SQLite (a simple file). This phase migrates to the real Postgres database on Supabase, adds the full production schema, and ensures every analysis is stored and queryable.

### Steps (developer executes)

1. Switch `DATABASE_URL` to the Supabase connection string (in `.env`)
2. Run Alembic migrations to create the full schema:
   - `webhook_deliveries` (PK = delivery GUID, deduplication)
   - `analyses` (one per PR analysis, idempotent on `repo + pr_number + head_sha`)
   - `findings` (append-only, never updated)
   - `audit_log` (config changes, bypass approvals)
   - `analyzer_health` (per-analyzer rolling stats)
3. Enable retention policy (findings older than N days are archived or deleted per config)
4. Test worker idempotency: if a PR is re-analyzed (e.g., new push to the same PR), the existing concluded analysis is refreshed rather than duplicated

```bash
# Run migrations
$ cd api
$ alembic upgrade head
```

### ✅ Verify Phase 5

- [ ] Analysis history queryable in Supabase table editor
- [ ] Redelivering the same webhook → deduplicated at DB level, no duplicate analysis row
- [ ] Re-pushing to an open PR → new analysis row created (different `head_sha`), old row preserved
- [ ] No analysis lost between the local SQLite phase and Supabase

---

## Phase 6 — Dashboard

### What you're doing and why

The dashboard is the web interface where users log in with GitHub, see their repositories, browse PR history, and read findings in a readable format. After this phase, the product is usable by real users — not just testable via raw GitHub PR checks.

### Steps (developer executes)

1. Initialize Next.js 15 project in `web/`:
```bash
$ npx create-next-app@latest web --typescript --tailwind --app
```
2. Add shadcn/ui components:
```bash
$ cd web && npx shadcn-ui@latest init
```
3. Set up Supabase Auth with GitHub OAuth (users log in with their GitHub account)
4. Build screens:
   - **Installations/repos** — list of repos where the App is installed
   - **PR history** — per-repo list of analyzed PRs with status dots (green/orange/red/yellow)
   - **Analysis detail** — findings list with rule ID, location, message, confidence level
5. Connect to the backend API to fetch analysis data
6. Deploy to Vercel:
   - Push the `web/` directory to GitHub
   - Connect the repo to Vercel (vercel.com → Import Project)
   - Vercel auto-deploys on every push

**Authorization rule (important for security):** A logged-in user may only view analyses for GitHub installations where they are an admin of the account. This prevents one user seeing another user's findings.

### ✅ Verify Phase 6

- [ ] Log in with GitHub OAuth → dashboard shows your repos
- [ ] Click a repo → see list of analyzed PRs
- [ ] Click a PR → see findings with locations
- [ ] A second GitHub account cannot see the first account's repos

---

## Phase 7 — The Crew (AI Explainer)

### What you're doing and why

The Guard finds problems. The Crew explains them. This phase adds the AI layer that takes each finding and writes a plain-English explanation — what it is, why it matters, and how to fix it, with a code example.

The Crew is advisory only. It does not change findings, does not block PRs, and does not assert that code was "AI-generated."

Primary model: **Claude Haiku 4.5** (fast, cheap, good at explanation). Fallback: **Gemini 2.5 Flash-Lite**.

### Steps (developer executes)

1. Build `crew/` module: prompt templates, LLM router, response caching
2. Context strategy: send only the diff (not the full repo) + the Finding to the LLM — minimizes cost and avoids sending unnecessary code
3. Enable prompt caching (Anthropic's feature that reuses cached prompt prefixes across calls)
4. Log cost per PR to the database
5. Add Crew output to the dashboard's analysis detail view
6. Rule: the Crew's output is clearly labeled "AI explanation — verify before acting" in the UI

```
# .env additions for Phase 7
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=your_gemini_key_here
```

### ✅ Verify Phase 7

- [ ] Flagged PR → plain-English explanation appears in dashboard for each finding
- [ ] Explanation is accurate (matches the actual finding)
- [ ] LLM cost logged per PR in database
- [ ] Cost per PR is a fraction of a cent (< $0.005)
- [ ] Guard finding conclusion is unchanged by the Crew (same confidence, same block_eligible status)
- [ ] If LLM is unavailable → finding still appears, just without Crew explanation (graceful degradation)

---

## Phase 8 — Configuration and Multi-Tenant

### What you're doing and why

Different repositories have different needs. A startup might want all checks on; an open-source project might want license checks off. This phase adds per-repo and per-org configuration.

### Steps (developer executes)

1. Build support for `.slopguard.yml` in the root of each repository:

```yaml
# .slopguard.yml example
block_mode: advisory          # or "block" (Phase 9, opt-in)
disabled_rules: []            # e.g., ["SQG007"]
allowlist:
  paths: ["test/", "fixtures/"]
  packages: ["@myorg/*"]
model: haiku                  # or "gemini-flash-lite"
privacy: standard             # controls how much diff context is sent to the LLM
```

2. Build org-level defaults (applies to all repos in the org unless overridden)
3. Add configuration editor to the dashboard
4. Every config change is written to `audit_log` (who changed what, when)

### ✅ Verify Phase 8

- [ ] Change a setting in the dashboard → takes effect on the next PR (not retroactive)
- [ ] Change is visible in the audit log
- [ ] Add `SQG003` to `disabled_rules` → placeholders no longer flagged on that repo
- [ ] Org-level default applies to repos without their own `.slopguard.yml`

---

## Phase 9 — Opt-In Blocking

### What you're doing and why

Until now, the app has been advisory only — findings appear but PRs are never blocked. This phase adds the ability to actually stop a PR from being merged when a verified-dangerous fact is found.

Blocking is a significant action. Getting it wrong (a false positive that blocks a legitimate PR) destroys trust. The gates are strict.

**Requirements before this phase ships:**
- Measured false-positive rate below 1% on real production PRs (not just fixtures)
- Only CERTAIN-confidence findings are block-eligible: SQG001 (confirmed fake package) and SQG002 (verified secret)
- SQG004 (CVEs) are HIGH confidence, not block-eligible

### Steps (developer executes)

1. Add `block_mode: block` option to `.slopguard.yml` and dashboard (opt-in only)
2. When `block_mode: block` AND finding is CERTAIN + block_eligible → set Check Run conclusion to `failure` (GitHub blocks merge)
3. Build the bypass flow in the dashboard: authorized user can approve a blocked PR; approval is logged in audit trail
4. Keep the kill switch: any analyzer can be disabled instantly without redeploy

### ✅ Verify Phase 9

- [ ] Repo with `block_mode: block` + PR with verified fake package → PR is blocked (merge button grayed out)
- [ ] Same PR on a repo with `block_mode: advisory` → not blocked (orange check, advisory only)
- [ ] Bypass flow: approve the blocked PR in dashboard → merge becomes available, bypass logged
- [ ] A HIGH-confidence finding (CVE, license) → never blocks even with `block_mode: block`

---

## Phase 10 — Harden and Ship to Production

### What you're doing and why

The product works. Now make it production-grade: secure containers, Cloudflare protection, zero-downtime deploys, full observability, and the app checking its own code with its own checks (dogfooding).

### Step 10.1 — Deploy API + Worker to Fly.io

```bash
# From the api/ directory
$ fly launch --name pr-quality-gate-api --region iad

# Set all secrets (never hard-code these)
$ fly secrets set \
  GITHUB_APP_ID=12345 \
  GITHUB_WEBHOOK_SECRET=your_secret \
  DATABASE_URL=postgres://... \
  REDIS_URL=rediss://... \
  ANTHROPIC_API_KEY=sk-ant-...

# Upload the private key
$ fly secrets set GITHUB_PRIVATE_KEY="$(cat github-app.pem)"

# Deploy
$ fly deploy
```

### Step 10.2 — Update GitHub App webhook URL

1. Go to your GitHub App settings
2. Update **Webhook URL** to: `https://pr-quality-gate-api.fly.dev/webhooks/github`

### Step 10.3 — Deploy Dashboard to Vercel

1. Push the `web/` directory to GitHub (if not already)
2. Go to vercel.com → Import Project → select the repo
3. Set environment variables in Vercel dashboard:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_API_URL=https://pr-quality-gate-api.fly.dev`
4. Vercel auto-deploys on every push to `main`

### Step 10.4 — Set up Cloudflare

1. Add your Fly.io webhook hostname to Cloudflare (proxy mode on)
2. Create a WAF rule: allow webhook path only from GitHub's published IP ranges
   - GitHub's hook IPs: check `api.github.com/meta` → `hooks` field
3. Enable rate limiting on the webhook path

### Step 10.5 — Verify the distroless container

The Dockerfile uses a multi-stage build with a distroless base image (minimal attack surface, no shell, no package manager in the final image) and runs as a non-root user.

```bash
# Verify image runs non-root
$ docker run --rm pr-quality-gate-api whoami
# Should print: nonroot (or a numeric UID, not root)
```

### Step 10.6 — Wire up CI to dogfood its own checks

The app's own GitHub Actions workflow runs the app's own checks on its own code:

```yaml
# .github/workflows/ci.yml (abbreviated)
- name: Run tests
  run: cd api && pytest tests/

- name: Secret scan (gitleaks)
  uses: gitleaks/gitleaks-action@v2

- name: SAST (Semgrep)
  uses: semgrep/semgrep-action@v1

- name: Vulnerability scan (Trivy)
  uses: aquasecurity/trivy-action@master

- name: Build image
  run: docker build -t pr-quality-gate-api api/

- name: Deploy to Fly.io
  run: fly deploy --now
```

### Step 10.7 — Set up alerts

Configure alerts in your observability tool (Sentry / Prometheus) for:
- Webhook ACK p95 exceeds 500 ms
- Worker queue depth exceeds threshold (worker falling behind)
- Analyzer failure rate exceeds 5%
- Any unhandled exception in production

### Step 10.8 — Rollback procedure

If a deploy breaks something:

```bash
# List recent releases
$ fly releases

# Roll back to the previous working release
$ fly deploy --image <previous-image-ref>
```

For the dashboard: Vercel dashboard → Deployments → click any previous deployment → Promote to Production (instant).

### ✅ Verify Phase 10 — Full Acceptance Test

Run through this sequence from start to finish:

1. Install the App on a fresh test repository (new install, not the one used during development)
2. Open a PR that adds:
   - A fake package: `import quantumllm_helper` (in `requirements.txt`)
   - A hardcoded API key: `STRIPE_KEY = "sk_live_XXXXXXXX"` (in a `.py` file)
   - A `# TODO: implement this` comment on a function with an empty body
   - A dependency with a known CVE (check OSV.dev for a real example)
3. Confirm within 30 seconds:
   - [ ] Server acknowledged with 202 in < 500 ms (check logs)
   - [ ] Worker dequeued and ran all checks
   - [ ] Orange `action_required` Check Run appears on the PR with all four findings at exact lines
   - [ ] AI Crew plain-English explanations appear in the dashboard
   - [ ] Rows in `analyses`, `findings`, and `audit_log` tables in Supabase
   - [ ] Entire trace visible in logs by delivery ID
4. Open a clean PR (only a README change):
   - [ ] Green check, zero findings
5. Turn on `block_mode: block` in dashboard for the test repo. Open a PR with the fake package:
   - [ ] PR is blocked (merge button grayed out)
   - [ ] A PR with only a CVE (HIGH confidence) is not blocked
6. Log into the dashboard:
   - [ ] Both analyses visible with drill-down
7. Push a change to the app's own repo:
   - [ ] CI runs, scans complete green, deploys with zero downtime

**All 7 points passing = live in production.**

---

## Quick Reference: Useful Commands

```bash
# Start everything locally (Postgres + Redis + API + Worker)
$ make dev

# Run tests
$ cd api && pytest tests/ -v

# Run database migrations
$ cd api && alembic upgrade head

# Check Fly.io app status
$ fly status

# View live logs from Fly.io
$ fly logs

# List Fly.io releases (for rollback)
$ fly releases

# Set a Fly.io secret
$ fly secrets set KEY=value

# Deploy to Fly.io
$ fly deploy

# Disable an analyzer without redeploying
$ fly secrets set DISABLED_ANALYZERS=SQG007
```

---

## Common Problems and Fixes

| Problem | Likely cause | Fix |
|---------|-------------|-----|
| Webhook returns 401 | Wrong webhook secret | Re-check `GITHUB_WEBHOOK_SECRET` in `.env` and Fly secrets |
| Worker never picks up jobs | Redis URL wrong or Upstash not reachable | Check `REDIS_URL`; test with `fly ssh console` |
| Check Run stuck "in progress" | Worker crashed mid-job | Reconciliation task closes it after 5 min; check `fly logs` for crash reason |
| False positive on a monorepo package | Package not in whitelist | Add to workspace config or repo allowlist in `.slopguard.yml` |
| Dashboard shows no repos | OAuth scope issue or installation not admin-owned | Re-install the App; check Supabase Auth GitHub scopes |
| Fly deploy fails | Image build error or secret missing | Run `fly logs` after deploy; check all secrets set with `fly secrets list` |

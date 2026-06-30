# DEPLOYMENT — Go-Live Runbook

Production setup: Fly.io (API + worker) + Vercel (dashboard) + Supabase (Postgres) + Upstash (Redis) + Cloudflare (edge).

---

## Pre-Deployment Checklist

- [ ] All Phase X work complete and tested locally.
- [ ] GitHub App registered with correct permissions + webhook secret.
- [ ] All production accounts created: Fly, Vercel, Supabase, Upstash, Cloudflare.
- [ ] Secrets in `.env.local` (dev only, never committed).
- [ ] CI tests green.
- [ ] Staging environment validated (Fly staging slot or separate Vercel preview).

---

## 0. Pre-Launch Critical Actions (do these first)

These are the must-not-skip steps before the app is reachable publicly. They reflect
the **current code** (the runbook below drifted from it in places — these override).

- [ ] **Rotate the LLM API key.** The NVIDIA NIM key used in local dev (`LLM_API_KEY`)
      was committed-adjacent during development and must be treated as burned. Generate a
      fresh key in the provider console and set it only as a production secret. Never reuse
      the dev key for a public deployment.
- [ ] **Generate a strong `GITHUB_WEBHOOK_SECRET`** (`openssl rand -hex 32`) and set the
      identical value in the GitHub App settings and the API secret store.
- [ ] **Point `DATABASE_URL` at Postgres.** Dev defaults to SQLite. Production must use the
      Supabase/Postgres connection string (plain `postgresql://…` is auto-mapped to asyncpg).
- [ ] **Schema creation:** tables are created automatically on API startup via `init_db()`
      (SQLAlchemy `create_all`). There are **no Alembic migrations yet** (backlog), so ignore
      `alembic upgrade head` references below — just boot the API once against the empty DB.
- [ ] **Set the dashboard Supabase keys** (`NEXT_PUBLIC_SUPABASE_URL`,
      `NEXT_PUBLIC_SUPABASE_ANON_KEY`) to enable real login. Until set, the dashboard runs in
      demo mode (the "Skip for now" button), which is intended for previews, not public launch.
- [ ] **Enable Email OTP (not Magic Link) in the Supabase project.** The sign-in flow sends a
      6-digit code (`signInWithOtp`) and verifies it with `verifyOtp({ type: "email" })`. In the
      Supabase dashboard → Authentication → Email, the "Email OTP" template/flow must be enabled;
      a Magic-Link-only project makes code verification fail with "Token has expired or is invalid".
- [ ] **Confirm the product honesty gate:** a registry/LLM outage must downgrade to advisory,
      never emit a false block. The Crew is advisory-only. (See `SECURITY.md` / `CLAUDE.md`.)

One Supabase project supplies **both** the `DATABASE_URL` (Postgres) and the dashboard
auth keys — provisioning it unblocks the DB migration and the login at once.

---

## 1. Supabase Setup

### Create Project

1. Log in to [supabase.com](https://supabase.com).
2. **New Project** → select region (e.g., `us-east-1`).
3. Save **Project URL** and **API Key** (for env vars).

### Initialize Schema

```bash
export DATABASE_URL="postgresql://[user]:[password]@[host]:[port]/[db]"
cd api
alembic upgrade head
```

Verify tables created:
```sql
\dt  -- in psql
```

---

## 2. Upstash Redis Setup

### Create Instance

1. Log in to [console.upstash.com](https://console.upstash.com).
2. **Create Database** → Redis.
3. Copy **UPSTASH_REDIS_URL** (includes auth).

---

## 3. Fly.io Setup (API + Worker)

### Install CLI

```bash
brew install flyctl  # or npm install -g flyctl
fly auth login
```

### Create App

```bash
cd api
fly apps create slopguard-api
```

### Configure `fly.toml`

```toml
app = "slopguard-api"
primary_region = "sjc"  # San Jose or your region

[build]
  image = "slopguard-api:latest"

[env]
  ENVIRONMENT = "production"
  LOG_LEVEL = "info"
  DISABLED_ANALYZERS = ""

[[services]]
  protocol = "tcp"
  internal_port = 8000
  processes = ["api"]

  [[services.ports]]
    port = 80
    handlers = ["http"]
  [[services.ports]]
    port = 443
    handlers = ["tls", "http"]

[[vm]]
  memory = "512mb"
  cpus = 1
```

### Set Secrets

```bash
fly secrets set \
  DATABASE_URL="postgresql://..." \
  GITHUB_APP_PRIVATE_KEY="$(cat /path/to/key.pem)" \
  GITHUB_APP_ID="12345" \
  GITHUB_WEBHOOK_SECRET="your-secret" \
  REDIS_URL="redis://..." \
  LLM_BASE_URL="https://integrate.api.nvidia.com/v1" \
  LLM_MODEL="minimaxai/minimax-m3" \
  LLM_API_KEY="<freshly-rotated-key>" \
  SENTRY_DSN="https://..."
```

> The Crew explainer is provider-agnostic (OpenAI-compatible). To use Claude instead,
> set `LLM_BASE_URL=https://api.anthropic.com/v1`, `LLM_MODEL=claude-haiku-4-5-20251001`,
> and `LLM_API_KEY` to your Anthropic key. Leaving `LLM_API_KEY` empty disables the
> explainer gracefully — findings still work.

### Deploy

```bash
fly deploy --strategy immediate
```

Monitor:
```bash
fly logs
fly status
```

### Worker Service (Same App, Separate Process)

Add to `fly.toml`:

```toml
[[processes]]
  type = "worker"
  cmd = "python -m api.worker"
  memory = "512mb"
  cpus = 1
```

Deploy worker:
```bash
fly deploy
```

---

## 4. Vercel Setup (Dashboard)

### Install CLI

```bash
npm install -g vercel
vercel login
```

### Deploy

```bash
cd web
vercel --prod
```

### Configure Environment

In Vercel dashboard:
- **Settings** → **Environment Variables**
- Set `NEXT_PUBLIC_API_URL="https://api.slopguard.dev"`
- Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` (anon key is public, safe).
  Both must be present for login to activate; absent → dashboard stays in demo/skip mode.

### Custom Domain

1. **Settings** → **Domains**.
2. Add `dashboard.slopguard.dev`.
3. Point DNS to Vercel's nameservers.
4. TLS auto-provisioned (Let's Encrypt).

---

## 5. Cloudflare Setup (Edge Protection)

### Create Zone

1. Log in to [cloudflare.com](https://cloudflare.com).
2. **Add Site** → `api.slopguard.dev`.
3. Use Cloudflare's nameservers.

### WAF Rules

1. **Security** → **WAF Rules**.
2. Add rule: **Managed Ruleset** (default).
3. **Rate Limiting** → 100 requests/min per IP.

### Origin Configuration

1. **DNS Records**:
   - Type: `CNAME`
   - Name: `api`
   - Target: `slopguard-api.fly.dev`
   - Proxy status: **Proxied** (orange cloud)

2. **SSL/TLS**:
   - **Encryption Mode**: `Full (strict)`
   - Let's Encrypt (auto from Fly + Cloudflare cert validation)

### IP Whitelist (GitHub Webhooks)

[GitHub's IP ranges](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-githubs-ip-addresses):

```bash
# Example (get current list from GitHub)
curl https://api.github.com/meta | jq '.hooks'
```

Cloudflare Firewall Rule:
```
(ip.src in {140.82.112.0/20 143.55.64.0/20} and http.request.uri.path contains "webhooks")
```

---

## 6. GitHub App Configuration

### Webhook URL

1. GitHub App settings → **Webhook**.
2. **Payload URL**: `https://api.slopguard.dev/webhooks/github`
3. **Content type**: `application/json`
4. **Secret**: stored in Fly secrets.
5. **Events to subscribe to**:
   - `pull_request` (opened, synchronize, reopened)
   - `installation` (added, removed)
   - `check_run` (optional, for status updates)

### Permissions

- **Pull Requests**: Read & write
- **Checks**: Read & write
- **Contents**: Read-only
- **Metadata**: Read-only

---

## 7. Domain & TLS

### API Domain

Set DNS (`api.slopguard.dev`):
```
CNAME api.slopguard.dev -> slopguard-api.fly.dev
```

Cloudflare proxies it. TLS via Let's Encrypt (automatic).

### Dashboard Domain

Set DNS (`dashboard.slopguard.dev`):
```
CNAME dashboard.slopguard.dev -> vercel.com
```

Vercel provisions TLS automatically.

---

## 8. Rolling Deploy

### Without Downtime

```bash
# Fly: rolling restart
fly deploy --strategy rolling

# Vercel: automatic (git push)
git push origin main
```

### Health Checks

Fly auto-configures from `GET /healthz` (200 = healthy).

---

## 9. Rollback

### API Rollback

```bash
# List releases
fly releases

# Rollback to previous
fly releases rollback
```

### Dashboard Rollback

In Vercel:
1. **Deployments** → select previous.
2. **Promote to Production**.

---

## 10. Secrets Management

### Never in Code/Image

- GitHub App private key.
- Database password.
- API keys (Anthropic, Upstash).
- Webhook secret.

### Storage

- **Fly secrets:** `fly secrets list` / `set` / `unset`.
- **Vercel env vars:** Dashboard → Settings → Environment Variables.
- **Supabase:** built-in secret storage (future).

### Rotation

- Change in platform (Fly, Vercel).
- Deploy to use new secret.
- Old secret still works (config for grace period if needed).

---

## 11. Observability

### Logging

```bash
fly logs
# or
fly logs --region all
```

### Tracing

Every PR tagged with correlation ID (via structlog + OTel). Query in Sentry.

### Metrics

Basic Prometheus counters (future):
```bash
# Counter: /metrics endpoint
GET /metrics
```

### Alerts

Sentry:
1. **Alerts** → **Create Alert Rule**.
2. Condition: `Error event` OR `Performance` (p95 > 5s).
3. Action: Email or Slack.

---

## 12. Verification

### Test End-to-End

1. Open a PR on a test repo with the app installed.
2. Expect webhook → 202 within 1s.
3. Worker processes in background.
4. Check Run appears on PR within 30s.
5. Dashboard shows the analysis.

### Test Blocking (Phase 9+)

1. Set `block_mode: true` in settings.
2. Open PR with a verified secret.
3. Expect check to be `failure` (red), merge blocked.
4. Dashboard allows bypass (logged in audit trail).

### Test Rollback

1. Deploy a broken version.
2. `fly releases rollback` → restored.
3. Health check passes.

---

## 13. Performance Budgets (Hard)

Monitored in CI; fail deploy if exceeded:

| Metric | Budget | Tool |
|---|---|---|
| Webhook ACK | <500ms | Fly logs |
| Dependency check | <2s | OTel span |
| Secret scan | <4s | OTel span |
| Full analysis | <30s | OTel span |
| Dashboard load | <1s | Vercel Analytics |

---

## 14. Cost Tracking

Monthly estimate (free tier):

| Service | Tier | Cost |
|---|---|---|
| Fly (API + worker) | Shared CPU | $0–5 (free tier: 3 shared CPUs, 30GB bandwidth) |
| Vercel | Pro ($20/mo) | $20 |
| Supabase | Free tier | $0 (up to 500MB DB, 2GB outbound/mo) |
| Upstash | Free tier | $0 (10K commands/day) |
| Cloudflare | Free | $0 |
| LLM API (Crew) | Usage-based | ~$0.003–0.01 per finding explained (advisory, on-demand only) |
| **Total** | | ~$20–30/mo |

---

## Checklist: Ready for Live

- [ ] All services running and healthy.
- [ ] Secrets set (never in code/image).
- [ ] GitHub App webhook receives PRs (check logs).
- [ ] Findings appear on PR + dashboard.
- [ ] AI Crew explains finding (Phase 7+).
- [ ] Blocking works correctly (Phase 9+).
- [ ] Rollback tested.
- [ ] Monitoring/alerts configured.
- [ ] Domain TLS valid.
- [ ] CI dogfood passes (the app checks itself).

**Status: READY FOR PRODUCTION.**

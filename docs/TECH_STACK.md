# TECH_STACK — Technologies, Versions, and Why

## Backend API

| Technology | Version | Why |
|---|---|---|
| **Python** | 3.12 | Modern, stable, best-in-class for data/analysis tools; async support. |
| **FastAPI** | 0.109+ (latest 0.x stable) | Fast, async-native ASGI framework; built-in OpenAPI docs; minimal boilerplate. |
| **httpx** | 0.25+ | HTTP client with async support, connection pooling, timeouts. |
| **SQLAlchemy** | 2.0+ | ORM layer; works with PostgreSQL locally and in production; declarative models; async support via `sqlalchemy[asyncio]`. |
| **Alembic** | 1.13+ | Database migrations; version control for schema changes; safe rollback. |
| **Pydantic** | 2.0+ | Data validation & serialization; comes with FastAPI; automatic OpenAPI schemas. |

---

## Background Worker

| Technology | Version | Why |
|---|---|---|
| **arq** | 0.25+ | Async Redis queue; lighter and simpler than Celery for single-queue systems; integrates seamlessly with FastAPI/asyncio. Can swap to Celery later if multi-worker scaling demands it. |
| **aioredis** | 2.0+ (via `aioredis` in `arq` dependencies) | Async Redis client; underpins `arq`. |

---

## Data Storage

| Technology | Version | Why |
|---|---|---|
| **PostgreSQL** | 14+ (Supabase managed) | Mature, battle-tested; JSON support; full-text search; excellent for relational data + audit logs. |
| **Supabase** | — | Managed Postgres + Auth + Storage; free tier sufficient for MVP; simple scaling. |
| **Redis** | 7.0+ (Upstash managed) | In-memory; job queue + dedupe cache + rate-limit state; free tier includes 10K commands/day. |
| **Upstash** | — | Serverless Redis; zero-maintenance; scales with load. |
| **SQLite** | 3.40+ (local dev only) | Drop-in replacement for Postgres in dev; same ORM/migrations, no external DB needed. |

---

## Frontend Dashboard

| Technology | Version | Why |
|---|---|---|
| **Next.js** | 15 (App Router) | Modern, fast, great DX; App Router for server/client separation; built-in image optimization. |
| **React** | 19 (bundled with Next.js 15) | Latest stable; hooks-based; component reusability. |
| **TypeScript** | 5.4+ | Type safety; catches bugs at build time; reusability. |
| **Tailwind CSS** | 4 | Utility-first CSS; rapid UI development; auto-purging. |
| **shadcn/ui** | Latest | High-quality React component library (button, card, dialog, etc.); styled with Tailwind; copy-paste customizable. |
| **Vercel** | — | Managed Next.js hosting; git push auto-deploys; built-in preview deployments. |

---

## Dashboard Authentication

| Technology | Version | Why |
|---|---|---|
| **Supabase Auth** | (bundled with Supabase) | Simple, OAuth-enabled; GitHub OAuth integration; free tier. |
| **GitHub OAuth** | — | Standard OAuth 2.0; users click "Sign in with GitHub"; no separate password. |

---

## The Guard — Checkers (Deterministic Analyzers)

| Check | Tool(s) | Version | Why |
|---|---|---|---|
| **Fake/hallucinated package** | Custom `registry_client` + `requests` / `httpx` | PyPI JSON API, npm registry, crates.io, Go proxy | Direct registry hits; no extra tool; proven accurate. |
| **Leaked secrets** | **gitleaks** + **trufflehog** (optional verification) | gitleaks 8.18+, trufflehog 3.63+ | gitleaks = fast, extensive patterns; TruffleHog = entropy + optional live verify. Ship v1 with offline patterns only. |
| **Security vulnerabilities (SAST)** | **Semgrep** | 1.45+ | OSS, rule-based, P0/P1 only (high signal). Via `semgrep-cli`. |
| **Known-vulnerable dependencies** | **Trivy** + **OSV-Scanner** | trivy 0.48+, osv-scanner 1.6+ | Trivy = comprehensive, fast; OSV = Google-backed vulnerability database. Run both, aggregate results. |
| **Risky/incompatible licenses** | **Trivy** + **Syft** | trivy 0.48+, syft 0.73+ | Trivy includes license scanning; Syft = detailed SBOM. |
| **Placeholder code** | **tree-sitter** + regex | tree-sitter-python 0.20+, tree-sitter-javascript 0.20+ | AST parsing for context-aware detection; regex as fallback. |
| **AI reasoning scratchpads** | Regex (text/markdown only) | — | Simple pattern match for `<thinking>`, `<plan>`, etc. Only flag in `.md`, `.txt` files (low FP). |

---

## The Crew — AI Explainer (Advisory Only, Phase 7+)

| Technology | Version | Why |
|---|---|---|
| **Claude Haiku 4.5** | Latest (Claude API) | Cheap (~$0.80 / 1M input tokens), fast, strong at plain-English explanations. |
| **Gemini 2.5 Flash-Lite** | Latest (Google AI API, fallback) | Fallback if Claude API is rate-limited or overloaded. Similar cost/speed. |
| **Prompt caching** | (via Claude API) | Reduce cost of repeated diffs; cache finding context. |
| **anthropic** Python SDK | 0.24+ | Official API client; streaming, structured output. |

---

## Hosting & Deployment

| Technology | Version | Why |
|---|---|---|
| **Fly.io** | — | Deploys Docker; manages rolling deploys, auto-restart, multi-region (scaling later); secrets via `fly secrets`. |
| **Vercel** | — | Next.js native; git push auto-deploys; instant rollback. |
| **Cloudflare** | — | Global CDN + WAF in front of Fly webhook endpoint; free tier includes DDoS protection, rate limiting. |
| **Let's Encrypt** | — | Free TLS certificates; auto-renewal; Fly/Vercel handle this. |

---

## Containers

| Technology | Version | Why |
|---|---|---|
| **Docker** | 24+ | Multi-stage builds; slim images. |
| **Distroless** | Python 3.12 / Node 20 | Minimal base image (no shell, no `apt`); ~100 MB instead of 1 GB. Non-root user by default. |

---

## Observability & Debugging

| Technology | Version | Why |
|---|---|---|
| **structlog** | 24.1+ | JSON structured logging; human-readable in dev, machine-parseable in prod. |
| **OpenTelemetry** | 1.21+ | Distributed tracing; correlation IDs; instrument every PR end-to-end. |
| **Sentry** | (SaaS) | Error tracking + alerting; replays + breadcrumbs. Free tier ample for MVP. |
| **Prometheus** | (optional, local dev) | Metrics; basic counters for analyzer performance. Later if needed. |

---

## CI/CD

| Technology | Version | Why |
|---|---|---|
| **GitHub Actions** | (native to GitHub) | The app checks itself on its own repo; no external CI needed. |

---

## Development & Local

| Technology | Version | Why |
|---|---|---|
| **uv** or **pip** | uv 0.1+ (recommended) | Fast Python package manager; faster lock resolution. |
| **poetry** | 1.7+ (alternative) | Alternative to `uv` for dependency management; `poetry.lock`. |
| **make** | 4.2+ | Simple local commands (`make dev`, `make test`). |
| **docker-compose** | 2.20+ | Local stack: postgres + redis + api + worker in one command. |

---

## Summary

**Principles:**
- **Simplicity over flexibility:** Proven tools, not the latest shiny thing.
- **Async-native:** FastAPI + arq fit the webhook model perfectly.
- **Zero cost at small scale:** Free tiers (Upstash, Supabase, Vercel, Cloudflare, GitHub Actions).
- **Single language where possible:** Python backend + JavaScript frontend (standard), not a third tech.
- **Incremental scaling:** SQLite → Postgres, single worker → multi-worker later.

**Deprecated/Not in Use:**
- Celery (use `arq` instead).
- GraphQL (REST is simpler for this scope).
- Kubernetes (Fly.io handles orchestration).
- TypeORM/Sequelize (SQLAlchemy is better for Python).

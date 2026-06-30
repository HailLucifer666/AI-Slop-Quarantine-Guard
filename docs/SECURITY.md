# SECURITY — How We Secure the App Itself

The Guard is a security tool; we dogfood it and hold ourselves to the same standards.

---

## Secret Handling

### Local Development

Secrets in `.env.local` (gitignored):

```env
DATABASE_URL=postgresql://...
GITHUB_APP_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\n...
GITHUB_APP_ID=12345
GITHUB_WEBHOOK_SECRET=secret123
UPSTASH_REDIS_URL=redis://...
UPSTASH_API_TOKEN=...
ANTHROPIC_API_KEY=sk-...
```

`.env.local` is in `.gitignore`. Never commit.

### Production

Secrets in platform vaults:

- **Fly.io:** `fly secrets set KEY=VALUE` (encrypted at rest, injected at runtime).
- **Vercel:** Dashboard → Settings → Environment Variables (never logged, never in build output).
- **Never in:** source code, Docker images, git history, logs.

### Secret Rotation

1. Generate new secret (GitHub App re-create key, change webhook secret, rotate API keys).
2. Set in platform: `fly secrets set NEW_KEY=value`.
3. Verify old key still works during grace period (if stateless).
4. Delete old secret from platform.
5. Audit log records the change.

---

## Webhook Hardening

### HMAC-SHA256 Verification

Every webhook signed by GitHub using the webhook secret.

```python
# api/app/security.py
import hmac
import hashlib

def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    expected = "sha256=" + hmac.new(
        secret.encode(),
        body,  # Raw body, not parsed JSON
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

**Key:** Use raw request body, not parsed JSON (parsing can reorder keys, breaking signature).

### Replay Protection

Deduplicate via `X-GitHub-Delivery` header (UUID):

```python
# Check database: has this delivery_id been seen?
existing = db.webhook_deliveries.filter_by(
    github_delivery_id=delivery_id
).first()

if existing:
    # Return 409 Conflict (idempotent, no duplicate processing)
    return 409

# Insert & process
db.webhook_deliveries.create(github_delivery_id=delivery_id, ...)
```

### Payload Size Cap

```python
if len(body) > 5_000_000:  # 5 MB
    return 413  # Payload Too Large
```

Prevents DoS via giant payloads.

---

## GitHub App Permissions (Principle of Least Privilege)

**Permissions requested (in `app.yml` or manifest):**

| Resource | Access | Reason |
|---|---|---|
| **Pull Requests** | Read & Write | Read PR diff; post reviews/comments; create check runs. |
| **Checks** | Read & Write | Create + update check run with findings. |
| **Contents** | Read-only | Fetch PR diff and files for analysis. |
| **Metadata** | Read-only | Read public repo info (required by GitHub). |

**NOT requested:**
- Admin (no need to manage repo settings).
- Workflows (no CI/CD integration).
- Issues (not used).
- Discussions (not used).

**Events subscribed to:**
- `pull_request` (opened, synchronize, reopened).
- `installation` (added, removed — for accounting).
- `check_run` (optional, for re-run support).

**NOT:**
- `push` (we only care about PRs, not every commit).

---

## CI Dogfood: The App Scans Itself

`.github/workflows/ci.yml`:

```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run the Guard's own checks
        run: |
          docker run --rm -v $(pwd):/repo slopguard-api:latest \
            python -m api.checks.runner --repo=/repo
      
      - name: Semgrep scan
        run: semgrep --config=p/security-audit .
      
      - name: Trivy scan
        run: trivy fs .
      
      - name: gitleaks scan
        run: gitleaks detect --verbose

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build distroless image
        run: |
          docker build \
            --target distroless \
            -t slopguard-api:latest \
            -f api/Dockerfile .

  deploy:
    needs: build
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to Fly.io
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
        run: fly deploy
```

**Principle:** No code lands in production without passing all the Guard's own checks.

---

## Container Security

### Dockerfile (Multi-Stage)

```dockerfile
# Stage 1: Build
FROM python:3.12-slim as builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN python -m pip install --upgrade pip uv && \
    uv pip install --target /app/venv -r requirements.txt

# Stage 2: Distroless runtime
FROM gcr.io/distroless/python3.12:nonroot
COPY --from=builder /app/venv /app/venv
COPY api /app/api
WORKDIR /app
ENV PATH="/app/venv/bin:$PATH"
EXPOSE 8000
CMD ["python", "-m", "api.main"]
```

**Benefits:**
- **Minimal attack surface:** no shell, no `apt`, no unnecessary tools.
- **Non-root user:** distroless default.
- **Small image:** ~200 MB vs. 1 GB for standard Python image.

### Image Scanning (CI)

```bash
trivy image slopguard-api:latest
```

Fails deploy if critical CVEs found in dependencies.

---

## Code Quality Gates

### Type Safety

```bash
mypy api/
```

Catch `None` dereference, type mismatches at build time.

### Linting

```bash
ruff check api/
black --check api/
```

Prevent unsafe patterns (e.g., broad except clauses).

### Dependency Audit

```bash
pip-audit -r requirements.txt
```

Fail if production dependencies have known CVEs.

### SAST on Our Own Code

```bash
semgrep --config=p/security-audit api/
```

Catch injection, unsafe deserialization, hardcoded secrets.

---

## Database Security

### Connection

- **TLS:** Supabase enforces TLS for all connections (encrypted in transit).
- **User:** Limited database user with write access only to specific tables.
- **Environment var:** `DATABASE_URL` injected at runtime (never in image).

### Queries

- **Parameterized:** All queries use SQLAlchemy with parameter binding (no string concatenation).
  
  ```python
  # Safe
  stmt = select(findings).where(findings.c.analysis_id == :analysis_id)
  db.execute(stmt, {"analysis_id": 123})
  
  # NOT SAFE (don't do this)
  db.execute(f"SELECT * FROM findings WHERE analysis_id = {analysis_id}")
  ```

### Row-Level Security (Future, Phase 8+)

Supabase RLS policies enforce that users can only see findings for installations they administer.

---

## Authentication & Authorization

### Dashboard Auth Flow

1. User clicks "Sign in with GitHub" (OAuth).
2. Redirected to GitHub → authorize.
3. Redirected back with code.
4. Dashboard exchanges code for access token.
5. Supabase Auth mints JWT.
6. **Authorization check:** user is admin of the installation (via GitHub API).

```python
# API endpoint
@router.get("/api/analyses")
async def list_analyses(authorization: str = Header(...)):
    user = verify_jwt(authorization)
    installation = get_installation(request.installation_id)
    
    # Check: is this user an admin of the installation?
    is_admin = github_client.is_user_admin(
        user.github_login,
        installation.github_account_name,
        installation.github_account_type
    )
    
    if not is_admin:
        raise HTTPException(403, "Unauthorized")
    
    return db.analyses.filter_by(installation_id=installation.id).all()
```

---

## Observability (Non-PII)

### Logging

No secrets logged:
- ✓ Analysis count, finding types, timing
- ✗ Secret snippets, API keys, user data

```python
# Safe
logger.info("analysis_completed", analysis_id=123, finding_count=3)

# NOT SAFE
logger.info(f"Found secret: {secret_snippet}")  # Don't do this
```

### Tracing

Correlation IDs tie requests together; never include sensitive data in spans.

---

## Rate Limiting & DoS Protection

### API Rate Limits

- Webhook: no limit (GitHub controls upstream; IP whitelisted via Cloudflare).
- Dashboard: 100 req/min per user (Cloudflare + app-level check).

### Payload Size

- Webhook: max 5 MB (prevent memory exhaustion).
- Diff parsing: max 50 MB lockfile/manifest (degrade gracefully).

### Job Queue Limits

- Max jobs in queue: 10,000 (above this, new jobs rejected w/ 503).
- Worker timeout: 5 min per PR (kill + log if exceeded).

---

## Incident Response

### Error Handling

- All errors logged with correlation ID.
- No sensitive data in error messages (generic `500 Internal Server Error` to user).
- Detailed logs in Sentry (private, operator-only).

### Kill Switch

Per analyzer: `DISABLED_ANALYZERS=SQG001,SQG002` disables checks without redeploy.

### Monitoring

Sentry alerts on:
- Error rate >1% per minute.
- P95 latency >5s.
- Queue depth >5000 jobs.

### Rollback

`fly releases rollback` instantly restores previous version.

---

## Compliance & Audit

### Audit Log

Every significant action logged (immutable):

```sql
INSERT INTO audit_log (action, actor, resource_type, resource_id, changes)
VALUES ('setting_changed', 'user@github', 'repo_setting', 'owner/repo', '{"block_mode": {"old": false, "new": true}}');
```

Retention: 1 year.

### Data Retention

- Findings: 90 days (configurable, user can set to 180 days).
- Webhook logs: 30 days (debug only).
- Audit log: 1 year (compliance).

### No Unauthorized Access

- Dashboard: GitHub OAuth + admin check.
- API: JWT + role-based access control (future).
- Webhook: HMAC-SHA256 + IP whitelist (Cloudflare).

---

## Third-Party Dependencies

### Regular Audits

```bash
# Weekly in CI
pip-audit -r requirements.txt
npm audit
```

Alerts if high/critical CVEs found.

### Frozen Lockfiles

- `uv.lock` / `poetry.lock` pinned (reproducible builds).
- No auto-upgrades; manual review + test before upgrade.

---

## Summary

The Guard holds itself to the same standard it enforces on user code:
- ✓ No secrets in code/images.
- ✓ Webhook HMAC verification + replay protection.
- ✓ Least-privilege GitHub App permissions.
- ✓ Distroless non-root containers.
- ✓ Parameterized queries, no string concatenation.
- ✓ Type safety (mypy), linting, SAST scans.
- ✓ Audit logging, minimal error verbosity.
- ✓ Rate limiting, DoS guards.
- ✓ Transparency: what we log, what we don't, why.

**Trust through verification, not claims.**

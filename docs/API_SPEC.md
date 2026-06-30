# API_SPEC — Endpoints & Contract

Base URL (production): `https://api.slopguard.dev` (custom domain, Phase 10).

---

## POST /webhooks/github

Receives webhook from GitHub when a PR opens, updates, or reopens.

### Request

**Headers:**
```
X-GitHub-Event: pull_request
X-GitHub-Delivery: {uuid}
X-Hub-Signature-256: sha256={hmac_hex}
Content-Type: application/json
```

**Body:** GitHub's standard webhook payload (PR event).

### Response

```json
{
  "status": 202,
  "message": "Queued for analysis"
}
```

**Status codes:**
- `202 Accepted` – webhook received, queued, dedup check passed.
- `400 Bad Request` – invalid JSON.
- `401 Unauthorized` – signature mismatch.
- `409 Conflict` – duplicate delivery (already processed).
- `413 Payload Too Large` – >5MB.
- `500 Internal Server Error` – DB/queue failure (retry expected).

### Processing

1. Verify HMAC-SHA256 signature on raw body (constant-time comparison).
2. Check `X-GitHub-Delivery` for dedup (DB lookup).
3. Parse JSON payload.
4. Enqueue job: `{installation_id, repo, pr_number, head_sha, ...}`.
5. Return 202.
6. Worker picks up job asynchronously.

---

## GET /healthz

Liveness & readiness probe.

### Response

```json
{
  "status": "ok",
  "timestamp": "2026-06-28T12:34:56Z",
  "database": "ok",
  "redis": "ok",
  "version": "1.0.0"
}
```

**Status codes:**
- `200 OK` – all systems green.
- `503 Service Unavailable` – database or Redis down.

---

## Dashboard API (Internal)

Used by the Next.js dashboard. Protected by Supabase Auth token.

### GET /api/analyses

List analyses for an installation.

**Query params:**
```
?installation_id={id}&limit=20&offset=0&sort=created_at&order=desc
```

**Response:**
```json
{
  "data": [
    {
      "id": 123,
      "repo_full_name": "owner/repo",
      "pr_number": 42,
      "pr_title": "Add user auth",
      "status": "completed",
      "trust_status": "completed",
      "finding_count": 3,
      "critical_count": 1,
      "created_at": "2026-06-28T12:00:00Z",
      "duration_ms": 2345
    }
  ],
  "total": 150,
  "limit": 20,
  "offset": 0
}
```

---

### GET /api/analyses/{analysis_id}

Detailed analysis result (findings, metadata).

**Response:**
```json
{
  "id": 123,
  "repo_full_name": "owner/repo",
  "pr_number": 42,
  "head_sha": "abc123...",
  "status": "completed",
  "trust_status": "completed",
  "findings": [
    {
      "id": 1001,
      "rule_id": "SQG001",
      "confidence": "CERTAIN",
      "file_path": "requirements.txt",
      "line_start": 15,
      "message": "Package 'fake_pkg' does not exist in PyPI",
      "evidence": {
        "snippet": "fake_pkg==1.0.0",
        "context_before": [...],
        "context_after": [...]
      },
      "fix_suggestion": "Use a real package name"
    },
    {
      "id": 1002,
      "rule_id": "SQG002",
      "confidence": "HIGH",
      "file_path": "config.py",
      "line_start": 8,
      "message": "Potential API key (pattern match)",
      "evidence": {...}
    }
  ],
  "check_run_url": "https://github.com/owner/repo/runs/12345",
  "created_at": "2026-06-28T12:00:00Z",
  "completed_at": "2026-06-28T12:02:23Z"
}
```

---

### GET /api/installations

List GitHub App installations (OAuth user must be admin).

**Response:**
```json
{
  "data": [
    {
      "id": 1,
      "github_installation_id": 54321,
      "github_account_name": "acme-corp",
      "github_account_type": "Organization",
      "repos_count": 12,
      "created_at": "2026-06-01T00:00:00Z"
    }
  ]
}
```

---

### GET /api/installations/{installation_id}/settings

Get settings for a repo.

**Response:**
```json
{
  "installation_id": 1,
  "repo_full_name": "owner/repo",
  "block_mode": false,
  "blocked_rules": "SQG001,SQG002",
  "ai_enabled": false,
  "ai_model": "claude-haiku-4-5",
  "path_allowlist": "test/\ndocs/",
  "rule_allowlist": "SQG003",
  "retain_findings_days": 90
}
```

---

### PATCH /api/installations/{installation_id}/settings

Update repo settings (requires admin auth).

**Request body:**
```json
{
  "block_mode": true,
  "ai_enabled": true,
  "path_allowlist": "test/\nfixtures/",
  "retain_findings_days": 180
}
```

**Response:** Updated settings object + audit log entry.

---

### GET /api/findings/{finding_id}/explain

AI Crew explanation (Phase 7+).

**Response:**
```json
{
  "finding_id": 1001,
  "plain_english": "Your code declares a package called 'fake_pkg' that doesn't exist in the Python package repository (PyPI). When you try to install dependencies, this will fail.",
  "why_matters": "Missing dependencies break deployments. This is almost certainly a typo in the package name.",
  "example_attack": null,
  "how_to_fix": "Check the correct package name on PyPI. Replace 'fake_pkg' with the real package (e.g., 'flask-utils' if that's what you meant).",
  "references": [
    "https://pypi.org/"
  ],
  "cost_tokens": 287,
  "cost_usd": 0.00012
}
```

---

### POST /api/findings/{finding_id}/bypass

Approve/bypass a finding (requires manual intervention + audit).

**Request:**
```json
{
  "reason": "This is a false positive; the package is internal.",
  "expires_at": "2026-07-28T00:00:00Z"
}
```

**Response:** Bypass record + audit log.

---

## Authentication

**Webhook:** No auth required (verified via HMAC signature).

**Dashboard API:** 
- All non-webhook endpoints require Supabase Auth JWT token.
- Token in `Authorization: Bearer {token}` header.
- Verify token signature + user ∈ installation admins (GitHub API check).

---

## Error Responses

All errors follow this format:

```json
{
  "error": "resource_not_found",
  "message": "Analysis ID 999 not found",
  "request_id": "req_12345"  // correlation ID for tracing
}
```

---

## Rate Limiting

- **Webhook:** No rate limit (GitHub controls upstream).
- **Dashboard:** 100 requests/minute per user.
- **Headers:** `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`.

---

## Pagination

Limit: 1–100 (default 20).
Offset: 0-based.

```
GET /api/analyses?limit=50&offset=100
```

---

## Webhooks (Outbound)

*Future (Phase 8+):* POST to user-supplied webhook URL when analysis completes (optional, per setting).

```json
{
  "event": "analysis.completed",
  "analysis_id": 123,
  "repo_full_name": "owner/repo",
  "pr_number": 42,
  "status": "completed",
  "finding_count": 3,
  "timestamp": "2026-06-28T12:02:23Z"
}
```

---

## OpenAPI / Swagger

Auto-generated from FastAPI. Available at `/docs` (dev) and `/redoc` (production docs).

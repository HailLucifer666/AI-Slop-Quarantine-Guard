# DATA_MODEL — PostgreSQL Schema (TARGET, not current)

> **Status: this document describes the intended schema, not the one running.**
>
> What actually ships today (`api/app/db/models.py`):
>
> - **SQLite**, not Postgres. `DATABASE_URL` defaults to a file under `api/`.
> - **No Alembic.** `api/alembic.ini` is an unconfigured placeholder with no `versions/`
>   directory. Additive columns are applied at startup from an explicit append-only list
>   (`db/session.py::_ADDED_COLUMNS`), which is idempotent but is not a migration tool.
> - **The `findings` and `analyses` tables below exist but are unused — 0 rows.** Whole-repo
>   scan results live as JSON text on the `scans` row (`findings_json`, `analytics_json`,
>   `coverage_json`, `groups_json`). Nothing writes per-finding rows.
> - The real `scans` table also carries columns this document doesn't mention:
>   `heartbeat_at` (worker liveness lease), `coverage_json`, `groups_json`, and the
>   provenance set `resolved_sha` / `content_hash` / `file_count` / `ingested_at` /
>   `engine_versions_json`.
>
> Normalizing findings into real rows, and adopting Alembic, are both still open. Until then
> treat `api/app/db/models.py` as the source of truth and this file as the destination.

All tables use PostgreSQL 14+, managed via Supabase. Migrations via Alembic.

---

## Tables

### `installations`
GitHub App installations (one row per org/user).

```sql
CREATE TABLE installations (
    id BIGSERIAL PRIMARY KEY,
    github_installation_id BIGINT UNIQUE NOT NULL,
    github_account_id BIGINT NOT NULL,
    github_account_name VARCHAR(255) NOT NULL,
    github_account_type VARCHAR(50) NOT NULL,  -- 'User' | 'Organization'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_installations_github_id ON installations(github_installation_id);
```

---

### `analyses`
One row per PR analysis (webhook trigger).

```sql
CREATE TABLE analyses (
    id BIGSERIAL PRIMARY KEY,
    installation_id BIGINT NOT NULL REFERENCES installations(id) ON DELETE CASCADE,
    
    -- PR context
    repo_owner VARCHAR(255) NOT NULL,
    repo_name VARCHAR(255) NOT NULL,
    repo_full_name VARCHAR(511) NOT NULL,  -- 'owner/repo'
    pr_number INTEGER NOT NULL,
    pr_title VARCHAR(1024),
    head_sha VARCHAR(40) NOT NULL,  -- commit SHA
    base_ref VARCHAR(255),
    head_ref VARCHAR(255),
    
    -- Deduplication & idempotency
    github_delivery_id VARCHAR(36) UNIQUE NOT NULL,  -- X-GitHub-Delivery header
    
    -- Status
    status VARCHAR(50) DEFAULT 'in_progress',  -- 'in_progress' | 'completed' | 'failed'
    trust_status VARCHAR(50) DEFAULT 'processing',  -- 'completed' | 'degraded' | 'failed' | 'skipped'
    check_run_id BIGINT,  -- GitHub Check Run ID (for updates)
    
    -- Timing
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms INTEGER,
    
    -- Cost tracking
    tokens_used INTEGER DEFAULT 0,
    cost_usd NUMERIC(7, 5) DEFAULT 0,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',  -- flexible storage
    
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_analyses_installation ON analyses(installation_id);
CREATE INDEX idx_analyses_pr ON analyses(repo_full_name, pr_number);
CREATE INDEX idx_analyses_delivery ON analyses(github_delivery_id);
CREATE INDEX idx_analyses_created ON analyses(created_at DESC);
CREATE INDEX idx_analyses_status ON analyses(status);
```

---

### `findings`
Individual issues detected in an analysis (one row per finding).

```sql
CREATE TABLE findings (
    id BIGSERIAL PRIMARY KEY,
    analysis_id BIGINT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    
    -- Finding identity
    rule_id VARCHAR(32) NOT NULL,  -- SQG001, SQG002, etc.
    tool VARCHAR(100) NOT NULL,    -- 'gitleaks', 'trivy', 'semgrep', etc.
    
    -- Severity & confidence
    confidence VARCHAR(50) NOT NULL,  -- 'CERTAIN' | 'HIGH' | 'MEDIUM'
    block_eligible BOOLEAN DEFAULT FALSE,
    
    -- Location in code
    file_path VARCHAR(1024) NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    
    -- Content
    message TEXT NOT NULL,
    evidence JSONB NOT NULL,  -- { snippet, context_before, context_after }
    fix_suggestion TEXT,
    
    -- Versions for reproducibility
    analyzer_version VARCHAR(20),
    rule_version VARCHAR(20),
    tool_version VARCHAR(20),
    diff_sha256 VARCHAR(64),
    evidence_sha256 VARCHAR(64),
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_findings_analysis ON findings(analysis_id);
CREATE INDEX idx_findings_rule ON findings(rule_id);
CREATE INDEX idx_findings_file ON findings(file_path);
CREATE INDEX idx_findings_confidence ON findings(confidence);
CREATE INDEX idx_findings_block ON findings(block_eligible);
```

---

### `webhook_deliveries`
Log of every webhook delivery (for debugging & deduplication).

```sql
CREATE TABLE webhook_deliveries (
    id BIGSERIAL PRIMARY KEY,
    github_delivery_id VARCHAR(36) UNIQUE NOT NULL,
    installation_id BIGINT NOT NULL REFERENCES installations(id) ON DELETE SET NULL,
    
    -- Webhook context
    event_type VARCHAR(100),  -- 'pull_request', 'check_run', etc.
    repo_full_name VARCHAR(511),
    
    -- Request details
    payload_size_bytes INTEGER,
    signature_valid BOOLEAN,
    
    -- Processing
    status VARCHAR(50) NOT NULL,  -- 'received' | 'queued' | 'processed' | 'failed'
    error_message TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);

CREATE INDEX idx_webhook_delivery_id ON webhook_deliveries(github_delivery_id);
CREATE INDEX idx_webhook_installation ON webhook_deliveries(installation_id);
CREATE INDEX idx_webhook_created ON webhook_deliveries(created_at DESC);
```

---

### `audit_log`
Every significant action (for transparency & debugging).

```sql
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    installation_id BIGINT REFERENCES installations(id) ON DELETE SET NULL,
    
    -- Action details
    action VARCHAR(100) NOT NULL,  -- 'analysis_started', 'check_run_created', 'setting_changed', etc.
    actor VARCHAR(255),  -- 'system', 'user@github', 'webhook'
    
    -- Target
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),
    
    -- Changes
    changes JSONB DEFAULT '{}',  -- { old_value, new_value }
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_installation ON audit_log(installation_id);
CREATE INDEX idx_audit_action ON audit_log(action);
CREATE INDEX idx_audit_created ON audit_log(created_at DESC);
```

---

### `settings`
Per-repo configuration (dashboard-editable).

```sql
CREATE TABLE settings (
    id BIGSERIAL PRIMARY KEY,
    installation_id BIGINT NOT NULL REFERENCES installations(id) ON DELETE CASCADE,
    repo_full_name VARCHAR(511) NOT NULL,
    
    -- Blocking & confidence
    block_mode BOOLEAN DEFAULT FALSE,  -- Enable blocking? (Phase 9+)
    blocked_rules VARCHAR(255) DEFAULT 'SQG001,SQG002',  -- Comma-separated
    
    -- AI Crew (Phase 7+)
    ai_enabled BOOLEAN DEFAULT FALSE,
    ai_model VARCHAR(100) DEFAULT 'claude-haiku-4-5',
    
    -- Allowlists
    path_allowlist TEXT,  -- Newline-separated globs
    rule_allowlist TEXT,  -- Comma-separated SQG###
    
    -- Privacy
    retain_findings_days INTEGER DEFAULT 90,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(installation_id, repo_full_name)
);

CREATE INDEX idx_settings_installation ON settings(installation_id);
CREATE INDEX idx_settings_repo ON settings(repo_full_name);
```

---

## Data Lifecycle

### Retention Policy

- **`findings`:** 90 days (default, configurable per repo).
- **`analyses`:** 180 days (for history).
- **`webhook_deliveries`:** 30 days (debug only).
- **`audit_log`:** 1 year (compliance).
- **`installations`:** indefinite (core identity).

Archive after retention window, then delete.

### Idempotency

`analyses` deduplicated by `github_delivery_id` (unique constraint). Webhook redelivery → same delivery ID → `INSERT ... ON CONFLICT DO UPDATE` (update check run status if already processed).

### Indexes

- All foreign keys indexed.
- Range queries: `created_at DESC` (recent first).
- Lookup: `installation_id`, `repo_full_name`, `rule_id`.
- Status/flag queries: `status`, `block_eligible`, `confidence`.

---

## Schema Diagram (Text)

```
┌─────────────┐
│installations│  (GitHub App installations)
└─────────────┘
      │
      ├─→ ┌──────────────────┐
      │   │analyses          │  (PR analyses, one per webhook)
      │   └──────────────────┘
      │         │
      │         ├─→ ┌──────────┐
      │         │   │findings  │  (individual issues)
      │         │   └──────────┘
      │         │
      │         └─→ ┌──────────────────┐
      │             │webhook_deliveries│  (webhook log)
      │             └──────────────────┘
      │
      ├─→ ┌──────────────┐
      │   │settings      │  (per-repo config)
      │   └──────────────┘
      │
      └─→ ┌──────────────┐
          │audit_log     │  (action history)
          └──────────────┘
```

---

## Universal Finding Record (Denormalized)

When returning a finding to the dashboard or API, include:

```python
{
    "id": 12345,
    "rule_id": "SQG001",
    "file_path": "requirements.txt",
    "line_start": 42,
    "line_end": 42,
    "confidence": "CERTAIN",
    "block_eligible": True,
    "message": "Package 'fake_pkg' does not exist in PyPI",
    "evidence": {
        "snippet": "fake_pkg==1.0.0",
        "context_before": ["flask==2.0.0"],
        "context_after": ["requests==2.28.0"]
    },
    "tool": "custom_registry_client",
    "fix_suggestion": "Replace 'fake_pkg' with a valid package name",
    "analyzer_version": "1.0.0",
    "rule_version": "1.0.0",
    "tool_version": "pypi_json_api"
}
```

---

## Migrations (Alembic)

Version every schema change in `api/app/db/migrations/`. Example:

```
migrations/
  versions/
    001_initial.py
    002_add_metadata_jsonb.py
    003_add_trust_status.py
```

Run `alembic upgrade head` on deploy. Test `alembic downgrade -1` for rollback path.

"""SQLAlchemy 2.0 declarative models — eight tables, three of them unused.

No longer the "stub columns, minimal schema" this docstring used to claim: ``Scan`` alone
carries the progress, lease, coverage, grouping and ingest-provenance columns the scanner
depends on.

What a reader needs to know before trusting the shape of this file — verified against the
live ``api/app.db``, which holds 19 scans:

* ``Scan``, ``AppSettings``, ``AuditLog`` and ``WorkerHeartbeat`` are live.
* ``Analysis`` and ``Finding`` are **empty (0 rows) and written by nothing.** A completed
  scan's findings are stored as a JSON blob on the ``scans`` row, not normalised into
  these tables. They describe an intended schema, not the one in use — do not read
  ``findings`` expecting to see results. ``docs/DATA_MODEL.md`` carries the same warning.
* ``Installation`` and ``WebhookDelivery`` are also empty, because no GitHub App
  installation has ever been recorded against this database.

New columns are added by the append-only ``_ADDED_COLUMNS`` tuple in ``session.py``, not
by Alembic — ``alembic.ini`` exists but has no ``versions/``. That is a deliberate
deviation for a single-node SQLite MVP and a debt to settle before Postgres.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class Analysis(Base):
    """Analysis record."""
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True)
    repo = Column(String, nullable=False)
    pr_number = Column(Integer, nullable=False)
    head_sha = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class Finding(Base):
    """Finding record."""
    __tablename__ = "findings"

    id = Column(Integer, primary_key=True)
    analysis_id = Column(Integer, nullable=False)
    rule_id = Column(String, nullable=False)
    category = Column(String, nullable=False)
    confidence = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    line_start = Column(Integer, nullable=False)
    line_end = Column(Integer, nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class WebhookDelivery(Base):
    """Webhook delivery record (dedupe key)."""
    __tablename__ = "webhook_deliveries"

    id = Column(Integer, primary_key=True)
    delivery_id = Column(String, unique=True, nullable=False)
    github_event = Column(String, nullable=False)
    received_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    """Audit log."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    action = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Installation(Base):
    """GitHub App installation record."""
    __tablename__ = "installations"

    id = Column(Integer, primary_key=True)
    installation_id = Column(Integer, unique=True, nullable=False)
    account_login = Column(String, nullable=False)
    repositories_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Scan(Base):
    """Whole-repo scan record (Stage 2).

    A scan runs the same 6 analyzers as the PR gate over an entire codebase
    (from a URL clone, an uploaded zip, or a local dir). Analytics and findings
    are stored as JSON on the row for the MVP; they get normalized in Phase 5.
    """
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True)
    source = Column(String, nullable=False)              # url | zip | local
    ref = Column(String, nullable=False)                 # url / filename / path (user-facing)
    status = Column(String, nullable=False, default="queued")  # queued|running|completed|failed
    files_scanned = Column(Integer, default=0)
    files_skipped = Column(Integer, default=0)
    duration_ms = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)                  # reason when status=failed
    analytics_json = Column(Text, nullable=True)         # json.dumps(analytics)
    findings_json = Column(Text, nullable=True)          # json.dumps([finding, ...])
    skipped_json = Column(Text, nullable=True)           # json.dumps([skipped paths])
    # Per-rule coverage (app.coverage.summarize). Without this a stored scan cannot
    # say which checks actually ran, so "0 findings" stays ambiguous forever.
    coverage_json = Column(Text, nullable=True)
    # Clustered view (app.grouping.summarize_groups). Redundant with findings_json by
    # construction, and stored anyway so the dashboard renders the same clustering the
    # PR comment does — a second implementation in TypeScript could disagree with this
    # one, and then two surfaces would report different totals for the same scan.
    groups_json = Column(Text, nullable=True)
    # --- provenance: what exactly was analyzed, so a result is checkable ----------
    resolved_sha = Column(String, nullable=True)         # git rev-parse HEAD, for url/local scans
    content_hash = Column(String, nullable=True)         # sha256 over the ingested file set
    file_count = Column(Integer, nullable=True)          # files handed to the analyzers
    ingested_at = Column(DateTime, nullable=True)        # when the snapshot was taken
    engine_versions_json = Column(Text, nullable=True)   # rule + engine versions used
    progress = Column(Text, nullable=True)               # json: live phase while status=running; cleared on finish
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    # Liveness lease while status=running. Stamped by the worker every
    # HEARTBEAT_INTERVAL_S; a lapsed lease means the worker died mid-scan and the row
    # is reconciled to failed (see store.reconcile_stale_scans). Without this, a dead
    # worker leaves the scan "running" forever and the dashboard — which reads only
    # completed scans — keeps rendering the PREVIOUS scan as the current answer.
    heartbeat_at = Column(DateTime, nullable=True)


class WorkerHeartbeat(Base):
    """Global "is a worker alive at all" signal — a single row (id=1).

    Distinct from Scan.heartbeat_at, which only exists while a specific scan runs. An
    idle worker has no scan to stamp, so /api/health could not otherwise tell "idle"
    apart from "process is gone" — the difference between a queue that will drain and
    one that never will.
    """
    __tablename__ = "worker_heartbeat"

    id = Column(Integer, primary_key=True)               # always 1
    updated_at = Column(DateTime, default=datetime.utcnow)


class AppSettings(Base):
    """Global repo-default settings — a single row (id=1). Phase 8.

    Stores the gate preferences shown on the dashboard Settings page. Saving these
    persists the user's intent; ENFORCEMENT (actually blocking a merge) is Phase 9
    and gated behind a measured <1% false-positive rate — so nothing here changes a
    scan's verdict yet.
    """
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True)               # always 1
    block_mode = Column(Boolean, nullable=False, default=False)
    blocked_rules = Column(Text, nullable=False, default="[]")  # json list of SQG ids
    retention_days = Column(Integer, nullable=False, default=90)
    updated_at = Column(DateTime, default=datetime.utcnow)

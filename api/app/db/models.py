"""SQLAlchemy 2.0 declarative models.

ponytail: stub columns, minimal schema.
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
    progress = Column(Text, nullable=True)               # json: live phase while status=running; cleared on finish
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


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

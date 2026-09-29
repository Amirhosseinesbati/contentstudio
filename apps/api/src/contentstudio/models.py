from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceAsset(Base):
    __tablename__ = "source_assets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "sha256", "title", name="uq_source_hash_title"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    title: Mapped[str] = mapped_column(String(250))
    kind: Mapped[str] = mapped_column(String(30))
    rights_status: Mapped[str] = mapped_column(String(30))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    media_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TranscriptVersion(Base):
    __tablename__ = "transcript_versions"
    __table_args__ = (UniqueConstraint("source_asset_id", "version", name="uq_transcript_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_asset_id: Mapped[str] = mapped_column(ForeignKey("source_assets.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    provenance: Mapped[str] = mapped_column(String(35))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Segment(Base):
    __tablename__ = "segments"
    __table_args__ = (
        UniqueConstraint("transcript_version_id", "stable_id", name="uq_segment_stable"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    stable_id: Mapped[str] = mapped_column(String(36), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    transcript_version_id: Mapped[str] = mapped_column(
        ForeignKey("transcript_versions.id"), index=True
    )
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str | None] = mapped_column(String(100), nullable=True)
    text: Mapped[str] = mapped_column(Text)


class BrandProfileVersion(Base):
    __tablename__ = "brand_profile_versions"
    __table_args__ = (UniqueConstraint("workspace_id", "name", "version", name="uq_brand_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    version: Mapped[int] = mapped_column(Integer)
    tone: Mapped[str] = mapped_column(String(300), default="Clear and precise")
    rules_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ContentBatch(Base):
    __tablename__ = "content_batches"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "source_hash",
            "recipe_version",
            "brand_profile_version_id",
            name="uq_batch_recipe",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_asset_id: Mapped[str] = mapped_column(ForeignKey("source_assets.id"), index=True)
    transcript_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("transcript_versions.id"), nullable=True
    )
    brand_profile_version_id: Mapped[str] = mapped_column(ForeignKey("brand_profile_versions.id"))
    recipe_version: Mapped[str] = mapped_column(String(40), default="v1")
    source_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("content_batches.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    source_segment_ids: Mapped[list] = mapped_column(JSON, default=list)
    verification_status: Mapped[str] = mapped_column(String(30), default="verified")


class ContentAssetVersion(Base):
    __tablename__ = "content_asset_versions"
    __table_args__ = (UniqueConstraint("logical_asset_id", "version", name="uq_asset_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("content_batches.id"), index=True)
    logical_asset_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    asset_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(250))
    text: Mapped[str] = mapped_column(Text, default="")
    slides_json: Mapped[list] = mapped_column(JSON, default=list)
    clip_range_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_segment_ids: Mapped[list] = mapped_column(JSON, default=list)
    warnings_json: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="review_pending")
    content_hash: Mapped[str] = mapped_column(String(64))
    render_urls_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    __table_args__ = (UniqueConstraint("asset_version_id", name="uq_review_once"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    asset_version_id: Mapped[str] = mapped_column(
        ForeignKey("content_asset_versions.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(20))
    expected_hash: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "operation_key", name="uq_job_operation"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("content_batches.id"), nullable=True)
    asset_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("content_asset_versions.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(30))
    operation_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class PublicationDraft(Base):
    __tablename__ = "publication_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    asset_version_id: Mapped[str] = mapped_column(
        ForeignKey("content_asset_versions.id"), index=True
    )
    channel: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="draft")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(150), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)


class DispatchLedger(Base):
    __tablename__ = "dispatch_ledger"
    __table_args__ = (
        UniqueConstraint("workspace_id", "operation_key", name="uq_dispatch_operation"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    operation_key: Mapped[str] = mapped_column(String(180))
    asset_version_id: Mapped[str] = mapped_column(ForeignKey("content_asset_versions.id"))
    channel: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="claimed")
    payload_hash: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str | None] = mapped_column(String(150), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("workspace_id", "event_id", name="uq_webhook_event"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(180))
    payload_hash: Mapped[str] = mapped_column(String(64))
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("content_batches.id"), nullable=True)


class WorkflowIncident(Base):
    __tablename__ = "workflow_incidents"
    __table_args__ = (
        UniqueConstraint("workspace_id", "operation_key", name="uq_incident_operation"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id"), nullable=True, index=True
    )
    operation_key: Mapped[str] = mapped_column(String(180))
    error: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InstallationBootstrap(Base):
    """Unique durable marker preventing concurrent first-admin creation."""

    __tablename__ = "installation_bootstrap"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

"""Dry-run-first cleanup of generated content in one seeded DEMO workspace.

This deliberately does not reset users, sources, transcripts, brands, n8n
executions, LangGraph checkpoints, or the shared connector simulator. Run it
with the API and n8n triggers stopped; a live worker could recreate records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import session_factory
from .models import (
    Claim,
    ContentAssetVersion,
    ContentBatch,
    DispatchLedger,
    InstallationBootstrap,
    Job,
    PublicationDraft,
    ReviewDecision,
    SourceAsset,
    WebhookEvent,
    WorkflowIncident,
    Workspace,
)

DEMO_WORKSPACES = frozenset({"studio-alpha", "studio-beta"})


@dataclass(frozen=True)
class ResetPlan:
    workspace_id: str
    workspace_slug: str
    cutoff_utc: datetime | None
    batch_ids: tuple[str, ...]
    plan_sha256: str
    asset_ids: tuple[str, ...]
    job_ids: tuple[str, ...]
    incident_ids: tuple[str, ...]
    counts: dict[str, int]
    media_dirs: tuple[Path, ...]


def seeded_workspace_id(slug: str) -> str:
    if slug not in DEMO_WORKSPACES:
        raise ValueError("Only the two seeded DEMO workspace slugs are allowed")
    return str(uuid5(NAMESPACE_URL, f"contentstudio-demo:workspace:{slug}"))


def _selected_batches(workspace_id: str, slug: str, cutoff: datetime | None):
    query = select(ContentBatch.id).where(ContentBatch.workspace_id == workspace_id)
    if cutoff is not None:
        # Age-based retention targets generated runs and preserves the known
        # archive and showcase fixtures.
        query = query.where(ContentBatch.created_at < cutoff)
        query = query.where(ContentBatch.recipe_version != "synthetic-archive-v1")
        if slug == "studio-alpha":
            showcase_source_id = str(uuid5(NAMESPACE_URL, "contentstudio-demo:source:studio-alpha:onboarding"))
            query = query.where(~and_(
                ContentBatch.recipe_version == "v1",
                ContentBatch.source_asset_id == showcase_source_id,
            ))
    return query.order_by(ContentBatch.id)


def safe_media_dir(media_root: Path, workspace_id: str, batch_id: str) -> Path:
    """Reject path traversal, symlinks, and any path outside the chosen workspace."""
    if str(UUID(workspace_id)) != workspace_id or str(UUID(batch_id)) != batch_id:
        raise ValueError("Workspace and batch IDs must be canonical UUIDs")
    root = media_root.resolve(strict=False)
    workspace = root / workspace_id
    target = workspace / batch_id
    if workspace.is_symlink() or target.is_symlink():
        raise ValueError("Refusing to remove a symlinked media directory")
    if workspace.resolve(strict=False).parent != root or target.resolve(strict=False).parent != workspace:
        raise ValueError("Media target escaped its DEMO workspace directory")
    return target


def plan_reset(
    db: Session,
    *,
    workspace_slug: str,
    media_root: Path,
    older_than_days: int | None = None,
    reference_time: datetime | None = None,
) -> ResetPlan:
    if get_settings().mode != "demo":
        raise ValueError("DEMO reset is disabled outside MODE=demo")
    expected_id = seeded_workspace_id(workspace_slug)
    workspace = db.scalar(select(Workspace).where(Workspace.slug == workspace_slug))
    if workspace is None or workspace.id != expected_id:
        raise ValueError("Selected workspace is not the seeded DEMO namespace")
    if db.scalar(select(InstallationBootstrap.id).limit(1)) is not None:
        raise ValueError("Connected installation marker exists; DEMO reset is disabled")
    if older_than_days is not None and older_than_days < 1:
        raise ValueError("Retention age must be at least one day")
    now = reference_time or datetime.now(UTC)
    cutoff = now - timedelta(days=older_than_days) if older_than_days is not None else None
    batch_ids = tuple(db.scalars(_selected_batches(expected_id, workspace_slug, cutoff)).all())
    source_ids = set(db.scalars(select(SourceAsset.id).where(SourceAsset.workspace_id == expected_id)).all())
    if source_ids.intersection(batch_ids):
        raise ValueError("A batch ID collides with a preserved source-media directory")
    asset_ids = tuple(sorted(db.scalars(select(ContentAssetVersion.id).where(
        ContentAssetVersion.workspace_id == expected_id,
        ContentAssetVersion.batch_id.in_(batch_ids),
    )).all()))
    jobs = db.scalars(select(Job).where(
        Job.workspace_id == expected_id,
        or_(Job.batch_id.in_(batch_ids), Job.asset_version_id.in_(asset_ids)),
    )).all()
    ledger = db.scalars(select(DispatchLedger).where(
        DispatchLedger.workspace_id == expected_id,
        DispatchLedger.asset_version_id.in_(asset_ids),
    )).all()
    related_keys = {row.operation_key for row in ledger}
    related_keys.update(row.operation_key for row in jobs if row.operation_key)
    related_keys.update(f"job:{row.id}" for row in jobs)
    incident_query = select(WorkflowIncident.id).where(
        WorkflowIncident.workspace_id == expected_id,
        WorkflowIncident.operation_key.in_(related_keys),
    )
    incident_ids = tuple(sorted(db.scalars(incident_query).all()))
    event_filter = (WebhookEvent.workspace_id == expected_id) & WebhookEvent.batch_id.in_(batch_ids)
    claim_ids = tuple(sorted(db.scalars(select(Claim.id).where(
        Claim.workspace_id == expected_id, Claim.batch_id.in_(batch_ids),
    )).all()))
    review_ids = tuple(sorted(db.scalars(select(ReviewDecision.id).where(
        ReviewDecision.workspace_id == expected_id,
        ReviewDecision.asset_version_id.in_(asset_ids),
    )).all()))
    draft_ids = tuple(sorted(db.scalars(select(PublicationDraft.id).where(
        PublicationDraft.workspace_id == expected_id,
        PublicationDraft.asset_version_id.in_(asset_ids),
    )).all()))
    webhook_ids = tuple(sorted(db.scalars(select(WebhookEvent.id).where(event_filter)).all()))
    ledger_ids = tuple(sorted(row.id for row in ledger))
    job_ids = tuple(sorted(row.id for row in jobs))
    counts = {
        "content_batches": len(batch_ids),
        "content_asset_versions": len(asset_ids),
        "claims": len(claim_ids),
        "review_decisions": len(review_ids),
        "jobs": len(job_ids),
        "publication_drafts": len(draft_ids),
        "dispatch_ledger": len(ledger_ids),
        "webhook_events": len(webhook_ids),
        "workflow_incidents": len(incident_ids),
    }
    media_dirs = tuple(safe_media_dir(media_root, expected_id, batch_id) for batch_id in batch_ids)
    fingerprint = hashlib.sha256(json.dumps({
        "workspace_id": expected_id,
        "batch_ids": batch_ids,
        "asset_ids": asset_ids,
        "claim_ids": claim_ids,
        "review_ids": review_ids,
        "job_ids": job_ids,
        "draft_ids": draft_ids,
        "ledger_ids": ledger_ids,
        "webhook_ids": webhook_ids,
        "incident_ids": incident_ids,
    }, sort_keys=True).encode("utf-8")).hexdigest()
    return ResetPlan(
        workspace_id=expected_id,
        workspace_slug=workspace_slug,
        cutoff_utc=cutoff,
        batch_ids=batch_ids,
        plan_sha256=fingerprint,
        asset_ids=asset_ids,
        job_ids=job_ids,
        incident_ids=incident_ids,
        counts=counts,
        media_dirs=media_dirs,
    )


def apply_reset(
    db: Session,
    plan: ResetPlan,
    *,
    media_root: Path,
    confirm_workspace_id: str,
    confirm_plan_sha256: str,
    expected_batch_count: int,
    offline_ack: bool,
) -> dict[str, object]:
    if get_settings().mode != "demo":
        raise ValueError("DEMO reset is disabled outside MODE=demo")
    if not offline_ack or confirm_workspace_id != plan.workspace_id:
        raise ValueError("Apply requires an offline acknowledgment and exact workspace UUID")
    if confirm_plan_sha256 != plan.plan_sha256:
        raise ValueError("Selected-row fingerprint differs from the reviewed dry run")
    if expected_batch_count != len(plan.batch_ids):
        raise ValueError("Batch count changed since dry run; inspect a new plan")
    if db.scalar(select(InstallationBootstrap.id).limit(1)) is not None:
        raise ValueError("Connected installation marker exists; DEMO reset is disabled")
    current = tuple(db.scalars(_selected_batches(
        plan.workspace_id, plan.workspace_slug, plan.cutoff_utc,
    )).all())
    if current != plan.batch_ids:
        raise ValueError("Selected batches changed since planning; aborting")
    if db.scalar(select(Job.id).where(Job.id.in_(plan.job_ids), Job.status == "running").limit(1)):
        raise ValueError("A selected job is still running")
    # Preflight every resolved absolute target before the first database delete.
    targets = tuple(safe_media_dir(media_root, plan.workspace_id, batch_id) for batch_id in plan.batch_ids)
    if targets != plan.media_dirs:
        raise ValueError("Media paths changed since planning")
    try:
        db.execute(delete(WorkflowIncident).where(
            WorkflowIncident.workspace_id == plan.workspace_id,
            WorkflowIncident.id.in_(plan.incident_ids),
        ))
        db.execute(delete(WebhookEvent).where(
            WebhookEvent.workspace_id == plan.workspace_id,
            WebhookEvent.batch_id.in_(plan.batch_ids),
        ))
        for model in (PublicationDraft, DispatchLedger, ReviewDecision):
            db.execute(delete(model).where(
                model.workspace_id == plan.workspace_id,
                model.asset_version_id.in_(plan.asset_ids),
            ))
        db.execute(delete(Job).where(Job.workspace_id == plan.workspace_id, Job.id.in_(plan.job_ids)))
        db.execute(delete(Claim).where(Claim.workspace_id == plan.workspace_id, Claim.batch_id.in_(plan.batch_ids)))
        db.execute(delete(ContentAssetVersion).where(
            ContentAssetVersion.workspace_id == plan.workspace_id,
            ContentAssetVersion.id.in_(plan.asset_ids),
        ))
        db.execute(delete(ContentBatch).where(
            ContentBatch.workspace_id == plan.workspace_id,
            ContentBatch.id.in_(plan.batch_ids),
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    removed_dirs: list[str] = []
    failed_dirs: list[str] = []
    for target in targets:
        try:
            checked = safe_media_dir(media_root, plan.workspace_id, target.name)
            if checked != target:
                raise ValueError("Media target changed after database commit")
            if target.exists():
                shutil.rmtree(target)
                removed_dirs.append(str(target))
        except (OSError, ValueError):
            failed_dirs.append(str(target))
    return {"deleted_rows": plan.counts, "removed_media_dirs": removed_dirs, "failed_media_dirs": failed_dirs}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-slug", required=True, choices=sorted(DEMO_WORKSPACES))
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all-batches", action="store_true", help="Reset all generated batches for this DEMO workspace")
    selection.add_argument("--older-than-days", type=int, help="Prune batches older than this many days")
    parser.add_argument("--apply", action="store_true", help="Delete planned rows and batch media directories")
    parser.add_argument("--confirm-workspace-id", help="Exact seeded workspace UUID required with --apply")
    parser.add_argument("--confirm-plan-sha256", help="Exact selected-row fingerprint from dry run")
    parser.add_argument("--expected-batch-count", type=int, help="Dry-run batch count required with --apply")
    parser.add_argument("--offline-ack", action="store_true", help="Assert API and n8n triggers are stopped")
    args = parser.parse_args()
    if os.environ.get("MODE") != "demo" or not os.environ.get("DATABASE_URL"):
        parser.error("Explicit MODE=demo and DATABASE_URL environment variables are required")
    settings = get_settings()
    if settings.mode != "demo":
        parser.error("Demo reset is disabled outside MODE=demo")
    if args.apply and (
        not args.confirm_workspace_id or not args.confirm_plan_sha256
        or args.expected_batch_count is None or not args.offline_ack
    ):
        parser.error("--apply requires workspace UUID, plan SHA-256, batch count and --offline-ack")
    try:
        with session_factory()() as db:
            plan = plan_reset(
                db, workspace_slug=args.workspace_slug, media_root=settings.media_root,
                older_than_days=args.older_than_days,
            )
            if args.apply:
                outcome = apply_reset(
                    db, plan, media_root=settings.media_root,
                    confirm_workspace_id=args.confirm_workspace_id,
                    confirm_plan_sha256=args.confirm_plan_sha256,
                    expected_batch_count=args.expected_batch_count, offline_ack=args.offline_ack,
                )
                print(json.dumps({"workspace_id": plan.workspace_id, "applied": True, **outcome}, indent=2))
                if outcome["failed_media_dirs"]:
                    raise SystemExit("Database reset committed, but some media directories need manual cleanup")
            else:
                print(json.dumps({
                    "workspace_id": plan.workspace_id, "workspace_slug": plan.workspace_slug,
                    "applied": False, "cutoff_utc": plan.cutoff_utc.isoformat() if plan.cutoff_utc else None,
                    "counts": plan.counts, "batch_ids": plan.batch_ids,
                    "plan_sha256": plan.plan_sha256,
                    "media_dirs": [str(path) for path in plan.media_dirs if path.exists()],
                }, indent=2))
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()

"""Service-token API for n8n workflow steps. These endpoints do not own branching."""

import hashlib
import html
import json
import re
import zipfile
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import require_service_token
from .config import get_settings
from .db import get_db
from .domain import canonical_hash
from .models import (
    BrandProfileVersion,
    Claim,
    ContentAssetVersion,
    ContentBatch,
    DispatchLedger,
    Job,
    PublicationDraft,
    ReviewDecision,
    SourceAsset,
    WebhookEvent,
    WorkflowIncident,
    Workspace,
    now,
)
from .schemas import (
    BatchStepInput,
    DispatchCompleteInput,
    DispatchPrepareInput,
    IntakeInput,
    OutboxInput,
    RenderStepInput,
    WorkflowErrorInput,
)
from .service import (
    GenerationInProgress,
    GenerationSourceChanged,
    asset_data,
    brand_data,
    create_batch,
    create_transcript,
    current_assets,
    ensure_job,
    generate_for_batch,
    invalidate_batch_package,
    latest_transcript,
    package_file_name,
    package_operation_key,
    render_file_paths,
    render_operation_key,
    scoped,
    segment_data,
    transcript_segments,
)
from .service import claim_job as _claim_job

router = APIRouter(prefix="/internal/workflows", dependencies=[Depends(require_service_token)])


def must_get(db: Session, model, item_id: str, workspace_id: str):
    item = (
        db.get(Workspace, item_id)
        if model is Workspace and item_id == workspace_id
        else scoped(db, model, item_id, workspace_id)
    )
    if item is None:
        raise HTTPException(404, "Item not found in workspace")
    return item


def _parse_now(value: str | None) -> datetime:
    if value:
        if get_settings().mode != "demo":
            raise HTTPException(403, "Clock override is available only in demo")
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if result.tzinfo is None:
                raise ValueError("Time zone required")
            return result
        except ValueError as error:
            raise HTTPException(422, "Use an ISO 8601 timestamp with time zone") from error
    return now()


@router.get("/workspaces")
def workspaces(db: Session = Depends(get_db)):
    return {
        "items": [
            {"id": w.id, "slug": w.slug, "name": w.name}
            for w in db.scalars(select(Workspace).order_by(Workspace.slug))
        ]
    }


@router.get("/demo-fixtures")
def demo_fixtures(db: Session = Depends(get_db)):
    if get_settings().mode != "demo":
        raise HTTPException(404, "Demo fixtures unavailable")
    sources = db.scalars(select(SourceAsset).order_by(SourceAsset.title).limit(5)).all()
    items = []
    for source in sources:
        brand = db.scalar(
            select(BrandProfileVersion)
            .where(BrandProfileVersion.workspace_id == source.workspace_id)
            .order_by(BrandProfileVersion.name)
            .limit(1)
        )
        if brand:
            items.append(
                {
                    "workspace_id": source.workspace_id,
                    "source_asset_id": source.id,
                    "brand_profile_version_id": brand.id,
                    "recipe_version": "scenario-v1",
                    "request_id": f"demo-{source.id}",
                }
            )
    return {"items": items}


@router.get("/demo-scenario-status")
def demo_scenario_status(
    workspace_id: str, request_id: str, db: Session = Depends(get_db)
):
    """Expose only persisted demo metadata for triggered workflow acceptance."""
    if get_settings().mode != "demo":
        raise HTTPException(404, "Demo scenario status unavailable")
    must_get(db, Workspace, workspace_id, workspace_id)
    event = db.scalar(
        select(WebhookEvent).where(
            WebhookEvent.workspace_id == workspace_id,
            WebhookEvent.event_id == request_id,
        )
    )
    if event is None or event.batch_id is None:
        return {"observed": False}
    batch = must_get(db, ContentBatch, event.batch_id, workspace_id)
    assets = current_assets(db, batch.id, workspace_id)
    claim_count = db.scalar(
        select(func.count(Claim.id)).where(
            Claim.workspace_id == workspace_id, Claim.batch_id == batch.id
        )
    ) or 0
    matching_batch_count = db.scalar(
        select(func.count(ContentBatch.id)).where(
            ContentBatch.workspace_id == workspace_id,
            ContentBatch.source_asset_id == batch.source_asset_id,
            ContentBatch.brand_profile_version_id == batch.brand_profile_version_id,
            ContentBatch.recipe_version == batch.recipe_version,
        )
    ) or 0
    return {
        "observed": True,
        "batch_id": batch.id,
        "source_asset_id": batch.source_asset_id,
        "recipe_version": batch.recipe_version,
        "status": batch.status,
        "asset_count": len(assets),
        "asset_type_counts": dict(Counter(asset.asset_type for asset in assets)),
        "claim_count": claim_count,
        "matching_batch_count": matching_batch_count,
        "payload_hash": event.payload_hash,
    }


@router.post("/intake")
def intake(payload: IntakeInput, db: Session = Depends(get_db)):
    source = must_get(db, SourceAsset, payload.source_asset_id, payload.workspace_id)
    brand = must_get(
        db, BrandProfileVersion, payload.brand_profile_version_id, payload.workspace_id
    )
    established_rights = source.rights_status in (
        "attested",
        "owned",
        "owned_synthetic_script",
    ) or (
        get_settings().mode == "demo"
        and source.rights_status == "owned_synthetic_media"
    )
    if not established_rights:
        raise HTTPException(422, "Source rights are not established")
    body_hash = canonical_hash(payload.model_dump(exclude={"request_id"}))
    prior = db.scalar(
        select(WebhookEvent).where(
            WebhookEvent.workspace_id == payload.workspace_id,
            WebhookEvent.event_id == payload.request_id,
        )
    )
    if prior:
        if prior.payload_hash != body_hash:
            raise HTTPException(409, "Conflicting duplicate event ID")
        batch = must_get(db, ContentBatch, prior.batch_id, payload.workspace_id)
        return {"batch_id": batch.id, "duplicate": True, "status": batch.status}
    try:
        batch, duplicate = create_batch(db, source, brand, payload.recipe_version)
        db.add(
            WebhookEvent(
                workspace_id=payload.workspace_id,
                event_id=payload.request_id,
                payload_hash=body_hash,
                batch_id=batch.id,
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        prior = db.scalar(
            select(WebhookEvent).where(
                WebhookEvent.workspace_id == payload.workspace_id,
                WebhookEvent.event_id == payload.request_id,
            )
        )
        if prior and prior.payload_hash == body_hash:
            batch = must_get(db, ContentBatch, prior.batch_id, payload.workspace_id)
            return {"batch_id": batch.id, "duplicate": True, "status": batch.status}
        raise HTTPException(409, "Concurrent conflicting intake") from None
    return {"batch_id": batch.id, "duplicate": duplicate, "status": batch.status}


def _transcribe_openai(path: Path) -> list[dict]:
    from openai import OpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OpenAI transcription requires OPENAI_API_KEY")
    if path.stat().st_size > 25 * 1024 * 1024:
        raise ValueError("OpenAI transcription upload exceeds 25 MB; split or compress the source")
    client = OpenAI(api_key=settings.openai_api_key, timeout=120, max_retries=2)
    with path.open("rb") as media:
        response = client.audio.transcriptions.create(
            model=settings.transcription_model,
            file=media,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    segments = getattr(response, "segments", None)
    if not segments:
        raise ValueError("Provider returned no measured timestamp segments")
    result = []
    for item in segments:
        result.append(
            {
                "start_ms": round(item.start * 1000),
                "end_ms": round(item.end * 1000),
                "speaker": None,
                "text": item.text.strip(),
            }
        )
    return result


@router.post("/transcribe")
def transcribe(payload: BatchStepInput, db: Session = Depends(get_db)):
    batch = must_get(db, ContentBatch, payload.batch_id, payload.workspace_id)
    source = must_get(db, SourceAsset, batch.source_asset_id, payload.workspace_id)
    transcript = latest_transcript(db, source)
    if transcript is not None:
        if batch.transcript_version_id and batch.transcript_version_id != transcript.id:
            raise HTTPException(409, "Source transcript changed; create a new batch")
        batch.transcript_version_id = transcript.id
        if not current_assets(db, batch.id, payload.workspace_id):
            batch.status = "generating"
        db.commit()
        return {
            "batch_id": batch.id,
            "transcript_version_id": transcript.id,
            "segments_count": len(transcript_segments(db, transcript)),
            "provenance": transcript.provenance,
        }
    if get_settings().transcription_provider != "openai":
        batch.status = "failed"
        batch.error = "No transcript fixture exists; live transcription is not configured"
        db.commit()
        raise HTTPException(422, batch.error)
    if not source.media_path:
        raise HTTPException(422, "Audio/video media is required for transcription")
    path = Path(source.media_path).resolve()
    root = (get_settings().media_root.resolve() / payload.workspace_id).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Media is unavailable")
    try:
        segments = _transcribe_openai(path)
    except Exception as error:
        batch.status = "failed"
        batch.error = f"Transcription failed: {type(error).__name__}: {str(error)[:300]}"
        db.commit()
        raise HTTPException(502, batch.error) from error
    transcript = create_transcript(db, source, segments, "openai_measured_segments")
    batch.transcript_version_id = transcript.id
    batch.status = "generating"
    db.commit()
    return {
        "batch_id": batch.id,
        "transcript_version_id": transcript.id,
        "segments_count": len(segments),
        "provenance": transcript.provenance,
    }


@router.post("/generate")
def generate(payload: BatchStepInput, db: Session = Depends(get_db)):
    batch = must_get(db, ContentBatch, payload.batch_id, payload.workspace_id)
    if not batch.transcript_version_id:
        raise HTTPException(409, "Transcribe before generation")
    try:
        return generate_for_batch(db, batch)
    except GenerationInProgress as error:
        raise HTTPException(409, str(error)) from error
    except GenerationSourceChanged as error:
        raise HTTPException(409, str(error)) from error
    except Exception as error:
        db.rollback()
        raise HTTPException(
            502, f"Generation failed: {type(error).__name__}: {str(error)[:300]}"
        ) from error


def _job_for(
    db: Session,
    workspace_id: str,
    kind: str,
    *,
    asset_id: str | None = None,
    batch_id: str | None = None,
) -> Job:
    if kind == "render":
        asset = must_get(db, ContentAssetVersion, asset_id, workspace_id)
        operation_key = render_operation_key(asset)
    else:
        approved = [
            asset for asset in current_assets(db, batch_id, workspace_id)
            if asset.status in ("approved", "rendered")
        ]
        operation_key = package_operation_key(batch_id, approved)
    job = ensure_job(
        db, workspace_id, kind, operation_key, batch_id=batch_id, asset_id=asset_id
    )
    db.commit()
    return job


@router.post("/render")
def render(payload: RenderStepInput, db: Session = Depends(get_db)):
    from .rendering import RendererUnavailable, RenderValidationError, render_carousel, render_clip

    asset = must_get(db, ContentAssetVersion, payload.asset_version_id, payload.workspace_id)
    if not asset.is_current or asset.status not in ("approved", "rendered"):
        raise HTTPException(409, "Current approved version required")
    decision = db.scalar(
        select(ReviewDecision).where(
            ReviewDecision.asset_version_id == asset.id,
            ReviewDecision.workspace_id == payload.workspace_id,
            ReviewDecision.decision == "approve",
            ReviewDecision.expected_hash == asset.content_hash,
        )
    )
    if not decision:
        raise HTTPException(409, "Exact asset version has no valid approval")
    if asset.warnings_json:
        raise HTTPException(409, "Asset has unresolved warnings")
    if asset.asset_type not in ("carousel", "clip"):
        raise HTTPException(422, "Only carousel and clip assets can be rendered")
    job = _job_for(db, payload.workspace_id, "render", asset_id=asset.id, batch_id=asset.batch_id)
    if job.status == "complete":
        return {"job_id": job.id, "status": job.status, "render_urls": asset.render_urls_json}
    lease_token = _claim_job(db, job)
    if not lease_token:
        return {"job_id": job.id, "status": "running"}
    batch = must_get(db, ContentBatch, asset.batch_id, payload.workspace_id)
    pinned_brand = must_get(db, BrandProfileVersion, batch.brand_profile_version_id, payload.workspace_id)
    source = must_get(db, SourceAsset, batch.source_asset_id, payload.workspace_id)
    transcript = latest_transcript(db, source)
    segments = [segment_data(s) for s in transcript_segments(db, transcript)] if transcript else []
    output_dir = get_settings().media_root.resolve() / payload.workspace_id / batch.id / asset.id / lease_token
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        if asset.asset_type == "carousel":
            result = render_carousel(asset.slides_json, asset.title, output_dir, brand=brand_data(pinned_brand))
            urls = {
                "png": [
                    f"/api/v1/assets/{asset.id}/renders/{lease_token}/{Path(path).name}"
                    for path in result["png_paths"]
                ],
                "pdf": f"/api/v1/assets/{asset.id}/renders/{lease_token}/{Path(result['pdf_path']).name}",
                "mp4": None,
            }
        else:
            if not source.media_path:
                raise ValueError("Transcript-only source has no playable media for clip rendering")
            if source.duration_ms > 0 and asset.clip_range_json.get("end_ms", 0) > source.duration_ms:
                raise ValueError("Clip range exceeds the owned recording duration")
            media = Path(source.media_path).resolve()
            media_root = (get_settings().media_root.resolve() / payload.workspace_id).resolve()
            if not media.is_relative_to(media_root) or not media.is_file():
                raise FileNotFoundError("Workspace media is unavailable")
            digest = hashlib.sha256()
            with media.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != source.sha256:
                raise ValueError("Owned recording bytes changed; restore the original source before rendering")
            result = render_clip(
                media,
                asset.clip_range_json,
                segments,
                asset.title,
                output_dir,
                asset.clip_range_json.get("aspect_ratio", "9:16"),
                brand=brand_data(pinned_brand),
            )
            urls = {
                "png": [],
                "pdf": None,
                "mp4": f"/api/v1/assets/{asset.id}/renders/{lease_token}/{Path(result['mp4_path']).name}",
            }
        result = db.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "running", Job.lease_token == lease_token)
            .values(status="complete", progress=100, result_json={"render_urls": urls})
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Render job lease was taken by another worker")
        current = db.execute(update(ContentAssetVersion).where(
            ContentAssetVersion.id == asset.id,
            ContentAssetVersion.is_current.is_(True),
            ContentAssetVersion.status.in_(["approved", "rendered"]),
            ContentAssetVersion.content_hash == asset.content_hash,
        ).values(status="rendered", render_urls_json=urls))
        if current.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Asset changed while rendering; review the current version")
        invalidate_batch_package(db, payload.workspace_id, batch.id)
        db.commit()
    except HTTPException:
        raise
    except Exception as error:
        db.rollback()
        error_message = f"{type(error).__name__}: {str(error)[:500]}"
        db.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "running", Job.lease_token == lease_token)
            .values(status="failed", error=error_message)
        )
        db.commit()
        code = 503 if isinstance(error, RendererUnavailable) else 422 if isinstance(error, RenderValidationError) else 409 if isinstance(error, (ValueError, FileNotFoundError)) else 500
        raise HTTPException(code, error_message) from error
    return {"job_id": job.id, "status": "complete", "render_urls": urls}


@router.post("/package")
def package(payload: BatchStepInput, db: Session = Depends(get_db)):
    batch = must_get(db, ContentBatch, payload.batch_id, payload.workspace_id)
    assets = [
        asset
        for asset in current_assets(db, batch.id, payload.workspace_id)
        if asset.status in ("approved", "rendered")
    ]
    if not assets:
        raise HTTPException(409, "No approved assets to package")
    approvals = {decision.asset_version_id: decision for decision in db.scalars(
        select(ReviewDecision).where(ReviewDecision.workspace_id == payload.workspace_id,
                                     ReviewDecision.asset_version_id.in_([a.id for a in assets]),
                                     ReviewDecision.decision == "approve")
    )}
    for asset in assets:
        decision = approvals.get(asset.id)
        if not decision or decision.expected_hash != asset.content_hash or asset.warnings_json:
            raise HTTPException(409, "Every packaged asset needs exact version approval without warnings")
        if asset.asset_type in ("carousel", "clip"):
            if asset.status != "rendered":
                raise HTTPException(409, "Render approved media before creating a publication package")
            try:
                render_file_paths(asset)
            except (OSError, ValueError) as error:
                raise HTTPException(409, str(error)) from error
    job = _job_for(db, payload.workspace_id, "package", batch_id=batch.id)
    if job.status == "complete":
        return {
            "job_id": job.id,
            "status": "complete",
            "download_url": f"/api/v1/batches/{batch.id}/download",
        }
    lease_token = _claim_job(db, job)
    if not lease_token:
        return {"job_id": job.id, "status": "running"}
    root = get_settings().media_root.resolve() / payload.workspace_id / batch.id
    root.mkdir(parents=True, exist_ok=True)
    destination = root / package_file_name(job.id, lease_token)
    temporary = destination.with_suffix(".tmp.zip")
    source = must_get(db, SourceAsset, batch.source_asset_id, payload.workspace_id)
    transcript = latest_transcript(db, source)
    segments = [segment_data(s) for s in transcript_segments(db, transcript)] if transcript else []
    try:
        manifest = {
            "product": "ContentStudio",
            "schema_version": 2,
            "synthetic_demo_dataset": get_settings().mode == "demo",
            "brand": brand_data(must_get(db, BrandProfileVersion, batch.brand_profile_version_id, payload.workspace_id)),
            "batch": {"id": batch.id, "recipe_version": batch.recipe_version,
                      "generation_transcript_version_id": batch.transcript_version_id},
            "source": {
                "id": source.id,
                "title": source.title,
                "rights_status": source.rights_status,
                "transcript_provenance": transcript.provenance if transcript else None,
                "transcript_version_id": transcript.id if transcript else None,
                "sha256": source.sha256,
            },
            "assets": [asset_data(a, segments) for a in assets],
            "approvals": [{"asset_version_id": a.id, "content_hash": a.content_hash,
                           "reviewer_id": approvals[a.id].user_id,
                           "decision": "approve"} for a in assets],
            "source_map": segments,
            "files": [],
        }
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for asset in assets:
                name = f"assets/{asset.asset_type}-{asset.id[:8]}.md"
                text_bytes = f"# {asset.title}\n\n{asset.text}\n".encode()
                archive.writestr(name, text_bytes)
                manifest["files"].append({"path": name, "sha256": hashlib.sha256(text_bytes).hexdigest(), "bytes": len(text_bytes)})
                for path in render_file_paths(asset):
                    name = f"renders/{asset.id[:8]}/{path.name}"
                    digest = hashlib.sha256()
                    byte_count = 0
                    with path.open("rb") as stream, archive.open(name, "w") as output:
                        while chunk := stream.read(1024 * 1024):
                            digest.update(chunk)
                            byte_count += len(chunk)
                            output.write(chunk)
                    manifest["files"].append({"path": name, "sha256": digest.hexdigest(), "bytes": byte_count})
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        temporary.replace(destination)
        download_url = f"/api/v1/batches/{batch.id}/download"
        result = db.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "running", Job.lease_token == lease_token)
            .values(
                status="complete",
                progress=100,
                result_json={"download_url": download_url, "file_name": destination.name},
            )
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Package job lease was taken by another worker")
        batch.status = "complete"
        db.commit()
    except HTTPException:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    except Exception as error:
        db.rollback()
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        error_message = f"{type(error).__name__}: {str(error)[:500]}"
        db.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "running", Job.lease_token == lease_token)
            .values(status="failed", error=error_message)
        )
        db.commit()
        raise HTTPException(500, error_message) from error
    return {"job_id": job.id, "status": "complete", "download_url": download_url}


@router.get("/due")
def due(
    workspace_id: str,
    now_override: str | None = Query(None, alias="now"),
    db: Session = Depends(get_db),
):
    must_get(db, Workspace, workspace_id, workspace_id)
    reference = _parse_now(now_override)
    items = []
    stale = reference - timedelta(minutes=10)
    jobs = db.scalars(
        select(Job).where(
            Job.workspace_id == workspace_id,
            Job.kind.in_(["render", "package"]),
            Job.status.in_(["queued", "running"]),
        )
    ).all()
    for job in jobs:
        if job.status == "running" and job.updated_at.replace(tzinfo=UTC) > stale:
            continue
        items.append(
            {
                "workspace_id": workspace_id,
                "batch_id": job.batch_id,
                "asset_version_id": job.asset_version_id,
                "channel": None,
                "operation_key": f"job:{job.id}",
                "action": job.kind,
            }
        )
    drafts = db.scalars(
        select(PublicationDraft).where(
            PublicationDraft.workspace_id == workspace_id,
            PublicationDraft.status == "draft",
        )
    ).all()
    for draft in drafts:
        scheduled = draft.scheduled_at
        if scheduled is None or scheduled.replace(tzinfo=UTC) <= reference:
            asset = must_get(db, ContentAssetVersion, draft.asset_version_id, workspace_id)
            if asset.is_current and asset.status in ("approved", "rendered"):
                items.append(
                    {
                        "workspace_id": workspace_id,
                        "batch_id": asset.batch_id,
                        "asset_version_id": asset.id,
                        "channel": draft.channel,
                        "operation_key": f"{draft.channel}:{asset.id}",
                        "action": "dispatch" if draft.channel == "wordpress" else "outbox",
                    }
                )
    return {"items": items}


@router.post("/outbox")
def prepare_outbox(payload: OutboxInput, db: Session = Depends(get_db)):
    asset = must_get(db, ContentAssetVersion, payload.asset_version_id, payload.workspace_id)
    decision = db.scalar(
        select(ReviewDecision).where(
            ReviewDecision.workspace_id == payload.workspace_id,
            ReviewDecision.asset_version_id == asset.id,
            ReviewDecision.decision == "approve",
            ReviewDecision.expected_hash == asset.content_hash,
        )
    )
    if (
        not asset.is_current
        or asset.status not in ("approved", "rendered")
        or decision is None
        or asset.warnings_json
    ):
        raise HTTPException(409, "Current asset lacks exact, warning-free approval")
    if asset.asset_type != payload.channel:
        raise HTTPException(422, "Outbox channel must match asset type")
    draft = db.scalar(
        select(PublicationDraft).where(
            PublicationDraft.workspace_id == payload.workspace_id,
            PublicationDraft.asset_version_id == asset.id,
            PublicationDraft.channel == payload.channel,
        )
    )
    if draft is None:
        raise HTTPException(409, "Schedule the asset first")
    outbound = {"title": asset.title, "content": asset.text, "status": "ready"}
    fingerprint = canonical_hash(outbound)
    existing = db.scalar(
        select(DispatchLedger).where(
            DispatchLedger.workspace_id == payload.workspace_id,
            DispatchLedger.operation_key == payload.operation_key,
        )
    )
    if existing:
        if existing.asset_version_id != asset.id or existing.payload_hash != fingerprint:
            raise HTTPException(409, "Operation key conflicts with a different payload")
        return {
            "ready": existing.status == "complete",
            "duplicate": True,
            "operation_key": existing.operation_key,
            "draft_id": draft.id,
        }
    db.add(
        DispatchLedger(
            workspace_id=payload.workspace_id,
            operation_key=payload.operation_key,
            asset_version_id=asset.id,
            channel=payload.channel,
            status="complete",
            payload_hash=fingerprint,
        )
    )
    draft.status = "ready"
    draft.payload_json = outbound
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Outbox operation already claimed") from None
    return {
        "ready": True,
        "duplicate": False,
        "operation_key": payload.operation_key,
        "draft_id": draft.id,
    }


def _wordpress_draft(asset: ContentAssetVersion) -> dict:
    escaped = html.escape(asset.text)
    paragraphs = "".join(f"<p>{line}</p>" for line in escaped.split("\n\n") if line.strip())
    slug = f"cs-{asset.id[:8]}-{asset.content_hash[:8]}"
    return {
        "title": asset.title,
        "content": paragraphs,
        "status": "draft",
        "excerpt": asset.text[:155],
        "slug": slug,
    }


@router.post("/dispatch/prepare")
def dispatch_prepare(payload: DispatchPrepareInput, db: Session = Depends(get_db)):
    asset = must_get(db, ContentAssetVersion, payload.asset_version_id, payload.workspace_id)
    decision = db.scalar(
        select(ReviewDecision).where(
            ReviewDecision.workspace_id == payload.workspace_id,
            ReviewDecision.asset_version_id == asset.id,
            ReviewDecision.decision == "approve",
            ReviewDecision.expected_hash == asset.content_hash,
        )
    )
    if (
        not asset.is_current
        or asset.status not in ("approved", "rendered")
        or decision is None
        or asset.warnings_json
    ):
        raise HTTPException(409, "Current asset lacks exact, warning-free approval")
    if asset.asset_type != "article" or payload.channel != "wordpress":
        raise HTTPException(422, "WordPress draft connector requires an article")
    draft = db.scalar(
        select(PublicationDraft).where(
            PublicationDraft.workspace_id == payload.workspace_id,
            PublicationDraft.asset_version_id == asset.id,
            PublicationDraft.channel == "wordpress",
        )
    )
    if draft is None:
        raise HTTPException(409, "Schedule the draft first")
    outbound = _wordpress_draft(asset)
    existing = db.scalar(
        select(DispatchLedger).where(
            DispatchLedger.workspace_id == payload.workspace_id,
            DispatchLedger.operation_key == payload.operation_key,
        )
    )
    if existing:
        if existing.asset_version_id != asset.id or existing.payload_hash != canonical_hash(
            outbound
        ):
            raise HTTPException(409, "Operation key conflicts with a different payload")
        return {
            "claimed": False,
            "operation_key": existing.operation_key,
            "workspace_id": payload.workspace_id,
            "channel": "wordpress",
            "status": existing.status,
            "draft": outbound,
        }
    ledger = DispatchLedger(
        workspace_id=payload.workspace_id,
        operation_key=payload.operation_key,
        asset_version_id=asset.id,
        channel="wordpress",
        status="claimed",
        payload_hash=canonical_hash(outbound),
    )
    db.add(ledger)
    draft.status = "dispatching"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Operation already claimed") from None
    return {
        "claimed": True,
        "operation_key": payload.operation_key,
        "workspace_id": payload.workspace_id,
        "channel": "wordpress",
        "draft": outbound,
    }


@router.post("/dispatch/complete")
def dispatch_complete(payload: DispatchCompleteInput, db: Session = Depends(get_db)):
    ledger = db.scalar(
        select(DispatchLedger).where(
            DispatchLedger.workspace_id == payload.workspace_id,
            DispatchLedger.operation_key == payload.operation_key,
        )
    )
    if ledger is None:
        raise HTTPException(404, "Operation not found")
    if ledger.status == "complete":
        if ledger.external_id != payload.external_id:
            raise HTTPException(409, "Different external ID for completed operation")
        return {"status": "complete", "duplicate": True, "external_id": ledger.external_id}
    ledger.status = "complete"
    ledger.external_id = payload.external_id
    draft = db.scalar(
        select(PublicationDraft).where(
            PublicationDraft.workspace_id == payload.workspace_id,
            PublicationDraft.asset_version_id == ledger.asset_version_id,
            PublicationDraft.channel == ledger.channel,
        )
    )
    if draft:
        draft.status = "created"
        draft.external_id = payload.external_id
    db.commit()
    return {"status": "complete", "duplicate": False, "external_id": payload.external_id}


@router.post("/errors")
def workflow_error(payload: WorkflowErrorInput, db: Session = Depends(get_db)):
    safe_error = re.sub(
        r"(?i)(bearer\s+|password\s*[=:]\s*|api[_-]?key\s*[=:]\s*)[^\s,;]+",
        r"\1[redacted]",
        payload.error,
    )
    if payload.workspace_id:
        must_get(db, Workspace, payload.workspace_id, payload.workspace_id)
        ledger = db.scalar(
            select(DispatchLedger).where(
                DispatchLedger.workspace_id == payload.workspace_id,
                DispatchLedger.operation_key == payload.operation_key,
            )
        )
        if ledger:
            ledger.status = "unknown" if payload.outcome == "unknown" else "failed"
            ledger.error = safe_error
    prior = db.scalar(
        select(WorkflowIncident).where(
            WorkflowIncident.workspace_id == payload.workspace_id,
            WorkflowIncident.operation_key == payload.operation_key,
        )
    )
    if not prior:
        db.add(
            WorkflowIncident(
                workspace_id=payload.workspace_id,
                operation_key=payload.operation_key,
                error=safe_error,
                outcome=payload.outcome,
            )
        )
    db.commit()
    return {"recorded": True}


@router.get("/reconcile")
def reconcile(
    workspace_id: str,
    now_override: str | None = Query(None, alias="now"),
    db: Session = Depends(get_db),
):
    must_get(db, Workspace, workspace_id, workspace_id)
    _parse_now(now_override)
    ledgers = db.scalars(
        select(DispatchLedger).where(
            DispatchLedger.workspace_id == workspace_id, DispatchLedger.status == "unknown"
        )
    ).all()
    items = []
    for ledger in ledgers:
        asset = must_get(db, ContentAssetVersion, ledger.asset_version_id, workspace_id)
        items.append(
            {
                "workspace_id": workspace_id,
                "operation_key": ledger.operation_key,
                "channel": ledger.channel,
                "slug": _wordpress_draft(asset)["slug"],
            }
        )
    return {"items": items}

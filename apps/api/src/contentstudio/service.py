"""Editorial use cases and scoped serialization shared by the portal and n8n steps."""

import re
from datetime import UTC, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .ai import generate_bundle
from .config import get_settings
from .domain import canonical_hash, content_hash, validate_asset
from .models import (
    BrandProfileVersion,
    Claim,
    ContentAssetVersion,
    ContentBatch,
    Job,
    PublicationDraft,
    Segment,
    SourceAsset,
    TranscriptVersion,
    now,
)


class GenerationInProgress(RuntimeError):
    """Another worker owns this batch's generation lease."""


class GenerationSourceChanged(RuntimeError):
    """The pinned source changed while a bundle was being generated."""


def scoped(db: Session, model, item_id: str, workspace_id: str):
    return db.scalar(select(model).where(model.id == item_id, model.workspace_id == workspace_id))


def latest_transcript(db: Session, source: SourceAsset) -> TranscriptVersion | None:
    return db.scalar(
        select(TranscriptVersion)
        .where(
            TranscriptVersion.source_asset_id == source.id,
            TranscriptVersion.workspace_id == source.workspace_id,
        )
        .order_by(TranscriptVersion.version.desc())
        .limit(1)
    )


def transcript_segments(db: Session, transcript: TranscriptVersion) -> list[Segment]:
    return list(
        db.scalars(
            select(Segment)
            .where(
                Segment.transcript_version_id == transcript.id,
                Segment.workspace_id == transcript.workspace_id,
            )
            .order_by(Segment.start_ms, Segment.id)
        )
    )


def segment_data(segment: Segment) -> dict:
    return {
        "id": segment.stable_id,
        "start_ms": segment.start_ms,
        "end_ms": segment.end_ms,
        "speaker": segment.speaker,
        "text": segment.text,
    }


def source_data(db: Session, source: SourceAsset) -> dict:
    transcript = latest_transcript(db, source)
    count = (
        db.scalar(
            select(func.count(ContentBatch.id)).where(ContentBatch.source_asset_id == source.id)
        )
        or 0
    )
    return {
        "id": source.id,
        "title": source.title,
        "kind": source.kind,
        "mime_type": source.mime_type,
        "duration_ms": source.duration_ms,
        "rights_status": source.rights_status,
        "created_at": source.created_at.isoformat(),
        "latest_transcript_version_id": transcript.id if transcript else None,
        "batch_count": count,
    }


def source_detail(db: Session, source: SourceAsset) -> dict:
    transcript = latest_transcript(db, source)
    return {
        "source": source_data(db, source),
        "transcript": {
            "id": transcript.id,
            "version": transcript.version,
            "provenance": transcript.provenance,
            "segments": [segment_data(s) for s in transcript_segments(db, transcript)],
        }
        if transcript
        else None,
        "media_url": f"/api/v1/sources/{source.id}/media" if source.media_path else None,
    }


def brand_data(brand: BrandProfileVersion) -> dict:
    return {
        "id": brand.id,
        "name": brand.name,
        "version": brand.version,
        "tone": brand.tone,
        "rules": brand.rules_json,
    }


def evidence_map(asset: ContentAssetVersion, segments: list[dict]) -> list[dict]:
    cited = [s for s in segments if s["id"] in asset.source_segment_ids]
    candidates = [part.strip() for part in re.split(r"\n\s*\n", asset.text) if part.strip()]
    candidates.extend(str(slide.get("body", "")).strip() for slide in asset.slides_json or [])
    found = []
    for text in candidates:
        if len(text) < 12:
            continue
        ids = [segment["id"] for segment in cited if text in segment["text"]]
        if ids:
            found.append({"text": text, "source_segment_ids": ids, "match": "verbatim"})
    return found


def asset_data(asset: ContentAssetVersion, segments: list[dict] | None = None) -> dict:
    return {
        "id": asset.id,
        "logical_asset_id": asset.logical_asset_id,
        "batch_id": asset.batch_id,
        "asset_type": asset.asset_type,
        "title": asset.title,
        "text": asset.text,
        "status": asset.status,
        "version": asset.version,
        "content_hash": asset.content_hash,
        "source_segment_ids": asset.source_segment_ids,
        "warnings": asset.warnings_json,
        "slides": asset.slides_json,
        "clip_range": asset.clip_range_json,
        "evidence_map": evidence_map(asset, segments or []),
        "render_urls": asset.render_urls_json or {"png": [], "pdf": None, "mp4": None},
    }


def current_assets(db: Session, batch_id: str, workspace_id: str) -> list[ContentAssetVersion]:
    return list(
        db.scalars(
            select(ContentAssetVersion)
            .where(
                ContentAssetVersion.batch_id == batch_id,
                ContentAssetVersion.workspace_id == workspace_id,
                ContentAssetVersion.is_current.is_(True),
            )
            .order_by(ContentAssetVersion.asset_type, ContentAssetVersion.created_at)
        )
    )


def render_operation_key(asset: ContentAssetVersion) -> str:
    return f"render:{asset.id}:{asset.content_hash[:24]}"


def package_operation_key(batch_id: str, assets: list[ContentAssetVersion]) -> str:
    fingerprint = [
        (asset.id, asset.content_hash, asset.status, asset.render_urls_json)
        for asset in sorted(assets, key=lambda item: item.id)
    ]
    return f"package:{batch_id}:{canonical_hash(fingerprint)[:24]}"


def package_file_name(job_id: str, lease_token: str) -> str:
    """Name immutable output by the worker claim that produced it."""
    if str(UUID(job_id)) != job_id or str(UUID(lease_token)) != lease_token:
        raise ValueError("Package job and lease must have canonical UUIDs")
    return f"pkg-{lease_token}.zip"


def package_result_path(job: Job | None) -> Path | None:
    if (
        job is None
        or job.kind != "package"
        or job.status != "complete"
        or not job.batch_id
        or not job.lease_token
    ):
        return None
    try:
        expected = package_file_name(job.id, job.lease_token)
    except ValueError:
        return None
    if (job.result_json or {}).get("file_name") != expected:
        return None
    root = (get_settings().media_root.resolve() / job.workspace_id / job.batch_id).resolve()
    path = (root / expected).resolve()
    try:
        return path if path.is_relative_to(root) and path.is_file() and path.stat().st_size > 0 else None
    except OSError:
        return None


def current_complete_package(db: Session, batch_id: str, workspace_id: str) -> Job | None:
    assets = [
        asset for asset in current_assets(db, batch_id, workspace_id)
        if asset.status in ("approved", "rendered")
    ]
    if not assets:
        return None
    return db.scalar(
        select(Job).where(
            Job.workspace_id == workspace_id,
            Job.batch_id == batch_id,
            Job.kind == "package",
            Job.operation_key == package_operation_key(batch_id, assets),
            Job.status == "complete",
        )
    )


def ensure_job(
    db: Session,
    workspace_id: str,
    kind: str,
    operation_key: str,
    *,
    batch_id: str | None = None,
    asset_id: str | None = None,
) -> Job:
    """Create once per immutable operation, including across concurrent requests."""
    query = select(Job).where(
        Job.workspace_id == workspace_id, Job.operation_key == operation_key
    )
    job = db.scalar(query)
    if job is None:
        job = Job(
            workspace_id=workspace_id,
            kind=kind,
            operation_key=operation_key,
            batch_id=batch_id,
            asset_version_id=asset_id,
            status="queued",
        )
        try:
            with db.begin_nested():
                db.add(job)
                db.flush()
        except IntegrityError:
            job = db.scalar(query)
            if job is None:
                raise
    if kind == "package" and job.status == "complete" and package_result_path(job) is None:
        job.status = "stale"
        db.flush()
    if job.status in ("failed", "cancelled", "stale"):
        db.execute(
            update(Job)
            .where(
                Job.id == job.id,
                Job.status.in_(["failed", "cancelled", "stale"]),
            )
            .values(status="queued", progress=0, error=None, result_json={}, lease_token=None)
        )
        db.refresh(job)
    return job


def claim_job(db: Session, job: Job) -> str | None:
    """Atomically claim a queued or expired job using its observed lease state."""
    if job.status == "complete":
        return None
    stale = now() - timedelta(minutes=10)
    eligible = job.status == "queued" or (
        job.status == "running" and job.updated_at.replace(tzinfo=UTC) < stale
    )
    if not eligible:
        return None
    lease_token = str(uuid4())
    result = db.execute(
        update(Job)
        .where(
            Job.id == job.id,
            Job.status == job.status,
            Job.updated_at == job.updated_at,
            Job.lease_token == job.lease_token,
        )
        .values(status="running", progress=10, updated_at=now(), lease_token=lease_token)
    )
    db.commit()
    return lease_token if result.rowcount == 1 else None


def batch_data(db: Session, batch: ContentBatch) -> dict:
    source = db.get(SourceAsset, batch.source_asset_id)
    assets = current_assets(db, batch.id, batch.workspace_id)
    transcript = latest_transcript(db, source)
    segments = [segment_data(s) for s in transcript_segments(db, transcript)] if transcript else []
    return {
        "batch": {
            "id": batch.id,
            "source_asset_id": batch.source_asset_id,
            "brand_profile_version_id": batch.brand_profile_version_id,
            "transcript_version_id": batch.transcript_version_id,
            "recipe_version": batch.recipe_version,
            "status": batch.status,
            "error": batch.error,
            "created_at": batch.created_at.isoformat(),
            "asset_count": len(assets),
        },
        "source": source_data(db, source),
        "claims": [
            {
                "id": c.id,
                "text": c.text,
                "source_segment_ids": c.source_segment_ids,
                "verification_status": c.verification_status,
            }
            for c in db.scalars(
                select(Claim).where(
                    Claim.batch_id == batch.id, Claim.workspace_id == batch.workspace_id
                )
            )
        ],
        "assets": [asset_data(a, segments) for a in assets],
    }


def create_transcript(
    db: Session, source: SourceAsset, segments: list[dict], provenance: str
) -> TranscriptVersion:
    previous = latest_transcript(db, source)
    transcript = TranscriptVersion(
        workspace_id=source.workspace_id,
        source_asset_id=source.id,
        version=(previous.version + 1 if previous else 1),
        provenance=provenance,
    )
    db.add(transcript)
    db.flush()
    for item in segments:
        db.add(
            Segment(
                workspace_id=source.workspace_id,
                transcript_version_id=transcript.id,
                stable_id=item.get("id") or str(uuid4()),
                start_ms=item["start_ms"],
                end_ms=item["end_ms"],
                speaker=item.get("speaker"),
                text=item["text"],
            )
        )
    source.duration_ms = max(source.duration_ms, max(s["end_ms"] for s in segments))
    db.flush()
    return transcript


def create_batch(
    db: Session, source: SourceAsset, brand: BrandProfileVersion, recipe_version: str
) -> tuple[ContentBatch, bool]:
    transcript = latest_transcript(db, source)
    source_hash = (
        canonical_hash([segment_data(s) for s in transcript_segments(db, transcript)])
        if transcript
        else source.sha256
    )
    existing = db.scalar(
        select(ContentBatch).where(
            ContentBatch.workspace_id == source.workspace_id,
            ContentBatch.source_hash == source_hash,
            ContentBatch.recipe_version == recipe_version,
            ContentBatch.brand_profile_version_id == brand.id,
        )
    )
    if existing:
        return existing, True
    batch = ContentBatch(
        workspace_id=source.workspace_id,
        source_asset_id=source.id,
        transcript_version_id=transcript.id if transcript else None,
        brand_profile_version_id=brand.id,
        recipe_version=recipe_version,
        source_hash=source_hash,
        status="queued",
    )
    db.add(batch)
    db.flush()
    return batch, False


def generate_for_batch(db: Session, batch: ContentBatch) -> dict:
    batch_id = batch.id
    workspace_id = batch.workspace_id
    source_id = batch.source_asset_id
    transcript_id = batch.transcript_version_id
    brand_id = batch.brand_profile_version_id
    source_hash = batch.source_hash
    if current_assets(db, batch_id, workspace_id):
        return batch_data(db, batch)
    if not transcript_id:
        raise ValueError("Batch has no transcript")
    job = ensure_job(
        db, workspace_id, "generate", f"generate:{batch_id}", batch_id=batch_id
    )
    db.commit()
    lease_token = claim_job(db, job)
    if lease_token is None:
        db.expire_all()
        if current_assets(db, batch_id, workspace_id):
            return batch_data(db, scoped(db, ContentBatch, batch_id, workspace_id))
        raise GenerationInProgress("Generation is already running for this batch")

    try:
        source = scoped(db, SourceAsset, source_id, workspace_id)
        transcript = scoped(db, TranscriptVersion, transcript_id, workspace_id)
        brand = scoped(db, BrandProfileVersion, brand_id, workspace_id)
        if source is None or transcript is None or brand is None:
            raise ValueError("Batch has missing source, transcript, or brand")
        latest = latest_transcript(db, source)
        if latest is None or latest.id != transcript_id:
            raise GenerationSourceChanged(
                "Source transcript changed; create a new batch from the latest version"
            )
        segments = [segment_data(s) for s in transcript_segments(db, transcript)]
        if not segments:
            raise ValueError("Transcript has no segments")
        brand_payload = brand_data(brand)
        prohibited = brand.rules_json.get("prohibited_phrases", [])
        db.execute(
            update(ContentBatch)
            .where(ContentBatch.id == batch_id, ContentBatch.workspace_id == workspace_id)
            .values(status="generating", error=None)
        )
        # Release source reads before the graph opens its own PostgreSQL connection.
        db.commit()
        # A recovered lease must not share checkpoint state with its old worker.
        bundle = generate_bundle(f"{batch_id}:{lease_token}", segments, brand_payload)
        claimed = db.execute(
            update(Job)
            .where(
                Job.id == job.id,
                Job.workspace_id == workspace_id,
                Job.status == "running",
                Job.lease_token == lease_token,
            )
            .values(status="complete", progress=100, updated_at=now(), error=None)
        )
        if claimed.rowcount != 1:
            db.rollback()
            raise GenerationInProgress("Generation lease was replaced")
        # Serialize finalization with source corrections, which lock the same row.
        current_source = db.scalar(
            select(SourceAsset)
            .where(SourceAsset.id == source_id, SourceAsset.workspace_id == workspace_id)
            .with_for_update()
        )
        current_batch = db.scalar(
            select(ContentBatch)
            .where(ContentBatch.id == batch_id, ContentBatch.workspace_id == workspace_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        current_transcript = latest_transcript(db, current_source) if current_source else None
        if (
            current_batch is None
            or current_transcript is None
            or current_transcript.id != transcript_id
            or current_batch.transcript_version_id != transcript_id
            or current_batch.source_asset_id != source_id
            or current_batch.brand_profile_version_id != brand_id
            or current_batch.source_hash != source_hash
        ):
            raise GenerationSourceChanged(
                "Source transcript changed during generation; create a new batch"
            )
        if current_assets(db, batch_id, workspace_id):
            db.commit()
            return batch_data(db, scoped(db, ContentBatch, batch_id, workspace_id))
        valid_segment_ids = {segment["id"] for segment in segments}
        for claim in bundle.claims:
            if not set(claim["source_segment_ids"]).issubset(valid_segment_ids):
                continue
            db.add(
                Claim(
                    workspace_id=workspace_id,
                    batch_id=batch_id,
                    text=claim["text"],
                    source_segment_ids=claim["source_segment_ids"],
                    verification_status=claim["verification_status"],
                )
            )
        for generated in bundle.assets:
            item = generated.model_dump()
            warnings = validate_asset(item, segments, prohibited)
            db.add(
                ContentAssetVersion(
                    workspace_id=workspace_id,
                    batch_id=batch_id,
                    logical_asset_id=str(uuid4()),
                    version=1,
                    asset_type=item["asset_type"],
                    title=item["title"],
                    text=item["text"],
                    slides_json=item["slides"],
                    clip_range_json=item["clip_range"],
                    source_segment_ids=item["source_segment_ids"],
                    warnings_json=warnings,
                    status="review_pending",
                    content_hash=content_hash(
                        item["title"],
                        item["text"],
                        item["slides"],
                        item["clip_range"],
                        item["source_segment_ids"],
                    ),
                    render_urls_json={"png": [], "pdf": None, "mp4": None},
                )
            )
        db.execute(
            update(ContentBatch)
            .where(ContentBatch.id == batch_id, ContentBatch.workspace_id == workspace_id)
            .values(status="review", error=None)
        )
        db.commit()
        return batch_data(db, scoped(db, ContentBatch, batch_id, workspace_id))
    except GenerationInProgress:
        db.rollback()
        raise
    except Exception as error:
        db.rollback()
        message = f"Generation failed: {type(error).__name__}: {str(error)[:300]}"
        owned = db.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "running", Job.lease_token == lease_token)
            .values(status="failed", error=message, updated_at=now())
        )
        if owned.rowcount == 1:
            db.execute(
                update(ContentBatch)
                .where(ContentBatch.id == batch_id, ContentBatch.workspace_id == workspace_id)
                .values(status="failed", error=message)
            )
            db.commit()
        else:
            db.rollback()
        raise


def new_asset_version(
    db: Session,
    asset: ContentAssetVersion,
    changes: dict,
    segments: list[dict],
    prohibited: list[str],
) -> ContentAssetVersion:
    title = changes.get("title") if changes.get("title") is not None else asset.title
    text = changes.get("text") if changes.get("text") is not None else asset.text
    slides = changes.get("slides") if changes.get("slides") is not None else asset.slides_json
    clip_range = (
        changes.get("clip_range")
        if changes.get("clip_range") is not None
        else asset.clip_range_json
    )
    source_ids = (
        changes.get("source_segment_ids")
        if changes.get("source_segment_ids") is not None
        else asset.source_segment_ids
    )
    candidate = {
        "asset_type": asset.asset_type,
        "title": title,
        "text": text,
        "slides": slides,
        "clip_range": clip_range,
        "source_segment_ids": source_ids,
    }
    updated = ContentAssetVersion(
        workspace_id=asset.workspace_id,
        batch_id=asset.batch_id,
        logical_asset_id=asset.logical_asset_id,
        version=asset.version + 1,
        asset_type=asset.asset_type,
        title=title,
        text=text,
        slides_json=slides,
        clip_range_json=clip_range,
        source_segment_ids=source_ids,
        warnings_json=validate_asset(candidate, segments, prohibited),
        status="review_pending",
        content_hash=content_hash(title, text, slides, clip_range, source_ids),
        render_urls_json={"png": [], "pdf": None, "mp4": None},
    )
    asset.is_current = False
    invalidate_asset_dependents(db, asset)
    db.add(updated)
    db.flush()
    return updated


def invalidate_batch_package(db: Session, workspace_id: str, batch_id: str) -> None:
    for job in db.scalars(
        select(Job).where(
            Job.workspace_id == workspace_id,
            Job.batch_id == batch_id,
            Job.kind == "package",
            Job.status.in_(["queued", "running", "complete"]),
        )
    ):
        job.status = "stale"
        job.result_json = {}


def invalidate_asset_dependents(db: Session, asset: ContentAssetVersion) -> None:
    invalidate_batch_package(db, asset.workspace_id, asset.batch_id)
    for draft in db.scalars(
        select(PublicationDraft).where(
            PublicationDraft.workspace_id == asset.workspace_id,
            PublicationDraft.asset_version_id == asset.id,
            PublicationDraft.status.in_(["draft", "ready", "dispatching"]),
        )
    ):
        draft.status = "stale"


def dependent_assets(
    db: Session, workspace_id: str, source_id: str, stable_segment_id: str
) -> list[ContentAssetVersion]:
    batches = list(
        db.scalars(
            select(ContentBatch.id).where(
                ContentBatch.workspace_id == workspace_id, ContentBatch.source_asset_id == source_id
            )
        )
    )
    if not batches:
        return []
    return [
        a
        for a in db.scalars(
            select(ContentAssetVersion).where(
                ContentAssetVersion.workspace_id == workspace_id,
                ContentAssetVersion.batch_id.in_(batches),
                ContentAssetVersion.is_current.is_(True),
            )
        )
        if stable_segment_id in a.source_segment_ids
    ]

import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .auth import (
    COOKIE_NAME,
    create_session,
    current_user,
    operator,
    token_hash,
    user_data,
    verify_password,
)
from .config import get_settings
from .db import get_db
from .domain import canonical_hash
from .login_throttle import login_allowed, login_failed, login_succeeded
from .models import (
    BrandProfileVersion,
    Claim,
    ContentAssetVersion,
    ContentBatch,
    Job,
    LoginSession,
    PublicationDraft,
    ReviewDecision,
    SourceAsset,
    User,
    Workspace,
)
from .n8n_status import contentstudio_pack_ready
from .schemas import (
    AssetEditInput,
    AssetOut,
    AuthOut,
    BatchDetailOut,
    BatchesOut,
    BatchInput,
    BootstrapOut,
    BrandsOut,
    CalendarOut,
    JobOut,
    LoginInput,
    ReviewInput,
    ScheduledOut,
    ScheduleInput,
    SegmentCorrectionInput,
    SourceDetailOut,
    SourcesOut,
    TranscriptSourceInput,
)
from .service import (
    asset_data,
    batch_data,
    brand_data,
    create_batch,
    create_transcript,
    current_assets,
    current_complete_package,
    dependent_assets,
    ensure_job,
    invalidate_asset_dependents,
    invalidate_batch_package,
    latest_transcript,
    new_asset_version,
    package_operation_key,
    package_result_path,
    render_operation_key,
    scoped,
    segment_data,
    source_data,
    source_detail,
    transcript_segments,
)

router = APIRouter(prefix="/api/v1")


def missing(what: str):
    raise HTTPException(404, f"{what} not found in this workspace")


def get_source(db: Session, item_id: str, user: User) -> SourceAsset:
    return scoped(db, SourceAsset, item_id, user.workspace_id) or missing("Source")


def get_batch(db: Session, item_id: str, user: User) -> ContentBatch:
    return scoped(db, ContentBatch, item_id, user.workspace_id) or missing("Batch")


def get_asset(db: Session, item_id: str, user: User) -> ContentAssetVersion:
    return scoped(db, ContentAssetVersion, item_id, user.workspace_id) or missing("Asset")


def job_data(job: Job) -> dict:
    return {
        "id": job.id,
        "job_id": job.id,
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
        "result": job.result_json,
    }


def asset_context(db: Session, asset: ContentAssetVersion):
    batch = db.get(ContentBatch, asset.batch_id)
    source = db.get(SourceAsset, batch.source_asset_id)
    transcript = latest_transcript(db, source)
    segments = [segment_data(s) for s in transcript_segments(db, transcript)] if transcript else []
    brand = db.get(BrandProfileVersion, batch.brand_profile_version_id)
    return batch, source, segments, brand


def _n8n_live() -> bool:
    settings = get_settings()
    url = settings.n8n_health_url
    if not url and settings.n8n_intake_webhook:
        url = settings.n8n_intake_webhook.split("/webhook/")[0] + "/healthz"
    if not url:
        return False
    try:
        response = httpx.get(url, timeout=2)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def _login_peer(request: Request) -> str:
    direct = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-real-ip", "")
    try:
        if ipaddress.ip_address(direct).is_private and forwarded:
            return str(ipaddress.ip_address(forwarded))
    except ValueError:
        pass
    return direct


@router.post("/auth/login", response_model=AuthOut)
def login(payload: LoginInput, response: Response, request: Request, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    peer = _login_peer(request)
    if not login_allowed(peer, email):
        raise HTTPException(429, "Too many sign-in attempts; retry in one minute", headers={"Retry-After": "60"})
    user = db.scalar(
        select(User).where(User.email == email, User.active.is_(True))
    )
    if not user or not verify_password(user.password_hash, payload.password):
        login_failed(peer, email)
        raise HTTPException(401, "Invalid credentials")
    login_succeeded(peer, email)
    token = create_session(db, user)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="strict",
        max_age=get_settings().session_hours * 3600,
        path="/",
    )
    return {"user": user_data(user), "mode": get_settings().mode}


@router.get("/auth/me", response_model=AuthOut)
def me(user: User = Depends(current_user)):
    return {"user": user_data(user), "mode": get_settings().mode}


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        session = db.get(LoginSession, token_hash(token))
        if session and session.user_id == user.id:
            db.delete(session)
            db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/bootstrap", response_model=BootstrapOut)
def bootstrap(db: Session = Depends(get_db), user: User = Depends(current_user)):
    settings = get_settings()
    n8n_live = _n8n_live()
    n8n_ready = n8n_live and contentstudio_pack_ready()
    workspace = db.get(Workspace, user.workspace_id)
    counts = {
        "sources": db.scalar(
            select(func.count(SourceAsset.id)).where(SourceAsset.workspace_id == user.workspace_id)
        )
        or 0,
        "batches": db.scalar(
            select(func.count(ContentBatch.id)).where(
                ContentBatch.workspace_id == user.workspace_id
            )
        )
        or 0,
        "review_pending": db.scalar(
            select(func.count(ContentAssetVersion.id)).where(
                ContentAssetVersion.workspace_id == user.workspace_id,
                ContentAssetVersion.is_current.is_(True),
                ContentAssetVersion.status == "review_pending",
            )
        )
        or 0,
    }
    return {
        "mode": settings.mode,
        "synthetic_demo_dataset": settings.mode == "demo",
        "workspace": {"id": workspace.id, "slug": workspace.slug, "name": workspace.name},
        "user": user_data(user),
        "stats": counts,
        "connection": {
            "n8n": "connected" if n8n_live else "disconnected",
            "n8n_intake": "connected" if n8n_ready else "disconnected",
            "model": "simulated"
            if settings.model_provider == "fixture"
            else (
                "configured" if settings.openai_api_key and settings.model_id else "disconnected"
            ),
            "transcription": "simulated"
            if settings.transcription_provider == "fixture"
            else ("configured" if settings.openai_api_key else "disconnected"),
            "wordpress": "configured" if settings.wordpress_base_url else "disconnected",
        },
    }


@router.get("/sources", response_model=SourcesOut)
def sources(db: Session = Depends(get_db), user: User = Depends(current_user)):
    records = db.scalars(
        select(SourceAsset)
        .where(SourceAsset.workspace_id == user.workspace_id)
        .order_by(SourceAsset.created_at.desc())
    ).all()
    return {"items": [source_data(db, source) for source in records]}


@router.get("/sources/{source_id}", response_model=SourceDetailOut)
def source(source_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return source_detail(db, get_source(db, source_id, user))


@router.post("/sources/transcript", status_code=201, response_model=SourceDetailOut)
def create_transcript_source(
    payload: TranscriptSourceInput, db: Session = Depends(get_db), user: User = Depends(operator)
):
    if not payload.rights_attested:
        raise HTTPException(422, "You must attest that you own or may use this source")
    segments = [segment.model_dump() for segment in payload.segments]
    if any(segments[i]["start_ms"] < segments[i - 1]["start_ms"] for i in range(1, len(segments))):
        raise HTTPException(422, "Segments must be ordered by timestamp")
    source_hash = canonical_hash(segments)
    existing = db.scalar(
        select(SourceAsset).where(
            SourceAsset.workspace_id == user.workspace_id,
            SourceAsset.sha256 == source_hash,
            SourceAsset.title == payload.title,
        )
    )
    if existing:
        return source_detail(db, existing)
    item = SourceAsset(
        workspace_id=user.workspace_id,
        title=payload.title,
        kind="transcript_fixture" if get_settings().mode == "demo" else "transcript_only",
        rights_status="attested",
        sha256=source_hash,
        duration_ms=max(s["end_ms"] for s in segments),
    )
    db.add(item)
    db.flush()
    create_transcript(db, item, segments, "manual_transcript")
    db.commit()
    return source_detail(db, item)


def _detect_media(header: bytes, filename: str) -> tuple[str, str]:
    suffix = Path(filename).suffix.lower()
    if suffix in (".mp4", ".m4a", ".mov") and b"ftyp" in header[:16]:
        return "video/mp4" if suffix != ".m4a" else "audio/mp4", suffix
    if suffix == ".mp3" and (header.startswith(b"ID3") or header[:1] == b"\xff"):
        return "audio/mpeg", suffix
    if suffix == ".wav" and header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "audio/wav", suffix
    if suffix == ".webm" and header.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm", suffix
    raise HTTPException(415, "Supported media: MP4, M4A, MOV, MP3, WAV, WebM")


def _probe_duration_ms(path: Path) -> int:
    binary = os.getenv("CONTENTSTUDIO_FFMPEG") or shutil.which("ffmpeg")
    if not binary:
        raise HTTPException(503, "FFmpeg is required to verify uploaded media duration")
    try:
        probe = subprocess.run(
            [binary, "-hide_banner", "-i", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HTTPException(503, "FFmpeg could not inspect uploaded media") from error
    metadata = probe.stderr
    duration = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", metadata)
    playable = re.search(r"Stream #\d+:\d+.*(?:Video|Audio):", metadata)
    if not duration or not playable:
        raise HTTPException(422, "Uploaded media has no playable audio/video duration")
    hours, minutes, seconds = duration.groups()
    duration_ms = round((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)
    if duration_ms <= 0:
        raise HTTPException(422, "Uploaded media duration must be greater than zero")
    return duration_ms


def _upload_limit_bytes(settings) -> int:
    configured = settings.upload_limit_mb * 1024 * 1024
    return min(configured, 25 * 1024 * 1024) if settings.transcription_provider == "openai" else configured


@router.post("/sources/upload", status_code=201, response_model=SourceDetailOut)
def upload_source(
    file: UploadFile = File(...),
    title: str = Form(...),
    rights_attested: bool = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(operator),
):
    if not rights_attested:
        raise HTTPException(422, "You must attest that you own or may use this source")
    if not 2 <= len(title) <= 250:
        raise HTTPException(422, "Title must be 2–250 characters")
    first = file.file.read(32)
    mime, suffix = _detect_media(first, file.filename or "")
    file.file.seek(0)
    settings = get_settings()
    size_limit = _upload_limit_bytes(settings)
    source_id = str(uuid4())
    destination = (
        settings.media_root.resolve() / user.workspace_id / source_id / f"original{suffix}"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    count = 0
    try:
        with destination.open("wb") as output:
            while chunk := file.file.read(1024 * 1024):
                count += len(chunk)
                if count > size_limit:
                    raise HTTPException(413, f"Media exceeds the {size_limit // (1024 * 1024)} MiB transcription limit")
                digest.update(chunk)
                output.write(chunk)
        duration_ms = _probe_duration_ms(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    existing = db.scalar(
        select(SourceAsset).where(
            SourceAsset.workspace_id == user.workspace_id,
            SourceAsset.sha256 == digest.hexdigest(),
            SourceAsset.title == title,
        )
    )
    if existing:
        destination.unlink(missing_ok=True)
        if existing.duration_ms <= 0:
            existing.duration_ms = duration_ms
            db.commit()
        return source_detail(db, existing)
    item = SourceAsset(
        id=source_id,
        workspace_id=user.workspace_id,
        title=title,
        kind="owned_media",
        rights_status="attested",
        sha256=digest.hexdigest(),
        duration_ms=duration_ms,
        media_path=str(destination),
        mime_type=mime,
    )
    db.add(item)
    db.commit()
    return source_detail(db, item)


@router.get("/sources/{source_id}/media")
def source_media(source_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = get_source(db, source_id, user)
    if not item.media_path:
        missing("Media")
    path = Path(item.media_path).resolve()
    root = (get_settings().media_root.resolve() / user.workspace_id).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        missing("Media")
    return FileResponse(
        path,
        media_type=item.mime_type
        or mimetypes.guess_type(path.name)[0]
        or "application/octet-stream",
    )


@router.patch("/sources/{source_id}/segments/{segment_id}", response_model=SourceDetailOut)
def correct_segment(
    source_id: str,
    segment_id: str,
    payload: SegmentCorrectionInput,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
):
    # Generation finalization locks this row too, so a correction either
    # invalidates a completed bundle or is observed before it is persisted.
    item = db.scalar(
        select(SourceAsset)
        .where(SourceAsset.id == source_id, SourceAsset.workspace_id == user.workspace_id)
        .with_for_update()
    ) or missing("Source")
    transcript = latest_transcript(db, item)
    if not transcript:
        missing("Transcript")
    old_segments = [segment_data(s) for s in transcript_segments(db, transcript)]
    target = next((s for s in old_segments if s["id"] == segment_id), None)
    if target is None:
        missing("Segment")
    if target["text"] == payload.text:
        return source_detail(db, item)
    updated_segments = [
        {**s, "text": payload.text if s["id"] == segment_id else s["text"]} for s in old_segments
    ]
    create_transcript(db, item, updated_segments, "manual_correction")
    for asset in dependent_assets(db, user.workspace_id, item.id, segment_id):
        asset.status = "stale"
        asset.render_urls_json = {"png": [], "pdf": None, "mp4": None}
        invalidate_asset_dependents(db, asset)
        batch = db.get(ContentBatch, asset.batch_id)
        batch.status = "review"
    batches = db.scalars(
        select(ContentBatch.id).where(
            ContentBatch.source_asset_id == item.id, ContentBatch.workspace_id == user.workspace_id
        )
    ).all()
    if batches:
        for claim in db.scalars(
            select(Claim).where(
                Claim.workspace_id == user.workspace_id, Claim.batch_id.in_(batches)
            )
        ):
            if segment_id in claim.source_segment_ids:
                claim.verification_status = "stale"
    db.commit()
    return source_detail(db, item)


@router.get("/brands", response_model=BrandsOut)
def brands(db: Session = Depends(get_db), user: User = Depends(current_user)):
    items = db.scalars(
        select(BrandProfileVersion)
        .where(BrandProfileVersion.workspace_id == user.workspace_id)
        .order_by(BrandProfileVersion.name, BrandProfileVersion.version.desc())
    ).all()
    return {"items": [brand_data(b) for b in items]}


@router.post("/sources/{source_id}/batches", status_code=202, response_model=BatchDetailOut)
def start_batch(
    source_id: str,
    payload: BatchInput,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
):
    source = get_source(db, source_id, user)
    brand = scoped(db, BrandProfileVersion, payload.brand_profile_id, user.workspace_id)
    if brand is None:
        missing("Brand")
    settings = get_settings()
    if latest_transcript(db, source) is None and (
        settings.transcription_provider != "openai" or not settings.openai_api_key
    ):
        raise HTTPException(
            409,
            "This source has no transcript; configure connected transcription before creating a batch",
        )
    batch, duplicate = create_batch(db, source, brand, payload.recipe_version)
    db.commit()
    db.refresh(batch)
    if duplicate and batch.status in ("review", "complete"):
        return batch_data(db, batch)
    if batch.status == "failed":
        db.execute(
            update(ContentBatch)
            .where(
                ContentBatch.id == batch.id,
                ContentBatch.workspace_id == user.workspace_id,
                ContentBatch.status == "failed",
            )
            .values(status="queued", error=None)
        )
        db.commit()
    if not settings.n8n_intake_webhook or not settings.service_token:
        error_message = "n8n intake webhook is not configured"
        db.execute(
            update(ContentBatch)
            .where(ContentBatch.id == batch.id, ContentBatch.status == "queued")
            .values(status="failed", error=error_message)
        )
        db.commit()
        raise HTTPException(503, error_message)
    request_id = str(uuid4())
    request_body = {
        "workspace_id": user.workspace_id,
        "source_asset_id": source.id,
        "recipe_version": payload.recipe_version,
        "brand_profile_version_id": brand.id,
        "request_id": request_id,
    }
    try:
        result = httpx.post(
            settings.n8n_intake_webhook,
            json=request_body,
            headers={"X-Service-Token": settings.service_token},
            timeout=settings.n8n_timeout_seconds,
        )
        result.raise_for_status()
    except httpx.HTTPError as error:
        error_message = f"n8n intake failed: {type(error).__name__}"
        db.execute(
            update(ContentBatch)
            .where(ContentBatch.id == batch.id, ContentBatch.status == "queued")
            .values(status="failed", error=error_message)
        )
        db.commit()
        raise HTTPException(503, error_message) from error
    db.refresh(batch)
    return batch_data(db, batch)


@router.get("/batches", response_model=BatchesOut)
def batches(db: Session = Depends(get_db), user: User = Depends(current_user)):
    items = db.scalars(
        select(ContentBatch)
        .where(ContentBatch.workspace_id == user.workspace_id)
        .order_by(ContentBatch.created_at.desc())
    ).all()
    return {"items": [batch_data(db, batch)["batch"] for batch in items]}


@router.get("/batches/{batch_id}", response_model=BatchDetailOut)
def batch(batch_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return batch_data(db, get_batch(db, batch_id, user))


@router.patch("/assets/{asset_id}", response_model=AssetOut)
def edit_asset(
    asset_id: str,
    payload: AssetEditInput,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
):
    asset = get_asset(db, asset_id, user)
    if not asset.is_current or asset.status == "stale":
        raise HTTPException(409, "Edit the current, source-valid version")
    _, _, segments, brand = asset_context(db, asset)
    if payload.clip_range:
        start, end = payload.clip_range.get("start_ms"), payload.clip_range.get("end_ms")
        if not isinstance(start, int) or not isinstance(end, int) or end <= start:
            raise HTTPException(422, "Invalid clip range")
    if payload.slides is not None and asset.asset_type != "carousel":
        raise HTTPException(422, "Slides are only valid for a carousel")
    updated = new_asset_version(
        db,
        asset,
        payload.model_dump(exclude_unset=True),
        segments,
        brand.rules_json.get("prohibited_phrases", []),
    )
    db.commit()
    return asset_data(updated, segments)


@router.post("/assets/{asset_id}/regenerate", response_model=AssetOut)
def regenerate_asset(asset_id: str, db: Session = Depends(get_db), user: User = Depends(operator)):
    from .ai import regenerate_one

    asset = get_asset(db, asset_id, user)
    if not asset.is_current:
        raise HTTPException(409, "Regenerate the current asset version")
    batch, _, segments, brand = asset_context(db, asset)
    siblings = [
        a
        for a in current_assets(db, batch.id, user.workspace_id)
        if a.asset_type == asset.asset_type
    ]
    ordinal = next((i for i, sibling in enumerate(siblings) if sibling.id == asset.id), 0)
    regenerated = regenerate_one(asset.asset_type, ordinal, segments, brand_data(brand))
    regenerated["source_segment_ids"] = [
        sid for sid in regenerated["source_segment_ids"] if sid in {s["id"] for s in segments}
    ]
    updated = new_asset_version(
        db, asset, regenerated, segments, brand.rules_json.get("prohibited_phrases", [])
    )
    db.commit()
    return asset_data(updated, segments)


@router.post("/assets/{asset_id}/review", response_model=AssetOut)
def review_asset(
    asset_id: str,
    payload: ReviewInput,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
):
    asset = get_asset(db, asset_id, user)
    if not asset.is_current or asset.status not in ("review_pending", "rejected"):
        raise HTTPException(409, "This asset version is not reviewable")
    if not secrets.compare_digest(asset.content_hash, payload.expected_hash):
        raise HTTPException(409, "Asset changed; reload before deciding")
    if payload.decision == "approve" and asset.warnings_json:
        raise HTTPException(
            409,
            {
                "message": "Resolve evidence and brand warnings before approval",
                "warnings": asset.warnings_json,
            },
        )
    if db.scalar(select(ReviewDecision.id).where(ReviewDecision.asset_version_id == asset.id)):
        raise HTTPException(409, "This version already has a review decision")
    asset.status = "approved" if payload.decision == "approve" else "rejected"
    if payload.decision == "approve":
        invalidate_batch_package(db, user.workspace_id, asset.batch_id)
    db.add(
        ReviewDecision(
            workspace_id=user.workspace_id,
            asset_version_id=asset.id,
            user_id=user.id,
            decision=payload.decision,
            expected_hash=asset.content_hash,
            reason=payload.reason,
        )
    )
    if payload.decision == "approve" and asset.asset_type in ("carousel", "clip"):
        ensure_job(
            db, user.workspace_id, "render", render_operation_key(asset),
            batch_id=asset.batch_id, asset_id=asset.id,
        )
    db.commit()
    _, _, segments, _ = asset_context(db, asset)
    return asset_data(asset, segments)


@router.post("/assets/{asset_id}/render", status_code=202, response_model=JobOut)
def request_render(asset_id: str, db: Session = Depends(get_db), user: User = Depends(operator)):
    asset = get_asset(db, asset_id, user)
    if (
        not asset.is_current
        or asset.status not in ("approved", "rendered")
        or asset.asset_type not in ("carousel", "clip")
    ):
        raise HTTPException(409, "Approve a current carousel or clip before rendering")
    job = ensure_job(
        db, user.workspace_id, "render", render_operation_key(asset),
        batch_id=asset.batch_id, asset_id=asset.id,
    )
    db.commit()
    return job_data(job)


@router.get("/assets/{asset_id}/renders/{filename}")
def rendered_file(
    asset_id: str, filename: str, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    asset = get_asset(db, asset_id, user)
    if filename != Path(filename).name or filename.startswith("."):
        missing("Rendered file")
    if not asset.is_current or asset.status != "rendered":
        missing("Rendered file")
    root = (
        get_settings().media_root.resolve() / user.workspace_id / asset.batch_id / asset.id
    ).resolve()
    path = (root / filename).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        missing("Rendered file")
    return FileResponse(path)


@router.get("/jobs/{job_id}", response_model=JobOut)
def job(job_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    record = scoped(db, Job, job_id, user.workspace_id) or missing("Job")
    return job_data(record)


@router.get("/jobs/{job_id}/events")
def job_events(job_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    scoped(db, Job, job_id, user.workspace_id) or missing("Job")
    workspace_id = user.workspace_id

    def events():
        from .db import session_factory

        for _ in range(30):
            with session_factory()() as fresh:
                latest = scoped(fresh, Job, job_id, workspace_id)
                if latest is None:
                    return
                yield f"data: {json.dumps(job_data(latest))}\n\n"
                if latest.status in ("complete", "failed", "cancelled"):
                    return
            time.sleep(2)

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(operator)):
    record = scoped(db, Job, job_id, user.workspace_id) or missing("Job")
    if record.status != "queued":
        raise HTTPException(409, "Only queued jobs can be cancelled")
    record.status = "cancelled"
    db.commit()
    return job_data(record)


@router.post("/batches/{batch_id}/package", status_code=202, response_model=JobOut)
def request_package(batch_id: str, db: Session = Depends(get_db), user: User = Depends(operator)):
    record = get_batch(db, batch_id, user)
    assets = [
        a for a in current_assets(db, record.id, user.workspace_id)
        if a.status in ("approved", "rendered")
    ]
    if not assets:
        raise HTTPException(409, "Approve at least one asset before packaging")
    job = ensure_job(
        db, user.workspace_id, "package", package_operation_key(record.id, assets),
        batch_id=record.id,
    )
    db.commit()
    return job_data(job)


@router.get("/batches/{batch_id}/download")
def download_package(
    batch_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    record = get_batch(db, batch_id, user)
    job = current_complete_package(db, record.id, user.workspace_id)
    path = package_result_path(job)
    if path is None:
        raise HTTPException(409, "Current package is not ready; request a rebuild")
    return FileResponse(
        path, filename=f"contentstudio-{record.id[:8]}.zip", media_type="application/zip"
    )


@router.post("/assets/{asset_id}/schedule", response_model=ScheduledOut)
def schedule_asset(
    asset_id: str,
    payload: ScheduleInput,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
):
    asset = get_asset(db, asset_id, user)
    if not asset.is_current or asset.status not in ("approved", "rendered"):
        raise HTTPException(409, "Approve current asset before scheduling")
    if payload.channel == "wordpress" and asset.asset_type != "article":
        raise HTTPException(422, "WordPress draft connector accepts article assets")
    if payload.channel in ("newsletter", "social") and asset.asset_type != payload.channel:
        raise HTTPException(422, "Outbox channel must match asset type")
    when = None
    if payload.scheduled_at:
        try:
            when = datetime.fromisoformat(payload.scheduled_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise HTTPException(422, "Invalid ISO 8601 schedule") from error
    existing = db.scalar(
        select(PublicationDraft).where(
            PublicationDraft.workspace_id == user.workspace_id,
            PublicationDraft.asset_version_id == asset.id,
            PublicationDraft.channel == payload.channel,
        )
    )
    if existing is None:
        existing = PublicationDraft(
            workspace_id=user.workspace_id,
            asset_version_id=asset.id,
            channel=payload.channel,
            status="draft",
            scheduled_at=when,
            payload_json={"title": asset.title, "content": asset.text},
        )
        db.add(existing)
    else:
        existing.scheduled_at = when
    db.commit()
    return {
        "id": existing.id,
        "asset_version_id": asset.id,
        "channel": existing.channel,
        "status": existing.status,
        "scheduled_at": existing.scheduled_at.isoformat() if existing.scheduled_at else None,
    }


@router.get("/calendar", response_model=CalendarOut)
def calendar(db: Session = Depends(get_db), user: User = Depends(current_user)):
    drafts = db.scalars(
        select(PublicationDraft)
        .where(PublicationDraft.workspace_id == user.workspace_id)
        .order_by(PublicationDraft.scheduled_at)
    ).all()
    return {
        "items": [
            {
                "id": d.id,
                "asset_version_id": d.asset_version_id,
                "batch_id": db.get(ContentAssetVersion, d.asset_version_id).batch_id,
                "channel": d.channel,
                "status": d.status,
                "scheduled_at": d.scheduled_at.isoformat() if d.scheduled_at else None,
                "title": db.get(ContentAssetVersion, d.asset_version_id).title,
            }
            for d in drafts
        ]
    }

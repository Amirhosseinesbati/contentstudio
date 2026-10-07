"""Idempotent synthetic demo import. No live connector requests are made here."""

import hashlib
import json
import shutil
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import get_settings
from .db import Base, engine, session_factory
from .domain import canonical_hash, content_hash
from .models import (
    BrandProfileVersion,
    ContentAssetVersion,
    ContentBatch,
    Job,
    ReviewDecision,
    SourceAsset,
    User,
    Workspace,
)
from .service import (
    create_batch,
    create_transcript,
    current_assets,
    current_complete_package,
    generate_for_batch,
    latest_transcript,
    package_result_path,
    render_file_paths,
    transcript_segments,
)


def fixed_id(kind: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"contentstudio-demo:{kind}:{key}"))


def _render_files_available(asset: ContentAssetVersion) -> bool:
    try:
        render_file_paths(asset)
        return True
    except (OSError, ValueError):
        return False


def prepare_demo_showcase(db: Session, batch: ContentBatch) -> None:
    """Prepare only the synthetic, unedited showcase; never dispatch externally."""
    if get_settings().mode != "demo":
        raise RuntimeError("Showcase preparation is available only in demo mode")
    assets = current_assets(db, batch.id, batch.workspace_id)
    if not assets or any(asset.version != 1 for asset in assets):
        return  # An editor has taken over this batch.
    if batch.status not in ("review", "demo_preparing", "complete"):
        return
    if batch.status == "review" and any(asset.status != "review_pending" for asset in assets):
        return  # Existing editorial work must remain under human control.
    if batch.status == "complete" and all(
        asset.status == "rendered" and _render_files_available(asset)
        if asset.asset_type in ("carousel", "clip")
        else asset.status == "approved"
        for asset in assets
    ):
        if package_result_path(
            current_complete_package(db, batch.id, batch.workspace_id)
        ) is not None:
            return
    if any(asset.warnings_json for asset in assets):
        raise RuntimeError("Synthetic showcase has evidence or brand warnings; fix fixtures first")
    source = db.get(SourceAsset, batch.source_asset_id)
    if any(asset.asset_type == "clip" for asset in assets) and (
        not source.media_path or not Path(source.media_path).is_file()
    ):
        raise RuntimeError("Synthetic showcase source media is missing")

    batch.status = "demo_preparing"
    db.commit()
    reviewer = db.scalar(
        select(User).where(User.workspace_id == batch.workspace_id, User.role == "admin").limit(1)
    )
    if reviewer is None:
        raise RuntimeError("Synthetic showcase needs its seeded administrator")
    for asset in assets:
        decision = db.scalar(
            select(ReviewDecision).where(ReviewDecision.asset_version_id == asset.id)
        )
        if decision is None:
            if asset.status != "review_pending":
                raise RuntimeError("Synthetic showcase has an unexpected unreviewed asset state")
            asset.status = "approved"
            db.add(
                ReviewDecision(
                    workspace_id=batch.workspace_id,
                    asset_version_id=asset.id,
                    user_id=reviewer.id,
                    decision="approve",
                    expected_hash=asset.content_hash,
                    reason="Synthetic demo preparation; no human editorial review",
                )
            )
        elif decision.decision != "approve" or decision.expected_hash != asset.content_hash:
            raise RuntimeError("Synthetic showcase approval does not match its content hash")
    db.commit()

    # Reuse the same approval, job, renderer, and package gates as n8n, without
    # making a webhook or external connector call during seed.
    from .internal_api import package, render
    from .schemas import BatchStepInput, RenderStepInput

    for asset in assets:
        if asset.asset_type not in ("carousel", "clip"):
            continue
        if asset.status == "rendered" and _render_files_available(asset):
            continue
        if asset.status == "rendered":
            asset.status = "approved"
            asset.render_urls_json = {"png": [], "pdf": None, "mp4": None}
            for job in db.scalars(
                select(Job).where(
                    Job.workspace_id == batch.workspace_id,
                    Job.asset_version_id == asset.id,
                    Job.kind == "render",
                    Job.status == "complete",
                )
            ):
                job.status = "stale"
            db.commit()
        result = render(
            RenderStepInput(workspace_id=batch.workspace_id, asset_version_id=asset.id), db
        )
        db.refresh(asset)
        if result["status"] != "complete" or not _render_files_available(asset):
            raise RuntimeError(f"Synthetic showcase render did not finish for {asset.id}")

    result = package(BatchStepInput(workspace_id=batch.workspace_id, batch_id=batch.id), db)
    if result["status"] != "complete" or package_result_path(db.get(Job, result["job_id"])) is None:
        raise RuntimeError("Synthetic showcase package did not finish")


def seed_demo(db: Session, *, generate_showcase: bool = True) -> dict:
    settings = get_settings()
    if settings.mode != "demo":
        raise RuntimeError("Demo seed may run only in MODE=demo")
    root = settings.fixtures_root.resolve()
    workspaces = {}
    for slug, name in (("studio-alpha", "Morrow Research"), ("studio-beta", "Second Studio")):
        workspace = db.scalar(select(Workspace).where(Workspace.slug == slug))
        if workspace is None:
            workspace = Workspace(id=fixed_id("workspace", slug), slug=slug, name=name)
            db.add(workspace)
        workspaces[slug] = workspace
    db.flush()
    users = [
        ("admin@studio.test", "studio-alpha", "admin"),
        ("editor@studio.test", "studio-alpha", "operator"),
        ("viewer@studio.test", "studio-alpha", "viewer"),
        ("beta-admin@studio.test", "studio-beta", "admin"),
    ]
    for email, slug, role in users:
        if not db.scalar(select(User).where(User.email == email)):
            db.add(
                User(
                    id=fixed_id("user", email),
                    workspace_id=workspaces[slug].id,
                    email=email,
                    role=role,
                    password_hash=hash_password(settings.demo_password),
                )
            )
    db.flush()
    brand_file = root / "brands.json"
    if brand_file.exists():
        for data in json.loads(brand_file.read_text(encoding="utf-8")):
            workspace = workspaces.get(data["workspace_slug"])
            if workspace is None:
                continue
            brand_id = fixed_id("brand", f"{workspace.slug}:{data['name']}:{data['version']}")
            existing_brand = db.get(BrandProfileVersion, brand_id)
            if existing_brand is None:
                db.add(
                    BrandProfileVersion(
                        id=brand_id,
                        workspace_id=workspace.id,
                        name=data["name"],
                        version=data["version"],
                        tone=data.get("tone", "Clear and precise"),
                        rules_json=data.get("rules", {}),
                    )
                )
    db.flush()
    source_lookup = {}
    source_dir = root / "sources"
    for path in sorted(source_dir.glob("*.json")) if source_dir.exists() else []:
        data = json.loads(path.read_text(encoding="utf-8"))
        workspace = workspaces.get(data["workspace_slug"])
        if workspace is None:
            continue
        source_key = data.get("source_key", path.stem)
        source_id = fixed_id("source", f"{workspace.slug}:{source_key}")
        source = db.get(SourceAsset, source_id)
        if source is None:
            source = SourceAsset(
                id=source_id,
                workspace_id=workspace.id,
                title=data["title"],
                kind=data.get("kind", "transcript_fixture"),
                rights_status=data.get("rights_status", "owned_synthetic_script"),
                duration_ms=data.get("duration_ms", 0),
                sha256=canonical_hash(data["segments"]),
            )
            db.add(source)
            db.flush()
        media_relative = data.get("media_path")
        if media_relative:
            candidate = (root / media_relative).resolve()
            if candidate.is_file() and candidate.is_relative_to(root):
                destination = (
                    settings.media_root.resolve()
                    / workspace.id
                    / source.id
                    / f"source{candidate.suffix.lower()}"
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.exists():
                    shutil.copyfile(candidate, destination)
                source.media_path = str(destination)
                source.kind = "owned_media"
                source.sha256 = hashlib.sha256(destination.read_bytes()).hexdigest()
                source.mime_type = (
                    "video/mp4" if destination.suffix.lower() == ".mp4" else "audio/mpeg"
                )
        if latest_transcript(db, source) is None:
            segments = [
                {**item, "id": fixed_id("segment", f"{source.id}:{i}")}
                for i, item in enumerate(data["segments"])
            ]
            create_transcript(db, source, segments, "synthetic_transcript_fixture")
        source_lookup[(workspace.slug, source_key)] = source
    db.flush()
    archive = root / "asset_versions.json"
    if archive.exists():
        for item in json.loads(archive.read_text(encoding="utf-8")):
            source = source_lookup.get((item["workspace_slug"], item["source_key"]))
            if source is None:
                continue
            workspace = workspaces[item["workspace_slug"]]
            brand = db.scalar(
                select(BrandProfileVersion)
                .where(BrandProfileVersion.workspace_id == workspace.id)
                .order_by(BrandProfileVersion.name)
                .limit(1)
            )
            if brand is None:
                continue
            batch, _ = create_batch(db, source, brand, "synthetic-archive-v1")
            asset_id = fixed_id("archive-asset", item["fixture_id"])
            if db.get(ContentAssetVersion, asset_id):
                continue
            transcript = latest_transcript(db, source)
            segments = transcript_segments(db, transcript)
            indices = item.get("source_segment_indices", [])
            source_ids = [segments[i].stable_id for i in indices if 0 <= i < len(segments)]
            if not source_ids:
                source_ids = [segments[0].stable_id]
            raw_status = item["status"]
            status = {
                "draft": "review_pending",
                "review": "review_pending",
                "needs_revision": "stale",
                "approved": "approved",
                "rejected": "rejected",
                "rendered": "approved",
            }.get(raw_status, "review_pending")
            warnings = (
                ["Synthetic archive state; no render output exists"]
                if raw_status == "rendered"
                else []
            )
            title = f"Synthetic {item['asset_type']} archive"
            text = item.get("text", "")
            asset = ContentAssetVersion(
                id=asset_id,
                workspace_id=workspace.id,
                batch_id=batch.id,
                logical_asset_id=fixed_id("archive-logical", item["fixture_id"]),
                version=item.get("version", 1),
                asset_type=item["asset_type"],
                title=title,
                text=text,
                source_segment_ids=source_ids,
                slides_json=[],
                clip_range_json=None,
                warnings_json=warnings,
                status=status,
                content_hash=content_hash(title, text, [], None, source_ids),
                render_urls_json={"png": [], "pdf": None, "mp4": None},
            )
            db.add(asset)
            db.flush()
            if status in ("approved", "rejected"):
                reviewer = db.scalar(
                    select(User)
                    .where(User.workspace_id == workspace.id, User.role == "admin")
                    .limit(1)
                )
                db.add(
                    ReviewDecision(
                        workspace_id=workspace.id,
                        asset_version_id=asset.id,
                        user_id=reviewer.id,
                        decision="approve" if status == "approved" else "reject",
                        expected_hash=asset.content_hash,
                        reason="Synthetic demo archive decision",
                    )
                )
            batch.status = "review"
    db.commit()
    if generate_showcase and source_lookup:
        source = source_lookup.get(("studio-alpha", "onboarding")) or next(
            iter(source_lookup.values())
        )
        brand = db.scalar(
            select(BrandProfileVersion)
            .where(BrandProfileVersion.workspace_id == source.workspace_id)
            .order_by(BrandProfileVersion.name)
            .limit(1)
        )
        batch, _ = create_batch(db, source, brand, "v1")
        db.commit()
        if not db.scalar(
            select(ContentAssetVersion.id).where(ContentAssetVersion.batch_id == batch.id).limit(1)
        ):
            generate_for_batch(db, batch)
        prepare_demo_showcase(db, batch)
    return {"workspaces": len(workspaces), "sources": len(source_lookup)}


def main() -> None:
    Base.metadata.create_all(engine())
    from .checkpoint_init import initialize_checkpoint_store

    initialize_checkpoint_store()
    with session_factory()() as db:
        print(seed_demo(db))


if __name__ == "__main__":
    main()

"""Local regressions for version pinning and durable editorial artifacts.

Render substitutes create tiny files: these tests exercise storage and approval
boundaries, not FFmpeg fidelity, model quality, or an actual n8n execution.
"""
import hashlib
import io
import json
import zipfile
from pathlib import Path

from sqlalchemy import select
from test_contentstudio import client as client  # Reuse the isolated SQLite fixture.
from test_contentstudio import create_source, login, make_bundle

from contentstudio.config import get_settings
from contentstudio.db import session_factory
from contentstudio.models import BrandProfileVersion, ContentAssetVersion, Job, SourceAsset
from contentstudio.service import render_file_paths

HEADERS = {"X-Service-Token": "test-service-token"}
RULES = {"accent": "#234567", "prohibited_phrases": ["invented certainty"], "max_social_chars": 280}


def prepared_carousel(client):
    source, bundle, payload = make_bundle(client)
    asset = next(a for a in bundle["assets"] if a["asset_type"] == "carousel")
    result = client.patch(f"/api/v1/assets/{asset['id']}", json={"slides": (asset["slides"] * 4)[:6]})
    assert result.status_code == 200, result.text
    asset = result.json()
    assert asset["warnings"] == []
    result = client.post(f"/api/v1/assets/{asset['id']}/review", json={
        "decision": "approve", "expected_hash": asset["content_hash"],
    })
    assert result.status_code == 200, result.text
    return source, bundle, payload, result.json()


def fake_carousel(slides, title, output_dir, brand=None):
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(len(slides)):
        path = output_dir / f"slide-{index + 1:02d}.png"
        path.write_bytes(b"fixture PNG")
        paths.append(str(path))
    path = output_dir / "carousel.pdf"
    path.write_bytes(b"fixture PDF")
    return {"png_paths": paths, "pdf_path": str(path)}


def run_render(client, payload, asset):
    return client.post("/internal/workflows/render", headers=HEADERS, json={
        "workspace_id": payload["workspace_id"], "asset_version_id": asset["id"],
    })


def test_brand_versions_pin_existing_batches(client):
    _, bundle, payload = make_bundle(client)
    old_id = payload["brand_profile_version_id"]
    before = next(b for b in client.get("/api/v1/brands").json()["items"] if b["id"] == old_id)
    revision = {"tone": "Measured and direct", "rules": RULES}
    result = client.put(f"/api/v1/brands/{old_id}", json=revision)
    assert result.status_code == 201, result.text
    after = result.json()
    assert after["version"] == before["version"] + 1
    assert after["id"] != old_id
    batch = client.get(f"/api/v1/batches/{bundle['batch']['id']}").json()
    assert batch["batch"]["brand_profile_version_id"] == old_id
    with session_factory()() as db:
        assert db.get(BrandProfileVersion, old_id).tone == before["tone"]
    assert client.put(f"/api/v1/brands/{old_id}", json=revision).status_code == 409
    same = client.put(f"/api/v1/brands/{after['id']}", json=revision)
    assert same.json()["id"] == after["id"]


def test_brand_authorization_and_validation(client):
    login(client)
    payload = {"name": "Client Studio", "tone": "Careful and practical", "rules": RULES}
    created = client.post("/api/v1/brands", json=payload)
    assert created.status_code == 201, created.text
    assert client.post("/api/v1/brands", json={**payload, "name": "client studio"}).status_code == 409
    assert client.post("/api/v1/brands", json={**payload, "name": "Another", "rules": {"accent": "url(secret)"}}).status_code == 422
    assert client.post("/api/v1/brands", json={**payload, "name": "Another", "rules": {"max_social_chars": 700}}).status_code == 422
    login(client, "viewer@studio.test")
    assert client.post("/api/v1/brands", json=payload).status_code == 403
    assert client.put(f"/api/v1/brands/{created.json()['id']}", json={"tone": "New tone", "rules": RULES}).status_code == 403
    login(client, "beta-admin@studio.test")
    assert client.put(f"/api/v1/brands/{created.json()['id']}", json={"tone": "New tone", "rules": RULES}).status_code == 404


def test_transcript_stale_editor_and_blank_input(client):
    login(client)
    source = create_source(client)
    path = f"/api/v1/sources/{source['source']['id']}/segments/{source['transcript']['segments'][0]['id']}"
    correction = {"text": "Corrected source context.", "expected_transcript_id": source["transcript"]["id"]}
    assert client.patch(path, json=correction).status_code == 200
    assert client.patch(path, json={**correction, "text": "Overwrite from old editor"}).status_code == 409
    assert client.patch(path, json={"text": "   "}).status_code == 422


def test_edit_evidence_and_shape_boundaries(client):
    _, bundle, _ = make_bundle(client)
    asset = next(a for a in bundle["assets"] if a["asset_type"] == "social")
    path = f"/api/v1/assets/{asset['id']}"
    assert client.patch(path, json={"expected_hash": "0" * 64, "text": asset["text"]}).status_code == 409
    assert client.patch(path, json={"clip_range": {}}).status_code == 422
    assert client.patch(path, json={"source_segment_ids": ["unknown"]}).status_code == 422
    updated = client.patch(path, json={"source_segment_ids": asset["source_segment_ids"], "expected_hash": asset["content_hash"]})
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    assert client.patch(path, json={"text": "Old editor"}).status_code == 409
    clip = next(a for a in bundle["assets"] if a["asset_type"] == "clip")
    assert client.patch(f"/api/v1/assets/{clip['id']}", json={"clip_range": {}}).status_code == 422
    assert client.patch(f"/api/v1/assets/{clip['id']}", json={"clip_range": {"start_ms": True, "end_ms": 30000}}).status_code == 422


def test_render_recovery_and_package_manifest(client, monkeypatch):
    _, bundle, payload, asset = prepared_carousel(client)
    monkeypatch.setattr("contentstudio.rendering.render_carousel", fake_carousel)
    rendered = run_render(client, payload, asset)
    assert rendered.status_code == 200, rendered.text
    urls = rendered.json()["render_urls"]
    assert client.get(urls["png"][0]).status_code == 200
    # Internal subtitle/title-card/temp files are never exposed by arbitrary filename.
    assert client.get(urls["pdf"].replace("carousel.pdf", "title-card.png")).status_code == 404
    packaged = client.post("/internal/workflows/package", headers=HEADERS, json={
        "workspace_id": payload["workspace_id"], "batch_id": bundle["batch"]["id"],
    })
    assert packaged.status_code == 200, packaged.text
    downloaded = client.get(packaged.json()["download_url"])
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema_version"] == 2
        assert manifest["brand"]["id"] == payload["brand_profile_version_id"]
        assert manifest["approvals"][0]["content_hash"] == asset["content_hash"]
        assert len(manifest["files"]) == 8
        for file in manifest["files"]:
            assert hashlib.sha256(archive.read(file["path"])).hexdigest() == file["sha256"]
    with session_factory()() as db:
        render_file_paths(db.get(ContentAssetVersion, asset["id"]))[-1].unlink()
    assert client.post("/internal/workflows/package", headers=HEADERS, json={
        "workspace_id": payload["workspace_id"], "batch_id": bundle["batch"]["id"],
    }).status_code == 409
    queued = client.post(f"/api/v1/assets/{asset['id']}/render")
    assert queued.status_code == 202 and queued.json()["status"] == "queued"
    assert client.get(packaged.json()["download_url"]).status_code == 409
    recovered = run_render(client, payload, asset)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["render_urls"] != urls
    assert client.get(urls["png"][0]).status_code == 404


def test_correction_during_render_invalidates_worker(client, monkeypatch):
    source, _, payload, asset = prepared_carousel(client)
    def interrupted(*args, **kwargs):
        result = fake_carousel(*args, **kwargs)
        segment = source["transcript"]["segments"][0]
        correction = client.patch(f"/api/v1/sources/{source['source']['id']}/segments/{segment['id']}", json={"text": "A corrected explanation with the complete context."})
        assert correction.status_code == 200, correction.text
        return result
    monkeypatch.setattr("contentstudio.rendering.render_carousel", interrupted)
    result = run_render(client, payload, asset)
    assert result.status_code == 409, result.text
    with session_factory()() as db:
        assert db.get(ContentAssetVersion, asset["id"]).status == "stale"
        assert db.scalar(select(Job).where(Job.asset_version_id == asset["id"], Job.kind == "render")).status == "stale"


def test_package_rejects_unrendered_media_and_fake_approval(client):
    _, bundle, payload, asset = prepared_carousel(client)
    package_payload = {"workspace_id": payload["workspace_id"], "batch_id": bundle["batch"]["id"]}
    assert client.post("/internal/workflows/package", headers=HEADERS, json=package_payload).status_code == 409
    other = next(a for a in bundle["assets"] if a["asset_type"] == "article")
    with session_factory()() as db:
        db.get(ContentAssetVersion, asset["id"]).status = "rejected"
        db.get(ContentAssetVersion, other["id"]).status = "approved"
        db.commit()
    assert client.post("/internal/workflows/package", headers=HEADERS, json=package_payload).status_code == 409


def test_duplicate_upload_restores_missing_source(client, monkeypatch):
    login(client)
    monkeypatch.setattr("contentstudio.public_api._probe_duration_ms", lambda path: 60000)
    content = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"fixture media"
    def upload():
        return client.post("/api/v1/sources/upload", data={"title": "Owned source", "rights_attested": "true"}, files={"file": ("source.wav", content, "audio/wav")})
    first = upload()
    assert first.status_code == 201, first.text
    source_id = first.json()["source"]["id"]
    with session_factory()() as db:
        Path(db.get(SourceAsset, source_id).media_path).unlink()
    assert client.get(f"/api/v1/sources/{source_id}").json()["media_status"] == "missing"
    restored = upload()
    assert restored.status_code == 201 and restored.json()["source"]["id"] == source_id
    assert restored.json()["media_status"] == "available"
    assert client.get(restored.json()["media_url"]).content == content


def test_changed_recording_cannot_render_cited_transcript(client, monkeypatch):
    source, bundle, payload = make_bundle(client)
    clip = next(a for a in bundle["assets"] if a["asset_type"] == "clip")
    assert clip["warnings"] == []
    approved = client.post(f"/api/v1/assets/{clip['id']}/review", json={
        "decision": "approve", "expected_hash": clip["content_hash"],
    })
    assert approved.status_code == 200, approved.text
    root = get_settings().media_root / payload["workspace_id"] / source["source"]["id"]
    root.mkdir(parents=True, exist_ok=True)
    media = root / "source.mp4"
    media.write_bytes(b"A different recording than the approved source")
    with session_factory()() as db:
        item = db.get(SourceAsset, source["source"]["id"])
        item.media_path = str(media)
        item.sha256 = "1" * 64
        db.commit()
    def should_not_render(*args, **kwargs):
        raise AssertionError("Changed recording must be blocked before the renderer")
    monkeypatch.setattr("contentstudio.rendering.render_clip", should_not_render)
    rejected = run_render(client, payload, clip)
    assert rejected.status_code == 409
    assert "recording bytes changed" in rejected.text


def test_source_change_during_regeneration_discards_work(client, monkeypatch):
    source, bundle, _ = make_bundle(client)
    article = next(a for a in bundle["assets"] if a["asset_type"] == "article")
    def interrupted(*args, **kwargs):
        segment = source["transcript"]["segments"][0]
        corrected = client.patch(f"/api/v1/sources/{source['source']['id']}/segments/{segment['id']}", json={"text": "Updated source context for the current review."})
        assert corrected.status_code == 200, corrected.text
        return {"title": article["title"], "text": article["text"], "source_segment_ids": article["source_segment_ids"]}
    monkeypatch.setattr("contentstudio.ai.regenerate_one", interrupted)
    result = client.post(f"/api/v1/assets/{article['id']}/regenerate")
    assert result.status_code == 409, result.text
    with session_factory()() as db:
        assert db.get(ContentAssetVersion, article["id"]).is_current
        assert db.get(ContentAssetVersion, article["id"]).status == "stale"


def test_jobs_survive_reload_and_respect_workspace_roles(client):
    _, bundle, payload, asset = prepared_carousel(client)
    path = f"/api/v1/jobs?batch_id={bundle['batch']['id']}"
    records = client.get(path)
    assert records.status_code == 200, records.text
    render_job = next(job for job in records.json()["items"] if job["kind"] == "render")
    assert render_job["asset_version_id"] == asset["id"]
    assert render_job["batch_id"] == bundle["batch"]["id"]
    assert render_job["updated_at"]
    login(client, "viewer@studio.test")
    assert client.get(path).status_code == 200
    assert client.post(f"/api/v1/jobs/{render_job['id']}/cancel").status_code == 403
    login(client, "beta-admin@studio.test")
    assert client.get(path).status_code == 404
    assert render_job["id"] not in {job["id"] for job in client.get("/api/v1/jobs").json()["items"]}
    login(client)
    cancelled = client.post(f"/api/v1/jobs/{render_job['id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    events = client.get(f"/api/v1/jobs/{render_job['id']}/events")
    assert events.status_code == 200 and '"status": "cancelled"' in events.text
    retry = client.post(f"/api/v1/assets/{asset['id']}/render")
    assert retry.status_code == 202 and retry.json()["id"] == render_job["id"]
    assert retry.json()["status"] == "queued"

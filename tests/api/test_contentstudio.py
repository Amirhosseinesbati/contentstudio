import json
import zipfile
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from contentstudio.ai import generate_bundle
from contentstudio.bootstrap_admin import bootstrap as bootstrap_admin
from contentstudio.checkpoint_init import initialize_checkpoint_store
from contentstudio.config import get_settings
from contentstudio.db import Base, engine, session_factory
from contentstudio.domain import validate_asset
from contentstudio.internal_api import _claim_job
from contentstudio.internal_api import package as package_step
from contentstudio.main import app
from contentstudio.models import (
    BrandProfileVersion,
    Claim,
    ContentAssetVersion,
    ContentBatch,
    InstallationBootstrap,
    Job,
    SourceAsset,
    User,
    Workspace,
    now,
)
from contentstudio.public_api import _upload_limit_bytes
from contentstudio.schemas import BatchStepInput
from contentstudio.seed import seed_demo
from contentstudio.service import (
    GenerationInProgress,
    GenerationSourceChanged,
    claim_job,
    current_complete_package,
    ensure_job,
    generate_for_batch,
    invalidate_batch_package,
    package_file_name,
    package_result_path,
    render_file_paths,
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    monkeypatch.setenv("MODE", "demo")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("FIXTURES_ROOT", str(fixtures))
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.setenv("SERVICE_TOKEN", "test-service-token")
    monkeypatch.setenv("DEMO_PASSWORD", "DemoStudio!2026")
    monkeypatch.setenv("MODEL_PROVIDER", "fixture")
    get_settings.cache_clear()
    engine.cache_clear()
    session_factory.cache_clear()
    with TestClient(app) as test_client:
        with session_factory()() as db:
            workspace = db.scalar(select(Workspace).where(Workspace.slug == "studio-alpha"))
            db.add(
                BrandProfileVersion(
                    workspace_id=workspace.id,
                    name="Test Brand",
                    version=1,
                    tone="Precise",
                    rules_json={"prohibited_phrases": ["guaranteed result"]},
                )
            )
            db.commit()
        yield test_client
    engine().dispose()
    get_settings.cache_clear()
    engine.cache_clear()
    session_factory.cache_clear()


def login(client: TestClient, email: str = "editor@studio.test"):
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "DemoStudio!2026"}
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def create_source(client: TestClient):
    response = client.post(
        "/api/v1/sources/transcript",
        json={
            "title": "Evidence workshop",
            "rights_attested": True,
            "segments": [
                {
                    "start_ms": 0,
                    "end_ms": 30000,
                    "speaker": "Host",
                    "text": "The first example includes 12 careful steps. Each step has an owner and a documented source.",
                },
                {
                    "start_ms": 30000,
                    "end_ms": 60000,
                    "speaker": "Host",
                    "text": "The second example includes 18 reviews. Reviewers should preserve context and show uncertainties.",
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def brand_id(client: TestClient):
    brands = client.get("/api/v1/brands").json()["items"]
    return brands[0]["id"]


def make_bundle(client: TestClient):
    user = login(client)
    source = create_source(client)
    workspace_id = user["workspace_id"]
    payload = {
        "workspace_id": workspace_id,
        "source_asset_id": source["source"]["id"],
        "brand_profile_version_id": brand_id(client),
        "recipe_version": "test-v1",
        "request_id": "request-one",
    }
    headers = {"X-Service-Token": "test-service-token"}
    intake = client.post("/internal/workflows/intake", headers=headers, json=payload)
    assert intake.status_code == 200, intake.text
    batch_id = intake.json()["batch_id"]
    transcribed = client.post(
        "/internal/workflows/transcribe",
        headers=headers,
        json={"workspace_id": workspace_id, "batch_id": batch_id},
    )
    assert transcribed.status_code == 200, transcribed.text
    generated = client.post(
        "/internal/workflows/generate",
        headers=headers,
        json={"workspace_id": workspace_id, "batch_id": batch_id},
    )
    assert generated.status_code == 200, generated.text
    return source, generated.json(), payload


def pending_generation(client: TestClient, recipe_version: str) -> tuple[str, str]:
    user = login(client)
    source = create_source(client)["source"]
    headers = {"X-Service-Token": "test-service-token"}
    intake = client.post(
        "/internal/workflows/intake",
        headers=headers,
        json={
            "workspace_id": user["workspace_id"],
            "source_asset_id": source["id"],
            "brand_profile_version_id": brand_id(client),
            "recipe_version": recipe_version,
            "request_id": recipe_version,
        },
    )
    assert intake.status_code == 200, intake.text
    batch_id = intake.json()["batch_id"]
    transcribed = client.post(
        "/internal/workflows/transcribe",
        headers=headers,
        json={"workspace_id": user["workspace_id"], "batch_id": batch_id},
    )
    assert transcribed.status_code == 200, transcribed.text
    return user["workspace_id"], batch_id


def test_demo_intake_accepts_owned_synthetic_media(client: TestClient):
    user = login(client)
    source = create_source(client)["source"]
    with session_factory()() as db:
        db.get(SourceAsset, source["id"]).rights_status = "owned_synthetic_media"
        db.commit()
    response = client.post(
        "/internal/workflows/intake",
        headers={"X-Service-Token": "test-service-token"},
        json={
            "workspace_id": user["workspace_id"],
            "source_asset_id": source["id"],
            "brand_profile_version_id": brand_id(client),
            "recipe_version": "synthetic-media-v1",
            "request_id": "synthetic-media-intake",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["duplicate"] is False


def test_evidence_validator_rejects_quote_number_and_cut_context():
    segments = [
        {"id": "s1", "start_ms": 0, "end_ms": 30000, "text": "The pilot measured 12 careful steps."}
    ]
    asset = {
        "asset_type": "clip",
        "title": "A 42 percent improvement",
        "text": "She said “the pilot is perfect”.",
        "source_segment_ids": ["s1"],
        "clip_range": {"start_ms": 5000, "end_ms": 30000},
    }
    warnings = validate_asset(asset, segments)
    assert any("Number lacks" in item for item in warnings)
    assert any("Quote not found" in item for item in warnings)
    assert any("cuts through" in item for item in warnings)


def test_article_and_newsletter_length_and_paragraph_policy():
    segments = [
        {"id": "s1", "text": "source " * 400},
        {"id": "s2", "text": "source " * 400},
    ]
    base = {"title": "Source-backed draft", "source_segment_ids": ["s1", "s2"]}
    for kind, minimum, maximum in (("article", 700, 1000), ("newsletter", 250, 450)):
        first = minimum // 2
        valid = "draft " * first + "\n\n" + "draft " * (minimum - first)
        asset = base | {"asset_type": kind, "text": valid}
        assert validate_asset(asset, segments) == []
        assert any(
            "too short" in warning
            for warning in validate_asset(asset | {"text": valid.rsplit("draft", 1)[0]}, segments)
        )
        assert any(
            f"exceeds {maximum} words" in warning
            for warning in validate_asset(asset | {"text": "draft " * (maximum + 1)}, segments)
        )
        assert any(
            "at least two paragraphs" in warning
            for warning in validate_asset(asset | {"text": "draft " * minimum}, segments)
        )


def test_social_format_and_short_source_length_policy():
    segments = [{"id": "s1", "text": "A concise source statement."}]
    base = {"title": "Field note", "source_segment_ids": ["s1"]}
    assert validate_asset(base | {"asset_type": "social", "text": "A concise post."}, segments) == []
    assert any(
        "nonempty body" in warning
        for warning in validate_asset(base | {"asset_type": "social", "text": " "}, segments)
    )
    long_post = "post " * 101
    long_warnings = validate_asset(base | {"asset_type": "social", "text": long_post}, segments)
    assert any("500 characters" in warning for warning in long_warnings)
    assert any("100 words" in warning for warning in long_warnings)
    for kind in ("article", "newsletter"):
        assert validate_asset(
            base | {"asset_type": kind, "text": "A concise source statement."}, segments
        ) == []


def test_short_source_floor_uses_cited_spans_for_each_draft():
    segments = [
        {"id": "s1", "text": "source " * 120},
        {"id": "s2", "text": "source " * 40},
    ]
    article = {
        "asset_type": "article", "title": "Short source article",
        "source_segment_ids": ["s1"], "text": "draft " * 60 + "\n\n" + "draft " * 60,
    }
    assert validate_asset(article, segments) == []
    assert any(
        "too short" in warning
        for warning in validate_asset(article | {"text": "draft " * 119}, segments)
    )
    newsletter = {
        "asset_type": "newsletter", "title": "Short source newsletter",
        "source_segment_ids": ["s2"], "text": "draft " * 20 + "\n\n" + "draft " * 20,
    }
    assert validate_asset(newsletter, segments) == []


def test_generated_short_transcript_drafts_remain_approvable(client: TestClient):
    _, bundle, _ = make_bundle(client)
    drafts = [
        asset for asset in bundle["assets"]
        if asset["asset_type"] in {"article", "newsletter", "social"}
    ]
    assert len(drafts) == 7
    assert all(asset["warnings"] == [] for asset in drafts)


def test_carousel_slide_evidence_is_checked_against_its_own_citations():
    segments = [
        {"id": "s1", "start_ms": 0, "end_ms": 30000, "text": "The first pilot measured 12 careful steps."},
        {"id": "s2", "start_ms": 30000, "end_ms": 60000, "text": "The second pilot measured 18 careful steps."},
    ]
    asset = {
        "asset_type": "carousel",
        "title": "Pilot findings",
        "text": "",
        "source_segment_ids": ["s1", "s2"],
        "slides": [
            {"heading": "18 careful steps", "body": "The second pilot", "source_segment_ids": ["s1"]},
            {"heading": "Finding", "body": "Detail", "source_segment_ids": ["missing"]},
            *[
                {"heading": "Finding", "body": "Detail", "source_segment_ids": ["s1"]}
                for _ in range(4)
            ],
        ],
    }
    warnings = validate_asset(asset, segments)
    assert any("Slide 1 number lacks" in warning for warning in warnings)
    assert any("Slide 2 has unknown" in warning for warning in warnings)


def test_connected_bootstrap_creates_only_one_admin(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MODE", "connected")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'bootstrap.db').as_posix()}")
    get_settings.cache_clear()
    engine.cache_clear()
    session_factory.cache_clear()
    Base.metadata.create_all(engine())
    try:
        created = bootstrap_admin("Owner@Example.test", "customer-one", "Customer One", "InitialPass12345")
        assert created == {"email": "owner@example.test", "workspace_slug": "customer-one"}
        with session_factory()() as db:
            assert db.get(InstallationBootstrap, 1) is not None
            owner = db.scalar(select(User).where(User.email == "owner@example.test"))
            assert owner is not None and owner.role == "admin" and owner.password_hash != "InitialPass12345"
        with pytest.raises(RuntimeError, match="already contains"):
            bootstrap_admin("Other@Example.test", "customer-two", "Customer Two", "AnotherPass12345")
    finally:
        engine().dispose()
        get_settings.cache_clear()
        engine.cache_clear()
        session_factory.cache_clear()


def test_openai_upload_cap_is_never_higher_than_provider_limit(monkeypatch):
    settings = get_settings()
    original_provider, original_limit = settings.transcription_provider, settings.upload_limit_mb
    try:
        settings.transcription_provider = "openai"
        settings.upload_limit_mb = 250
        assert _upload_limit_bytes(settings) == 25 * 1024 * 1024
        settings.upload_limit_mb = 8
        assert _upload_limit_bytes(settings) == 8 * 1024 * 1024
    finally:
        settings.transcription_provider = original_provider
        settings.upload_limit_mb = original_limit


def test_checkpoint_setup_runs_at_init_not_during_graph_invocation(monkeypatch):
    from langgraph.checkpoint.postgres import PostgresSaver

    settings = get_settings()
    previous_url = settings.database_url
    calls = {"setup": 0, "invoke": 0}

    class Saver:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def setup(self):
            calls["setup"] += 1

    class Graph:
        def compile(self, checkpointer=None):
            assert isinstance(checkpointer, Saver)
            return self

        def invoke(self, state, config):
            calls["invoke"] += 1
            return {"claims": [], "assets": []}

    try:
        settings.database_url = "postgresql+psycopg://fixture/isolated"
        monkeypatch.setattr(PostgresSaver, "from_conn_string", lambda uri: Saver())
        monkeypatch.setattr("contentstudio.ai.build_graph", lambda: Graph())
        initialize_checkpoint_store()
        generated = generate_bundle("thread-id", [], {})
        assert generated.assets == []
        assert calls == {"setup": 1, "invoke": 1}
    finally:
        settings.database_url = previous_url


def test_upload_persists_probed_duration(client: TestClient, monkeypatch):
    login(client)
    monkeypatch.setattr("contentstudio.public_api._probe_duration_ms", lambda path: 59_000)
    response = client.post(
        "/api/v1/sources/upload",
        data={"title": "A verified upload", "rights_attested": "true"},
        files={"file": ("talk.mp4", b"\x00\x00\x00\x18ftypisom" + b"example", "video/mp4")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["source"]["duration_ms"] == 59_000


def test_demo_upload_without_transcript_cannot_queue_batch(client: TestClient, monkeypatch):
    login(client)
    monkeypatch.setattr("contentstudio.public_api._probe_duration_ms", lambda path: 59_000)
    uploaded = client.post(
        "/api/v1/sources/upload",
        data={"title": "Untranscribed demo talk", "rights_attested": "true"},
        files={"file": ("talk.mp4", b"\x00\x00\x00\x18ftypisom" + b"example", "video/mp4")},
    )
    assert uploaded.status_code == 201, uploaded.text
    source_id = uploaded.json()["source"]["id"]
    started = client.post(
        f"/api/v1/sources/{source_id}/batches",
        json={"brand_profile_id": brand_id(client), "recipe_version": "demo-untranscribed-v1"},
    )
    assert started.status_code == 409
    assert "no transcript" in started.json()["detail"]
    with session_factory()() as db:
        assert db.scalar(select(ContentBatch.id).where(ContentBatch.source_asset_id == source_id)) is None


def test_start_batch_does_not_overwrite_workflow_review_status(client: TestClient, monkeypatch):
    login(client)
    source = create_source(client)
    settings = get_settings()
    settings.n8n_intake_webhook = "http://n8n.test/webhook/contentstudio/intake"

    def callback(*args, **kwargs):
        with session_factory()() as db:
            batch = db.scalar(select(ContentBatch).where(ContentBatch.source_asset_id == source["source"]["id"]))
            assert batch is not None
            batch.status = "review"
            db.commit()

        class Accepted:
            def raise_for_status(self):
                pass

        return Accepted()

    monkeypatch.setattr("contentstudio.public_api.httpx.post", callback)
    response = client.post(
        f"/api/v1/sources/{source['source']['id']}/batches",
        json={"brand_profile_id": brand_id(client), "recipe_version": "race-v1"},
    )
    assert response.status_code == 202, response.text
    assert response.json()["batch"]["status"] == "review"


def test_stale_worker_claim_and_duplicate_job_are_single_winner(client: TestClient):
    user = login(client)
    with session_factory()() as db:
        first = ensure_job(db, user["workspace_id"], "render", "render:race-test")
        again = ensure_job(db, user["workspace_id"], "render", "render:race-test")
        assert first.id == again.id
        first.status = "running"
        first.updated_at = now() - timedelta(minutes=11)
        db.commit()
        observed = Job(id=first.id, status="running", updated_at=first.updated_at, lease_token=None)
    with session_factory()() as db:
        winner = _claim_job(db, observed)
    with session_factory()() as db:
        loser = _claim_job(db, observed)
        current = db.get(Job, observed.id)
    assert winner is not None
    assert loser is None
    assert current.lease_token == winner and current.status == "running"


def test_generation_lease_blocks_concurrent_request_and_replay_is_idempotent(
    client: TestClient, monkeypatch
):
    workspace_id, batch_id = pending_generation(client, "generate-concurrent-v1")
    concurrent_statuses = []

    def generate_while_competing(thread_id, segments, brand):
        contender = client.post(
            "/internal/workflows/generate",
            headers={"X-Service-Token": "test-service-token"},
            json={"workspace_id": workspace_id, "batch_id": batch_id},
        )
        concurrent_statuses.append(contender.status_code)
        return generate_bundle(thread_id, segments, brand)

    monkeypatch.setattr("contentstudio.service.generate_bundle", generate_while_competing)
    with session_factory()() as db:
        first = generate_for_batch(db, db.get(ContentBatch, batch_id))
    assert concurrent_statuses == [409]
    assert first["batch"]["status"] == "review"
    assert len(first["assets"]) == 11
    replay = client.post(
        "/internal/workflows/generate",
        headers={"X-Service-Token": "test-service-token"},
        json={"workspace_id": workspace_id, "batch_id": batch_id},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["batch"]["status"] == "review"
    assert {asset["id"] for asset in replay.json()["assets"]} == {
        asset["id"] for asset in first["assets"]
    }
    repeated_transcription = client.post(
        "/internal/workflows/transcribe",
        headers={"X-Service-Token": "test-service-token"},
        json={"workspace_id": workspace_id, "batch_id": batch_id},
    )
    assert repeated_transcription.status_code == 200
    assert client.get(f"/api/v1/batches/{batch_id}").json()["batch"]["status"] == "review"
    with session_factory()() as db:
        jobs = list(db.scalars(select(Job).where(Job.batch_id == batch_id, Job.kind == "generate")))
        assets = list(db.scalars(select(ContentAssetVersion).where(ContentAssetVersion.batch_id == batch_id)))
    assert len(jobs) == 1 and jobs[0].status == "complete"
    assert len(assets) == 11


def test_expired_generation_worker_cannot_persist_after_lease_takeover(
    client: TestClient, monkeypatch
):
    _, batch_id = pending_generation(client, "generate-stale-v1")
    replacement_leases = []

    def generate_after_takeover(thread_id, segments, brand):
        with session_factory()() as db:
            job = db.scalar(select(Job).where(Job.batch_id == batch_id, Job.kind == "generate"))
            old_lease = job.lease_token
            job.updated_at = now() - timedelta(minutes=11)
            db.commit()
            observed = Job(
                id=job.id,
                status="running",
                updated_at=job.updated_at,
                lease_token=old_lease,
            )
        with session_factory()() as db:
            replacement = claim_job(db, observed)
        assert replacement is not None and replacement != old_lease
        replacement_leases.append(replacement)
        return generate_bundle(thread_id, segments, brand)

    monkeypatch.setattr("contentstudio.service.generate_bundle", generate_after_takeover)
    with session_factory()() as db, pytest.raises(
        GenerationInProgress, match="lease was replaced"
    ):
        generate_for_batch(db, db.get(ContentBatch, batch_id))
    assert len(replacement_leases) == 1
    with session_factory()() as db:
        job = db.scalar(select(Job).where(Job.batch_id == batch_id, Job.kind == "generate"))
        assert job.status == "running" and job.lease_token == replacement_leases[0]
        assert db.get(ContentBatch, batch_id).status == "generating"
        assert list(db.scalars(select(ContentAssetVersion).where(ContentAssetVersion.batch_id == batch_id))) == []
        assert list(db.scalars(select(Claim).where(Claim.batch_id == batch_id))) == []


def test_failed_generation_job_can_retry_without_duplicate_bundle(
    client: TestClient, monkeypatch
):
    workspace_id, batch_id = pending_generation(client, "generate-retry-v1")
    attempts = 0

    def fail_once(thread_id, segments, brand):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary model failure")
        return generate_bundle(thread_id, segments, brand)

    monkeypatch.setattr("contentstudio.service.generate_bundle", fail_once)
    headers = {"X-Service-Token": "test-service-token"}
    payload = {"workspace_id": workspace_id, "batch_id": batch_id}
    first = client.post("/internal/workflows/generate", headers=headers, json=payload)
    assert first.status_code == 502
    with session_factory()() as db:
        job = db.scalar(select(Job).where(Job.batch_id == batch_id, Job.kind == "generate"))
        assert job.status == "failed"
        assert db.get(ContentBatch, batch_id).status == "failed"
        assert list(db.scalars(select(ContentAssetVersion).where(ContentAssetVersion.batch_id == batch_id))) == []
    second = client.post("/internal/workflows/generate", headers=headers, json=payload)
    assert second.status_code == 200, second.text
    assert second.json()["batch"]["status"] == "review"
    assert len(second.json()["assets"]) == 11
    assert attempts == 2
    with session_factory()() as db:
        job = db.scalar(select(Job).where(Job.batch_id == batch_id, Job.kind == "generate"))
        assert job.status == "complete"
        assert len(list(db.scalars(select(ContentAssetVersion).where(ContentAssetVersion.batch_id == batch_id)))) == 11


def test_source_correction_during_generation_discards_old_bundle(
    client: TestClient, monkeypatch
):
    workspace_id, batch_id = pending_generation(client, "generate-correction-v1")
    with session_factory()() as db:
        batch = db.get(ContentBatch, batch_id)
        source_id = batch.source_asset_id
        brand_id = batch.brand_profile_version_id
        pinned_transcript_id = batch.transcript_version_id
    source = client.get(f"/api/v1/sources/{source_id}").json()
    segment_id = source["transcript"]["segments"][0]["id"]
    corrected_text = "The corrected count is 14 careful steps, not 12."

    def correct_before_finalization(thread_id, segments, brand):
        correction = client.patch(
            f"/api/v1/sources/{source_id}/segments/{segment_id}",
            json={"text": corrected_text},
        )
        assert correction.status_code == 200, correction.text
        return generate_bundle(thread_id, segments, brand)

    monkeypatch.setattr("contentstudio.service.generate_bundle", correct_before_finalization)
    with session_factory()() as db, pytest.raises(
        GenerationSourceChanged, match="create a new batch"
    ):
        generate_for_batch(db, db.get(ContentBatch, batch_id))
    with session_factory()() as db:
        batch = db.get(ContentBatch, batch_id)
        job = db.scalar(select(Job).where(Job.batch_id == batch_id, Job.kind == "generate"))
        assert batch.status == "failed" and batch.transcript_version_id == pinned_transcript_id
        assert job.status == "failed"
        assert list(db.scalars(select(ContentAssetVersion).where(ContentAssetVersion.batch_id == batch_id))) == []
        assert list(db.scalars(select(Claim).where(Claim.batch_id == batch_id))) == []
    headers = {"X-Service-Token": "test-service-token"}
    rejected = client.post(
        "/internal/workflows/transcribe",
        headers=headers,
        json={"workspace_id": workspace_id, "batch_id": batch_id},
    )
    assert rejected.status_code == 409
    fresh = client.post(
        "/internal/workflows/intake",
        headers=headers,
        json={
            "workspace_id": workspace_id,
            "source_asset_id": source_id,
            "brand_profile_version_id": brand_id,
            "recipe_version": "generate-correction-v1",
            "request_id": "generate-correction-retry",
        },
    )
    assert fresh.status_code == 200, fresh.text
    fresh_batch_id = fresh.json()["batch_id"]
    assert fresh_batch_id != batch_id
    monkeypatch.setattr("contentstudio.service.generate_bundle", generate_bundle)
    transcribed = client.post(
        "/internal/workflows/transcribe",
        headers=headers,
        json={"workspace_id": workspace_id, "batch_id": fresh_batch_id},
    )
    assert transcribed.status_code == 200, transcribed.text
    generated = client.post(
        "/internal/workflows/generate",
        headers=headers,
        json={"workspace_id": workspace_id, "batch_id": fresh_batch_id},
    )
    assert generated.status_code == 200, generated.text
    assert len(generated.json()["assets"]) == 11
    article = next(a for a in generated.json()["assets"] if a["asset_type"] == "article")
    assert corrected_text in article["text"]


def test_package_jobs_are_invalidated_at_all_active_stages(client: TestClient):
    _, bundle, payload = make_bundle(client)
    batch_id = bundle["batch"]["id"]
    with session_factory()() as db:
        jobs = [
            Job(
                workspace_id=payload["workspace_id"],
                kind="package",
                batch_id=batch_id,
                operation_key=f"package:invalidation:{status}",
                status=status,
            )
            for status in ("queued", "running", "complete")
        ]
        db.add_all(jobs)
        db.commit()
        invalidate_batch_package(db, payload["workspace_id"], batch_id)
        db.commit()
        assert all(db.get(Job, job.id).status == "stale" for job in jobs)


def test_losing_package_worker_cannot_replace_current_download(client: TestClient, monkeypatch):
    _, bundle, payload = make_bundle(client)
    article = next(asset for asset in bundle["assets"] if asset["asset_type"] == "article")
    assert article["warnings"] == []
    approved = client.post(
        f"/api/v1/assets/{article['id']}/review",
        json={"decision": "approve", "expected_hash": article["content_hash"]},
    )
    assert approved.status_code == 200, approved.text
    batch_id = bundle["batch"]["id"]
    root = get_settings().media_root.resolve() / payload["workspace_id"] / batch_id
    original_zip = zipfile.ZipFile
    raced = {}

    with session_factory()() as db:
        def steal_lease(path, mode="r", *args, **kwargs):
            if mode == "w" and not raced:
                job = db.scalar(
                    select(Job).where(
                        Job.workspace_id == payload["workspace_id"],
                        Job.batch_id == batch_id,
                        Job.kind == "package",
                        Job.status == "running",
                    )
                )
                assert job is not None and job.lease_token
                replacement_lease = str(uuid4())
                winner_name = package_file_name(job.id, replacement_lease)
                raced["winner"] = root / winner_name
                raced["loser"] = root / package_file_name(job.id, job.lease_token)
                with original_zip(raced["winner"], "w") as archive:
                    archive.writestr("manifest.json", json.dumps({"winner": True}))
                db.execute(
                    update(Job)
                    .where(Job.id == job.id)
                    .values(
                        status="complete", lease_token=replacement_lease, progress=100,
                        result_json={
                            "download_url": f"/api/v1/batches/{batch_id}/download",
                            "file_name": winner_name,
                        },
                    )
                )
                db.commit()
            return original_zip(path, mode, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr("contentstudio.internal_api.zipfile.ZipFile", steal_lease)
            with pytest.raises(HTTPException) as failure:
                package_step(
                    BatchStepInput(workspace_id=payload["workspace_id"], batch_id=batch_id), db
                )
        assert failure.value.status_code == 409

    assert not raced["loser"].exists()
    assert client.get(f"/api/v1/batches/{batch_id}/download").status_code == 200
    with original_zip(raced["winner"]) as archive:
        assert json.loads(archive.read("manifest.json"))["winner"] is True


def test_fresh_demo_seed_prepares_real_scoped_showcase_files_once(tmp_path: Path, monkeypatch):
    fixtures = tmp_path / "fixtures"
    source_dir = fixtures / "sources"
    media_dir = fixtures / "media" / "onboarding"
    source_dir.mkdir(parents=True)
    media_dir.mkdir(parents=True)
    (media_dir / "presentation.mp4").write_bytes(b"synthetic fixture media; renderer mocked")
    (fixtures / "brands.json").write_text(
        json.dumps([{
            "workspace_slug": "studio-alpha", "name": "Morrow", "version": 1,
            "tone": "Precise", "rules": {"accent": "#C45B35"},
        }]), encoding="utf-8",
    )
    segments = [
        {
            "start_ms": index * 30_000,
            "end_ms": (index + 1) * 30_000,
            "speaker": "Host",
            "text": f"This section explains the onboarding method for team {chr(65 + index)} with a documented source and a clear owner.",
        }
        for index in range(8)
    ]
    (source_dir / "onboarding.json").write_text(
        json.dumps({
            "workspace_slug": "studio-alpha", "source_key": "onboarding",
            "title": "Onboarding Briefing", "kind": "owned_media",
            "rights_status": "owned_synthetic_script", "duration_ms": 240_000,
            "media_path": "media/onboarding/presentation.mp4", "segments": segments,
        }), encoding="utf-8",
    )
    monkeypatch.setenv("MODE", "demo")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'showcase.db').as_posix()}")
    monkeypatch.setenv("FIXTURES_ROOT", str(fixtures))
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "output"))
    monkeypatch.setenv("MODEL_PROVIDER", "fixture")
    get_settings.cache_clear()
    engine.cache_clear()
    session_factory.cache_clear()
    calls = {"carousel": 0, "clip": 0}

    def fake_carousel(slides, title, output_dir, brand=None):
        assert brand["name"] == "Morrow"
        calls["carousel"] += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        png_paths = []
        for index in range(len(slides)):
            path = output_dir / f"slide-{index + 1:02d}.png"
            path.write_bytes(b"PNG demo fixture")
            png_paths.append(str(path))
        pdf_path = output_dir / "carousel.pdf"
        pdf_path.write_bytes(b"PDF demo fixture")
        return {"png_paths": png_paths, "pdf_path": str(pdf_path)}

    def fake_clip(media, clip_range, segments, title, output_dir, aspect_ratio, brand=None):
        assert brand["name"] == "Morrow"
        calls["clip"] += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        mp4_path = output_dir / "clip.mp4"
        mp4_path.write_bytes(b"MP4 demo fixture")
        return {"mp4_path": str(mp4_path)}

    monkeypatch.setattr("contentstudio.rendering.render_carousel", fake_carousel)
    monkeypatch.setattr("contentstudio.rendering.render_clip", fake_clip)
    Base.metadata.create_all(engine())
    try:
        with session_factory()() as db:
            seed_demo(db)
            batch = db.scalar(select(ContentBatch).where(ContentBatch.recipe_version == "v1"))
            assert batch is not None and batch.status == "complete"
            showcase_assets = db.scalars(
                select(ContentAssetVersion).where(ContentAssetVersion.batch_id == batch.id)
            ).all()
            assert len(showcase_assets) == 11
            assert len([asset for asset in showcase_assets if asset.status == "rendered"]) == 4
            assert calls == {"carousel": 1, "clip": 3}
            package_path = package_result_path(
                current_complete_package(db, batch.id, batch.workspace_id)
            )
            assert package_path is not None
            with zipfile.ZipFile(package_path) as archive:
                files = archive.namelist()
                assert any(name.endswith("carousel.pdf") for name in files)
                assert len([name for name in files if name.endswith("clip.mp4")]) == 3
            seed_demo(db)
            assert calls == {"carousel": 1, "clip": 3}
            assert db.get(ContentBatch, batch.id).status == "complete"
            clip = next(asset for asset in showcase_assets if asset.asset_type == "clip")
            render_file_paths(clip)[0].unlink()
            seed_demo(db)
            assert calls == {"carousel": 1, "clip": 4}
            assert db.get(ContentBatch, batch.id).status == "complete"
    finally:
        engine().dispose()
        get_settings.cache_clear()
        engine.cache_clear()
        session_factory.cache_clear()


def test_workspace_boundary_and_viewer_write_denial(client: TestClient):
    login(client)
    source = create_source(client)
    other = TestClient(app)
    login(other, "beta-admin@studio.test")
    assert other.get(f"/api/v1/sources/{source['source']['id']}").status_code == 404
    assert other.get("/api/v1/sources").json()["items"] == []
    client.post("/api/v1/auth/logout")
    login(client, "viewer@studio.test")
    assert (
        client.post(
            "/api/v1/sources/transcript",
            json={
                "title": "Another",
                "rights_attested": True,
                "segments": [{"start_ms": 0, "end_ms": 1000, "text": "Hello."}],
            },
        ).status_code
        == 403
    )


def test_intake_idempotency_and_conflicting_event(client: TestClient):
    _, bundle, payload = make_bundle(client)
    headers = {"X-Service-Token": "test-service-token"}
    duplicate = client.post("/internal/workflows/intake", headers=headers, json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    conflicting = {**payload, "recipe_version": "different"}
    assert (
        client.post("/internal/workflows/intake", headers=headers, json=conflicting).status_code
        == 409
    )
    assert len(bundle["assets"]) == 11
    assert len([asset for asset in bundle["assets"] if asset["asset_type"] == "clip"]) == 3


def test_demo_scenario_status_links_event_to_complete_bundle(client: TestClient):
    source, bundle, payload = make_bundle(client)
    url = "/internal/workflows/demo-scenario-status"
    query = {"workspace_id": payload["workspace_id"], "request_id": payload["request_id"]}
    assert client.get(url, params=query).status_code == 401
    headers = {"X-Service-Token": "test-service-token"}
    status = client.get(url, headers=headers, params=query)
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["observed"] is True
    assert body["batch_id"] == bundle["batch"]["id"]
    assert body["source_asset_id"] == source["source"]["id"]
    assert body["recipe_version"] == payload["recipe_version"]
    assert body["status"] == "review"
    assert body["asset_count"] == 11
    assert body["asset_type_counts"] == {
        "article": 1, "newsletter": 1, "social": 5, "carousel": 1, "clip": 3
    }
    assert body["claim_count"] > 0
    assert body["matching_batch_count"] == 1
    unknown = client.get(
        url, headers=headers,
        params={"workspace_id": payload["workspace_id"], "request_id": "missing-event"},
    )
    assert unknown.status_code == 200 and unknown.json() == {"observed": False}


def test_edit_version_review_hash_and_source_invalidation(client: TestClient):
    source, bundle, _ = make_bundle(client)
    social = next(
        a
        for a in bundle["assets"]
        if a["asset_type"] == "social"
        and source["transcript"]["segments"][0]["id"] in a["source_segment_ids"]
    )
    edit = client.patch(
        f"/api/v1/assets/{social['id']}",
        json={"text": "This achieved a guaranteed result of 42% growth."},
    )
    assert edit.status_code == 200, edit.text
    changed = edit.json()
    assert changed["version"] == 2
    assert changed["warnings"]
    rejected_approval = client.post(
        f"/api/v1/assets/{changed['id']}/review",
        json={"decision": "approve", "expected_hash": changed["content_hash"]},
    )
    assert rejected_approval.status_code == 409
    corrected = client.patch(
        f"/api/v1/assets/{changed['id']}",
        json={"title": "Revised source note", "text": source["transcript"]["segments"][0]["text"]},
    )
    assert corrected.status_code == 200
    fixed = corrected.json()
    assert fixed["warnings"] == []
    assert (
        client.post(
            f"/api/v1/assets/{fixed['id']}/review",
            json={"decision": "approve", "expected_hash": social["content_hash"]},
        ).status_code
        == 409
    )
    approved = client.post(
        f"/api/v1/assets/{fixed['id']}/review",
        json={"decision": "approve", "expected_hash": fixed["content_hash"]},
    )
    assert approved.status_code == 200, approved.text
    segment = source["transcript"]["segments"][0]
    correction = client.patch(
        f"/api/v1/sources/{source['source']['id']}/segments/{segment['id']}",
        json={"text": "The corrected count is 14 careful steps. The earlier count was wrong."},
    )
    assert correction.status_code == 200
    updated = client.get(f"/api/v1/batches/{bundle['batch']['id']}").json()
    assert (
        next(a for a in updated["assets"] if a["logical_asset_id"] == fixed["logical_asset_id"])[
            "status"
        ]
        == "stale"
    )
    unrelated = [a for a in updated["assets"] if segment["id"] not in a["source_segment_ids"]]
    assert unrelated and all(a["status"] != "stale" for a in unrelated)


def test_dispatch_ledger_is_single_claim_and_completion_is_idempotent(client: TestClient):
    _, bundle, payload = make_bundle(client)
    article = next(a for a in bundle["assets"] if a["asset_type"] == "article")
    assert article["warnings"] == []
    assert (
        client.post(
            f"/api/v1/assets/{article['id']}/review",
            json={"decision": "approve", "expected_hash": article["content_hash"]},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/assets/{article['id']}/schedule", json={"channel": "wordpress"}
        ).status_code
        == 200
    )
    headers = {"X-Service-Token": "test-service-token"}
    prepared = {
        "workspace_id": payload["workspace_id"],
        "asset_version_id": article["id"],
        "channel": "wordpress",
        "operation_key": "wp-test-one",
    }
    first = client.post("/internal/workflows/dispatch/prepare", headers=headers, json=prepared)
    assert first.status_code == 200, first.text
    assert first.json()["claimed"] is True
    assert first.json()["draft"]["status"] == "draft"
    assert (
        client.post("/internal/workflows/dispatch/prepare", headers=headers, json=prepared).json()[
            "claimed"
        ]
        is False
    )
    completed = {
        "workspace_id": payload["workspace_id"],
        "operation_key": "wp-test-one",
        "external_id": "42",
    }
    assert (
        client.post(
            "/internal/workflows/dispatch/complete", headers=headers, json=completed
        ).json()["duplicate"]
        is False
    )
    assert (
        client.post(
            "/internal/workflows/dispatch/complete", headers=headers, json=completed
        ).json()["duplicate"]
        is True
    )
    assert (
        client.post(
            "/internal/workflows/dispatch/complete",
            headers=headers,
            json={**completed, "external_id": "43"},
        ).status_code
        == 409
    )


def test_scheduled_newsletter_becomes_local_outbox_without_sending(client: TestClient):
    _, bundle, payload = make_bundle(client)
    newsletter = next(a for a in bundle["assets"] if a["asset_type"] == "newsletter")
    assert newsletter["warnings"] == []
    approval = client.post(
        f"/api/v1/assets/{newsletter['id']}/review",
        json={"decision": "approve", "expected_hash": newsletter["content_hash"]},
    )
    assert approval.status_code == 200
    scheduled = client.post(
        f"/api/v1/assets/{newsletter['id']}/schedule", json={"channel": "newsletter"}
    )
    assert scheduled.status_code == 200
    headers = {"X-Service-Token": "test-service-token"}
    due = client.get(
        "/internal/workflows/due",
        params={"workspace_id": payload["workspace_id"]},
        headers=headers,
    )
    assert due.status_code == 200
    item = next(i for i in due.json()["items"] if i["asset_version_id"] == newsletter["id"])
    assert item["action"] == "outbox"
    body = {
        "workspace_id": item["workspace_id"],
        "asset_version_id": item["asset_version_id"],
        "channel": item["channel"],
        "operation_key": item["operation_key"],
    }
    first = client.post("/internal/workflows/outbox", headers=headers, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["ready"] is True and first.json()["duplicate"] is False
    second = client.post("/internal/workflows/outbox", headers=headers, json=body)
    assert second.json()["duplicate"] is True
    calendar = client.get("/api/v1/calendar").json()["items"]
    assert next(i for i in calendar if i["asset_version_id"] == newsletter["id"])["status"] == "ready"


def test_source_correction_revokes_old_render_and_package_urls(client: TestClient):
    source, bundle, payload = make_bundle(client)
    carousel = next(a for a in bundle["assets"] if a["asset_type"] == "carousel")
    edited = client.patch(f"/api/v1/assets/{carousel['id']}", json={
        "slides": (carousel["slides"] * 4)[:6],
    })
    assert edited.status_code == 200, edited.text
    carousel = edited.json()
    root = get_settings().media_root.resolve() / payload["workspace_id"] / bundle["batch"]["id"]
    rendered = root / carousel["id"] / "slide-01.png"
    rendered.parent.mkdir(parents=True, exist_ok=True)
    rendered.write_bytes(b"fake-image-for-access-check")
    approved = client.post(
        f"/api/v1/assets/{carousel['id']}/review",
        json={"decision": "approve", "expected_hash": carousel["content_hash"]},
    )
    assert approved.status_code == 200, approved.text
    png_urls = []
    for index in range(len(carousel["slides"])):
        filename = f"slide-{index + 1:02d}.png"
        (rendered.parent / filename).write_bytes(b"fake-image-for-access-check")
        png_urls.append(f"/api/v1/assets/{carousel['id']}/renders/{filename}")
    (rendered.parent / "carousel.pdf").write_bytes(b"fake-pdf-for-access-check")
    with session_factory()() as db:
        asset = db.get(ContentAssetVersion, carousel["id"])
        asset.status = "rendered"
        asset.render_urls_json = {"png": png_urls, "pdf": f"/api/v1/assets/{asset.id}/renders/carousel.pdf", "mp4": None}
        db.commit()
    package_response = client.post(
        "/internal/workflows/package",
        headers={"X-Service-Token": "test-service-token"},
        json={"workspace_id": payload["workspace_id"], "batch_id": bundle["batch"]["id"]},
    )
    assert package_response.status_code == 200, package_response.text
    render_url = f"/api/v1/assets/{carousel['id']}/renders/slide-01.png"
    package_url = f"/api/v1/batches/{bundle['batch']['id']}/download"
    assert client.get(render_url).status_code == 200
    assert client.get(package_url).status_code == 200
    segment = source["transcript"]["segments"][0]
    corrected = client.patch(
        f"/api/v1/sources/{source['source']['id']}/segments/{segment['id']}",
        json={"text": "The revised example includes 14 careful steps and an owner."},
    )
    assert corrected.status_code == 200
    assert client.get(render_url).status_code == 404
    assert client.get(package_url).status_code == 409

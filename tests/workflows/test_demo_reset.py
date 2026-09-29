"""Scoped DEMO cleanup is exercised only against disposable SQLite and media."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
from contentstudio.db import Base
from contentstudio.demo_reset import (
    apply_reset,
    plan_reset,
    safe_media_dir,
    seeded_workspace_id,
)
from contentstudio.models import (
    BrandProfileVersion,
    Claim,
    ContentAssetVersion,
    ContentBatch,
    DispatchLedger,
    InstallationBootstrap,
    Job,
    PublicationDraft,
    ReviewDecision,
    SourceAsset,
    User,
    WebhookEvent,
    WorkflowIncident,
    Workspace,
)


def new_id() -> str:
    return str(uuid4())


class DemoResetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.media_root = Path(self.temp.name) / "media"
        self.engine = create_engine("sqlite:///:memory:")

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        self.now = datetime(2026, 9, 28, tzinfo=UTC)
        self.alpha = seeded_workspace_id("studio-alpha")
        self.beta = seeded_workspace_id("studio-beta")
        self.db.add_all([
            Workspace(id=self.alpha, slug="studio-alpha", name="Alpha"),
            Workspace(id=self.beta, slug="studio-beta", name="Beta"),
        ])
        self.db.flush()
        self.old_alpha = self.make_batch(self.alpha, "old-alpha", self.now - timedelta(days=40))
        self.new_alpha = self.make_batch(self.alpha, "new-alpha", self.now - timedelta(days=2))
        self.seeded_alpha = self.make_batch(
            self.alpha, "seeded-alpha", self.now - timedelta(days=60), recipe_version="synthetic-archive-v1",
        )
        self.old_beta = self.make_batch(self.beta, "old-beta", self.now - timedelta(days=50))
        self.db.add_all([
            WorkflowIncident(id=new_id(), workspace_id=self.alpha,
                             operation_key="unrelated-system-error", error="synthetic",
                             outcome="failed", created_at=self.now - timedelta(days=90)),
            WebhookEvent(id=new_id(), workspace_id=self.alpha, batch_id=None,
                         event_id="unlinked-event", payload_hash="c" * 64),
        ])
        self.db.commit()

    def make_batch(
        self, workspace_id: str, label: str, created_at: datetime, recipe_version: str = "scenario",
    ) -> str:
        user = User(id=new_id(), workspace_id=workspace_id, email=f"{label}@example.test",
                    password_hash="synthetic", role="admin", active=True)
        source = SourceAsset(id=new_id(), workspace_id=workspace_id, title=label,
                             kind="transcript_fixture", rights_status="owned_synthetic_script",
                             sha256=label.ljust(64, "0"), duration_ms=1000)
        brand = BrandProfileVersion(id=new_id(), workspace_id=workspace_id, name=label,
                                    version=1, tone="clear", rules_json={})
        self.db.add_all([user, source, brand])
        self.db.flush()
        batch = ContentBatch(id=new_id(), workspace_id=workspace_id, source_asset_id=source.id,
                             brand_profile_version_id=brand.id, source_hash=source.sha256,
                             recipe_version=recipe_version, status="review", created_at=created_at)
        self.db.add(batch)
        self.db.flush()
        asset = ContentAssetVersion(
            id=new_id(), workspace_id=workspace_id, batch_id=batch.id, logical_asset_id=new_id(),
            version=1, asset_type="article", title=label, text="synthetic", slides_json=[],
            source_segment_ids=[], warnings_json=[], status="approved", content_hash="f" * 64,
            render_urls_json={"png": [], "pdf": None, "mp4": None},
        )
        self.db.add(asset)
        self.db.flush()
        if label == "old-alpha":
            operation_key = f"wordpress:{asset.id}"
            self.db.add_all([
                Claim(id=new_id(), workspace_id=workspace_id, batch_id=batch.id,
                      text="synthetic claim", source_segment_ids=[], verification_status="verified"),
                ReviewDecision(id=new_id(), workspace_id=workspace_id, asset_version_id=asset.id,
                               user_id=user.id, decision="approve", expected_hash=asset.content_hash),
                Job(id=new_id(), workspace_id=workspace_id, batch_id=batch.id,
                    asset_version_id=asset.id, kind="render", operation_key=f"render:{asset.id}", status="complete"),
                PublicationDraft(id=new_id(), workspace_id=workspace_id, asset_version_id=asset.id,
                                 channel="wordpress", status="created", payload_json={}),
                DispatchLedger(id=new_id(), workspace_id=workspace_id, asset_version_id=asset.id,
                               operation_key=operation_key, channel="wordpress", status="complete",
                               payload_hash="a" * 64),
                WebhookEvent(id=new_id(), workspace_id=workspace_id, batch_id=batch.id,
                             event_id="old-event", payload_hash="b" * 64),
                WorkflowIncident(id=new_id(), workspace_id=workspace_id,
                                 operation_key=operation_key, error="synthetic", outcome="failed",
                                 created_at=created_at),
            ])
        folder = safe_media_dir(self.media_root, workspace_id, batch.id)
        folder.mkdir(parents=True)
        (folder / "render.txt").write_text(label, encoding="utf-8")
        return batch.id

    def test_age_prune_is_scoped_and_requires_exact_confirmation(self) -> None:
        plan = plan_reset(self.db, workspace_slug="studio-alpha", media_root=self.media_root,
                          older_than_days=30, reference_time=self.now)
        self.assertEqual(plan.batch_ids, (self.old_alpha,))
        self.assertEqual(plan.counts["content_asset_versions"], 1)
        self.assertEqual(plan.counts["workflow_incidents"], 1)
        self.assertEqual(plan.counts["webhook_events"], 1)
        with self.assertRaisesRegex(ValueError, "offline acknowledgment"):
            apply_reset(self.db, plan, media_root=self.media_root,
                        confirm_workspace_id=self.alpha, confirm_plan_sha256=plan.plan_sha256,
                        expected_batch_count=1, offline_ack=False)
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            apply_reset(self.db, plan, media_root=self.media_root,
                        confirm_workspace_id=self.alpha, confirm_plan_sha256="0" * 64,
                        expected_batch_count=1, offline_ack=True)
        with self.assertRaisesRegex(ValueError, "Batch count"):
            apply_reset(self.db, plan, media_root=self.media_root,
                        confirm_workspace_id=self.alpha, confirm_plan_sha256=plan.plan_sha256,
                        expected_batch_count=2, offline_ack=True)
        self.assertTrue(self.db.get(ContentBatch, self.old_alpha))
        self.assertTrue(safe_media_dir(self.media_root, self.alpha, self.old_alpha).exists())
        outcome = apply_reset(self.db, plan, media_root=self.media_root,
                              confirm_workspace_id=self.alpha, confirm_plan_sha256=plan.plan_sha256,
                              expected_batch_count=1, offline_ack=True)
        self.assertEqual(outcome["failed_media_dirs"], [])
        self.assertIsNone(self.db.get(ContentBatch, self.old_alpha))
        self.assertIsNotNone(self.db.get(ContentBatch, self.new_alpha))
        self.assertIsNotNone(self.db.get(ContentBatch, self.seeded_alpha))
        self.assertIsNotNone(self.db.get(ContentBatch, self.old_beta))
        self.assertFalse(safe_media_dir(self.media_root, self.alpha, self.old_alpha).exists())
        self.assertTrue(safe_media_dir(self.media_root, self.alpha, self.new_alpha).exists())
        self.assertTrue(safe_media_dir(self.media_root, self.beta, self.old_beta).exists())
        self.assertEqual(len(self.db.scalars(select(SourceAsset).where(SourceAsset.workspace_id == self.alpha)).all()), 3)
        self.assertIsNotNone(self.db.scalar(select(WorkflowIncident).where(
            WorkflowIncident.operation_key == "unrelated-system-error",
        )))
        self.assertIsNotNone(self.db.scalar(select(WebhookEvent).where(
            WebhookEvent.event_id == "unlinked-event",
        )))

    def test_all_batch_reset_includes_fixture_baseline_but_preserves_other_workspace(self) -> None:
        plan = plan_reset(self.db, workspace_slug="studio-alpha", media_root=self.media_root)
        self.assertEqual(set(plan.batch_ids), {self.old_alpha, self.new_alpha, self.seeded_alpha})
        apply_reset(self.db, plan, media_root=self.media_root,
                    confirm_workspace_id=self.alpha, confirm_plan_sha256=plan.plan_sha256,
                    expected_batch_count=3, offline_ack=True)
        self.assertEqual(len(self.db.scalars(select(ContentBatch).where(
            ContentBatch.workspace_id == self.alpha,
        )).all()), 0)
        self.assertIsNotNone(self.db.get(ContentBatch, self.old_beta))
        self.assertTrue(safe_media_dir(self.media_root, self.beta, self.old_beta).exists())
        self.assertEqual(len(self.db.scalars(select(SourceAsset).where(
            SourceAsset.workspace_id == self.alpha,
        )).all()), 3)
        self.assertIsNotNone(self.db.scalar(select(WorkflowIncident).where(
            WorkflowIncident.operation_key == "unrelated-system-error",
        )))
        self.assertIsNotNone(self.db.scalar(select(WebhookEvent).where(
            WebhookEvent.event_id == "unlinked-event",
        )))

    def test_new_linked_row_invalidates_reviewed_fingerprint(self) -> None:
        before = plan_reset(self.db, workspace_slug="studio-alpha", media_root=self.media_root,
                            older_than_days=30, reference_time=self.now)
        self.db.add(Claim(id=new_id(), workspace_id=self.alpha, batch_id=self.old_alpha,
                          text="later synthetic claim", source_segment_ids=[],
                          verification_status="verified"))
        self.db.flush()
        after = plan_reset(self.db, workspace_slug="studio-alpha", media_root=self.media_root,
                           older_than_days=30, reference_time=self.now)
        self.assertEqual(before.batch_ids, after.batch_ids)
        self.assertNotEqual(before.plan_sha256, after.plan_sha256)

    def test_connected_marker_and_path_escape_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            safe_media_dir(self.media_root, self.alpha, "../other")
        with self.assertRaises(ValueError):
            plan_reset(self.db, workspace_slug="customer", media_root=self.media_root)
        self.db.add(InstallationBootstrap(id=1))
        self.db.flush()
        with self.assertRaisesRegex(ValueError, "Connected installation marker"):
            plan_reset(self.db, workspace_slug="studio-alpha", media_root=self.media_root)

    def test_connected_mode_is_rejected_even_without_marker(self) -> None:
        with (
            patch("contentstudio.demo_reset.get_settings", return_value=SimpleNamespace(mode="connected")),
            self.assertRaisesRegex(ValueError, "outside MODE=demo"),
        ):
            plan_reset(self.db, workspace_slug="studio-alpha", media_root=self.media_root)


if __name__ == "__main__":
    unittest.main()

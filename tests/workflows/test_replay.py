"""Acceptance checks must reject a healthy webhook without persisted results."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
N8N_SCRIPTS = ROOT / "scripts" / "n8n"
sys.path.insert(0, str(N8N_SCRIPTS))
spec = importlib.util.spec_from_file_location("cs_replay", N8N_SCRIPTS / "replay.py")
assert spec and spec.loader
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class ReplayAcceptanceTest(unittest.TestCase):
    def test_fresh_fixture_uses_new_request_and_recipe(self) -> None:
        original = {"workspace_id": "ws", "source_asset_id": "src", "recipe_version": "old", "request_id": "old-id"}
        fresh = replay.fresh_fixture(original, "run-123", 2)
        self.assertEqual(fresh["recipe_version"], "scenario-run-123")
        self.assertEqual(fresh["request_id"], "replay-run-123-2")
        self.assertEqual(original["request_id"], "old-id")

    def test_bundle_requires_source_recipe_claims_and_all_asset_types(self) -> None:
        body = {"source_asset_id": "src", "recipe_version": "scenario"}
        status = {
            "observed": True, "source_asset_id": "src", "recipe_version": "scenario",
            "status": "review", "asset_count": 11, "asset_type_counts": replay.EXPECTED_ASSET_TYPES,
            "claim_count": 2, "matching_batch_count": 1,
        }
        replay.validate_bundle(status, body)
        for change in ({"observed": False}, {"claim_count": 0}, {"asset_count": 10},
                       {"matching_batch_count": 2}, {"source_asset_id": "other"},
                       {"asset_type_counts": {"article": 1}}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                replay.validate_bundle(status | change, body)

    def test_execution_wait_rejects_failed_success_scenario(self) -> None:
        with (
            patch.object(replay, "executions", return_value=[{"id": "run-1", "status": "error"}]),
            self.assertRaisesRegex(RuntimeError, "Expected n8n execution success"),
        ):
            replay.wait_for_execution("http://n8n", "key", "intake", set(), "success", 3)

    def test_replay_checks_eight_outcomes_and_saves_metadata_only(self) -> None:
        fixtures = [
            {"workspace_id": "ws", "source_asset_id": f"source-{index}",
             "brand_profile_version_id": "brand", "recipe_version": "scenario-v1",
             "request_id": f"old-{index}"}
            for index in range(1, 6)
        ]
        statuses = ["success"] * 6 + ["error", "success", "error", "success"]
        execution_counter = iter(range(1, 11))

        def fake_wait(base, key, workflow_id, seen, expected, timeout):
            actual = statuses[next_index := next(execution_counter) - 1]
            self.assertEqual(expected, actual, f"step {next_index + 1}")
            return {"id": str(next_index + 1), "workflowId": workflow_id, "status": actual}

        def fake_call(url, token, body=None):
            return (200, {"items": fixtures}) if url.endswith("/demo-fixtures") else (202, None)

        def fake_status(api_url, token, workspace_id, request_id):
            if request_id.startswith("malformed-"):
                return {"observed": False}
            run_and_index = request_id.removeprefix("replay-")
            run_id, index = run_and_index.rsplit("-", 1)
            return {
                "observed": True, "batch_id": f"batch-{index}",
                "source_asset_id": f"source-{index}", "recipe_version": f"scenario-{run_id}",
                "status": "review", "asset_count": 11,
                "asset_type_counts": replay.EXPECTED_ASSET_TYPES, "claim_count": 3,
                "matching_batch_count": 1, "payload_hash": "abc",
            }

        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "evidence.json"
            args = argparse.Namespace(
                n8n_url="http://n8n", api_url="http://api", service_token="test-token",
                api_key="test-key", timeout_seconds=3, out=output,
            )
            workflows = {
                "ContentStudio / Intake owned source": {"id": "intake"},
                "ContentStudio / Shared execution error": {"id": "errors"},
            }
            with patch.object(replay, "list_workflows", return_value=workflows), \
                 patch.object(replay, "executions", return_value=[]), \
                 patch.object(replay, "call_json", side_effect=fake_call), \
                 patch.object(replay, "wait_for_execution", side_effect=fake_wait), \
                 patch.object(replay, "scenario_status", side_effect=fake_status), \
                 patch.object(replay.secrets, "token_hex", return_value="abc123"):
                self.assertEqual(replay.run_acceptance(args), 0)
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(evidence["triggered_events"]), 8)
            self.assertEqual([item["status"] for item in evidence["intake_executions"]],
                             ["success"] * 6 + ["error"] * 2)
            self.assertEqual(len(evidence["error_handler_executions"]), 2)
            self.assertTrue(evidence["payloads_and_secrets_saved"] is False)
            self.assertNotIn("test-token", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

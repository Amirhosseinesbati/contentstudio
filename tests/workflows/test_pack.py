from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkflowPackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((ROOT / "workflows" / "manifest.json").read_text(encoding="utf-8"))
        cls.bootstrap = load_module("cs_bootstrap", ROOT / "scripts" / "n8n" / "bootstrap.py")

    def test_all_references_resolve_and_connections_are_valid(self) -> None:
        ids = {}
        for entry in self.manifest["workflows"]:
            substitutions = {
                "__API_BASE_URL__": "http://api:8000",
                "__WORDPRESS_BASE_URL__": "http://connector-sim:8081",
                "__SERVICE_CREDENTIAL_ID__": "test-service-credential",
                "__WORDPRESS_CREDENTIAL_ID__": "test-wordpress-credential",
            } | {f"__workflow:{key}__": workflow_id for key, workflow_id in ids.items()}
            compiled = self.bootstrap.compile_workflow(entry, substitutions)
            names = {node["name"] for node in compiled["nodes"]}
            self.assertEqual(len(names), len(compiled["nodes"]), entry["key"])
            for source, branches in compiled["connections"].items():
                self.assertIn(source, names)
                for branch in branches["main"]:
                    for edge in branch:
                        self.assertIn(edge["node"], names)
            ids[entry["key"]] = f"imported-{entry['key']}"

    def test_no_exported_secrets_or_pinned_result_data(self) -> None:
        for entry in self.manifest["workflows"]:
            exported = json.loads((ROOT / "workflows" / entry["file"]).read_text(encoding="utf-8"))
            self.assertFalse(exported["active"])
            self.assertEqual(exported["pinData"], {})
            content = json.dumps(exported)
            self.assertNotIn("sk-", content)
            self.assertNotIn("@example.com", content)
            self.assertNotIn("127.0.0.1", content)
            self.assertNotIn("localhost", content)
            for node in exported["nodes"]:
                for reference in node.get("credentials", {}).values():
                    self.assertIn(reference["id"], {"__SERVICE_CREDENTIAL_ID__", "__WORDPRESS_CREDENTIAL_ID__"})

    def test_demo_activation_is_explicit_and_scoped(self) -> None:
        activated = {entry["key"] for entry in self.manifest["workflows"] if entry["activate_for_demo"]}
        self.assertEqual(activated, {entry["key"] for entry in self.manifest["workflows"]})
        self.assertEqual(len(activated), 7)

    def test_due_outbox_is_a_local_ready_action(self) -> None:
        entry = next(entry for entry in self.manifest["workflows"] if entry["key"] == "due_items")
        exported = json.loads((ROOT / "workflows" / entry["file"]).read_text(encoding="utf-8"))
        outbox = next(node for node in exported["nodes"] if node["name"] == "Prepare newsletter or social outbox")
        self.assertEqual(outbox["parameters"]["url"], "__API_BASE_URL__/internal/workflows/outbox")
        branches = exported["connections"]["Needs dispatch?"]["main"]
        self.assertEqual(branches[1][0]["node"], "Needs local outbox?")
        self.assertIn("ready", entry["output_schema"]["oneOf"][2]["properties"])

    def test_webhook_v2_acknowledges_accepted_events(self) -> None:
        for key in ("intake", "due_items", "reconcile"):
            with self.subTest(workflow=key):
                entry = next(item for item in self.manifest["workflows"] if item["key"] == key)
                exported = json.loads((ROOT / "workflows" / entry["file"]).read_text(encoding="utf-8"))
                webhook = next(node for node in exported["nodes"] if node["type"] == "n8n-nodes-base.webhook")
                self.assertEqual(webhook["typeVersion"], 2.1)
                self.assertNotIn("responseCode", webhook["parameters"])
                self.assertEqual(webhook["parameters"]["options"]["responseCode"]["values"],
                                 {"responseCode": "customCode", "customCode": 202})

    def test_wordpress_basic_auth_transport_is_restricted(self) -> None:
        allowed = [
            ("http://connector-sim:8081", "demo"),
            ("http://localhost:8081", "demo"),
            ("https://customer.example.com/blog", "connected"),
        ]
        for url, mode in allowed:
            with self.subTest(url=url, mode=mode):
                self.bootstrap.validate_wordpress_base_url(url, mode)
        rejected = [
            ("http://connector-sim:8081", "connected"),
            ("http://customer.example.com", "connected"),
            ("http://customer.example.com", "demo"),
            ("https://user:password@customer.example.com", "connected"),
            ("https://customer.example.com/?key=secret", "connected"),
        ]
        for url, mode in rejected:
            with self.subTest(url=url, mode=mode), self.assertRaises(ValueError):
                self.bootstrap.validate_wordpress_base_url(url, mode)
        with patch.dict(os.environ, {"MODE": "connected", "WORDPRESS_BASE_URL": "http://customer.example.com"}), patch.object(sys, "argv", ["bootstrap.py", "--dry-run"]), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as blocked:
                self.bootstrap.main()
            self.assertEqual(blocked.exception.code, 2)
        with patch.dict(os.environ, {"MODE": "connected", "WORDPRESS_BASE_URL": "https://customer.example.com"}), patch.object(sys, "argv", ["bootstrap.py", "--dry-run"]), redirect_stdout(io.StringIO()):
            self.assertEqual(self.bootstrap.main(), 0)

    def test_readback_rejects_missing_credential_or_child_reference(self) -> None:
        entry = next(entry for entry in self.manifest["workflows"] if entry["key"] == "intake")
        mapping = {
            "__API_BASE_URL__": "http://api:8000",
            "__WORDPRESS_BASE_URL__": "http://connector-sim:8081",
            "__SERVICE_CREDENTIAL_ID__": "service-id",
            "__WORDPRESS_CREDENTIAL_ID__": "wordpress-id",
            "__workflow:error_handler__": "error-id",
            "__workflow:transcribe_generate__": "child-id",
        }
        expected = self.bootstrap.compile_workflow(entry, mapping)
        saved = json.loads(json.dumps(expected))
        self.bootstrap.verify_readback(expected, saved)
        webhook = next(node for node in saved["nodes"] if node["type"] == "n8n-nodes-base.webhook")
        webhook["credentials"]["httpHeaderAuth"]["id"] = "wrong-id"
        with self.assertRaises(self.bootstrap.N8nAPIError):
            self.bootstrap.verify_readback(expected, saved)


if __name__ == "__main__":
    unittest.main()

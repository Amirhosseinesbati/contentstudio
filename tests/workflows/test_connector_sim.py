from __future__ import annotations

import base64
import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("connector_sim", ROOT / "infra" / "connector_sim" / "server.py")
assert SPEC and SPEC.loader
SIM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SIM)


class ConnectorSimulatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        SIM.DATA_PATH = Path(self.tmp.name) / "simulator.json"
        SIM.WP_USER = "demo"
        SIM.WP_PASSWORD = "test-secret"
        SIM.CONTROL_TOKEN = "control-secret"
        SIM.FAIL_NEXT.update(mode="", count=0, retry_after=1)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), SIM.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.auth = "Basic " + base64.b64encode(b"demo:test-secret").decode()
        self.draft = {"title": "An owned webinar", "content": "Source-backed notes", "status": "draft", "slug": "source-backed-notes"}

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def request(self, path: str, data: dict | None = None, *, key: str = "batch:article:1", control: bool = False):
        headers = {"Authorization": self.auth, "Idempotency-Key": key, "Content-Type": "application/json"}
        if control:
            headers["X-Sim-Control-Token"] = SIM.CONTROL_TOKEN
        request = urllib.request.Request(
            self.base + path,
            data=None if data is None else json.dumps(data).encode(),
            headers=headers,
            method="GET" if data is None else "POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_wordpress_draft_idempotency_and_conflict(self) -> None:
        first_status, first = self.request("/wp-json/wp/v2/posts", self.draft)
        second_status, second = self.request("/wp-json/wp/v2/posts", self.draft)
        conflict_status, _ = self.request("/wp-json/wp/v2/posts", self.draft | {"title": "Changed"})
        self.assertEqual((first_status, second_status, conflict_status), (201, 200, 409))
        self.assertEqual(first["id"], second["id"])
        status, matches = self.request("/wp-json/wp/v2/posts?slug=source-backed-notes&status=draft")
        self.assertEqual(status, 200)
        self.assertEqual(len(matches), 1)

    def test_rate_limit_then_success(self) -> None:
        self.request("/__control/fail-next", {"mode": "429", "retry_after": 1}, control=True)
        first_status, _ = self.request("/wp-json/wp/v2/posts", self.draft)
        second_status, _ = self.request("/wp-json/wp/v2/posts", self.draft)
        self.assertEqual((first_status, second_status), (429, 201))

    def test_unknown_outcome_is_reconcilable_without_replay(self) -> None:
        self.request("/__control/fail-next", {"mode": "after_write_timeout"}, control=True)
        with self.assertRaises(OSError):
            self.request("/wp-json/wp/v2/posts", self.draft)
        _, matches = self.request("/wp-json/wp/v2/posts?slug=source-backed-notes&status=draft")
        self.assertEqual(len(matches), 1)


if __name__ == "__main__":
    unittest.main()

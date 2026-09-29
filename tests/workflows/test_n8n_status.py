from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
from contentstudio import n8n_status


def response(value: object) -> io.BytesIO:
    return io.BytesIO(json.dumps(value).encode("utf-8"))


def settings(*, key: str = "test-key") -> SimpleNamespace:
    return SimpleNamespace(
        n8n_api_key=key,
        n8n_health_url="http://n8n:5678/healthz",
        n8n_timeout_seconds=2.0,
    )


class N8nPackStatusTest(unittest.TestCase):
    def test_required_names_match_exported_manifest(self) -> None:
        manifest = json.loads((ROOT / "workflows" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            n8n_status.REQUIRED_WORKFLOW_NAMES,
            {entry["name"] for entry in manifest["workflows"]},
        )

    def test_all_seven_active_across_pages_is_ready(self) -> None:
        names = sorted(n8n_status.REQUIRED_WORKFLOW_NAMES)
        pages = [
            response({"data": [{"name": name, "active": True} for name in names[:3]], "nextCursor": "page-2"}),
            response({"data": [{"name": name, "active": True} for name in names[3:]], "nextCursor": None}),
        ]
        with patch.object(n8n_status.urllib.request, "urlopen", side_effect=pages) as open_url:
            self.assertTrue(n8n_status.contentstudio_pack_ready(settings()))
        self.assertEqual(open_url.call_count, 2)
        request = open_url.call_args_list[0].args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIn("/api/v1/workflows?limit=100", request.full_url)
        self.assertEqual(dict(request.header_items())["X-n8n-api-key"], "test-key")
        self.assertIn("cursor=page-2", open_url.call_args_list[1].args[0].full_url)

    def test_missing_key_or_inactive_workflow_is_not_ready(self) -> None:
        with patch.object(n8n_status.urllib.request, "urlopen") as open_url:
            self.assertFalse(n8n_status.contentstudio_pack_ready(settings(key="")))
            open_url.assert_not_called()
        names = sorted(n8n_status.REQUIRED_WORKFLOW_NAMES)
        rows = [{"name": name, "active": name != names[0]} for name in names]
        with patch.object(n8n_status.urllib.request, "urlopen", return_value=response({"data": rows})):
            self.assertFalse(n8n_status.contentstudio_pack_ready(settings()))

    def test_api_failure_or_invalid_json_is_not_ready(self) -> None:
        with patch.object(n8n_status.urllib.request, "urlopen", side_effect=urllib.error.URLError("offline")):
            self.assertFalse(n8n_status.contentstudio_pack_ready(settings()))
        with patch.object(n8n_status.urllib.request, "urlopen", return_value=io.BytesIO(b"not json")):
            self.assertFalse(n8n_status.contentstudio_pack_ready(settings()))


if __name__ == "__main__":
    unittest.main()

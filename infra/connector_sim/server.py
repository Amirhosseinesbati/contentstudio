"""Local, persistent WordPress/SMTP-style outbox simulator for DEMO only.

It shares the WordPress draft HTTP contract used by the n8n dispatch workflow.
Nothing here sends mail or publishes publicly.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import tempfile
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


DATA_PATH = Path(os.environ.get("SIM_DATA_PATH", "/data/simulator.json"))
WP_USER = os.environ.get("SIM_WORDPRESS_USER", "demo")
WP_PASSWORD = os.environ.get("SIM_WORDPRESS_PASSWORD", "")
CONTROL_TOKEN = os.environ.get("SIM_CONTROL_TOKEN", "")
LOCK = threading.RLock()
FAIL_NEXT: dict[str, object] = {"mode": "", "count": 0, "retry_after": 1}


def load_data() -> dict:
    if not DATA_PATH.exists():
        return {"posts": [], "outbox": [], "next_id": 1001}
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def save_data(data: dict) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=DATA_PATH.parent, delete=False) as tmp:
        json.dump(data, tmp, ensure_ascii=False, sort_keys=True)
        tmp.flush()
        os.fsync(tmp.fileno())
        temp_path = Path(tmp.name)
    temp_path.replace(DATA_PATH)


class Handler(BaseHTTPRequestHandler):
    server_version = "ContentStudioConnectorSim/1"

    def log_message(self, format: str, *args: object) -> None:
        # Never log Authorization or body. stdlib's default line is path/status only.
        print("connector-sim: " + format % args, flush=True)

    def send_json(self, status: int, value: object, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-ContentStudio-Simulated", "true")
        for key, item in (headers or {}).items():
            self.send_header(key, item)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 1_000_000:
                return None
            value = json.loads(self.rfile.read(length))
            return value if isinstance(value, dict) else None
        except (ValueError, json.JSONDecodeError):
            return None

    def check_basic_auth(self) -> bool:
        expected = "Basic " + base64.b64encode(f"{WP_USER}:{WP_PASSWORD}".encode()).decode()
        return bool(WP_PASSWORD) and hmac.compare_digest(self.headers.get("Authorization", ""), expected)

    def check_control(self) -> bool:
        return bool(CONTROL_TOKEN) and hmac.compare_digest(self.headers.get("X-Sim-Control-Token", ""), CONTROL_TOKEN)

    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        if parts.path == "/health":
            self.send_json(200, {"status": "ok", "mode": "simulated"})
            return
        if parts.path == "/wp-json/wp/v2/posts":
            if not self.check_basic_auth():
                self.send_json(401, {"code": "rest_not_logged_in", "message": "Authentication required"})
                return
            query = parse_qs(parts.query)
            slug = query.get("slug", [""])[0]
            status = query.get("status", ["draft"])[0]
            with LOCK:
                posts = [post for post in load_data()["posts"] if (not slug or post["slug"] == slug) and post["status"] == status]
            self.send_json(200, posts)
            return
        if parts.path == "/outbox":
            if not self.check_control():
                self.send_json(403, {"error": "Control token required"})
                return
            with LOCK:
                messages = load_data()["outbox"]
            self.send_json(200, {"items": messages})
            return
        self.send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        parts = urlsplit(self.path)
        if parts.path == "/__control/fail-next":
            if not self.check_control():
                self.send_json(403, {"error": "Control token required"})
                return
            payload = self.read_json()
            if not payload or payload.get("mode") not in {"429", "500", "after_write_timeout"}:
                self.send_json(400, {"error": "mode must be 429, 500 or after_write_timeout"})
                return
            with LOCK:
                FAIL_NEXT.update(mode=payload["mode"], count=min(3, max(1, int(payload.get("count", 1)))), retry_after=min(60, max(1, int(payload.get("retry_after", 1)))))
            self.send_json(200, {"simulated": True, "failure_armed": payload["mode"]})
            return
        if parts.path == "/outbox":
            if not self.check_control():
                self.send_json(403, {"error": "Control token required"})
                return
            payload = self.read_json()
            if not payload or not str(payload.get("to", "")).endswith(("@example.com", ".test")):
                self.send_json(400, {"error": "Only reserved demo recipients are allowed"})
                return
            with LOCK:
                data = load_data()
                data["outbox"].append({"id": len(data["outbox"]) + 1, **payload, "simulated": True})
                save_data(data)
            self.send_json(201, {"queued": True, "simulated": True})
            return
        if parts.path != "/wp-json/wp/v2/posts":
            self.send_json(404, {"error": "Not found"})
            return
        if not self.check_basic_auth():
            self.send_json(401, {"code": "rest_not_logged_in", "message": "Authentication required"})
            return
        payload = self.read_json()
        operation_key = self.headers.get("Idempotency-Key", "")
        if not payload or not operation_key or len(operation_key) > 200:
            self.send_json(400, {"error": "JSON body and Idempotency-Key required"})
            return
        if payload.get("status") != "draft" or not all(payload.get(key) for key in ("title", "content", "slug")):
            self.send_json(400, {"error": "Draft title, content, slug and status=draft required"})
            return
        body_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with LOCK:
            mode = str(FAIL_NEXT["mode"]) if int(FAIL_NEXT["count"]) > 0 else ""
            if mode:
                FAIL_NEXT["count"] = int(FAIL_NEXT["count"]) - 1
            if mode == "429":
                self.send_json(429, {"code": "rest_rate_limited", "message": "Simulated rate limit"}, {"Retry-After": str(FAIL_NEXT["retry_after"])})
                return
            if mode == "500":
                self.send_json(500, {"code": "simulated_provider_failure", "message": "Simulated 500"})
                return
            data = load_data()
            existing = next((post for post in data["posts"] if post["operation_key"] == operation_key), None)
            if existing and existing["body_hash"] != body_hash:
                self.send_json(409, {"error": "Conflicting duplicate operation key"})
                return
            if existing:
                post = existing
            else:
                post = {
                    "id": data["next_id"],
                    "slug": payload["slug"],
                    "status": "draft",
                    "title": {"rendered": payload["title"]},
                    "content": {"rendered": payload["content"]},
                    "excerpt": {"rendered": payload.get("excerpt", "")},
                    "link": f"http://connector-sim:8081/?p={data['next_id']}",
                    "operation_key": operation_key,
                    "body_hash": body_hash,
                    "simulated": True,
                }
                data["next_id"] += 1
                data["posts"].append(post)
                save_data(data)
        if mode == "after_write_timeout":
            self.close_connection = True
            return
        self.send_json(HTTPStatus.CREATED if not existing else HTTPStatus.OK, post)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8081), Handler)
    print("ContentStudio simulated connector listening on 8081", flush=True)
    server.serve_forever()

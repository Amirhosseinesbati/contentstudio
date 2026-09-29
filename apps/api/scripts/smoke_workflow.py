"""Exercise the seeded local approval, render and package API path once."""

import json
import os
import time
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("SERVICE_TOKEN", "local-smoke-token")
local_ffmpeg = Path(__file__).resolve().parents[3] / "tmp/ffmpeg-package/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe"
if local_ffmpeg.is_file():
    os.environ.setdefault("CONTENTSTUDIO_FFMPEG", str(local_ffmpeg))

from contentstudio.config import get_settings  # noqa: E402
from contentstudio.main import app  # noqa: E402


def main():
    settings = get_settings()
    if settings.mode != "demo":
        raise RuntimeError("This smoke test is for synthetic demo only")
    started = time.monotonic()
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@studio.test",
                "password": settings.demo_password,
            },
        )
        login.raise_for_status()
        workspace_id = login.json()["user"]["workspace_id"]
        batches = client.get("/api/v1/batches").json()["items"]
        showcase = next(batch for batch in batches if batch["recipe_version"] == "v1")
        detail = client.get(f"/api/v1/batches/{showcase['id']}").json()
        targets = [
            asset
            for asset in detail["assets"]
            if asset["asset_type"] in ("article", "carousel", "clip")
        ]
        assert len(targets) == 5
        headers = {"X-Service-Token": settings.service_token}
        rendered = []
        for asset in targets:
            if asset["status"] == "review_pending":
                response = client.post(
                    f"/api/v1/assets/{asset['id']}/review",
                    json={"decision": "approve", "expected_hash": asset["content_hash"]},
                )
                assert response.status_code == 200, response.text
            if asset["asset_type"] in ("carousel", "clip"):
                response = client.post(
                    "/internal/workflows/render",
                    headers=headers,
                    json={"workspace_id": workspace_id, "asset_version_id": asset["id"]},
                )
                assert response.status_code == 200, response.text
                assert response.json()["status"] == "complete", response.text
                rendered.append(response.json()["render_urls"])
        queued = client.post(f"/api/v1/batches/{showcase['id']}/package")
        assert queued.status_code == 202, queued.text
        response = client.post(
            "/internal/workflows/package",
            headers=headers,
            json={"workspace_id": workspace_id, "batch_id": showcase["id"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "complete"
        with client.stream("GET", f"/api/v1/batches/{showcase['id']}/download") as package_response:
            assert package_response.status_code == 200
            assert next(package_response.iter_bytes())[:2] == b"PK"
        package_path = settings.media_root.resolve() / workspace_id / showcase["id"] / "content-package.zip"
        with zipfile.ZipFile(package_path) as archive:
            names = archive.namelist()
            assert "manifest.json" in names
            assert sum(name.endswith(".mp4") for name in names) == 3
            assert sum(name.endswith(".png") for name in names) == 7
            assert any(name.endswith(".pdf") for name in names)
        print(json.dumps({"status": "complete", "rendered_assets": len(rendered), "package_files": len(names), "elapsed_seconds": round(time.monotonic() - started, 2), "download_url": response.json()["download_url"]}, indent=2))


if __name__ == "__main__":
    main()

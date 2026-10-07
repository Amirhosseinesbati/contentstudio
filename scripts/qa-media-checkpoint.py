"""Actual local media/ZIP QA with fixture AI and direct internal API step calls.

Uses installed FFmpeg, existing owned synthetic media, and a copied database.
This is not an actual n8n-triggered run or a connected provider evaluation.
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))


def main():
    output = ROOT / "tmp/media-checkpoint"
    output.mkdir(parents=True, exist_ok=True)
    database = output / f"qa-{int(time.time())}.db"
    shutil.copyfile(ROOT / "tmp/preview/contentstudio.db", database)
    ffmpeg = ROOT / "tmp/ffmpeg-package/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe"
    if not ffmpeg.is_file():
        raise RuntimeError("Existing local FFmpeg installation required")
    os.environ.update({
        "MODE": "demo", "DATABASE_URL": f"sqlite:///{database.as_posix()}",
        "FIXTURES_ROOT": str(ROOT / "fixtures"), "MEDIA_ROOT": str(ROOT / "apps/api/data/media"),
        "MODEL_PROVIDER": "fixture", "TRANSCRIPTION_PROVIDER": "fixture",
        "OPENAI_API_KEY": "", "N8N_INTAKE_WEBHOOK": "", "N8N_HEALTH_URL": "",
        "WORDPRESS_BASE_URL": "", "SERVICE_TOKEN": "media-checkpoint-local",
        "CONTENTSTUDIO_FFMPEG": str(ffmpeg), "MEDIA_RENDER_THREADS": "2",
    })
    from fastapi.testclient import TestClient

    from contentstudio.main import app
    started = time.perf_counter()
    headers = {"X-Service-Token": "media-checkpoint-local"}
    def checked(response):
        response.raise_for_status()
        return response.json()
    with TestClient(app) as client:
        user = checked(client.post("/api/v1/auth/login", json={"email": "admin@studio.test", "password": "DemoStudio!2026"}))["user"]
        sources = checked(client.get("/api/v1/sources"))["items"]
        source = next(item for item in sources if item["kind"] == "owned_media" and item["latest_transcript_version_id"])
        brand = checked(client.post("/api/v1/brands", json={"name": f"Fidelity QA {int(time.time())}", "tone": "Careful and practical", "rules": {"accent": "#234567"}}))
        intake = checked(client.post("/internal/workflows/intake", headers=headers, json={
            "workspace_id": user["workspace_id"], "source_asset_id": source["id"],
            "brand_profile_version_id": brand["id"], "recipe_version": "checkpoint-v2", "request_id": f"qa-{brand['id']}",
        }))
        step = {"workspace_id": user["workspace_id"], "batch_id": intake["batch_id"]}
        checked(client.post("/internal/workflows/transcribe", headers=headers, json=step))
        bundle = checked(client.post("/internal/workflows/generate", headers=headers, json=step))
        assert len(bundle["assets"]) == 11
        selected = [next(asset for asset in bundle["assets"] if asset["asset_type"] == kind) for kind in ("article", "carousel", "clip")]
        renders = []
        for asset in selected:
            assert not asset["warnings"], asset["warnings"]
            checked(client.post(f"/api/v1/assets/{asset['id']}/review", json={"decision": "approve", "expected_hash": asset["content_hash"]}))
            if asset["asset_type"] == "article":
                continue
            render_step = {"workspace_id": user["workspace_id"], "asset_version_id": asset["id"]}
            result = checked(client.post("/internal/workflows/render", headers=headers, json=render_step))
            repeated = checked(client.post("/internal/workflows/render", headers=headers, json=render_step))
            assert repeated["job_id"] == result["job_id"] and repeated["render_urls"] == result["render_urls"]
            urls = result["render_urls"]
            for url in [*urls["png"], urls["pdf"], urls["mp4"]]:
                if url:
                    assert client.get(url).status_code == 200
            renders.append({"asset_id": asset["id"], "type": asset["asset_type"], "urls": urls})
        package = checked(client.post("/internal/workflows/package", headers=headers, json=step))
        downloaded = client.get(package["download_url"])
        downloaded.raise_for_status()
        target = output / "publication-package.zip"
        target.write_bytes(downloaded.content)
        with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["brand"]["id"] == brand["id"]
            assert len(manifest["approvals"]) == 3
            for item in manifest["files"]:
                data = archive.read(item["path"])
                assert len(data) == item["bytes"] and hashlib.sha256(data).hexdigest() == item["sha256"]
            clip_name = next(name for name in archive.namelist() if name.endswith("clip.mp4"))
            clip = output / "clip.mp4"
            clip.write_bytes(archive.read(clip_name))
            decoded = subprocess.run([str(ffmpeg), "-v", "error", "-threads", "2", "-i", str(clip), "-f", "null", "-"], capture_output=True, text=True, timeout=120)
            assert decoded.returncode == 0 and not decoded.stderr.strip(), decoded.stderr
            from PIL import Image
            png_name = next(name for name in archive.namelist() if name.endswith(".png"))
            with Image.open(io.BytesIO(archive.read(png_name))) as image:
                assert image.size == (1080, 1350)
            file_count = len(archive.namelist())
        report = {"label": "Actual installed FFmpeg + owned synthetic recordings; fixture AI/direct API steps", "source_id": source["id"], "batch_id": intake["batch_id"], "brand_id": brand["id"], "generated_asset_count": 11, "approved_packaged_assets": 3, "manifest_schema": 2, "package_files": file_count, "package_bytes": len(downloaded.content), "clip_full_decode_ok": True, "carousel_dimensions": [1080, 1350], "render_replay_idempotent": True, "file_hashes_verified": True, "n8n_triggered": False, "connected_providers_called": False, "wall_seconds": round(time.perf_counter() - started, 2)}
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

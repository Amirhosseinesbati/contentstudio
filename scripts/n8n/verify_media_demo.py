"""Run one DEMO batch through n8n render/package and save redacted evidence."""

from __future__ import annotations

import datetime as dt
import http.cookiejar
import io
import json
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from bootstrap import api_request
from PIL import Image
from provision_demo import read_env

ROOT = Path(__file__).resolve().parents[2]
API = "http://127.0.0.1:8000"


def main() -> None:
    env = read_env()
    if env.get("MODE") != "demo":
        raise RuntimeError("This acceptance run requires MODE=demo")
    latest = max((ROOT / "workflows" / "evidence").glob("replay-*.json"))
    replay = json.loads(latest.read_text(encoding="utf-8"))
    batch_id = next(item["batch_id"] for item in replay["triggered_events"] if item["scenario"] == "intake-1")
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def business(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(API + "/api/v1" + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        with opener.open(req, timeout=30) as response:
            return json.load(response)

    login = business("POST", "/auth/login", {"email": "admin@studio.test", "password": env["DEMO_PASSWORD"]})
    workspace_id = login["user"]["workspace_id"]
    n8n_url = env["N8N_PUBLIC_URL"]
    api_key = env["N8N_API_KEY"]
    workflows = api_request(n8n_url, api_key, "GET", "/workflows?limit=100")["data"]
    workflow_ids = {item["name"]: item["id"] for item in workflows}
    render_id = workflow_ids["ContentStudio / Render approved asset"]
    due_id = workflow_ids["ContentStudio / Process due editorial actions"]

    def executions(workflow_id: str) -> list[dict[str, Any]]:
        result = api_request(n8n_url, api_key, "GET", "/executions?limit=100")
        return [item for item in result["data"] if item["workflowId"] == workflow_id]

    def trigger_due() -> int:
        req = urllib.request.Request(
            n8n_url.rstrip("/") + "/webhook/contentstudio/due-demo", data=b"{}", method="POST",
            headers={"X-Service-Token": env["SERVICE_TOKEN"], "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            if response.status != 202:
                raise RuntimeError(f"Due webhook returned HTTP {response.status}")
            return response.status

    def wait_job(job_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            job = business("GET", "/jobs/" + job_id)
            if job["status"] == "complete":
                return job
            if job["status"] in {"failed", "cancelled"}:
                raise RuntimeError(f"Job {job_id} ended as {job['status']}: {job.get('error', '')[:200]}")
            time.sleep(2)
        raise RuntimeError(f"Job {job_id} exceeded five minutes")

    def new_success(workflow_id: str, before: set[str]) -> str:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            fresh = [row for row in executions(workflow_id) if row["id"] not in before]
            success = next((row for row in fresh if row["status"] == "success"), None)
            if success:
                return success["id"]
            time.sleep(1)
        raise RuntimeError(f"No new successful n8n execution for workflow {workflow_id}")

    batch = business("GET", "/batches/" + batch_id)
    assets = [item for item in batch["assets"] if item["asset_type"] in {"carousel", "clip"}]
    if len(assets) != 4 or [item["asset_type"] for item in assets].count("clip") != 3:
        raise RuntimeError("Expected one carousel and three clip versions")
    report: dict[str, Any] = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "environment": "local-demo", "simulated_external_systems": True,
        "source_retranscribed": False, "batch_id": batch_id, "workspace_id": workspace_id,
        "renders": [], "package": {}, "payloads_and_secrets_saved": False,
    }
    for asset in assets:
        if asset["warnings"]:
            raise RuntimeError(f"Asset {asset['id']} has approval warnings")
        before_render = {row["id"] for row in executions(render_id)}
        before_due = {row["id"] for row in executions(due_id)}
        if asset["status"] == "review_pending":
            business("POST", "/assets/" + asset["id"] + "/review", {
                "decision": "approve", "expected_hash": asset["content_hash"],
            })
        elif asset["status"] not in {"approved", "rendered"}:
            raise RuntimeError(f"Asset {asset['id']} has unexpected status {asset['status']}")
        job = business("POST", "/assets/" + asset["id"] + "/render")
        start = time.monotonic()
        trigger_due()
        stats: dict[str, str] | None = None
        if asset["asset_type"] == "clip":
            time.sleep(2)
            sample = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}|{{.MemUsage}}", "contentstudio-api-1"],
                capture_output=True, text=True, timeout=15, check=True,
            ).stdout.strip()
            cpu, memory = sample.split("|", 1)
            stats = {"cpu": cpu, "memory": memory}
        finished = wait_job(job["id"])
        elapsed = round(time.monotonic() - start, 2)
        render_exec = new_success(render_id, before_render)
        due_exec = new_success(due_id, before_due)
        report["renders"].append({
            "asset_version_id": asset["id"], "asset_type": asset["asset_type"],
            "job_id": job["id"], "job_status": finished["status"],
            "due_execution_id": due_exec, "render_execution_id": render_exec,
            "elapsed_seconds": elapsed, "api_container_sample": stats,
        })
        print(f"rendered {asset['asset_type']} {asset['id'][:8]} in {elapsed}s", flush=True)

    before_due = {row["id"] for row in executions(due_id)}
    package_job = business("POST", "/batches/" + batch_id + "/package")
    start = time.monotonic()
    trigger_due()
    finished = wait_job(package_job["id"])
    elapsed = round(time.monotonic() - start, 2)
    due_exec = new_success(due_id, before_due)
    req = urllib.request.Request(API + "/api/v1/batches/" + batch_id + "/download")
    with opener.open(req, timeout=60) as response:
        archive_bytes = response.read()
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Downloaded ZIP failed CRC validation")
        names = archive.namelist()
        pngs = [name for name in names if name.lower().endswith(".png")]
        mp4s = [name for name in names if name.lower().endswith(".mp4")]
        pdfs = [name for name in names if name.lower().endswith(".pdf")]
        if len(mp4s) != 3 or not pngs or len(pdfs) != 1:
            raise RuntimeError("Package is missing expected carousel or clip renders")
        image_dimensions = []
        for name in pngs:
            with Image.open(io.BytesIO(archive.read(name))) as image:
                image.verify()
                image_dimensions.append({"member": name, "width": image.width, "height": image.height})
        pdf_bytes = archive.read(pdfs[0])
        if not pdf_bytes.startswith(b"%PDF-") or b"%%EOF" not in pdf_bytes[-1024:]:
            raise RuntimeError("Carousel PDF structure is invalid")
    latest_batch = business("GET", "/batches/" + batch_id)
    clips = [item for item in latest_batch["assets"] if item["asset_type"] == "clip"]
    video_metadata = []
    for clip in clips:
        filename = Path(clip["render_urls"]["mp4"]).name
        path = f"/data/media/{workspace_id}/{batch_id}/{clip['id']}/{filename}"
        result = subprocess.run(
            ["docker", "exec", "contentstudio-api-1", "ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,duration", "-of", "json", path],
            capture_output=True, text=True, timeout=30, check=True,
        )
        stream = json.loads(result.stdout)["streams"][0]
        if float(stream["duration"]) <= 0 or int(stream["width"]) <= 0 or int(stream["height"]) <= 0:
            raise RuntimeError(f"Invalid rendered MP4 stream for {clip['id']}")
        video_metadata.append({
            "asset_version_id": clip["id"], "width": int(stream["width"]),
            "height": int(stream["height"]), "duration_seconds": float(stream["duration"]),
        })
    report["package"] = {
        "job_id": package_job["id"], "job_status": finished["status"],
        "due_execution_id": due_exec, "elapsed_seconds": elapsed,
        "zip_bytes": len(archive_bytes), "zip_crc_valid": True,
        "member_count": len(names), "png_dimensions": image_dimensions,
        "pdf_count": len(pdfs), "mp4_streams": video_metadata,
    }
    out = ROOT / "workflows" / "evidence" / f"media-{replay['run_id']}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Redacted media evidence: {out}", flush=True)


if __name__ == "__main__":
    main()

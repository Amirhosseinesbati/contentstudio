"""Trigger five unique intake scenarios in actual n8n and save redacted evidence.

Requires the running DEMO stack, imported/activated workflows, a service token,
and an n8n API key. No external recipient or provider is used.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from bootstrap import N8nAPIError, api_request, list_workflows, load_private_env

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_ASSET_TYPES = {"article": 1, "newsletter": 1, "social": 5, "carousel": 1, "clip": 3}
TERMINAL_EXECUTION_STATUSES = {"success", "error", "crashed", "canceled"}


def call_json(url: str, token: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode(),
        method="GET" if body is None else "POST",
        headers={"X-Service-Token": token, "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        return error.code, None


def executions(base: str, api_key: str, workflow_id: str) -> list[dict[str, Any]]:
    value = api_request(base, api_key, "GET", f"/executions?workflowId={workflow_id}&limit=100")
    return value.get("data", [])


def scenario_status(api_url: str, token: str, workspace_id: str, request_id: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"workspace_id": workspace_id, "request_id": request_id})
    status, body = call_json(
        api_url.rstrip("/") + "/internal/workflows/demo-scenario-status?" + query, token
    )
    if status != 200 or not isinstance(body, dict):
        raise RuntimeError(f"Demo scenario status endpoint returned HTTP {status}")
    return body


def fresh_fixture(original: dict[str, Any], run_id: str, index: int) -> dict[str, Any]:
    """A replay must create a new batch, not pass by reading a previous run."""
    return original | {
        "recipe_version": f"scenario-{run_id}",
        "request_id": f"replay-{run_id}-{index}",
    }


def validate_bundle(status: dict[str, Any], body: dict[str, Any]) -> None:
    if not status.get("observed"):
        raise RuntimeError("n8n reported success but no webhook event was persisted")
    if status.get("source_asset_id") != body["source_asset_id"]:
        raise RuntimeError("Persisted batch belongs to a different source")
    if status.get("recipe_version") != body["recipe_version"]:
        raise RuntimeError("Persisted batch has a different recipe version")
    if status.get("status") not in ("review", "complete"):
        raise RuntimeError(f"Persisted batch is not reviewable: {status.get('status')}")
    if status.get("asset_type_counts") != EXPECTED_ASSET_TYPES:
        raise RuntimeError(f"Persisted asset bundle is incomplete: {status.get('asset_type_counts')}")
    if status.get("asset_count") != 11 or status.get("claim_count", 0) < 1:
        raise RuntimeError("Persisted batch lacks eleven assets or source-backed claims")
    if status.get("matching_batch_count") != 1:
        raise RuntimeError("Scenario created more than one matching content batch")


def wait_for_execution(
    base: str,
    api_key: str,
    workflow_id: str,
    seen_ids: set[str],
    expected_status: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        recent = [row for row in executions(base, api_key, workflow_id) if str(row["id"]) not in seen_ids]
        terminal = [row for row in recent if row.get("status") in TERMINAL_EXECUTION_STATUSES]
        if len(terminal) > 1:
            raise RuntimeError("Multiple new terminal executions appeared; scenario attribution is ambiguous")
        if terminal:
            row = terminal[0]
            if row.get("status") != expected_status:
                raise RuntimeError(
                    f"Expected n8n execution {expected_status}, observed {row.get('status')}"
                )
            seen_ids.add(str(row["id"]))
            return row
        time.sleep(3)
    raise RuntimeError(
        f"No new {expected_status} execution was saved within {timeout_seconds}s; "
        "check successful execution persistence and workflow activation"
    )


def execution_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in ("id", "workflowId", "status", "startedAt", "stoppedAt", "mode")}


def run_acceptance(args: argparse.Namespace) -> int:
    workflows = list_workflows(args.n8n_url, args.api_key)
    names = {
        "intake": "ContentStudio / Intake owned source",
        "error": "ContentStudio / Shared execution error",
    }
    for name in names.values():
        if name not in workflows:
            raise RuntimeError(f"Workflow not imported: {name}")
    intake_id = workflows[names["intake"]]["id"]
    error_id = workflows[names["error"]]["id"]
    seen_intake = {str(item["id"]) for item in executions(args.n8n_url, args.api_key, intake_id)}
    seen_error = {str(item["id"]) for item in executions(args.n8n_url, args.api_key, error_id)}
    fixture_status, fixtures = call_json(
        args.api_url.rstrip("/") + "/internal/workflows/demo-fixtures", args.service_token
    )
    if fixture_status != 200 or not isinstance(fixtures, dict) or len(fixtures.get("items", [])) < 5:
        raise RuntimeError("Backend did not supply five seeded demo fixture request bodies")
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + secrets.token_hex(3)
    bodies = [fresh_fixture(original, run_id, index) for index, original in enumerate(fixtures["items"][:5], 1)]
    events: list[dict[str, Any]] = []
    intake_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    webhook = args.n8n_url.rstrip("/") + "/webhook/contentstudio/intake"

    for index, body in enumerate(bodies, 1):
        response_status, _ = call_json(webhook, args.service_token, body)
        if response_status != 202:
            raise RuntimeError(f"intake-{index} returned HTTP {response_status}, expected 202")
        execution = wait_for_execution(
            args.n8n_url, args.api_key, intake_id, seen_intake, "success", args.timeout_seconds
        )
        state = scenario_status(args.api_url, args.service_token, body["workspace_id"], body["request_id"])
        validate_bundle(state, body)
        intake_rows.append(execution_metadata(execution))
        events.append({
            "scenario": f"intake-{index}", "webhook_status": response_status,
            "execution_id": execution["id"], "batch_id": state["batch_id"],
            "asset_count": state["asset_count"], "claim_count": state["claim_count"],
            "asset_type_counts": state["asset_type_counts"], "persisted_status": state["status"],
        })

    first = bodies[0]
    original = scenario_status(args.api_url, args.service_token, first["workspace_id"], first["request_id"])
    duplicate_status, _ = call_json(webhook, args.service_token, first)
    if duplicate_status != 202:
        raise RuntimeError(f"Duplicate event returned HTTP {duplicate_status}, expected 202")
    duplicate_execution = wait_for_execution(
        args.n8n_url, args.api_key, intake_id, seen_intake, "success", args.timeout_seconds
    )
    duplicate_state = scenario_status(args.api_url, args.service_token, first["workspace_id"], first["request_id"])
    if duplicate_state != original or duplicate_state["matching_batch_count"] != 1:
        raise RuntimeError("Duplicate event changed the existing batch or created another batch")
    intake_rows.append(execution_metadata(duplicate_execution))
    events.append({
        "scenario": "same-event-duplicate", "webhook_status": duplicate_status,
        "execution_id": duplicate_execution["id"], "batch_id": duplicate_state["batch_id"],
        "duplicate_preserved_batch": True,
    })

    rejected_cases = [
        ("conflicting-event-id", first | {"recipe_version": first["recipe_version"] + "-conflict"}),
        ("malformed-event-error-trigger", {"workspace_id": first["workspace_id"], "request_id": f"malformed-{run_id}"}),
    ]
    for label, payload in rejected_cases:
        response_status, _ = call_json(webhook, args.service_token, payload)
        if response_status != 202:
            raise RuntimeError(f"{label} returned HTTP {response_status}, expected webhook 202")
        execution = wait_for_execution(
            args.n8n_url, args.api_key, intake_id, seen_intake, "error", args.timeout_seconds
        )
        error_execution = wait_for_execution(
            args.n8n_url, args.api_key, error_id, seen_error, "success", args.timeout_seconds
        )
        intake_rows.append(execution_metadata(execution))
        error_rows.append(execution_metadata(error_execution))
        if label == "conflicting-event-id":
            state = scenario_status(args.api_url, args.service_token, first["workspace_id"], first["request_id"])
            if state != original:
                raise RuntimeError("Conflicting event modified the original event or batch")
        else:
            state = scenario_status(args.api_url, args.service_token, payload["workspace_id"], payload["request_id"])
            if state.get("observed"):
                raise RuntimeError("Malformed event unexpectedly entered the durable event ledger")
        events.append({
            "scenario": label, "webhook_status": response_status,
            "execution_id": execution["id"], "error_workflow_execution_id": error_execution["id"],
            "rejected_without_state_change": True,
        })

    evidence = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "environment": "local-demo", "simulated_external_systems": True,
        "workflow_version": "2.40.7", "run_id": run_id,
        "triggered_events": events,
        "intake_executions": intake_rows,
        "error_handler_executions": error_rows,
        "payloads_and_secrets_saved": False,
    }
    path = args.out or (ROOT / "workflows" / "evidence" / f"replay-{run_id}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"Redacted execution evidence: {path}")
    print("Five new review bundles, one idempotent duplicate, and two rejected events verified")
    return 0


def main() -> int:
    load_private_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n8n-url", default=os.getenv("N8N_PUBLIC_URL", "http://localhost:5678"))
    parser.add_argument("--api-url", default=os.getenv("API_PUBLIC_URL", "http://localhost:8000"))
    parser.add_argument("--service-token", default=os.getenv("SERVICE_TOKEN"))
    parser.add_argument("--api-key", default=os.getenv("N8N_API_KEY"))
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    if not args.service_token or not args.api_key:
        parser.error("SERVICE_TOKEN and N8N_API_KEY are required")
    if args.timeout_seconds < 3:
        parser.error("--timeout-seconds must be at least 3")
    return run_acceptance(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, N8nAPIError, KeyError, urllib.error.URLError) as error:
        print(f"replay failed: {error}", file=sys.stderr)
        sys.exit(1)

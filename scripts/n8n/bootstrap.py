"""Idempotently import ContentStudio workflows through the n8n public API.

No credentials or endpoint URLs are stored in committed workflow exports. Create
two credentials in n8n before running this script:
  * Header Auth: X-Service-Token = SERVICE_TOKEN
  * Basic Auth: WordPress application user/password (demo simulator in DEMO)

The script never activates workflows unless --activate-demo is specified.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "workflows" / "manifest.json"


class N8nAPIError(RuntimeError):
    pass


def load_private_env() -> None:
    """Read only simple KEY=VALUE lines from the local, ignored .env file."""
    env_file = ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.isidentifier():
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def api_request(base: str, api_key: str, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        base.rstrip("/") + "/api/v1" + path,
        data=data,
        method=method,
        headers={"X-N8N-API-KEY": api_key, "Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        # API errors can echo request data, including credential IDs. Never log bodies.
        raise N8nAPIError(f"{method} {path}: HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise N8nAPIError(f"{method} {path}: n8n is unreachable ({error.reason})") from error


def list_workflows(base: str, api_key: str) -> dict[str, dict[str, Any]]:
    cursor: str | None = None
    result: dict[str, dict[str, Any]] = {}
    while True:
        query = "?limit=250" + ("&cursor=" + urllib.parse.quote(cursor, safe="") if cursor else "")
        page = api_request(base, api_key, "GET", "/workflows" + query)
        for item in page.get("data", []):
            result[item["name"]] = item
        cursor = page.get("nextCursor")
        if not cursor:
            return result


def replace_placeholders(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: replace_placeholders(part, replacements) for key, part in value.items()}
    if isinstance(value, list):
        return [replace_placeholders(part, replacements) for part in value]
    if isinstance(value, str):
        for token, replacement in replacements.items():
            value = value.replace(token, replacement)
        return value
    return value


def validate_wordpress_base_url(url: str, mode: str) -> None:
    """Keep Basic Auth credentials off cleartext networks in connected mode."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("WordPress base URL must be an HTTP(S) URL with a host")
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ValueError("WordPress base URL must not contain credentials, a query or a fragment")
    if parsed.scheme == "https":
        return
    local_simulators = {"connector-sim", "localhost", "127.0.0.1", "::1"}
    if mode.lower() != "demo" or parsed.hostname not in local_simulators:
        raise ValueError("WordPress HTTP is allowed only for the local DEMO simulator; CONNECTED requires HTTPS")


def compile_workflow(entry: dict[str, Any], replacements: dict[str, str]) -> dict[str, Any]:
    source = json.loads((MANIFEST.parent / entry["file"]).read_text(encoding="utf-8"))
    compiled = replace_placeholders(source, replacements)
    unresolved = json.dumps(compiled)
    if "__workflow:" in unresolved or "__SERVICE_CREDENTIAL_ID__" in unresolved or "__WORDPRESS_CREDENTIAL_ID__" in unresolved or "__API_BASE_URL__" in unresolved or "__WORDPRESS_BASE_URL__" in unresolved:
        raise N8nAPIError(f"Unresolved reference in {entry['file']}")
    return {field: compiled[field] for field in ("name", "nodes", "connections", "settings")}


def verify_readback(expected: dict[str, Any], saved: dict[str, Any]) -> None:
    actual_nodes = {node["name"]: node for node in saved.get("nodes", [])}
    if len(actual_nodes) != len(expected["nodes"]):
        raise N8nAPIError(f"Readback node count mismatch for {expected['name']}")
    for node in expected["nodes"]:
        actual = actual_nodes.get(node["name"])
        if actual is None or actual.get("type") != node["type"]:
            raise N8nAPIError(f"Readback node type mismatch: {node['name']}")
        for kind, reference in node.get("credentials", {}).items():
            if actual.get("credentials", {}).get(kind, {}).get("id") != reference["id"]:
                raise N8nAPIError(f"Credential reference mismatch: {node['name']}")
        if node["type"] == "n8n-nodes-base.executeWorkflow":
            wanted = node["parameters"]["workflowId"]["value"]
            actual_id = actual.get("parameters", {}).get("workflowId", {}).get("value")
            if actual_id != wanted:
                raise N8nAPIError(f"Sub-workflow reference mismatch: {node['name']}")
    wanted_error = expected["settings"].get("errorWorkflow")
    if wanted_error and saved.get("settings", {}).get("errorWorkflow") != wanted_error:
        raise N8nAPIError(f"Error-workflow reference mismatch for {expected['name']}")


def main() -> int:
    load_private_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n8n-url", default=os.getenv("N8N_PUBLIC_URL", "http://localhost:5678"))
    parser.add_argument("--api-base-url", default=os.getenv("API_BASE_URL", "http://api:8000"))
    parser.add_argument("--wordpress-base-url", default=os.getenv("WORDPRESS_BASE_URL", "http://connector-sim:8081"))
    parser.add_argument("--service-credential-id", default=os.getenv("N8N_SERVICE_CREDENTIAL_ID"))
    parser.add_argument("--wordpress-credential-id", default=os.getenv("N8N_WORDPRESS_CREDENTIAL_ID"))
    parser.add_argument("--api-key", default=os.getenv("N8N_API_KEY"))
    parser.add_argument("--activate-demo", action="store_true", help="Publish demo entrypoints and their pack dependencies")
    parser.add_argument("--dry-run", action="store_true", help="Validate and compile with placeholder IDs, without contacting n8n")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest["n8n_version"] != "2.40.7":
        raise N8nAPIError("Workflow pack version differs from pinned Docker image")
    if not args.dry_run and (not args.api_key or not args.service_credential_id or not args.wordpress_credential_id):
        parser.error("N8N_API_KEY, N8N_SERVICE_CREDENTIAL_ID and N8N_WORDPRESS_CREDENTIAL_ID are required")
    if args.activate_demo and args.dry_run:
        parser.error("--activate-demo requires an n8n instance")
    mode = os.getenv("MODE", "demo").lower()
    if args.activate_demo:
        if mode != "demo":
            parser.error("--activate-demo is allowed only when MODE=demo")
        simulator_hosts = {"connector-sim", "localhost", "127.0.0.1"}
        if urllib.parse.urlsplit(args.wordpress_base_url).hostname not in simulator_hosts:
            parser.error("--activate-demo requires a local WordPress simulator URL")
    if urllib.parse.urlsplit(args.api_base_url).scheme not in {"http", "https"}:
        parser.error("--api-base-url must be HTTP(S)")
    try:
        validate_wordpress_base_url(args.wordpress_base_url, mode)
    except ValueError as error:
        parser.error(str(error))

    replacements = {
        "__API_BASE_URL__": args.api_base_url.rstrip("/"),
        "__WORDPRESS_BASE_URL__": args.wordpress_base_url.rstrip("/"),
        "__SERVICE_CREDENTIAL_ID__": args.service_credential_id or "dry-service-id",
        "__WORDPRESS_CREDENTIAL_ID__": args.wordpress_credential_id or "dry-wordpress-id",
    }
    existing = {} if args.dry_run else list_workflows(args.n8n_url, args.api_key)
    ids: dict[str, str] = {}
    entries = sorted(manifest["workflows"], key=lambda entry: entry["import_order"])
    for entry in entries:
        for dependency in entry["dependencies"]:
            if dependency not in ids:
                raise N8nAPIError(f"Import order invalid: {entry['key']} requires {dependency}")
        scoped_replacements = replacements | {f"__workflow:{key}__": value for key, value in ids.items()}
        compiled = compile_workflow(entry, scoped_replacements)
        if args.dry_run:
            ids[entry["key"]] = f"dry-{entry['key']}"
            print(f"validated {entry['file']}: {len(compiled['nodes'])} nodes")
            continue
        old = existing.get(compiled["name"])
        if old:
            workflow_id = old["id"]
            if old.get("active"):
                api_request(args.n8n_url, args.api_key, "POST", f"/workflows/{workflow_id}/deactivate", {})
            api_request(args.n8n_url, args.api_key, "PUT", f"/workflows/{workflow_id}", compiled)
            operation = "updated"
        else:
            created = api_request(args.n8n_url, args.api_key, "POST", "/workflows", compiled)
            workflow_id = created["id"]
            operation = "created"
        ids[entry["key"]] = workflow_id
        saved = api_request(args.n8n_url, args.api_key, "GET", f"/workflows/{workflow_id}")
        verify_readback(compiled, saved)
        print(f"{operation} {entry['key']}: {workflow_id} (inactive)")
    if args.activate_demo:
        for entry in entries:
            if entry["activate_for_demo"]:
                api_request(args.n8n_url, args.api_key, "POST", f"/workflows/{ids[entry['key']]}/activate", {})
                print(f"published demo pack workflow: {entry['key']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (N8nAPIError, OSError, ValueError, KeyError) as error:
        print(f"bootstrap failed: {error}", file=sys.stderr)
        sys.exit(1)

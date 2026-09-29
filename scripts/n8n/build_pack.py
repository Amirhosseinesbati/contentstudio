"""Build the deterministic, secret-free ContentStudio n8n export pack.

Run `python scripts/n8n/build_pack.py` after changing a workflow definition.
The generated JSON is intentionally committed and can be imported through
`bootstrap.py`, which resolves real instance IDs and credential references.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "workflows"
NAMESPACE = uuid.UUID("6c103294-c28f-44c9-9767-0a30f3779724")
SERVICE_CREDENTIAL = {"httpHeaderAuth": {"id": "__SERVICE_CREDENTIAL_ID__", "name": "ContentStudio service token"}}
WORDPRESS_CREDENTIAL = {"httpBasicAuth": {"id": "__WORDPRESS_CREDENTIAL_ID__", "name": "ContentStudio WordPress draft"}}
API = "__API_BASE_URL__/internal/workflows"


def node_id(flow: str, name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{flow}:{name}"))


class Flow:
    def __init__(self, key: str, name: str, *, error: bool = True) -> None:
        self.key, self.name = key, name
        self.nodes: list[dict[str, Any]] = []
        self.connections: dict[str, dict[str, Any]] = {}
        self.error = error

    def add(
        self,
        name: str,
        kind: str,
        version: float,
        parameters: dict[str, Any],
        x: int,
        y: int = 220,
        *,
        credentials: dict[str, Any] | None = None,
        **properties: Any,
    ) -> str:
        item: dict[str, Any] = {
            "id": node_id(self.key, name),
            "name": name,
            "type": f"n8n-nodes-base.{kind}",
            "typeVersion": version,
            "position": [x, y],
            "parameters": parameters,
        }
        if credentials:
            item["credentials"] = credentials
        item.update(properties)
        self.nodes.append(item)
        return name

    def note(self, name: str, body: str, x: int, y: int = -20, width: int = 440) -> None:
        self.add(name, "stickyNote", 1, {"content": body, "height": 180, "width": width}, x, y)

    def link(self, source: str, target: str, *, output: int = 0, target_input: int = 0) -> None:
        main = self.connections.setdefault(source, {"main": []})["main"]
        while len(main) <= output:
            main.append([])
        main[output].append({"node": target, "type": "main", "index": target_input})

    def export(self) -> dict[str, Any]:
        settings: dict[str, Any] = {
            "executionOrder": "v1",
            "saveDataErrorExecution": "all",
            "saveManualExecutions": False,
        }
        if self.error:
            settings["errorWorkflow"] = "__workflow:error_handler__"
        return {
            "id": f"contentstudio_{self.key}_v1",
            "name": self.name,
            "nodes": self.nodes,
            "connections": self.connections,
            "settings": settings,
            "active": False,
            "pinData": {},
        }


def http(
    flow: Flow,
    name: str,
    path: str,
    x: int,
    y: int = 220,
    *,
    method: str = "POST",
    body: str | None = None,
    query: list[dict[str, str]] | None = None,
    credential: dict[str, Any] = SERVICE_CREDENTIAL,
    timeout: int = 120000,
    full_response: bool = False,
    never_error: bool = False,
    continue_error: bool = False,
    extra_headers: list[dict[str, str]] | None = None,
) -> str:
    p: dict[str, Any] = {
        "method": method,
        "url": path,
        "authentication": "genericCredentialType",
        "genericAuthType": next(iter(credential)),
        "options": {"timeout": timeout, "redirect": {"redirect": {"followRedirects": False}}},
    }
    if method == "GET":
        p.pop("method")
    if body is not None:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    if query:
        p.update({"sendQuery": True, "queryParameters": {"parameters": query}})
    if full_response or never_error:
        p["options"]["response"] = {"response": {"fullResponse": full_response, "neverError": never_error, "responseFormat": "json"}}
    if extra_headers:
        p.update({"sendHeaders": True, "headerParameters": {"parameters": extra_headers}})
    extras = {"onError": "continueErrorOutput"} if continue_error else {}
    return flow.add(name, "httpRequest", 4.2, p, x, y, credentials=credential, **extras)


def iff(flow: Flow, name: str, condition: str, x: int, y: int = 220) -> str:
    return flow.add(
        name,
        "if",
        2.2,
        {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                "conditions": [
                    {
                        "id": node_id(flow.key, name + " condition"),
                        "leftValue": condition,
                        "rightValue": "",
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        x,
        y,
    )


def subcall(flow: Flow, name: str, target: str, x: int, y: int = 220) -> str:
    return flow.add(
        name,
        "executeWorkflow",
        1.2,
        {
            "source": "database",
            "workflowId": {"__rl": True, "value": f"__workflow:{target}__", "mode": "id"},
            "options": {"waitForSubWorkflow": True},
        },
        x,
        y,
    )


def code(flow: Flow, name: str, js: str, x: int, y: int = 220) -> str:
    return flow.add(name, "code", 2, {"mode": "runOnceForAllItems", "jsCode": js}, x, y)


def error_handler() -> Flow:
    f = Flow("error_handler", "ContentStudio / Shared execution error", error=False)
    f.note("Error policy", "## System incident\nOnly workflow/node identifiers are forwarded. Raw stack traces and payloads stay out of the business exception queue.", 0)
    f.add("Catch production failure", "errorTrigger", 1, {}, 40)
    http(
        f,
        "Record system incident",
        API + "/errors",
        320,
        body="={{ JSON.stringify({workspace_id: null, operation_key: 'n8n:' + ($json.workflow?.id || 'unknown') + ':' + ($json.execution?.id || $json.trigger?.error?.timestamp || 'unknown'), error: 'n8n execution failed at ' + ($json.execution?.lastNodeExecuted || 'trigger'), outcome: 'failed'}) }}",
    )
    f.link("Catch production failure", "Record system incident")
    return f


def transcribe_generate() -> Flow:
    f = Flow("transcribe_generate", "ContentStudio / Transcribe and draft bundle")
    f.note("AI boundary", "## Source → transcript → AI bundle\nThe API owns typed transcription and the LangGraph AI task. n8n owns the order, retries, and failure path. No media bytes enter execution JSON.", 0, width=540)
    f.add("Accept batch", "executeWorkflowTrigger", 1.1, {"inputSource": "passthrough"}, 40)
    http(
        f,
        "Transcribe source",
        API + "/transcribe",
        320,
        body="={{ JSON.stringify({workspace_id: $('Accept batch').first().json.workspace_id, batch_id: $('Accept batch').first().json.batch_id}) }}",
        timeout=240000,
    )
    http(
        f,
        "Generate review bundle",
        API + "/generate",
        620,
        body="={{ JSON.stringify({workspace_id: $('Accept batch').first().json.workspace_id, batch_id: $('Accept batch').first().json.batch_id}) }}",
        timeout=240000,
    )
    f.link("Accept batch", "Transcribe source")
    f.link("Transcribe source", "Generate review bundle")
    return f


def intake() -> Flow:
    f = Flow("intake", "ContentStudio / Intake owned source")
    f.note("Intake boundary", "## Authenticated event\nThe portal posts a source ID, never media bytes. Header Auth checks X-Service-Token. The API validates schema, rights, hash, recipe and creates a durable batch. 202 is sent immediately.", 0, width=620)
    f.add(
        "Receive intake event",
        "webhook",
        2.1,
        {"httpMethod": "POST", "path": "contentstudio/intake", "authentication": "headerAuth", "responseMode": "onReceived", "options": {"noResponseBody": True, "responseCode": {"values": {"responseCode": "customCode", "customCode": 202}}}},
        40,
        credentials=SERVICE_CREDENTIAL,
        webhookId=node_id(f.key, "intake webhook"),
    )
    http(f, "Claim source and batch", API + "/intake", 320, body="={{ JSON.stringify($json.body) }}")
    code(f, "Attach workspace to batch", "return [{json: {...$input.first().json, workspace_id: $('Receive intake event').first().json.body.workspace_id}}];", 600)
    iff(f, "Already processed?", "={{ $json.duplicate === true }}", 880)
    subcall(f, "Transcribe and generate", "transcribe_generate", 1160, 360)
    f.link("Receive intake event", "Claim source and batch")
    f.link("Claim source and batch", "Attach workspace to batch")
    f.link("Attach workspace to batch", "Already processed?")
    f.link("Already processed?", "Transcribe and generate", output=1)
    return f


def render_item() -> Flow:
    f = Flow("render_item", "ContentStudio / Render approved asset")
    f.note("Render boundary", "## Approved version only\nThe service verifies exact approval/version and renders via validated FFmpeg/template arguments. A retry uses the durable render job key.", 0, width=500)
    f.add("Accept approved item", "executeWorkflowTrigger", 1.1, {"inputSource": "passthrough"}, 40)
    http(
        f,
        "Render approved version",
        API + "/render",
        340,
        body="={{ JSON.stringify({workspace_id: $json.workspace_id, asset_version_id: $json.asset_version_id}) }}",
        timeout=300000,
    )
    f.link("Accept approved item", "Render approved version")
    return f


def dispatch() -> Flow:
    f = Flow("dispatch_draft", "ContentStudio / Dispatch WordPress draft")
    f.note("Dispatch boundary", "## Draft only\nPrepare claims a unique operation key. WordPress receives status=draft. A known 429 waits once with Retry-After plus jitter. Permanent 4xx goes to the exception queue. Timeout or 5xx is uncertain and enters reconciliation; no blind write retry.", 0, width=760)
    f.add("Accept draft item", "executeWorkflowTrigger", 1.1, {"inputSource": "passthrough"}, 40)
    http(
        f,
        "Claim dispatch operation",
        API + "/dispatch/prepare",
        320,
        body="={{ JSON.stringify({workspace_id: $json.workspace_id, asset_version_id: $json.asset_version_id, channel: $json.channel, operation_key: $json.operation_key}) }}",
    )
    iff(f, "Claim acquired?", "={{ $json.claimed === true }}", 600)
    wp_headers = [{"name": "Idempotency-Key", "value": "={{ $('Claim dispatch operation').first().json.operation_key }}"}]
    http(
        f,
        "Create WordPress draft",
        "__WORDPRESS_BASE_URL__/wp-json/wp/v2/posts",
        900,
        credential=WORDPRESS_CREDENTIAL,
        body="={{ JSON.stringify($('Claim dispatch operation').first().json.draft) }}",
        timeout=15000,
        full_response=True,
        never_error=True,
        continue_error=True,
        extra_headers=wp_headers,
    )
    iff(f, "Draft created?", "={{ $json.statusCode >= 200 && $json.statusCode < 300 && !!$json.body?.id }}", 1180)
    http(
        f,
        "Complete dispatch ledger",
        API + "/dispatch/complete",
        1490,
        80,
        body="={{ JSON.stringify({workspace_id: $('Accept draft item').first().json.workspace_id, operation_key: $('Claim dispatch operation').first().json.operation_key, external_id: String($json.body.id), status: 'draft'}) }}",
    )
    iff(f, "Rate limited?", "={{ $json.statusCode === 429 }}", 1450, 360)
    f.add(
        "Wait for retry window",
        "wait",
        1.1,
        {
            "resume": "timeInterval",
            "amount": "={{ Math.min(60, Math.max(2, Number($json.headers?.['retry-after']) || 2)) + Math.random() }}",
            "unit": "seconds",
        },
        1740,
        280,
    )
    http(
        f,
        "Retry WordPress draft once",
        "__WORDPRESS_BASE_URL__/wp-json/wp/v2/posts",
        2020,
        280,
        credential=WORDPRESS_CREDENTIAL,
        body="={{ JSON.stringify($('Claim dispatch operation').first().json.draft) }}",
        timeout=15000,
        full_response=True,
        never_error=True,
        continue_error=True,
        extra_headers=wp_headers,
    )
    iff(f, "Retry created draft?", "={{ $json.statusCode >= 200 && $json.statusCode < 300 && !!$json.body?.id }}", 2300, 280)
    http(
        f,
        "Complete retried dispatch",
        API + "/dispatch/complete",
        2580,
        180,
        body="={{ JSON.stringify({workspace_id: $('Accept draft item').first().json.workspace_id, operation_key: $('Claim dispatch operation').first().json.operation_key, external_id: String($json.body.id), status: 'draft'}) }}",
    )
    response_failure_body = "={{ JSON.stringify({workspace_id: $('Accept draft item').first().json.workspace_id, operation_key: $('Claim dispatch operation').first().json.operation_key, error: 'WordPress draft HTTP ' + String($json.statusCode ?? 'unavailable'), outcome: ($json.statusCode >= 400 && $json.statusCode < 500 && $json.statusCode !== 408 ? 'failed' : 'unknown')}) }}"
    timeout_failure_body = "={{ JSON.stringify({workspace_id: $('Accept draft item').first().json.workspace_id, operation_key: $('Claim dispatch operation').first().json.operation_key, error: 'WordPress draft network outcome uncertain; reconcile by slug', outcome: 'unknown'}) }}"
    http(f, "Queue rejected or uncertain response", API + "/errors", 1740, 510, body=response_failure_body)
    http(f, "Queue exhausted retry", API + "/errors", 2580, 420, body=response_failure_body)
    http(f, "Queue network timeout", API + "/errors", 1190, 620, body=timeout_failure_body)
    http(f, "Queue retry timeout", API + "/errors", 2300, 620, body=timeout_failure_body)
    f.link("Accept draft item", "Claim dispatch operation")
    f.link("Claim dispatch operation", "Claim acquired?")
    f.link("Claim acquired?", "Create WordPress draft", output=0)
    f.link("Create WordPress draft", "Draft created?", output=0)
    f.link("Create WordPress draft", "Queue network timeout", output=1)
    f.link("Draft created?", "Complete dispatch ledger", output=0)
    f.link("Draft created?", "Rate limited?", output=1)
    f.link("Rate limited?", "Wait for retry window", output=0)
    f.link("Rate limited?", "Queue rejected or uncertain response", output=1)
    f.link("Wait for retry window", "Retry WordPress draft once")
    f.link("Retry WordPress draft once", "Retry created draft?", output=0)
    f.link("Retry WordPress draft once", "Queue retry timeout", output=1)
    f.link("Retry created draft?", "Complete retried dispatch", output=0)
    f.link("Retry created draft?", "Queue exhausted retry", output=1)
    return f


def due_items() -> Flow:
    f = Flow("due_items", "ContentStudio / Process due editorial actions")
    f.note("Scheduled work", "## Recoverable polling\nApproved render/package/dispatch work is queried from Postgres. This avoids one Wait node per approval. Only explicit demo activation publishes this schedule.", 0, width=600)
    f.add("Check due items", "scheduleTrigger", 1.3, {"rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}}, 40)
    f.add(
        "Replay due fixture",
        "webhook",
        2.1,
        {"httpMethod": "POST", "path": "contentstudio/due-demo", "authentication": "headerAuth", "responseMode": "onReceived", "options": {"noResponseBody": True, "responseCode": {"values": {"responseCode": "customCode", "customCode": 202}}}},
        40,
        430,
        credentials=SERVICE_CREDENTIAL,
        webhookId=node_id(f.key, "due webhook"),
    )
    http(f, "List workspaces", API + "/workspaces", 320, method="GET")
    code(f, "Expand workspaces", "return ($input.first().json.items || []).map((workspace, i) => ({json: {workspace_id: workspace.id}, pairedItem: {item: 0}}));", 600)
    http(f, "Find due actions", API + "/due", 880, method="GET", query=[{"name": "workspace_id", "value": "={{ $json.workspace_id }}"}])
    code(f, "Expand due actions", "return $input.all().flatMap((row, i) => (row.json.items || []).map(item => ({json: item, pairedItem: {item: i}})));", 1160)
    iff(f, "Needs render?", "={{ $json.action === 'render' }}", 1450)
    subcall(f, "Render version", "render_item", 1720, 80)
    iff(f, "Needs package?", "={{ $json.action === 'package' }}", 1720, 360)
    http(f, "Package approved batch", API + "/package", 2010, 280, body="={{ JSON.stringify({workspace_id: $json.workspace_id, batch_id: $json.batch_id}) }}", timeout=180000)
    iff(f, "Needs dispatch?", "={{ $json.action === 'dispatch' }}", 2010, 510)
    subcall(f, "Dispatch WordPress draft", "dispatch_draft", 2300, 510)
    iff(f, "Needs local outbox?", "={{ $json.action === 'outbox' }}", 2300, 760)
    http(
        f,
        "Prepare newsletter or social outbox",
        API + "/outbox",
        2590,
        760,
        body="={{ JSON.stringify({workspace_id: $json.workspace_id, asset_version_id: $json.asset_version_id, channel: $json.channel, operation_key: $json.operation_key}) }}",
    )
    f.link("Check due items", "List workspaces")
    f.link("Replay due fixture", "List workspaces")
    f.link("List workspaces", "Expand workspaces")
    f.link("Expand workspaces", "Find due actions")
    f.link("Find due actions", "Expand due actions")
    f.link("Expand due actions", "Needs render?")
    f.link("Needs render?", "Render version", output=0)
    f.link("Needs render?", "Needs package?", output=1)
    f.link("Needs package?", "Package approved batch", output=0)
    f.link("Needs package?", "Needs dispatch?", output=1)
    f.link("Needs dispatch?", "Dispatch WordPress draft", output=0)
    f.link("Needs dispatch?", "Needs local outbox?", output=1)
    f.link("Needs local outbox?", "Prepare newsletter or social outbox", output=0)
    return f


def reconcile() -> Flow:
    f = Flow("reconcile", "ContentStudio / Reconcile uncertain drafts")
    f.note("Unknown outcome", "## Read before retry\nSearch WordPress by stable slug. Matching drafts close the ledger. Missing drafts remain in the business exception queue for an operator; this workflow never replays an ambiguous write.", 0, width=680)
    f.add("Check uncertain actions", "scheduleTrigger", 1.3, {"rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}}, 40)
    f.add(
        "Replay reconciliation fixture",
        "webhook",
        2.1,
        {"httpMethod": "POST", "path": "contentstudio/reconcile-demo", "authentication": "headerAuth", "responseMode": "onReceived", "options": {"noResponseBody": True, "responseCode": {"values": {"responseCode": "customCode", "customCode": 202}}}},
        40,
        430,
        credentials=SERVICE_CREDENTIAL,
        webhookId=node_id(f.key, "reconcile webhook"),
    )
    http(f, "List reconcilable workspaces", API + "/workspaces", 320, method="GET")
    code(f, "Expand reconciliation workspaces", "return ($input.first().json.items || []).map(workspace => ({json: {workspace_id: workspace.id}, pairedItem: {item: 0}}));", 600)
    http(f, "Find uncertain drafts", API + "/reconcile", 880, method="GET", query=[{"name": "workspace_id", "value": "={{ $json.workspace_id }}"}])
    code(f, "Expand uncertain drafts", "return $input.all().flatMap((row, i) => (row.json.items || []).map(item => ({json: item, pairedItem: {item: i}})));", 1160)
    http(
        f,
        "Find WordPress draft by slug",
        "__WORDPRESS_BASE_URL__/wp-json/wp/v2/posts",
        1450,
        method="GET",
        credential=WORDPRESS_CREDENTIAL,
        query=[{"name": "slug", "value": "={{ $json.slug }}"}, {"name": "status", "value": "draft"}],
        full_response=True,
        never_error=True,
        timeout=15000,
    )
    iff(f, "Found matching draft?", "={{ $json.statusCode === 200 && Array.isArray($json.body) && $json.body.length === 1 }}", 1740)
    http(
        f,
        "Resolve dispatch ledger",
        API + "/dispatch/complete",
        2030,
        80,
        body="={{ JSON.stringify({workspace_id: $('Expand uncertain drafts').item.json.workspace_id, operation_key: $('Expand uncertain drafts').item.json.operation_key, external_id: String($json.body[0].id), status: 'draft'}) }}",
    )
    f.link("Check uncertain actions", "List reconcilable workspaces")
    f.link("Replay reconciliation fixture", "List reconcilable workspaces")
    f.link("List reconcilable workspaces", "Expand reconciliation workspaces")
    f.link("Expand reconciliation workspaces", "Find uncertain drafts")
    f.link("Find uncertain drafts", "Expand uncertain drafts")
    f.link("Expand uncertain drafts", "Find WordPress draft by slug")
    f.link("Find WordPress draft by slug", "Found matching draft?")
    f.link("Found matching draft?", "Resolve dispatch ledger", output=0)
    return f


FLOW_BUILDERS = {
    "error_handler": error_handler,
    "transcribe_generate": transcribe_generate,
    "render_item": render_item,
    "dispatch_draft": dispatch,
    "intake": intake,
    "due_items": due_items,
    "reconcile": reconcile,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"pack": "ContentStudio", "version": 1, "n8n_version": "2.40.7", "workflows": []}
    dependencies = {
        "error_handler": [],
        "transcribe_generate": ["error_handler"],
        "render_item": ["error_handler"],
        "dispatch_draft": ["error_handler"],
        "intake": ["error_handler", "transcribe_generate"],
        "due_items": ["error_handler", "render_item", "dispatch_draft"],
        "reconcile": ["error_handler"],
    }
    def obj(fields: dict[str, Any], required: list[str] | None = None, *, extra: bool = False) -> dict[str, Any]:
        return {"type": "object", "properties": fields, "required": required or [], "additionalProperties": extra}

    identifier = {"type": "string", "format": "uuid"}
    text = {"type": "string", "minLength": 1}
    # n8n forwards the parent item, including scheduling and deduplication
    # metadata. Sub-workflow contracts validate required fields, not a closed
    # object shape that would reject those useful extra fields.
    batch_input = obj({"workspace_id": identifier, "batch_id": identifier}, ["workspace_id", "batch_id"], extra=True)
    asset_input = obj({"workspace_id": identifier, "asset_version_id": identifier}, ["workspace_id", "asset_version_id"], extra=True)
    contracts = {
        "error_handler": (
            obj({"workflow": {"type": "object"}, "execution": {"type": "object"}, "trigger": {"type": "object"}}, ["workflow"]),
            obj({"recorded": {"type": "boolean"}}, ["recorded"]),
        ),
        "transcribe_generate": (
            batch_input,
            obj({"batch": obj({"id": identifier, "status": {"type": "string"}}, ["id", "status"], extra=True), "source": {"type": "object"}, "claims": {"type": "array"}, "assets": {"type": "array"}}, ["batch", "source", "claims", "assets"], extra=True),
        ),
        "render_item": (asset_input, obj({"job_id": identifier, "status": {"type": "string"}, "render_urls": {"type": "object"}}, ["job_id", "status"])),
        "dispatch_draft": (
            obj({"workspace_id": identifier, "asset_version_id": identifier, "channel": {"const": "wordpress"}, "operation_key": text}, ["workspace_id", "asset_version_id", "channel", "operation_key"], extra=True),
            obj({"status": {"const": "complete"}, "duplicate": {"type": "boolean"}, "external_id": {"type": "string"}}, ["status", "external_id"], extra=True),
        ),
        "intake": (
            obj({"workspace_id": identifier, "source_asset_id": identifier, "recipe_version": text, "brand_profile_version_id": identifier, "request_id": text}, ["workspace_id", "source_asset_id", "recipe_version", "brand_profile_version_id", "request_id"]),
            obj({"http_status": {"const": 202}}),
        ),
        # Scheduled routers emit zero or more branch results, not an
        # aggregated {items: [...]} response. The Webhook entrypoint itself
        # acknowledges HTTP 202 before the branch results are produced.
        "due_items": (obj({}, extra=True), {"description": "Per processed action: render, package, WordPress draft or local outbox result; zero items when no work is due", "oneOf": [obj({"job_id": identifier, "status": {"type": "string"}}, ["job_id", "status"], extra=True), obj({"status": {"const": "complete"}, "external_id": {"type": "string"}}, ["status", "external_id"], extra=True), obj({"ready": {"const": True}, "duplicate": {"type": "boolean"}, "operation_key": text, "draft_id": identifier}, ["ready", "duplicate", "operation_key", "draft_id"], extra=True)]}),
        "reconcile": (obj({}, extra=True), obj({"status": {"const": "complete"}, "external_id": {"type": "string"}}, ["status", "external_id"], extra=True)),
    }
    for order, (key, builder) in enumerate(FLOW_BUILDERS.items(), start=1):
        flow = builder()
        export = flow.export()
        with (OUT / f"{order:02d}-{key.replace('_', '-')}.json").open("w", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(export, indent=2, ensure_ascii=False) + "\n")
        manifest["workflows"].append(
            {
                "key": key,
                "name": flow.name,
                "logical_id": export["id"],
                "file": f"{order:02d}-{key.replace('_', '-')}.json",
                "dependencies": dependencies[key],
                "credentials": sorted({kind for node in flow.nodes for kind in node.get("credentials", {})}),
                "input_schema": contracts[key][0],
                "output_schema": contracts[key][1],
                "import_order": order,
                # n8n 2.x requires referenced/error workflows to have a
                # published version before a parent can be published.
                "activate_for_demo": True,
            }
        )
    with (OUT / "manifest.json").open("w", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"Built {len(FLOW_BUILDERS)} workflow exports in {OUT}")


if __name__ == "__main__":
    main()

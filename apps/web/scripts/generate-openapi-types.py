"""Generate small, dependency-free TypeScript types from the FastAPI OpenAPI export.

Run from the repository root or this directory. --check fails when generated types
do not match apps/api/openapi.json, which keeps the client contract reviewable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = WEB_ROOT.parent / "api" / "openapi.json"
OUTPUT_PATH = WEB_ROOT / "src" / "openapi.generated.ts"


def ts(schema: dict) -> str:
    if not schema:
        return "unknown"
    if "$ref" in schema:
        return f'components["schemas"]["{schema["$ref"].split("/")[-1]}"]'
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    for key, operator in (("anyOf", " | "), ("oneOf", " | "), ("allOf", " & ")):
        if key in schema:
            return "(" + operator.join(ts(item) for item in schema[key]) + ")"
    kind = schema.get("type")
    if isinstance(kind, list):
        return "(" + " | ".join(ts({**schema, "type": value}) for value in kind) + ")"
    if kind == "array":
        return f"Array<{ts(schema.get('items', {}))}>"
    if kind == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        parts = [f'{json.dumps(name)}{"" if name in required else "?"}: {ts(value)}' for name, value in properties.items()]
        if schema.get("additionalProperties") is True and not parts:
            return "Record<string, unknown>"
        if isinstance(schema.get("additionalProperties"), dict) and not parts:
            return f"Record<string, {ts(schema['additionalProperties'])}>"
        if not parts:
            return "Record<string, unknown>"
        return "{ " + "; ".join(parts) + " }"
    if kind == "string":
        return "Blob" if schema.get("format") == "binary" else "string"
    if kind in ("integer", "number"):
        return "number"
    if kind == "boolean":
        return "boolean"
    if kind == "null":
        return "null"
    return "unknown"


def response_schema(operation: dict) -> dict:
    for code, response in sorted(operation.get("responses", {}).items()):
        if code.startswith("2"):
            content = response.get("content", {})
            return content.get("application/json", {}).get("schema", {})
    return {}


def make_types(spec: dict, digest: str) -> str:
    lines = [
        "// Generated from apps/api/openapi.json. Do not edit by hand.",
        f"// SHA256: {digest}",
        "export interface components {",
        "  schemas: {",
    ]
    for name, schema in sorted(spec.get("components", {}).get("schemas", {}).items()):
        lines.append(f'    {json.dumps(name)}: {ts(schema)}')
    lines += ["  }", "}", "", "export interface paths {"]
    for path, methods in sorted(spec.get("paths", {}).items()):
        lines.append(f"  {json.dumps(path)}: {{")
        for method, operation in methods.items():
            if method not in ("get", "post", "patch", "put", "delete"):
                continue
            body = operation.get("requestBody", {}).get("content", {})
            request = body.get("application/json", {}).get("schema", {}) or body.get("multipart/form-data", {}).get("schema", {})
            lines.append(f"    {method}: {{ request: {ts(request)}; response: {ts(response_schema(operation))} }}")
        lines.append("  }")
    lines += ["}", "", "export type ApiResponse<P extends keyof paths, M extends keyof paths[P]> = paths[P][M] extends { response: infer R } ? R : never", "export type ApiRequest<P extends keyof paths, M extends keyof paths[P]> = paths[P][M] extends { request: infer R } ? R : never", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Verify generated TypeScript is up to date")
    args = parser.parse_args()
    raw = SPEC_PATH.read_bytes()
    spec = json.loads(raw)
    generated = make_types(spec, hashlib.sha256(raw).hexdigest())
    if args.check:
        if not OUTPUT_PATH.is_file() or OUTPUT_PATH.read_text(encoding="utf-8") != generated:
            raise SystemExit("OpenAPI types are stale. Run python scripts/generate-openapi-types.py")
        print("OpenAPI response/request types match apps/api/openapi.json")
        return
    OUTPUT_PATH.write_text(generated, encoding="utf-8")
    print(f"Generated {OUTPUT_PATH.relative_to(WEB_ROOT)} from {SPEC_PATH}")


if __name__ == "__main__":
    main()

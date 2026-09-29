"""Provision the private, loopback-only n8n DEMO owner and pack credentials.

This writes secrets to the ignored .env and never prints their values. It uses
n8n's authenticated local REST endpoint only for first-run owner/API-key setup;
the public API creates credentials used by the importable workflow pack.
"""

from __future__ import annotations

import http.cookiejar
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"
DEMO_API_SCOPES = frozenset({
    "credential:create",
    "workflow:create", "workflow:read", "workflow:update", "workflow:list",
    "workflow:activate", "workflow:deactivate",
    "execution:list", "execution:read",
})


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def set_env(updates: dict[str, str]) -> None:
    for value in updates.values():
        if "\n" in value or "\r" in value:
            raise ValueError("Environment values must fit on one line")
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    old_keys = {line.split("=", 1)[0] for line in lines if "=" in line and not line.startswith("#")}
    rewritten = [f"{line.split('=', 1)[0]}={updates[line.split('=', 1)[0]]}"
                 if "=" in line and line.split("=", 1)[0] in updates and not line.startswith("#")
                 else line for line in lines]
    rewritten.extend(f"{key}={value}" for key, value in updates.items() if key not in old_keys)
    ENV_FILE.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def request(opener: urllib.request.OpenerDirector, base: str, method: str,
            path: str, payload: dict[str, Any] | None = None,
            api_key: str | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        headers["X-N8N-API-KEY"] = api_key
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with opener.open(req, timeout=20) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        # n8n may include the submitted credential data in a validation error.
        raise RuntimeError(f"{method} {path} returned HTTP {error.code}") from error


def main() -> None:
    env = read_env()
    if env.get("MODE", "demo").lower() != "demo":
        raise RuntimeError("Provisioning is allowed only in MODE=demo")
    parsed = urllib.parse.urlsplit(env["N8N_PUBLIC_URL"])
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.scheme != "http":
        raise RuntimeError("Provisioning requires loopback HTTP n8n")
    base = env["N8N_PUBLIC_URL"].rstrip("/")
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    settings = request(opener, base, "GET", "/rest/settings")
    if settings.get("data", {}).get("userManagement", {}).get("showSetupOnFirstLoad"):
        email = env.get("N8N_OWNER_EMAIL") or "operator@contentstudio.test"
        password = env.get("N8N_OWNER_PASSWORD") or "Cs!" + secrets.token_urlsafe(24)
        set_env({"N8N_OWNER_EMAIL": email, "N8N_OWNER_PASSWORD": password})
        request(opener, base, "POST", "/rest/owner/setup", {
            "email": email, "firstName": "Content", "lastName": "Studio", "password": password,
        })
        print("Created local n8n DEMO owner")
    else:
        if not env.get("N8N_OWNER_EMAIL") or not env.get("N8N_OWNER_PASSWORD"):
            raise RuntimeError("Existing owner requires N8N_OWNER_EMAIL and N8N_OWNER_PASSWORD in .env")
        request(opener, base, "POST", "/rest/login", {
            "emailOrLdapLoginId": env["N8N_OWNER_EMAIL"],
            "password": env["N8N_OWNER_PASSWORD"],
        })
        print("Authenticated local n8n DEMO owner")
    env = read_env()
    api_key = env.get("N8N_API_KEY")
    if not api_key:
        scope_response = request(opener, base, "GET", "/rest/api-keys/scopes")
        scopes_data = scope_response.get("data", scope_response)
        scopes = [item["scope"] if isinstance(item, dict) else item for item in scopes_data]
        available = {scope for scope in scopes if isinstance(scope, str)}
        if not DEMO_API_SCOPES <= available:
            raise RuntimeError("n8n did not offer the required DEMO API key scopes")
        key_response = request(opener, base, "POST", "/rest/api-keys/", {
            "label": "ContentStudio local DEMO", "scopes": sorted(DEMO_API_SCOPES), "expiresAt": None,
        })
        api_key = key_response.get("data", {}).get("rawApiKey")
        if not api_key:
            raise RuntimeError("n8n did not return a raw API key")
        set_env({"N8N_API_KEY": api_key})
        print(f"Created local n8n API key with {len(DEMO_API_SCOPES)} required scopes")
    else:
        print("Reusing local n8n API key")
    env = read_env()
    if not env.get("N8N_SERVICE_CREDENTIAL_ID"):
        created = request(opener, base, "POST", "/api/v1/credentials", {
            "name": "ContentStudio service token", "type": "httpHeaderAuth",
            "data": {"name": "X-Service-Token", "value": env["SERVICE_TOKEN"]},
        }, api_key)
        credential_id = created.get("id") or created.get("data", {}).get("id")
        if not credential_id:
            raise RuntimeError("n8n did not return service credential ID")
        set_env({"N8N_SERVICE_CREDENTIAL_ID": credential_id})
        print("Created service-token credential")
    if not env.get("N8N_WORDPRESS_CREDENTIAL_ID"):
        created = request(opener, base, "POST", "/api/v1/credentials", {
            "name": "ContentStudio WordPress draft DEMO", "type": "httpBasicAuth",
            "data": {"user": env["SIM_WORDPRESS_USER"], "password": env["SIM_WORDPRESS_PASSWORD"]},
        }, api_key)
        credential_id = created.get("id") or created.get("data", {}).get("id")
        if not credential_id:
            raise RuntimeError("n8n did not return WordPress credential ID")
        set_env({"N8N_WORDPRESS_CREDENTIAL_ID": credential_id})
        print("Created WordPress simulator credential")


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, RuntimeError, ValueError) as error:
        raise SystemExit(f"provision failed: {error}") from None

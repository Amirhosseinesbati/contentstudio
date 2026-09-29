"""Read-only readiness check for the installed ContentStudio n8n pack."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Protocol

REQUIRED_WORKFLOW_NAMES = frozenset(
    {
        "ContentStudio / Shared execution error",
        "ContentStudio / Transcribe and draft bundle",
        "ContentStudio / Render approved asset",
        "ContentStudio / Dispatch WordPress draft",
        "ContentStudio / Intake owned source",
        "ContentStudio / Process due editorial actions",
        "ContentStudio / Reconcile uncertain drafts",
    }
)


class N8nStatusSettings(Protocol):
    n8n_api_key: str
    n8n_health_url: str
    n8n_timeout_seconds: float


def contentstudio_pack_ready(settings: N8nStatusSettings | None = None) -> bool:
    """Return true only when every required workflow is published/active.

    The API key needs only n8n's ``workflow:list`` scope. A missing key, bad
    response, timeout, or partial pack fails closed without exposing details.
    """
    try:
        if settings is None:
            from .config import get_settings

            settings = get_settings()
        if not settings.n8n_api_key or not settings.n8n_health_url:
            return False
        health = urllib.parse.urlsplit(settings.n8n_health_url)
        if health.scheme not in {"http", "https"} or not health.netloc or health.path.rstrip("/").split("/")[-1] != "healthz":
            return False
        if health.username is not None or health.password is not None or health.query or health.fragment:
            return False
        prefix = health.path.rstrip("/")[: -len("/healthz")]
        base = urllib.parse.urlunsplit((health.scheme, health.netloc, prefix, "", ""))
        remaining = set(REQUIRED_WORKFLOW_NAMES)
        cursor: str | None = None
        seen_cursors: set[str] = set()
        deadline = time.monotonic() + min(max(settings.n8n_timeout_seconds, 0.1), 3.0)
        for _ in range(10):
            query = {"limit": "100"}
            if cursor:
                query["cursor"] = cursor
            request = urllib.request.Request(
                base + "/api/v1/workflows?" + urllib.parse.urlencode(query),
                headers={"X-N8N-API-KEY": settings.n8n_api_key, "Accept": "application/json"},
                method="GET",
            )
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                return False
            with urllib.request.urlopen(request, timeout=timeout) as response:
                page = json.load(response)
            if not isinstance(page, dict) or not isinstance(page.get("data"), list):
                return False
            for workflow in page["data"]:
                if isinstance(workflow, dict) and workflow.get("active") is True:
                    remaining.discard(workflow.get("name"))
            if not remaining:
                return True
            cursor = page.get("nextCursor")
            if not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
                return False
            seen_cursors.add(cursor)
    except Exception:
        # Readiness must fail closed; this path must not log the API key.
        return False
    return False

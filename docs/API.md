# API contract

FastAPI serves OpenAPI at `/openapi.json` and the interactive reference at `/docs` after startup. The portal sends the HTTP-only `contentstudio_session` cookie and never receives n8n credentials. All human routes below are prefixed `/api/v1`. Except for login and `/healthz`, a session is required; source, batch, asset, job, file, and calendar IDs are always checked against the signed-in workspace. Admin/operator can mutate; viewer is read-only.

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/auth/login` | `{email,password}` creates a server-side session. |
| GET / POST | `/auth/me`, `/auth/logout` | Inspect or revoke the session. |
| GET | `/bootstrap` | Mode, user/workspace, counts, real connector status. |
| GET / POST | `/sources`, `/sources/transcript` | List sources or create a rights-attested transcript-only source. |
| POST | `/sources/upload` | Multipart owned media with `file`, `title`, `rights_attested`; configured limit is 250 MiB by default. |
| GET | `/sources/{id}`, `/sources/{id}/media` | Transcript detail or authenticated playback/download. |
| PATCH | `/sources/{id}/segments/{segment_id}` | Correct one segment; create a transcript version and invalidate dependent assets. |
| GET | `/brands` | Workspace brand versions. |
| POST | `/sources/{id}/batches` | `{brand_profile_id,recipe_version}` requests an n8n intake. Source hash + recipe + brand is deduplicated. |
| GET | `/batches`, `/batches/{id}` | Board list and review bundle with claims and current assets. |
| PATCH / POST | `/assets/{id}`, `/assets/{id}/regenerate` | Create a new editable version or regenerate only this logical asset. |
| POST | `/assets/{id}/review` | `{decision:"approve"|"reject",expected_hash,reason?}`; hash must match the current version. |
| POST / GET | `/assets/{id}/render`, `/assets/{id}/renders/{filename}` | Queue approved carousel/clip render and retrieve scoped file. |
| POST / GET | `/batches/{id}/package`, `/batches/{id}/download` | Queue a package and download its ZIP after completion. |
| GET / GET / POST | `/jobs/{id}`, `/jobs/{id}/events`, `/jobs/{id}/cancel` | Persisted status, SSE progress, queued cancellation. |
| POST / GET | `/assets/{id}/schedule`, `/calendar` | Create a publication-ready draft/outbox entry and inspect the calendar. |

Example review request:

```json
{"decision":"approve","expected_hash":"<64-character hash from the current asset response>"}
```

The API rejects a changed asset with HTTP 409 and blocks approval while evidence/brand warnings remain. A render request returns a job ID; poll its SSE stream or status endpoint, then reload the asset for scoped render URLs. Transcript corrections create new versions instead of overwriting the old text.

## n8n service boundary

`/internal/workflows/*` requires the constant-time-checked `X-Service-Token` header. The intake request is:

```json
{
  "workspace_id": "<server-owned UUID>",
  "source_asset_id": "<server-owned UUID>",
  "brand_profile_version_id": "<server-owned UUID>",
  "recipe_version": "v1",
  "request_id": "<unique event identifier>"
}
```

The service exposes intake, transcription, generation, render, package, dispatch prepare/complete, error, due-items, reconciliation, workspace, and demo-fixture routes. Workflow JSON and `workflows/manifest.json` carry exact request/response shapes and dependency order. The service token is never placed in browser code or exported workflow JSON. A repeated event ID with a different payload hash is a conflict; a repeated dispatch operation key must not create another draft. Unknown WordPress outcomes go to reconciliation before retry.

The local WordPress simulator implements the draft endpoint shape. Connected WordPress needs an HTTPS base URL and a scoped application password configured in n8n credentials. Social platform publishing is not part of this API.

## Failure behavior

401 means missing/expired human session or invalid internal token; 403 means an insufficient role; 404 deliberately covers out-of-workspace objects; 409 covers stale versions, duplicate/conflicting events, unapproved render attempts, and unavailable packages; 413/415/422 cover upload size, media type, and input validation; 503 means n8n intake is not configured or reachable. The portal should show the returned error near the action and preserve local edits. A disconnected connection indicator comes from `/bootstrap` health/configuration checks rather than a fabricated success screen.

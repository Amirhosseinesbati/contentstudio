# Handover

Updated 2026-09-28. The delivered local pilot revision is tagged `contentstudio-pilot-2026-09-28`; `git rev-parse contentstudio-pilot-2026-09-28` gives its exact commit. The earlier `handover-2026-09-28` tag remains a baseline.

## Exact launch commands

From the project root, use PowerShell `Copy-Item .env.example .env` or POSIX `cp .env.example .env`, fill the placeholder secrets, then run:

```text
docker compose up --build -d
```

Open `http://localhost:4173`. Create the n8n owner/API key and Header Auth + local simulator Basic Auth credentials, set the IDs in `.env`, then run `python scripts/n8n/bootstrap.py`, `python scripts/n8n/bootstrap.py --activate-demo`, and `python scripts/n8n/replay.py` for actual demo triggers. `workflows/README.md` gives the credential table, import order, and replay behavior. The earlier verified local run used `N8N_HOST_PORT=15679` and `SIM_HOST_PORT=18081`; the private `.env` now also sets `API_HOST_PORT=18000` after a collision on 8000. The new API port has not been verified healthy while Docker is degraded. Do not activate connected schedules as part of import.

## Demo credentials

The example default password is `DemoStudio!2026` unless `DEMO_PASSWORD` overrides it. The verified local installation uses a private override; read its actual value from the ignored `.env` file. These accounts are for **demo mode only** and should never be used in a customer deployment.

| Email | Workspace | Role |
| --- | --- | --- |
| `admin@studio.test` | `studio-alpha` | admin |
| `editor@studio.test` | `studio-alpha` | operator |
| `viewer@studio.test` | `studio-alpha` | viewer |
| `beta-admin@studio.test` | `studio-beta` | admin |

## Implemented, verified, pending

| Area | Implemented | Verified here | Pending gate |
| --- | --- | --- | --- |
| API auth, roles, workspace scope, versioned review | Yes | Final combined local API/workflow check: 55 passed and 17 subtests passed in 20.19 s; Ruff clean; seven-workflow bootstrap dry-run and `git diff --check` clean. Fresh SQLite migration/seed, PostgreSQL migration `c041f713d2a0`, and cross-workspace 404 also passed. This static/local suite passed while Docker runtime was degraded. | Customer security review and concurrency test. |
| Synthetic data | Yes | 12 sources, 240 segments, 4 brands, 120 archive versions, 11 showcase assets; 70/70 deterministic fixture warnings | Human-reviewed real-source sample. |
| Three playable synthetic sources | Yes | MP4 audio/video full decode, measured 550–600 s, scoped API playback HTTP 200 | Real audio transcription test; synthetic scripts are not proof of ASR quality. |
| Carousel/clip render and ZIP | Yes | API-local review → 7 slides/PDF → 3 subtitled MP4s → 17-file ZIP in 24.31 s; separate empty-database seed → fully rendered 11-asset showcase and valid 23-file ZIP in 15.79 s. The Compose API served the rendered carousel, three clips, and ZIP. | Audible boundary review and an n8n-triggered render/recovery drill. |
| Workflow pack | Yes | Seven exports/57 nodes; n8n 2.40.7 clean import, credential/reference readback, all seven active at the time. [Intake replay evidence](../workflows/evidence/replay-20260928T083343b793bd.json) covers five successful persisted review bundles, a duplicate, and conflict/malformed Error Trigger executions. [Dispatch evidence](../workflows/evidence/dispatch-429-duplicate-20260928.json) covers a simulated 429 wait/retry and a duplicate due trigger with one resulting draft. | Restore Docker health; n8n-triggered render/package, restart, timeout/5xx retry, concurrent processing, and ambiguous external outcome tests. |
| Scoped database restore | Yes | 243,539-byte ContentStudio `pg_dump` restored into a disposable PostgreSQL database with counts checked across 14 tables. | Full media, n8n database/volume, and encryption-key restore. |
| React portal | Yes | Generated OpenAPI types, build/type/lint, browser journeys, and eight 1440/1024/390 screenshots in `docs/screenshots/` | Keyboard-only journey review. |
| Connected model/transcription/WordPress | Adapters/contracts | Local simulator and request shapes | Authorized credentials, spending limit, and live smoke tests. |

Docker Desktop recovered from a full C: drive and stale socket long enough for the local five-service Compose stack to run on ports 4173, 8000 (API at the time), 15679, 18081, and 5433. Actual n8n intake/dispatch evidence and a scoped PostgreSQL restore are recorded above. Later, global Docker virtual-disk I/O errors appeared, the API returned 500, and a project-only restart failed. A global Docker Desktop restart awaits owner approval because it would affect 26 running containers, including unrelated projects. The earlier evidence remains valid, but current stack health is degraded. The replay uses synthetic sources and a local simulator; connected providers, full restore, n8n-triggered render/package, and recovery under restart/additional retry remain unverified. `docs/IMPLEMENTATION_STATUS.md` and `docs/EVALUATION.md` track the exact state.

The fresh demo showcase is packaged for inspection without n8n or external services. Its approvals are labeled **synthetic demo decisions**, not human review. In a local API-only preview, new n8n-dependent batch/render/package actions are disabled with an explanation; enable the n8n stack for those journeys.

## Browser evidence

The captured browser PNGs are `docs/screenshots/01-login-1440.png`, `02-studio-1440.png`, `03-carousel-1440.png`, `04-clip-1440.png`, `05-review-1024.png`, `06-board-1024.png`, `07-calendar-390.png`, and `08-library-390.png`. `docs/screenshots/manifest.json` records capture dimensions and confirms no horizontal document overflow at those widths. The media renderer's separate contact sheets are under ignored `output/render-qa/` and can be regenerated with the documented scripts.

## Customer-specific next steps

Replace demo accounts and secrets; set up TLS/reverse proxy and secure cookies; confirm owned-media rights and retention; configure brand rules and WordPress draft permissions; recreate n8n credentials and import on the customer installation; perform authorized model/transcription and WordPress tests; complete a PostgreSQL/media/n8n-key restore drill; review sample claims and all media outputs with an editor; decide redistribution/licensing terms for the delivery form. This is a pilot handover, not a production certification.

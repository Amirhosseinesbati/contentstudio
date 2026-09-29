# ContentStudio implementation status

Updated: 2026-09-28. This file records the actual state of the build; the product requirements is a target, not evidence of completion.

## Product and architecture plan

ContentStudio is a self-hosted editorial workflow for owned webinar and podcast material. A reviewer can trace derived claims to transcript spans, revise and approve individual assets, render approved media, and collect a downloadable publication package. The demo uses fictional data and local connector simulators. Connected mode requires configured provider credentials and authorized sources.

- **n8n** owns intake triggers, dispatch, retries, reconciliation, and workflow execution.
- **FastAPI** owns authenticated business records, versioned review, claims, media assets, and the typed AI task. LangGraph is limited to analysis, planning, generation, and evidence checks.
- **PostgreSQL** is the source of truth. Large media and generated files live in scoped storage with database references. n8n uses separate internal tables.
- **React** provides a review portal backed by the API. It shows source evidence and actual generated files, with honest status for disconnected connectors.
- **Demo data** is deterministic. The two demo workspaces are isolated; no demo action sends to a real external recipient.

The first vertical slice is: transcript fixture intake -> AI review bundle -> per-asset editing and approval -> rendered carousel/clip preview -> package download. Audio transcription and WordPress draft dispatch are separate adapters and gates.

## Progress

| Area | State | Evidence / next action |
| --- | --- | --- |
| Brief and constraints | Complete | `09-n8n-contentstudio.md` reviewed. |
| API, database, AI graph | Implemented; local and PostgreSQL verification | Versioned review, workspace auth, LangGraph fixture generation, render/package jobs, one-time connected admin bootstrap. Final combined local API/workflow checks passed: 55 tests and 17 subtests in 20.19 s, Ruff clean, seven-export bootstrap dry-run, and clean diff check. During the earlier healthy Compose run, the API migrated PostgreSQL to `c041f713d2a0`; cross-workspace access returned 404. The API later returned 500 amid Docker virtual-disk I/O errors. |
| Editorial portal | Implemented; browser QA recorded | React portal, generated OpenAPI types, TypeScript, ESLint, and Vite production build passed. Login, source seek, review, media, board, calendar, library, and offline controls were exercised at desktop, tablet, and mobile widths. Eight screenshots are in `docs/screenshots/`. |
| n8n pack and local stack | Intake and dispatch demo paths verified; current stack degraded | Seven exports/57 nodes; actual n8n 2.40.7 clean import, credential/reference readback, and seven active workflows at the time. [Intake evidence](../workflows/evidence/replay-20260928T083343b793bd.json) ties five successful executions to five persisted 11-asset review bundles; a duplicate preserved its batch, and conflict/malformed events invoked the Error Trigger. [Dispatch evidence](../workflows/evidence/dispatch-429-duplicate-20260928.json) records one simulated 429 wait/retry and one draft after a duplicate due trigger. |
| Synthetic dataset and media | Complete; local verification | 12 transcripts, 4 brands, 120 archive assets, 80 validation cases, 3 owned synthetic MP4s (550–600 s), plus an 11-asset showcase. Full media decode and 70/70 executable deterministic validation cases passed. |
| Rendering and packaging | Implemented; local and earlier Compose verification | An API smoke produced seven PNG/PDF pages, three subtitled clips, and a 17-file ZIP in 24.31 s. A fresh demo seed produced a rendered 11-asset showcase and valid 23-file ZIP. During the earlier healthy Compose run, the API served the carousel, three clips, and ZIP. n8n-triggered render/package and audible boundary review remain pending. |
| End-to-end browser and n8n verification | Selected local synthetic journeys passed | Portal journeys passed at 1440/1024/390 widths without horizontal overflow. The actual n8n-triggered five-scenario intake replay and one 429 dispatch retry passed against persisted business data. Restart, timeout/5xx retry, and concurrency tests remain. |
| Backup and restore | Scoped database drill passed; full restore pending | A 243,539-byte ContentStudio `pg_dump` restored into a disposable database with row counts checked across 14 tables. Media and n8n volume/key restoration were not part of this drill. |
| Connected credentials smoke tests | Pending | No authorized model, transcription, or WordPress credentials supplied. |

## Environment constraints observed

Docker Desktop initially had a full C: drive and stale socket; it recovered long enough to run all five services on host ports 4173 (web), 8000 (API at the time), 15679 (n8n), 18081 (simulator), and 5433 (PostgreSQL). Host collisions led the private `.env` to set `N8N_HOST_PORT=15679`, `SIM_HOST_PORT=18081`, and later `API_HOST_PORT=18000`; the earlier API 8000 result is historical. Global Docker virtual-disk I/O errors then appeared, the API returned 500, and a project-only restart failed. A global Docker Desktop restart remains subject to owner approval because it would affect 26 running containers, including unrelated projects. Current stack health is unverified/degraded, so port 18000 is configuration rather than a verified healthy endpoint. FFmpeg was not on the host `PATH` at initial inspection; the API image installs it. Connected deployment, n8n recovery under restart/additional retry/concurrency, full-volume restore, and live-provider quality remain release gates. This is a pilot, not production certification.

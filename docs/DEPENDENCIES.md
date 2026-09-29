# Dependencies and tested versions

The Python lock is `apps/api/uv.lock`; the frontend lock is `apps/web/pnpm-lock.yaml`. The API Dockerfile uses `uv sync --locked --no-dev`. Compose pins explicit image tags. Rebuild lockfiles only after checking compatibility and running the full suite.

| Component | Local resolved/tested version or pinned image | Verification status |
| --- | --- | --- |
| Python | 3.12.13 local; `python:3.12.11-slim-bookworm` container base | Local tests and an earlier healthy Compose API run verified; current Docker health is degraded. |
| uv | 0.11.28 | Local lock generation; API image pins same version. |
| FastAPI / Pydantic | 0.141.1 / 2.13.5 | Local API tests. |
| SQLAlchemy / Alembic / psycopg | 2.1.1 / 1.20.0 / 3.3.6 | SQLite and PostgreSQL migration to `c041f713d2a0` verified; scoped 14-table database restore passed. |
| LangChain / core / OpenAI adapter | 1.4.2 / 1.6.5 / 1.6.6 | Fixture graph and typed boundary tested; connected model pending credentials. |
| LangGraph / PostgreSQL checkpointer | 1.2.12 / 3.1.2 | Fixture graph and n8n-triggered PostgreSQL-backed review bundles verified; checkpoint/restart recovery pending. |
| OpenAI Python SDK | 3.19.2 | Installed through locked adapter; no paid call made. |
| Pillow / ReportLab | 12.3.0 / 4.5.1 | PNG and PDF render QA passed locally. |
| FFmpeg | Temporary local FFmpeg 7.1 binary from imageio-ffmpeg 0.6.0; `ffmpeg` installed in API image | Three source videos and three clips encoded/decoded locally; the Compose API served rendered carousel/clips/ZIP before Docker degraded. |
| n8n | `docker.n8n.io/n8nio/n8n:2.40.7` | Earlier healthy run: clean import, credential/reference readback, seven active workflows, five triggered persisted review bundles, duplicate/error replay, and one simulated 429 dispatch retry. Current Docker health is degraded. |
| PostgreSQL | `postgres:16.15-bookworm` | Compose runtime migration and scoped `pg_dump` restore to a disposable database passed; full volume/key restore pending. |
| Connector simulator | `python:3.12.11-slim-bookworm` | Local contract tests and earlier healthy Compose simulator verified. |
| React / Vite / TypeScript | 19.3.0 / 7.3.6 / 5.9.3 | OpenAPI type check, TypeScript, ESLint, and Vite production build passed locally. |
| Tailwind CSS / TanStack Query | 4.3.3 / 5.104.0 | Resolved by pnpm; frontend checks passed locally. |
| Node / pnpm | 24.18.0 local / 11.19.0; `node:24.13.0-alpine3.22` build image | Local build and earlier Compose web runtime verified. |
| Nginx | `nginx:1.29.3-alpine3.22` | Compose portal served a successful login through Nginx before Docker degraded. |

LangChain/LangGraph code was checked against current [LangChain structured-output](https://docs.langchain.com/oss/python/langchain/structured-output) and [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) guidance. n8n workflow nodes and import behavior use the pinned 2.40.7 export format; runtime replay evidence now confirms the local synthetic intake path, while connected and recovery paths remain to be tested.

The renderer uses installed DejaVu fonts rather than bundling third-party font files. FFmpeg and n8n are third-party components with their own distribution terms. Review all dependency, image, font, and asset licenses for the exact delivery form before reselling or publishing an image; `docs/COMMERCIALIZATION.md` records the specific n8n use-case distinction. This inventory is not a blanket redistribution license.

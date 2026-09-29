# Operations

## Prerequisites and first demo launch

Use Docker Compose, an available Docker daemon, and free loopback ports 4173, 5433, and the configured API/n8n/simulator ports. Their defaults are 8000/5678/8081; `API_HOST_PORT`, `N8N_HOST_PORT`, and `SIM_HOST_PORT` in `.env` can move them when occupied. The earlier verified local run used API 8000, n8n 15679, and simulator 18081; the private `.env` now reserves API 18000 after a collision on 8000. The Compose images are pinned in `docker-compose.yml`. In PowerShell, run `Copy-Item .env.example .env`; in a POSIX shell, run `cp .env.example .env`. Replace every placeholder secret in `.env`: `POSTGRES_PASSWORD`, `SERVICE_TOKEN`, `N8N_ENCRYPTION_KEY` (a random 32-byte value/hex string), `SIM_WORDPRESS_PASSWORD`, and `SIM_CONTROL_TOKEN`. Do not commit `.env`.

After prerequisites and configuration, one command starts the stack:

```text
docker compose up --build -d
```

Portal: `http://localhost:4173`; API/OpenAPI defaults to `http://localhost:8000/docs`; n8n defaults to `http://localhost:5678` and the local connector simulator to `http://localhost:8081`. Use the `.env` host ports when overridden: the current private configuration reserves API 18000, n8n 15679, and simulator 18081. Port 18000 has not been verified healthy since Docker degraded. PostgreSQL binds only to `127.0.0.1:5433`. The API applies Alembic migrations and seeds demo users, sources, and brands at startup in demo mode. Demo credentials are in `docs/HANDOVER.md`.

The five services were healthy earlier on 2026-09-28, but this host later reported global Docker virtual-disk I/O errors, the API returned 500, and a project-only restart failed. Current health is degraded. A global Docker Desktop restart would affect 26 running containers, including unrelated projects, and awaits owner approval; do not infer current service readiness from the earlier replay evidence. Preserve volumes and inspect Docker storage/health before another build.

The portal has a seeded, rendered showcase with a downloadable package. Its approval records say they are synthetic demo decisions, not human review. To run **actual n8n-triggered workflows**, create the n8n owner account, an n8n API key, a Header Auth credential carrying `X-Service-Token`, and a Basic Auth credential for the local WordPress simulator. Put their IDs/API key in `.env` as described in `workflows/README.md`. Run `python scripts/n8n/bootstrap.py` to import inactive, then `python scripts/n8n/bootstrap.py --activate-demo` to publish only demo triggers, and `python scripts/n8n/replay.py` to run five fixture scenarios plus duplicate, conflict, and malformed events. The replay script saves redacted evidence. Import is intentionally inactive by default. Restart the API container after adding `N8N_API_KEY`; the portal enables workflow actions only after its read-only check finds all seven pack workflows active. The key needs n8n `workflow:list` access. A healthy n8n process by itself is shown separately from a ready workflow pack.

Windows without a system `python` can use a Python 3.12 executable explicitly. For a local API process, from `apps/api` run `uv sync --extra dev`, `uv run alembic upgrade head`, then `uv run uvicorn contentstudio.main:app --reload`; from `apps/web` run `pnpm install --frozen-lockfile` and `pnpm dev`. Set `N8N_INTAKE_WEBHOOK` and `SERVICE_TOKEN` for new batch requests. The local SQLite default is a development convenience; the Compose deployment uses PostgreSQL.

In the default DEMO configuration, an uploaded media file is stored and playable but is not automatically given a transcript. Add an owned transcript as a separate source, or configure and verify the connected transcription adapter before starting a new media batch. The seeded synthetic presentations already have transcript fixtures. The portal disables batch creation for an untranscribed upload unless connected transcription is configured and the workflow pack is ready.

## Connected configuration

Set `MODE=connected`, `MODEL_PROVIDER=openai`, `MODEL_ID`, `OPENAI_API_KEY`, `TRANSCRIPTION_PROVIDER=openai`, `TRANSCRIPTION_MODEL`, and an HTTPS `WORDPRESS_BASE_URL`. Configure a customer-owned WordPress application password in the n8n credential, scoped to a user allowed to create drafts. The [WordPress REST API authentication guide](https://developer.wordpress.org/rest-api/using-the-rest-api/authentication/) describes HTTPS Basic Auth with application passwords; the [posts endpoint](https://developer.wordpress.org/rest-api/reference/posts/) supports `status: draft`. Use only authorized test accounts/recipients for live smoke tests and set a spending cap first. A missing or failed live adapter must remain an error.

After the connected database migration, create its **first** administrator once. Run this from `apps/api` with the connected environment loaded, or prefix it with `docker compose exec api` in a running Compose installation:

```text
python -m contentstudio.bootstrap_admin --email owner@example.com --workspace-slug your-workspace --workspace-name "Your Workspace"
```

The command prompts twice for a unique 12–128 character password with upper/lowercase letters and a digit; it never takes a password argument. For an unattended secret-injection step, use `--password-stdin` and pipe from a secure secret source without writing it to shell history. A database marker and account check reject a second bootstrap. Replace the example address, slug, and workspace name with customer values; do not use demo credentials in connected mode.

Place a TLS reverse proxy in front of the portal/API and set `COOKIE_SECURE=true`, `N8N_PROTOCOL=https`, `N8N_SECURE_COOKIE=true`, and the public webhook base URL. Keep n8n's UI, internal service token, simulator control API, and database off public networks. The current Compose uses n8n's internal task runner for demo; use an external task runner and validate its configuration for connected deployment. Full customer backup/restore and n8n recovery tests are release gates.

## Jobs, retries, and recovery

`/api/v1/jobs/{id}` stores status, progress, result/failure, and supports SSE. Queued jobs can be cancelled. n8n workflows use bounded retries for transient 429/timeout/5xx, route permanent errors to incidents, and put unknown external outcomes into reconciliation. Before retrying an ambiguous WordPress write, inspect the provider draft and the dispatch ledger. Do not assume arbitrary third-party exactly-once semantics. The [intake replay](../workflows/evidence/replay-20260928T083343b793bd.json) verified Error Trigger runs for conflict and malformed events. The [dispatch replay](../workflows/evidence/dispatch-429-duplicate-20260928.json) verified one simulated 429 wait/retry and one draft after a duplicate due trigger. Restart, timeout/5xx retry, concurrent processing, and ambiguous provider-outcome tests remain pending.

Health probes: API `/healthz`, n8n `/healthz`, simulator `/health`, and PostgreSQL `pg_isready`. The portal's connection indicator reads API configuration/health.

## DEMO reset and retention

After Docker health is restored and the updated API image is built, stop the API and n8n triggers, take a backup, then preview a one-workspace cleanup. The utility requires explicit `MODE=demo` and `DATABASE_URL`; `--older-than-days 30` selects generated batches older than 30 days. It prints exact batch IDs, row counts, media paths, workspace UUID, and a plan fingerprint without deleting anything:

```text
docker compose --env-file .env stop api n8n
docker compose --env-file .env run --rm --no-deps --entrypoint python api -m contentstudio.demo_reset --workspace-slug studio-alpha --older-than-days 30
```

Only after reviewing that plan, rerun the same command with `--apply --offline-ack --confirm-workspace-id <printed-UUID> --confirm-plan-sha256 <printed-SHA256> --expected-batch-count <printed-count>`. The utility rechecks the selected batches and workspace scope before deleting linked assets, reviews, jobs, drafts, ledgers, incidents, and selected batch media. It preserves users, sources/source media, transcripts, brands, the other workspace, n8n data, the simulator, LangGraph checkpoints, and backups. `--all-batches` also selects the seed showcase/archive in that workspace. Media deletion failures are reported after the database commit for manual cleanup. This utility was tested on disposable data and **was not run against the delivered DEMO**. n8n execution pruning is configured separately; no automatic business-content sweep or full data erasure is claimed. See [workflow setup](../workflows/README.md#demo-reset-and-retention) for details.

## Backup and restore smoke test

Back up both PostgreSQL databases (`contentstudio`, `n8n`), the `media_data` and `n8n_data` volumes, and the **same** `N8N_ENCRYPTION_KEY` in a separate secret store. The simulator's `connector_data` is useful for demo replay but is not customer business truth. An example logical database backup, after the stack is running, is:

```text
docker compose exec -T postgres pg_dump -U contentstudio -Fc -f /tmp/contentstudio.dump contentstudio
docker compose exec -T postgres pg_dump -U contentstudio -Fc -f /tmp/n8n.dump n8n
docker compose cp postgres:/tmp/contentstudio.dump ./contentstudio.dump
docker compose cp postgres:/tmp/n8n.dump ./n8n.dump
```

For a restore drill, create a fresh isolated installation with an empty data volume, restore both dumps with `pg_restore`, restore the media and n8n volumes, inject the saved encryption key, then verify login, one source playback, one rendered file, one n8n credential, and a duplicate replay that creates no second draft. Record the drill date and hashes. On 2026-09-28, a narrower drill restored a 243,539-byte ContentStudio `pg_dump` into a disposable PostgreSQL database and compared row counts across 14 tables. It did not restore media files, the n8n database or volume, or the encryption key. The full drill described above remains pending.

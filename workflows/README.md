# ContentStudio n8n workflow pack

This directory contains seven readable n8n exports plus `manifest.json`. The exports target n8n **2.40.7**, a stable release published on 25 September 2026. They use built-in nodes only; no community or enterprise node is required. All seven were imported, read back and activated on a local n8n 2.40.7 DEMO instance on 28 September 2026; the triggered intake and WordPress draft retry paths were verified with real executions.

## Responsibilities

| Workflow | Trigger | Effect |
| --- | --- | --- |
| `intake` | Authenticated POST `/webhook/contentstudio/intake` | Claims a source/versioned batch, then invokes transcription and generation. Returns HTTP 202 promptly. |
| `transcribe_generate` | Sub-workflow | Calls typed transcription and AI-bundle steps in order. |
| `due_items` | Five-minute schedule or authenticated demo replay webhook | Reads due actions from the business DB through the API and routes render/package/WordPress dispatch/local outbox preparation. |
| `render_item` | Sub-workflow | Invokes rendering of an exactly approved asset version. |
| `dispatch_draft` | Sub-workflow | Claims a durable operation, creates a WordPress **draft**, and records the external ID. |
| `reconcile` | Fifteen-minute schedule or authenticated demo replay webhook | Searches WordPress by stable slug for uncertain writes; leaves unresolved actions queued. |
| `error_handler` | Error Trigger | Records a redacted system incident in the business exception queue. |

Large media stays in the API's scoped media storage. n8n execution data carries IDs and small typed results. The API is the source of truth for assets, approvals, jobs, and dispatch ledger. The review portal calls the authenticated API, never the n8n admin API or a Wait resume URL.

## Configuration and import

1. For DEMO, run `python scripts/n8n/create_demo_env.py` to create a private `.env` with independent random secrets, then run `docker compose --env-file .env up --build -d`. Set `--n8n-port` and `--sim-port` on the generator if the default host ports are occupied. On a fresh PostgreSQL volume, the init script creates separate `contentstudio` and `n8n` databases.
2. For a loopback DEMO instance, run `python scripts/n8n/provision_demo.py`. It creates or signs into a local n8n owner, creates a scoped public API key and the required Header Auth and Basic Auth credentials, then saves IDs and secrets only in the ignored `.env` without printing their values. If the API container was already created, recreate just that container so it receives `N8N_API_KEY`.
3. For a CONNECTED installation, create the n8n owner and API key through its admin UI. Create a **Header Auth** credential named `ContentStudio service token`: header name `X-Service-Token`, value exactly `SERVICE_TOKEN` from `.env`. Create a **Basic Auth** credential named `ContentStudio WordPress draft` using a scoped WordPress application password over HTTPS. Put the two credential IDs and key into private `.env` as `N8N_SERVICE_CREDENTIAL_ID`, `N8N_WORDPRESS_CREDENTIAL_ID`, and `N8N_API_KEY`.
4. Import the workflows. The script reads the local `.env` without printing secrets. In PowerShell or POSIX shell, run:

   ```powershell
   python scripts/n8n/bootstrap.py
   ```

   Use the `--n8n-url`, `--api-base-url` and `--wordpress-base-url` flags if endpoints differ. The defaults are localhost n8n, Docker-internal API, and Docker-internal simulator. In `MODE=connected`, set `WORDPRESS_BASE_URL` to an HTTPS origin before importing; bootstrap rejects cleartext WordPress URLs because the workflow uses Basic Auth. HTTP is accepted only for the local DEMO simulator. The script resolves actual imported workflow IDs in manifest order, wires parent and error-workflow references, maps credential IDs, updates matching workflow names idempotently, reads every workflow back, and leaves all seven inactive.
5. For the local simulated demo only, run the same command with `--activate-demo`. This publishes the three entrypoint workflows and their four required sub/error dependencies. The due/reconcile webhooks are meant only for authorized local replay. Never use this flag against a connected customer deployment without reviewing connector configuration and scheduled drafts.

`python scripts/n8n/bootstrap.py --dry-run` checks the pack without n8n. `python scripts/n8n/build_pack.py` regenerates exports after edits. On n8n 2.x, [sub-workflow](https://docs.n8n.io/build/flow-logic/break-workflows-into-smaller-parts) and [error-workflow](https://docs.n8n.io/build/flow-logic/handle-errors-gracefully) references must resolve before activation. Error Trigger behavior must be verified through a **published production execution**, not a manual canvas run.

## Connector contract

| Boundary | Request | Success | Retry or recovery |
| --- | --- | --- | --- |
| API intake | `POST /internal/workflows/intake` with workspace/source/brand/recipe/request IDs | `{batch_id, duplicate, status}` | Conflicting same event ID returns 409; business ledger prevents duplicate batch. |
| Transcription / generation | `POST /transcribe`, then `/generate`, each with `{workspace_id,batch_id}` | Persisted transcript and review bundle | Backend records failed stage; a later replay can retry idempotent step. |
| Render / package | `POST /render` by asset version or `/package` by batch | Persisted render job/package | Jobs are claimed in the DB, and stale leases can be recovered. |
| Dispatch prepare | `POST /dispatch/prepare` with unique operation key | `{claimed, draft}` | Only `claimed=true` reaches WordPress; subsequent claims do not rewrite. |
| WordPress draft | `POST /wp-json/wp/v2/posts` with status `draft`, stable slug, Basic Auth | `{id,status,slug}` | A known 429 waits once honoring `Retry-After` (capped at 60s) plus jitter. Permanent 4xx creates a failed incident; timeout/5xx or another uncertain result enters reconciliation, with no blind write replay. |
| Reconcile | `GET /wp-json/wp/v2/posts?slug=…&status=draft` | Exactly one match closes ledger | Zero/multiple matches stay in exception queue for operator review. |
| Local outbox | `POST /internal/workflows/outbox` with due item IDs and operation key | A ready newsletter/social draft in the business DB | Idempotent; it never sends an email or posts to a social account. |

The local connector simulator implements the same draft POST/search shapes. It persists drafts, deduplicates an `Idempotency-Key`, rejects a conflicting key, and offers a simulated mail outbox. Real WordPress does **not** promise idempotency from that header; stable slug lookup and human reconciliation are therefore required after ambiguous outcomes. The simulator supports controlled `429`, `500`, and after-write connection loss via `POST /__control/fail-next`, authenticated with `X-Sim-Control-Token`.

Use the [HTTP Request node's full response and never-error options](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/) to classify provider responses. The pack uses HTTP Request 4.2, Webhook 2.1, Schedule Trigger 1.3, Code 2, IF 2.2, Execute Workflow 1.2, Execute Workflow Trigger 1.1, Wait 1.1, Error Trigger 1, and Sticky Note 1. Import/readback and the triggered intake, due, WordPress retry, and Error Trigger paths ran on n8n 2.40.7. The scheduled trigger and render, package, and reconciliation branches have not been verified through n8n yet.

## Replay and evidence

After seeding the API and activating the demo pack, run:

```powershell
python scripts/n8n/replay.py
```

The replay obtains five seeded request bodies from the service-token-protected demo endpoint, triggers five real production webhooks, then sends a duplicate, a conflicting event ID, and a malformed payload. It checks successful n8n executions and persisted 11-asset review bundles for all five sources, proves the duplicate preserves its batch, and checks both rejected events invoke the Error Trigger without changing durable state. It writes only IDs, statuses, counts and timings to `workflows/evidence/replay-*.json`. [The recorded local replay](evidence/replay-20260928T083343b793bd.json) passed on 28 September 2026. A fixture transcript run is **not** an audio-transcription quality test.

To process approved jobs without waiting for the schedule, POST `{}` with `X-Service-Token` to `/webhook/contentstudio/due-demo`. To force reconciliation after simulating an unknown write, POST `{}` to `/webhook/contentstudio/reconcile-demo`. The API's `GET /due` and `/reconcile` accept an ISO-8601 `now` override only in DEMO mode.

The local WordPress simulator returned one controlled 429; n8n waited, retried once and completed the ledger with exactly one draft. A duplicate due trigger and repeated dispatch claim left that draft count at one; see the [redacted dispatch record](evidence/dispatch-429-duplicate-20260928.json). The API's startup showcase separately rendered a carousel, three clips, and a downloadable ZIP. An additional run of those jobs through the n8n due webhook, with per-file timing and resource measurements, paused before the first render when the host's C: disk filled and API login returned 500. Later Docker virtual-disk I/O errors mean current service health must be checked before resuming.

## DEMO reset and retention

`python -m contentstudio.demo_reset` is a **dry run by default**. It requires explicit `MODE=demo`, `DATABASE_URL`, and one of the two seeded workspace slugs. `--older-than-days 30` selects generated batches older than 30 days and their linked assets, reviews, jobs, draft records, dispatch and webhook ledgers, incidents, and batch media. It excludes the seeded archive and showcase. `--all-batches` selects every batch in that one DEMO workspace, including the seed baseline. Unlinked webhook events and system incidents stay in place. Users, sources, source media, transcripts, brand profiles, the other workspace, n8n data, the shared connector simulator, LangGraph checkpoints, and backups stay in place.

For an actual reset, stop the API and n8n triggers, take a backup, review the dry-run batch IDs/count/media paths/fingerprint, then rerun with `--apply --offline-ack --confirm-workspace-id <exact-UUID> --confirm-plan-sha256 <dry-run-fingerprint> --expected-batch-count <dry-run-count>`. The command refuses a connected installation marker, a different seeded workspace ID, an active render job, a changed batch set, or a media path escaping the selected workspace. It commits database deletion before removing only that workspace's selected batch directories; if media removal fails, it reports those paths for manual cleanup. No reset was run against the delivered DEMO data. A typical one-off invocation in a rebuilt Compose image is:

```text
docker compose --env-file .env stop api n8n
docker compose --env-file .env run --rm --no-deps --entrypoint python api -m contentstudio.demo_reset --workspace-slug studio-alpha --older-than-days 30
# Review the printed plan before appending the explicit --apply confirmations.
```

n8n execution pruning is separate from the business-content reset. Compose sets `EXECUTIONS_DATA_PRUNE=true`, with `N8N_EXECUTION_MAX_AGE_HOURS=24` and `N8N_EXECUTION_MAX_COUNT=1000` by default; these values can be changed in private `.env`. The [n8n execution-data guide](https://docs.n8n.io/deploy/host-n8n/configure-n8n/scaling/manage-execution-data) says pruning is rolling and does not apply to running, waiting, or annotated executions. DEMO saves successful execution details for replay evidence, potentially including webhook headers. Use `N8N_SAVE_SUCCESS_EXECUTIONS=none` and a reviewed retention policy in CONNECTED mode. Source files, transcript history, simulator drafts, LangGraph checkpoints, and backups need separate customer retention and deletion procedures; this utility does not claim full data erasure.

## Deployment and license boundary

The example binds all exposed service ports to loopback, uses a single n8n process, and keeps n8n metadata separate from business data. Back up PostgreSQL, the media volume, and n8n's **encryption key** together. Do not expose n8n admin or simulator control endpoints to the public Internet. `N8N_SAVE_SUCCESS_EXECUTIONS=all` is for the synthetic DEMO replay only: n8n may persist webhook headers and payloads, including token-bearing headers, in its local PostgreSQL database until its rolling prune runs. Commit only redacted evidence files, and set this value to `none` for CONNECTED installations. The Compose file uses an internal Code-node task runner for the isolated synthetic demo; [n8n recommends an external runner for instances holding sensitive data](https://docs.n8n.io/deploy/host-n8n/configure-n8n/set-up-task-runners). Configure that, HTTPS, secure cookies, restricted network paths, managed secrets, backups, and connector credentials per customer before a connected deployment.

n8n's [Sustainable Use License](https://github.com/n8n-io/n8n/blob/master/LICENSE.md) is not a blanket right to host client workflows or embed n8n. n8n's [use-case guidance](https://support.n8n.io/article/can-i-use-your-license-for-my-use-case) distinguishes consulting on client-owned instances from hosting clients' workflows/credentials or embedding n8n in a product; get the relevant commercial entitlement before the latter offerings.

# ContentStudio functional checkpoint — 2026-10-06

This file records the earlier nonvisual checkpoint. The subsequent approved production layout and appearance rollout is recorded in [THEME_ROLLOUT.md](THEME_ROLLOUT.md).

This checkpoint implements the bounded nonvisual portfolio pass. The later production desk and appearance rollout is documented separately above. All work stayed inside ContentStudio. Existing dirty README/ignore/CI/product/status/evaluation/browser-security edits and teaser assets were preserved; no sibling project, shared root script, live provider, publication schedule, push, or deployment was modified.

## Implemented behavior

- Operators/admins can create and revise brand profiles from Source library. Revisions are immutable, history remains visible, concurrent/stale revision IDs are rejected, and existing batches keep their pinned brand. Demo reseeding preserves stored brand versions. Prohibited phrases, accent, tone and social character limits have bounded validation.
- Transcript corrections reject stale editor snapshots. Asset edits support explicit source citations and expected content hashes, reject invalid type-specific shapes, and reopen a completed batch for review. If the source changes while regenerating an asset, the generated work is discarded.
- Missing original media is labeled accurately and can be restored by uploading the same recording/title. Playback includes a retry path. Clip rendering checks measured duration and the original recording's content hash. FFmpeg filtering/encoding uses a configurable bounded thread count.
- Render attempts have immutable lease-specific directories. Source/asset edits revoke render jobs; an obsolete worker cannot register current output. Public routes serve only registered, current, complete render files. Missing completed render files can be requeued without a new asset approval.
- Publication packages require exact version approvals and complete rendered media. Schema version 2 manifests include the pinned brand, generation/current transcript IDs, source provenance/rights/hash, approval hashes, and streamed payload checksums/byte counts. Old package schemas have a different operation fingerprint. Failed/missing media is never silently omitted.
- Scoped job discovery restores render/package status after reload. Stale/cancelled jobs stop polling and event streams. Queued cancellation checks state atomically. The editorial desk resets transient state when its batch/source changes, and logout now clears workspace data and returns to sign-in.

The BrandManager and MediaPlayback modules isolate workflow behavior from appearance. No CSS/theme restyling was performed in this pass.

## Current verification

| Check | Result | Boundary |
| --- | --- | --- |
| API pytest | **43 passed**, 27.46 s | Isolated SQLite, fixture AI, real approval/storage routes; regression render substitutes for failure/race cases |
| Workflow unittest | **23 passed**, 2.10 s | Local connector simulator and mocks; not an actual n8n execution |
| Deterministic validation evaluation | **70 passed**, 10 not run, no failures, out of 80 cases | The 10 non-executable cases remain unverified |
| Ruff | **Passed** | API, API tests, and new media QA script |
| Generated API contract | **Passed** | OpenAPI and TypeScript request/response types regenerated with stable LF newlines |
| Frontend ESLint/TypeScript/Vite | **Passed** | Final production build: 1,636 modules, JS 335.07 kB / 102.11 kB gzip |
| Dedicated headless Chrome QA | **Passed** | Brand v1→v2/history, media failure/retry, logout/login, viewer UI/API write denial, job discovery and package status after reload; no page errors |
| Responsive functional QA | **Passed** | 1,440 / 1,024 / 390 px source views without horizontal overflow; these are functional checks, not final design approval |
| Actual synthetic recording/media/package QA | **Passed**, 7.80 s | Installed FFmpeg and existing owned synthetic recordings, direct internal API steps and fixture AI; no n8n trigger or connected provider |

The real media QA produced 11 drafts, selected three approved assets (article, carousel and clip), rendered a 1,080×1,350 carousel and a subtitled clip, fully decoded the clip, verified every packaged payload checksum, and confirmed repeated render steps reused the completed operation. The resulting ZIP has **13 files / 1,869,265 bytes**. It demonstrates an approved subset, not completion or approval of the other eight drafts.

Workspace-local receipts are in `tmp/preview/qa/portal-checkpoint.json` and `tmp/media-checkpoint/report.json`; responsive diagnostic screenshots are in `tmp/preview/qa/`. The real sample is `tmp/media-checkpoint/publication-package.zip`. These are ignored local outputs. Repeatable QA source is in `scripts/qa-portal-checkpoint.cjs` and `scripts/qa-media-checkpoint.py`.

## Preview and reuse

The current loopback preview is **http://127.0.0.1:4319**, API **8319**, using `tmp/preview/contentstudio.db`, a copy of the original demo database. Demo accounts use `DemoStudio!2026`. The preview uses existing media and fixture adapters, with external provider/WordPress/n8n intake configuration disabled. Its displayed intake/connector unavailability is intentional and accurate. Logs and the launched process IDs are in `tmp/preview`.

See [customization and local launch](CUSTOMIZATION.md) for brand rules, source recovery, package semantics, extension boundaries and verification commands.

## Remaining boundaries

Actual n8n-triggered rendering/packaging/restart/concurrency, PostgreSQL concurrency behavior, connected model/transcription and live providers, full media/n8n-key restore, and audible editorial caption/context review retain their separate release gates. No paid API, social posting, publication scheduling or live external workflow was executed. Old render attempt files remain for recovery/audit; no retention cleanup was run.

The nonvisual pass is complete; the later production desk and theme rollout is documented in [THEME_ROLLOUT.md](THEME_ROLLOUT.md).

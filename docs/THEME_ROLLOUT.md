# ContentStudio production desk and appearance rollout

Production desk and appearance checkpoint, 2026-10-07. Verification uses local synthetic fixtures; no deployment, live provider, social scheduling or n8n execution was performed in this rollout.

## Implemented experience

- A source-first production desk with timestamped transcript spans, claim ledger, pinned brand version, working assets, exact-version review and a delivery queue.
- A four-stage readiness strip derived from actual transcript/asset state. Review counts remain distinct from approval of the subset selected for a package.
- Advisory package preflight blocks missing approval, evidence, validation warnings and incomplete media files. Server-side rights, approval/hash, source-version and registered-file checks remain authoritative. The existing workflow-unavailable state stays visible and prevents new queued render/assembly requests; completed files remain downloadable.
- Semantic Light, Dark and System chrome across sign-in, studio, board, library, calendar, editing, recovery and notices. Dark is the fresh-visit default. Valid preferences persist; System alone listens to OS appearance changes; blocked storage uses a safe session preference.
- A same-origin blocking theme bootstrap and canvas stylesheet run before the bundle. The native color scheme and browser theme color match before application mounting. No external font download is required.
- Theme state is independent of application state. Only the appearance controls subscribe; drafts, DOM editors, filters, selected evidence, routes and active jobs remain mounted. Authored paper, draft slides, rendered images, video and brand/media accents retain their own palettes.
- Accessible mobile navigation with background inertness, focus trapping, Escape handling and focus restoration. Appearance changes preserve an open menu. Article preview scrolls within the authored paper rather than stretching the workspace to the entire document length.

## Verification

| Check | Result | Practical boundary |
| --- | --- | --- |
| API regression | 43 passed, 30.99 s | Isolated SQLite and fixture adapters; render substitutions cover integrity/race failures |
| Workflow unit tests | 23 passed, 2.23 s | Local connector simulator/mocks, not actual n8n |
| Appearance/preflight unit tests | 7 passed | Real entry-point ordering, defaults, persistence, System listener, blocked storage, cross-tab changes and production-file preflight |
| API Ruff | Passed | Run from `apps/api` so first-party import discovery uses the project configuration |
| Generated API types | Passed | Matches the current OpenAPI snapshot |
| Frontend ESLint and TypeScript | Passed | Final changed source |
| Production Vite build | Passed, 1,640 modules | JS 347.69 kB / 104.99 kB gzip; CSS 69.74 kB / 13.90 kB gzip |
| Dedicated appearance browser QA | Passed | Actual installed headless Chrome, local fixture preview; checks below |
| Preserved functional browser QA | Passed | Brand v1/v2/history, source playback abort/retry, viewer UI/API denial, logout/login, durable jobs and package status after reload |
| Actual installed FFmpeg sample | Previously passed, unchanged rendering source | 11 drafts, three approved packaged assets, 13-file ZIP, full clip decode and payload hashes; fixture AI/direct internal API, not n8n |

Browser checks cover fresh Dark on a light OS, saved preference after reload, live System changes, explicit-mode independence, denied storage, a restrictive same-origin CSP prepaint page, retained editor DOM and unsaved text, selected source spans/type filter, brand draft/media accent, retained navigation route, no extra business requests from appearance, immutable authored paper palette, mobile focus/Escape and service-error recovery states. Both themes have zero horizontal overflow at 1,440 / 1,024 / 768 / 390 px, zero page errors and zero CSP errors in the dedicated prepaint check.

The final image set is visually inspected at desktop/mobile and intermediate sizes. These are actual synthetic-fixture screenshots, not product mockups or proof of connected model quality. Existing sample media and old package statuses can correctly show synthetic presentation content or a stale package; the UI does not relabel those as newly completed work.

## Evidence and repeatable checks

- [Representative desktop/mobile Light and Dark screenshots](evidence/theme-rollout/README.md) and [exact source image hashes](evidence/theme-rollout/manifest.json). Four public images represent the full 22-image local QA set.
- Repeatable checks: `scripts/test-theme.cjs`, `scripts/qa-theme-rollout.cjs`, `scripts/qa-portal-checkpoint.cjs`, `scripts/qa-media-checkpoint.py`.
- [Client configuration and local fixture launch](CUSTOMIZATION.md). Full QA receipts, copied databases and media package outputs remain ignored local files; they are not required to browse this repository.

Actual n8n-triggered/restarted workflows, PostgreSQL concurrency, connected transcription/model/provider quality, full media/key restore and audible editorial context review retain their existing release gates. GitHub source publication does not validate or activate these external services.

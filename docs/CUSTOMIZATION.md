# Reuse and customize ContentStudio

ContentStudio is an editorial production pilot for an owned recording or a supplied transcript. Use it for a consultant's knowledge library, a B2B webinar desk, or an internal communications team. The current deterministic demo proves workflow behavior; it does not prove connected model quality or provider reliability. The production desk now has semantic Light, Dark and System appearance controls; its authored media palette remains independent.

## Local review without Docker

Existing local Python/Node dependencies, DejaVu fonts, and FFmpeg are required. The preview script installs nothing. From the repository root on Windows:

```powershell
./scripts/start-local-preview.ps1
```

Open `http://127.0.0.1:4319` (API `8319`). Sign in as `admin@studio.test`, `editor@studio.test`, or `viewer@studio.test` with `DemoStudio!2026`. The script copies the existing local database into `tmp/preview/contentstudio.db` and resets only the four copied demo account passwords. Media stays in the existing project storage. Logs and the two process IDs are in `tmp/preview`. The API uses fixtures with n8n, WordPress, and external provider configuration disabled in this preview. Intake is therefore honestly marked unavailable; this launcher does not execute or simulate an n8n trigger.

If the checkout was renamed and pnpm's Windows junctions still target the previous folder, repair existing local targets with:

```powershell
./scripts/repair-local-web-links.ps1 -PreviousWebRoot 'D:\previous-checkout\apps\web'
```

The script checks that every replacement exists within this checkout's `apps/web/node_modules`, then replaces only the individual junctions. It neither installs packages nor recursively deletes directories. On another machine use the documented locked install instead.

## Application appearance

The workspace and sign-in screen provide Light, Dark and System controls. Fresh visits default to Dark; valid stored choices under `contentstudio.theme` are retained. System alone follows operating-system changes. Storage denial keeps an in-memory preference without interrupting work. Theme changes update document attributes and only the appearance control subscribes: editors, filters, selected source evidence, routes and jobs stay mounted.

`apps/web/public/theme-init.js` is a blocking same-origin prepaint script; `theme-base.css` supplies matching canvas and native control colors before the app bundle arrives. Both work with `script-src 'self'; style-src 'self'` without inline bootstrap code. `src/theme.css` owns semantic chrome tokens. Authored paper and draft-slide palettes stay in `src/style.css`, while brand accents and production media remain versioned server data. Do not replace those authored palettes with application tokens or add global image/video inversion.

The production path is an advisory view of current evidence, review and delivery readiness. Package preflight requires an approved subset with linked evidence, clean validation and complete media render URLs. The server still verifies exact approval hashes, current source versions, rights and registered-file integrity. An existing completed package can be downloaded while n8n intake is unavailable; new renders and assembly stay paused.

Repeat the appearance tests with `node scripts/test-theme.cjs`. The local headless workflow is `scripts/qa-theme-rollout.cjs`; use the existing Playwright runtime through `CONTENTSTUDIO_PLAYWRIGHT` and the installed Chrome path through `CONTENTSTUDIO_BROWSER`, with preview URL restricted to loopback. Its screenshots and report are written to `tmp/preview/theme-qa/`. No install, live provider call or publication is performed.

## Brand customization

Open Source library → Brand profiles and version history. Operators/admins can create a brand or revise its latest version. Viewers can inspect history. The server accepts a brand name of 2–45 characters, tone of 2–300 characters, a six-digit hex accent, up to 50 prohibited phrases, and a social character limit of 80–500. The 500-character editorial ceiling remains in force for historical fixture brands configured above that ceiling.

`POST /api/v1/brands` creates version 1. `PUT /api/v1/brands/{latest-version-id}` stores a new immutable version. A stale revision ID returns 409 and must be reloaded. Saving identical settings returns the existing version. Batch records retain their exact `brand_profile_version_id`; later brand edits never change past draft rules, approvals, or rendered branding. Demo reseeding also preserves existing brand records. Create a new batch with the desired brand version to adopt revised rules.

Brand presentation and editorial rules are separate from the application's appearance system. `features/BrandManager.tsx` contains the authoring flow; `rendering.py` owns the media tokens. Changing a brand accent affects its derived media, not the overall portal theme.

## Source and evidence editing

Record source rights at intake. Manual transcript text cannot be blank. Corrections create a transcript version with stable segment IDs and invalidate dependent current assets, render jobs, packages, and pending publication drafts. The portal sends `expected_transcript_id` when correcting text; another editor's newer transcript returns 409 instead of being overwritten.

The asset editor supports changing the cited source spans as well as copy, slides, and clip range. The API accepts only distinct segment IDs from that source's current transcript and an optional `expected_hash`. Saving creates a new asset version and reopens the batch for review. Carousel slides have their own citations, which must also appear in the asset's selected source map. A stale source asset must be regenerated before editing. If the source changes during regeneration, the new copy is discarded and the current source can be reviewed again.

Clip ranges require integer timestamps and one of `9:16`, `1:1`, or `16:9`. Ranges cannot be attached to text assets. Rendered clips must fit inside the measured recording duration; the original recording bytes must still match the source's SHA256. A supplied transcript's timestamps are not proof of audio alignment. Human review of caption timing and complete context remains necessary.

## Failure recovery and durable output

- Source detail reports `available`, `missing`, or `transcript_only`. Playback includes a retry control. Upload the same recording with the same title to restore a missing original while retaining the source ID and transcript.
- Render attempts write into separate lease directories. A stale worker cannot replace the current attempt's URLs, and source/asset changes revoke active render jobs. Public render routes serve only the complete registered current output set; temporary title cards and arbitrary filenames are inaccessible.
- If a completed render loses a registered file, requesting render again requeues the same immutable operation and invalidates its package. Renderer dependency failures return 503; invalid render content returns 422; unavailable or changed source media returns 409. Job records preserve the failure reason.
- A publication package requires exact version approvals and warning-free current assets. Approved carousel/clip assets must be fully rendered. Missing media cannot silently disappear from a ZIP. Text-only approved subsets remain supported.
- `manifest.json` schema version 2 records the batch recipe, pinned brand settings, generation/current transcript version IDs, source rights/provenance and hash, reviewed content hashes, and SHA256/byte counts for every packaged payload file. Checksums are computed from the actual streamed ZIP bytes. The manifest does not checksum itself. Rebuild a missing ZIP from the current approvals.
- `stale` and `cancelled` are terminal job states in the portal and event stream. Cancelling a queued operation uses an atomic state check so it cannot cancel an operation that just started.
- Workspace-scoped `GET /api/v1/jobs?batch_id=...` restores render/package progress after a page reload. The portal keys each editorial desk to its current batch/source so temporary form and package states do not leak to another batch. Sign-out removes cached workspace data and returns to the login form.

Keep source media, immutable render attempts, package files, and database backups together. Old attempt files remain for recovery/audit; this upgrade does not run retention cleanup. Preserve referenced versions and current manifests before applying a project-specific retention policy.

`MEDIA_RENDER_THREADS` defaults to 2 and accepts 1–16; it bounds both FFmpeg filtering and video encoding for modest workstations. Changing the package manifest schema also changes its immutable operation fingerprint, so packages from the previous format are rebuilt instead of being reused as current output.

## Extend without mixing responsibilities

Keep provider adaptation in the existing API adapters, workflow triggers/retries in n8n, editorial state in the API/database, and frontend feature components independent of presentation tokens. New output formats should carry stable source IDs, bounded validators, version-specific review decisions, an immutable render operation key, and a package manifest entry. Do not add social publishing as an implicit side effect of preview or package creation.

Brand authoring, media recovery, and job status now live in isolated frontend modules that can be recomposed when the flagship visual direction is supplied. Product-specific visual opportunities include a source timeline with caption context, a clear evidence rail beside copy, a version comparison view, and a publication package preflight showing exactly which reviewed versions and files will be included.

## Verify customization

```powershell
cd apps/api
$env:PYTHONPATH='src'
$env:TEMP=(Resolve-Path '../../tmp').Path
$env:TMP=$env:TEMP
./.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp='../../tmp/customization-qa'
./.venv/Scripts/python.exe -m unittest discover -s ../../tests/workflows -v
./.venv/Scripts/ruff.exe check --no-cache src ../../tests/api
./.venv/Scripts/python.exe -m contentstudio.export_openapi
./.venv/Scripts/python.exe ../web/scripts/generate-openapi-types.py
cd ../web
node node_modules/eslint/bin/eslint.js .
node node_modules/typescript/bin/tsc -b --pretty false
node node_modules/vite/bin/vite.js build
```

Use a short fresh pytest base path on Windows to keep nested media paths below platform path limits. API regression render substitutes deliberately create tiny fixture files; they validate approval/storage/concurrency behavior, not media fidelity. `scripts/verify_media.py` separately exercises installed FFmpeg and real synthetic recordings. Actual n8n, PostgreSQL concurrency, connected transcription/model quality, and live provider behavior retain their separate release gates in the existing implementation status.

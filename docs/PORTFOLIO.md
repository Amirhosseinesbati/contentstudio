# ContentStudio — independent portfolio project

This is an independently built portfolio project with a **Synthetic demo dataset**. Morrow Research, Alder Field Notes, all participants, media, customers, and editorial outcomes are fictional. It is a commercial pilot starting point, not a claim of deployed customer work or measured marketing lift.

## Case study

**Problem.** A B2B team can turn an owned talk into many drafts, but each channel edit can lose caveats, numeric context, or source provenance. Review work becomes hard to repeat and clips can cut away a qualifying phrase.

**Solution.** ContentStudio stores a versioned source transcript and claim ledger, generates a bounded bundle of 11 draft assets, blocks exact-quote and numeric mismatches before approval, and lets an operator edit/regenerate one asset without discarding siblings. Approval binds to the exact content hash. n8n coordinates intake, rendering, packaging, and WordPress draft dispatch, while the Python service handles the typed AI task and media renderer. The React portal keeps source spans and review state visible.

**Technical choices.** PostgreSQL is business truth; n8n uses a separate database on the same server. Large media lives outside workflow JSON. A fixture model and local WordPress-like simulator make the demo safe; connected adapters require configuration. Renderer arguments are validated data, not model-written commands. An operation ledger controls retries and external draft reconciliation.

**Measured local evidence.** Twelve fictional transcripts of 2,727–2,797 words, three playable synthetic presentations of 550–600 seconds, four brand versions, and 120 archive asset versions were generated reproducibly. The API seed produced a separate 11-asset showcase. Seventy of seventy executed planted deterministic validation cases emitted the expected warning; ten duplicate-dispatch cases require the persisted integration path. A local API smoke completed review, seven-slide PNG/PDF render, three subtitled MP4 renders, and a 17-file ZIP in 24.31 seconds on this Windows host. A fresh empty-database demo seed completed a fully rendered showcase and valid 23-file ZIP in 15.79 seconds; those approvals were explicitly synthetic demo decisions. Actual n8n 2.40.7 import and [intake evidence](../workflows/evidence/replay-20260928T083343b793bd.json) verified five triggered, persisted 11-asset review bundles, an idempotent duplicate, and conflict/malformed Error Trigger runs against a local simulator. [Dispatch evidence](../workflows/evidence/dispatch-429-duplicate-20260928.json) verifies one 429 wait/retry and one simulator draft after a duplicate due trigger. A scoped 243,539-byte PostgreSQL dump restored to a disposable database with 14 table counts checked. Docker later degraded with virtual-disk I/O errors and API 500. These historical results do not measure live model accuracy, real transcription, audience engagement, customer ROI, or full backup recovery.

## 60–90 second demo script

“This is ContentStudio, an editorial review workspace for owned talks. Everything you see here is a synthetic demonstration. I’ll open a fictional ten-minute presentation and select a source sentence. The timestamp and surrounding paragraph remain beside the draft, so an editor can check what the speaker actually said. The batch contains an article, newsletter, five social drafts, a seven-slide carousel, and three clip proposals. I can revise this headline without changing the other assets. Approval is tied to the exact version, and a changed source passage marks dependent assets stale. Now I’ll render the approved carousel and clips. These are actual PNG, PDF, and MP4 files with subtitles, not static mockups. The package includes a source map and publication-ready drafts. A WordPress draft can be prepared through the connector; this demo uses a local simulator and sends nothing to a real audience. Five fresh batches were also triggered through the running n8n workflow and persisted for review. Live transcription, real WordPress dispatch, and restart/retry recovery still need customer-authorized verification.”

## 3–5 minute technical walkthrough

1. **Source and provenance (about 45 seconds).** Show the three synthetic owned MP4s and nine transcript-only fixtures. Explain the rights attestation and type/size checks. Open one segment with its measured media boundary. Note that subtitle timing inside a segment is interpolated and still needs editorial review.
2. **Data model and graph (about 60 seconds).** Show `SourceAsset → TranscriptVersion → Segment`, then `ContentBatch → Claim → ContentAssetVersion`. Walk through analyze → claim ledger → asset plan → bounded generation → evidence/brand checks → one revision. n8n owns the business workflow; the AI graph never performs WordPress writes.
3. **Human review and versioning (about 60 seconds).** Edit one asset, compare old/new versions, approve using the returned hash, then correct a source segment. Show that only dependent claims/assets become stale. Explain why a stale hash causes HTTP 409 and why a quote/number warning blocks approval.
4. **Media and package (about 60 seconds).** Render all seven carousel slides and three 9:16 MP4 excerpts. Point to actual PNG/PDF/MP4 files, subtitle SRT, authenticated media routes, job status/SSE, and the package source map. The renderer preserves full source frames instead of cropping away slide context.
5. **Recovery and limits (about 45 seconds).** Show the n8n workflow exports, import manifest, local simulator, dispatch ledger, error/reconciliation workflows, [intake evidence](../workflows/evidence/replay-20260928T083343b793bd.json), and [429 dispatch evidence](../workflows/evidence/dispatch-429-duplicate-20260928.json). Explain the five successful review bundles, duplicate/error cases, and one bounded retry. Distinguish these historical local synthetic runs from pending live provider calls, audible clip review, restart/additional retry checks, and full restore drill.

## Three content angles

- **Product:** “One source, many drafts, every claim traceable back to the moment it came from.” Demonstrate source highlighting and single-asset revision.
- **Engineering:** “Why content approval is a versioned side effect.” Explain hashes, scoped records, dispatch keys, and ambiguous provider outcomes.
- **Editorial practice:** “A short clip can be accurate word-for-word and still misleading.” Show full-segment boundaries, preserved negation, and human context review.

## Verified screenshot paths

Eight real browser captures are committed under `docs/screenshots/`. The 1440-pixel set covers [login](screenshots/01-login-1440.png), [Studio](screenshots/02-studio-1440.png), [carousel](screenshots/03-carousel-1440.png), and [clip](screenshots/04-clip-1440.png). The 1024-pixel set covers [review](screenshots/05-review-1024.png) and [board](screenshots/06-board-1024.png). The 390-pixel set covers [calendar](screenshots/07-calendar-390.png) and [library](screenshots/08-library-390.png). `docs/screenshots/manifest.json` records actual dimensions and scroll widths. Media visual QA sheets exist separately at `output/render-qa/carousel-contact-sheet.png` and `output/render-qa/clips-contact-sheet.png`; these ignored local artifacts are renderer evidence, not browser screenshots.

## Resume bullet templates using measured results

- Built an independent ContentStudio pilot combining n8n, FastAPI/LangGraph, PostgreSQL, and React to review 11 source-linked editorial assets per batch; generated 12 fictional transcripts, three playable synthetic presentations, and four brand versions for local demonstration.
- Implemented version-bound review and scoped media rendering; a local API smoke rendered a seven-slide carousel, three subtitled MP4 clips, and a 17-file ZIP in 24.31 seconds on one Windows test host.
- Imported and activated seven workflows in n8n 2.40.7; verified five triggered 11-asset review bundles plus duplicate and error-handler behavior against a local simulator.
- Verified one n8n 429 wait/retry and duplicate due trigger against a local WordPress-like simulator, with one resulting draft.
- Created 80 planted validation scenarios with entity-disjoint development/held-out sources; the deterministic checker found expected warnings in 70/70 executable cases, while ten persisted dispatch scenarios and live-model quality remain separately gated.

Do not replace these with unmeasured claims about customers, accuracy, revenue, latency in another environment, connected providers, or complete recovery.

# ContentStudio

ContentStudio is a self-hosted editorial pilot for a consultant or B2B team. It turns an owned presentation, recording, or transcript into a source-linked review bundle: one article, one newsletter draft, five social drafts, a seven-slide carousel, and three 20–60 second clip proposals. Operators can inspect source passages, correct a transcript, edit or regenerate one asset, approve it against its exact version, render approved media, and collect a package and calendar drafts.

The local demo uses a **Synthetic demo dataset**. The first three sources are playable code-generated slide presentations with local synthetic narration; the other nine are transcript-only fixtures. The four brands, users, scenarios, and any numbers in them are fictional. Fixture generation is deterministic and clearly different from connected model/transcription quality. Nothing in demo mode publishes to real recipients.

## Roles and workflow

| Role | Intended access |
| --- | --- |
| Admin | Configure and review workspace content; manage the demo installation. |
| Operator | Correct sources and edit, approve, reject, regenerate, render, package, and schedule drafts. |
| Viewer | Read workspace-scoped sources, batches, assets, and calendar. |

1. Record owned source rights and upload media or import a transcript fixture. The API validates upload size/type and stores media outside n8n execution data.
2. n8n receives an intake event, validates/deduplicates it through the API, and coordinates transcription and AI generation. The AI service is limited to transcript analysis, claim ledger, asset planning, bounded generation, and evidence checks.
3. A reviewer sees source-backed claims and asset warnings. The reviewer can edit, reject, or regenerate an individual version. Transcript corrections invalidate only dependent assets; old versions remain as history.
4. An approved version is bound to its content hash. The API can render a branded carousel PNG/PDF and MP4 clip excerpts with burned subtitles and title card. All publishable assets remain subject to editorial review of meaning and context.
5. The API assembles a ZIP with source map, approved material, and rendered files. n8n dispatches publication-ready WordPress drafts through a credentialed connector; social platform posting is outside v1.

## Draft length and format policy

The validator requires nonempty titles and bodies for article, newsletter, and social drafts. An article targets 700–1,000 body words; a newsletter targets 250–450. When the full transcript is shorter than a channel's minimum, the floor is reduced to the number of words in the draft's cited source spans, so a small source is not pushed to invent material. Substantial transcripts keep the normal channel minimum. Article and newsletter bodies need at least two paragraphs when the source has multiple segments. Each social draft is one text asset capped at 500 characters and 100 words. A violation is a review warning and blocks approval; an editor can revise the individual asset. These checks do not establish factual or editorial quality.

## Modes and gates

**DEMO** uses fictional fixtures, a deterministic AI adapter, locally synthesized presentations, and a local WordPress-like connector simulator. The same authenticated API and persistence paths are exercised. The portal labels simulated responses.

**CONNECTED** uses configured OpenAI model and transcription adapters and a customer-owned WordPress application password. Model IDs, keys, and connector credentials are configuration. There is no automatic fallback from a failed connected request to fixture success. Connected model/transcription and real WordPress smoke tests remain pending until authorized credentials and a spending limit are available.

## Release targets and current evidence

The product requirements defines release targets. Deterministic fixture checks, API tests, media render checks, and browser journeys are recorded in `docs/EVALUATION.md` and `docs/HANDOVER.md`. During an earlier healthy Compose run, the local demo completed an actual n8n 2.40.7 import and five triggered fixture scenarios, with [intake evidence](../workflows/evidence/replay-20260928T083343b793bd.json), an idempotent duplicate, and Error Trigger runs for conflict/malformed intake. A [dispatch replay](../workflows/evidence/dispatch-429-duplicate-20260928.json) verified one simulated 429 retry with no duplicate draft. Docker later degraded with virtual-disk I/O errors and API 500. n8n-triggered render/package, restart and additional retry/concurrency, complete media/n8n-key restoration, audible clip review, and connected provider calls remain release gates. The pilot is not production-ready.

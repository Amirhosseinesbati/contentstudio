# Commercialization notes

## Buyer and offer

The initial buyer is a small B2B consulting or education team that owns webinars/podcasts, needs consistent branded drafts, and has a human editor. Sell customer-specific installation, workflow configuration, training, and ongoing support. The deliverable is a controlled editorial operation and source trail, not a guarantee of engagement, leads, or revenue. Start with one customer per installation and a limited number of authorized WordPress drafts. Public social posting is optional future work.

## Customer onboarding

1. Confirm the customer owns or may process each source, including speaker consent, retention, and permitted model-provider use.
2. Deploy PostgreSQL, n8n, API, portal, media storage, TLS, backups, and a secret manager under the customer's control. Replace seeded demo users and all example secrets.
3. Configure brand tone, prohibited claims, length limits, review roles, media/storage limits, and the content calendar.
4. Create an n8n owner, API key, scoped service credential, and a customer-owned WordPress application password. Import inactive workflows, map credentials, then activate only authorized triggers.
5. Run a short owned source through transcript correction, claim review, all asset types, carousel/clip render, package, and draft creation. Review real examples with the editor before any connected routine use.
6. Record actual model/transcription usage, storage growth, workflow errors, and a restore drill. Define support ownership for uncertain external writes and credential rotation.

## Reusable modules and integrations

Reusable modules are the transcription adapter boundary, source/segment provenance, claim-ledger validation, content version/review ledger, scoped media renderer, package assembler, n8n import pack, and local connector simulator. v1 supports owned upload/transcript fixture intake, an OpenAI model/transcription adapter, local simulator, and WordPress **draft** creation. Arbitrary URL downloading and direct social publication are not included. Connected integration contracts are implemented but not live-tested without credentials.

## Configurable cost estimate

The product records real token usage/cost indicators when a connected provider returns them; pricing depends on provider agreement and deployment. Use customer-specific inputs rather than a fixed price claim:

| Input | Symbol | Monthly estimate |
| --- | --- | --- |
| Source minutes processed | `M` | Enter expected approved/attempted minutes. |
| Transcription price per minute | `T` | `M × T`, including failed/retried calls where billed. |
| Model input/output tokens | `I`, `O` | `(I/1,000,000 × input_rate) + (O/1,000,000 × output_rate)`. |
| Stored GB-months | `S` | `S × storage_rate`, plus backup copies and egress. |
| Compute and operations | `C` | VM/container, PostgreSQL, backup, support, and render CPU. |

Estimated monthly external/infra cost is `M×T + I/1e6×input_rate + O/1e6×output_rate + S×storage_rate + C`. Divide the measured total by approved assets only after recording the actual denominator; a fixture run has zero paid API cost but still consumes CPU/storage. Current pilot lacks measured connected provider cost, so do not populate a customer quote from fixture numbers.

## Licensing and delivery boundary

The [n8n licensing FAQ](https://support.n8n.io/article/can-i-use-your-license-for-my-use-case) says consulting on a client's own internal instance generally does not require a separate commercial license for the consultant, while hosting clients' workflows and credentials on the consultant's own instance requires Enterprise, and embedding n8n for client-facing workflow management requires Embed. The customer's use case still determines its entitlement; confirm it with n8n before each commercial deployment. This project is a customer-specific automation pilot, not a licensed hosted n8n service.

Original scripts, slides, and fictional narratives in this repository were created for this project. The generated videos use local synthetic voices and code-generated slides; no stock footage or external logo is bundled. The renderer uses installed DejaVu fonts and FFmpeg from the deployment image. Before redistributing a packaged image, verify the exact versions' licenses, attribution/source obligations, and customer rights for any newly supplied fonts, media, plugins, and templates. No unverified rights are claimed for third-party dependencies.

## v1 limits

No public self-service SaaS, payments, queue-mode cluster, autonomous publishing, social posting, arbitrary URL ingestion, verified speaker diarization, or engagement prediction. Local synthetic n8n intake and one 429 dispatch retry passed; connected credentials and provider reconciliation, n8n restart/additional retry/concurrency checks, full backup/restore, and customer security review remain required before a production sale claim.

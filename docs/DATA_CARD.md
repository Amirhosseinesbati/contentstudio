# Synthetic demo dataset

The entire dataset is fictional. Morrow Research and Alder Field Notes are invented brands; the scenarios, speakers, customers, and any outcome language are authored examples. No real customer data, consent, revenue, engagement, or model accuracy is implied.

## Reproduction and scope

Run `scripts/generate_demo_data.py --seed 4209 --reference-date 2026-09-01` to rebuild the text fixtures. The full generator is deterministic and makes no model or network calls. It creates 12 authored transcript fixtures, 4 brand versions, 120 content-asset versions, and 80 validation cases. The first three transcript fixtures can then be converted to synthetic owned media with `scripts/generate_demo_media.ps1`; this uses local Windows SAPI narration and FFmpeg. On a repeat seed, the generator preserves measured boundaries and media metadata when the script text still matches; it stops with an error if the text changed and the video must be regenerated. `fixtures/manifest.json` records text hashes, measured duration for the three media sources, and estimated script duration for the remaining transcript-only sources; each video has its own measured `provenance.json`.

| Entity | Count | Distribution |
| --- | ---: | --- |
| Source transcripts | 12 | Six per workspace; 2,727–2,797 words each. Twelve fictional business and technical topics. |
| Playable media presentations | 3 | First three sources, about 9.2–10.0 minutes each, 1280×720 MP4 with audio and eight authored slides. |
| Brand profile versions | 4 | Two versions each for `studio-alpha` and `studio-beta`. |
| Content-asset versions | 120 | 24 per article/newsletter/social/carousel/clip type; 20 per draft/review/approved/rendered/rejected/needs-revision state. |
| Validation cases | 80 | 20 development, 60 held out; ten each of eight defect families. |

The transcript scenarios cover onboarding, privacy, building energy, supplier resilience, accessibility, analytics quality, remote facilitation, security incidents, circular purchasing, industrial maintenance, internal knowledge, and fictional service operations. Each contains a correction or qualification for context-loss tests. The first three videos use synthetic narration of the authored text; the other nine remain transcript-only fixtures and must be labeled that way in the UI.

## Ground truth and split

Structured topic notes in `scripts/generate_demo_data.py` are the source scenario. The text generator never calls the model under evaluation. Validation expected outcomes live only in `evals/datasets/validation_cases.json`, outside the runtime fixture directory and model prompts. Development cases use the first four source entities; held-out cases use the other eight. `template_group` includes the split to prevent a template identifier from crossing the boundary. This is synthetic entity separation, not proof of generalization to real customers.

The defect families are altered number, unsupported statistic, quote drift, missing attribution, negation removed by clipping, corrected transcript, render failure, and duplicate publishing. The labels are `block` or `review` according to the planted scenario. The current case text is deliberately compact; human-reviewed samples are required before any model-quality claim.

## Provenance and limitations

Transcript fixture timestamps are estimated at 178 words per minute and are **not** measured audio alignment. For the first three generated videos, segment start and end times are measured from each synthesized WAV before concatenation. Subtitle timing inside a segment is interpolated from word count and requires editorial inspection. Narration is a fast local synthetic voice, not a recording of a real presenter. The videos contain no licensed external footage, fonts, music, or logos; the renderer uses locally installed DejaVu fonts. Media generation is Windows-specific; the resulting MP4 files play on other systems.

These data deliberately include caveats, revisions, and fictional numeric examples, but the templated speaking structure is more regular than natural webinars. Evaluation on these cases cannot establish customer accuracy, speaker diarization quality, or real engagement outcomes. Retain the source hashes and split when comparing model versions.

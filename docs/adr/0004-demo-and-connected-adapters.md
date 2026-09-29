# ADR 0004: explicit demo and connected adapters

Status: accepted for v1, 2026-09-28.

Demo uses authored transcript/media fixtures, deterministic generation, and local connector simulators. Connected mode requires configured model, transcription, and WordPress credentials and surfaces failures. This allows a safe local walkthrough without paid calls or real recipients. The tradeoff is that fixture pass rates do not establish live model or transcription quality; those remain separate release gates.

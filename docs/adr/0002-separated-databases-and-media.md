# ADR 0002: separate n8n and business databases, scoped media volume

Status: accepted for v1, 2026-09-28.

One PostgreSQL server hosts separate `contentstudio` and `n8n` databases. Business tables remain outside n8n's migration lifecycle. Large source and render binaries live on a media volume and are referenced by scoped paths. This keeps workflow execution JSON small and makes backup boundaries explicit. It does require coordinated database, media, and encryption-key backup and restore.

# ADR 0003: approvals bind to exact asset content

Status: accepted for v1, 2026-09-28.

Each edit/regeneration creates a new content version and hash. Review decisions are single-use records for that exact version. A transcript correction rechecks source dependencies and invalidates affected approvals while preserving unrelated reviewed assets and manual edits. This is more bookkeeping than overwriting a draft, but it prevents a stale approval from silently authorizing changed words or a changed clip range.

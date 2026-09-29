# ADR 0001: n8n owns business coordination

Status: accepted for v1, 2026-09-28.

The brief requires an importable n8n product. n8n therefore owns intake triggers, schedules, business branching, connector calls, and reconciliation routes. FastAPI owns versioned records, authorization, rendering, and a bounded AI graph. This avoids two orchestrators issuing the same external write. The tradeoff is that full runtime acceptance requires an actual n8n instance; API-only demo behavior cannot stand in for triggered workflow evidence.

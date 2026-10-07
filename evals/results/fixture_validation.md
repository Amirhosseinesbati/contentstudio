# Fixture validation

Run UTC: 2026-10-06T17:10:47.208008+00:00

These are synthetic planted cases. The measure is whether the expected deterministic warning appeared; it does not measure model quality or semantic truth.

Results: 70 passed / 70 executed; 10 integration-only cases not run.

| Defect | Passed | Failed | Not run |
| --- | ---: | ---: | ---: |
| altered_number | 10 | 0 | 0 |
| corrected_transcript | 10 | 0 | 0 |
| duplicate_publishing | 0 | 0 | 10 |
| missing_attribution | 10 | 0 | 0 |
| negation_removed_by_clipping | 10 | 0 | 0 |
| quote_drift | 10 | 0 | 0 |
| render_failure | 10 | 0 | 0 |
| unsupported_statistic | 10 | 0 | 0 |

## Limits

Duplicate publishing requires the API/n8n persistence integration and is not counted as a pass here. Numeric and quote string checks do not establish contextual correctness. A human must review selected source spans and generated media before publication.

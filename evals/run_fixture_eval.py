"""Evaluate planted deterministic validation cases; no model calls or credentials."""

from __future__ import annotations

import json
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
from contentstudio.domain import validate_asset  # noqa: E402


def main() -> None:
    cases = json.loads((ROOT / "evals" / "datasets" / "validation_cases.json").read_text(encoding="utf-8"))
    sources = {source["source_key"]: source for path in (ROOT / "fixtures" / "sources").glob("*.json")
               for source in [json.loads(path.read_text(encoding="utf-8"))]}
    rows = []
    for case in cases:
        if case["expected_warning"] == "integration_only":
            rows.append({"case_id": case["case_id"], "defect_type": case["defect_type"],
                         "split": case["split"], "status": "not_run", "reason": "Requires persisted dispatch integration"})
            continue
        source = sources[case["source_key"]]
        segments = [{**segment, "id": f"{source['source_key']}:{index}"}
                    for index, segment in enumerate(source["segments"])]
        warnings = validate_asset(case["candidate"], segments)
        passed = any(case["expected_warning"] in warning for warning in warnings)
        rows.append({"case_id": case["case_id"], "defect_type": case["defect_type"],
                     "split": case["split"], "status": "pass" if passed else "fail",
                     "expected_warning": case["expected_warning"], "actual_warnings": warnings})
    totals = Counter(row["status"] for row in rows)
    groups = {kind: dict(Counter(row["status"] for row in rows if row["defect_type"] == kind))
              for kind in sorted({row["defect_type"] for row in rows})}
    result = {"run_at_utc": datetime.now(timezone.utc).isoformat(),
              "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
              "dataset": "Synthetic demo dataset; entity-disjoint development/held-out split",
              "total_cases": len(rows), "totals": dict(totals), "by_defect": groups, "cases": rows,
              "interpretation": "A deterministic warning match, not a model accuracy or factual correctness score."}
    output = ROOT / "evals" / "results"
    output.mkdir(parents=True, exist_ok=True)
    (output / "fixture_validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines = ["# Fixture validation", "", f"Run UTC: {result['run_at_utc']}", "",
             "These are synthetic planted cases. The measure is whether the expected deterministic warning appeared; it does not measure model quality or semantic truth.",
             "", f"Results: {totals['pass']} passed / {totals['pass'] + totals['fail']} executed; {totals['not_run']} integration-only cases not run.",
             "", "| Defect | Passed | Failed | Not run |", "| --- | ---: | ---: | ---: |"]
    for kind, counts in groups.items():
        lines.append(f"| {kind} | {counts.get('pass', 0)} | {counts.get('fail', 0)} | {counts.get('not_run', 0)} |")
    failures = [row for row in rows if row["status"] == "fail"]
    if failures:
        lines.extend(["", "## Unmet cases", ""])
        lines.extend(f"- {row['case_id']} ({row['defect_type']}): expected `{row['expected_warning']}`; got {row['actual_warnings']}" for row in failures)
    lines.extend(["", "## Limits", "",
                  "Duplicate publishing requires the API/n8n persistence integration and is not counted as a pass here. Numeric and quote string checks do not establish contextual correctness. A human must review selected source spans and generated media before publication.", ""])
    (output / "fixture_validation.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"total": len(rows), **dict(totals), "failures": [row["case_id"] for row in failures]}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

---
name: tier2-integration-review
description: Tier 2 integration review phase agent. Verifies the cross-domain migrated target after rewiring and records final routing.
---

# Tier 2 Integration Review Agent

## Deterministic First

The orchestrator prebuilds:
- `{output_dir}/parity-results.json`
- `{output_dir}/integration-review.json`
- `{output_dir}/INTEGRATION_REVIEW.md`

Those files are the review baseline. Refine them in place.

## Inputs

Read from context:
- `output_dir`
- `domain_execution_output`
- `rewiring_output`
- `domain_execution_overview_path`
- `rewiring_summary_path`
- `parity_results_path`
- `diff_scorer_script`
- `source_path`
- `target_path`
- `testCommand`
- `buildCommand`
- `lintCommand`
- `review_checks`

## Task

1. Review deterministic checks first.
2. Add broader safe review evidence if you can run it.
3. Keep the routing truthful:
   - `pass`
   - `fail`
   - `human`

## Required JSON Contract

```json
{
  "checks": [
    {
      "name": "string",
      "status": "pass|fail|human-review",
      "details": {}
    }
  ],
  "routing": {
    "pass": ["string"],
    "fail": ["string"],
    "human": ["string"]
  },
  "summary": {
    "status": "pass|fail|human-review",
    "totalChecks": 0,
    "passed": 0,
    "failed": 0,
    "humanReview": 0
  }
}
```

## Output Rules

- Do not overwrite `parity-results.json` except to repair corruption.
- Keep `integration-review.json` machine-readable.
- Keep `INTEGRATION_REVIEW.md` concise and decision-oriented.
- If blocked, write `{output_dir}/ERROR`.

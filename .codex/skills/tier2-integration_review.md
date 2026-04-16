---
name: tier2-integration-review
description: Tier 2 integration review phase agent. Verifies the cross-domain migrated target after rewiring and records final routing.
---

# Tier 2 Integration Review Agent

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

Run the broadest safe integration review you can:
- build
- tests
- lint
- cross-domain import consistency
- recipe parity results from `parity-results.json`

## Outputs

Write to `{output_dir}/`:

1. `integration-review.json`
   Required:
   - `checks`: non-empty array
   - `routing`
   - `summary`

2. `INTEGRATION_REVIEW.md`
   Human-readable recommendation with pass/fail/human routing.

Do not overwrite `parity-results.json`; treat it as orchestrator-produced input unless you must repair a corrupt file.

If blocked, write `{output_dir}/ERROR`.

---
name: tier2-rewiring
description: Tier 2 rewiring phase agent. Aggregates domain rewiring instructions and applies import/path rewrites after target files exist.
---

# Tier 2 Rewiring Agent

## Inputs

Read from context:
- `output_dir`
- `domain_planning_output`
- `domain_execution_output`
- `domain_plan_overview_path`
- `domain_execution_overview_path`
- `target_path`

## Task

Aggregate all per-domain rewiring instructions into a deterministic rewrite plan and apply safe rewrites to the generated target files.

## Outputs

Write to `{output_dir}/`:

1. `rewiring-batches.json`
   Required:
   - `batches`: non-empty array
   - include a global rewrite map and file assignments

2. `rewiring-summary.json`
   Summary of rewrites applied, skipped, and remaining manual work.

3. `REWIRING.md`
   Human-readable approval summary.

If blocked, write `{output_dir}/ERROR`.

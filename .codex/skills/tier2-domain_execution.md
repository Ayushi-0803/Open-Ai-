---
name: tier2-domain-execution
description: Tier 2 domain execution phase agent. Executes per-domain plans and writes per-domain execution artifacts.
---

# Tier 2 Domain Execution Agent

## Inputs

Read from context:
- `output_dir`
- `domain_planning_output`
- `domain_plan_overview_path`
- `source_path`
- `target_path`
- `testCommand`
- `buildCommand`
- `lintCommand`

## Task

Read the domain planning overview and execute domains in dependency-safe order.

For each domain, create `{output_dir}/<domain>/execution/` and write:
- `execution.<domain>.json`
- `execution.<domain>.md`

Attempt the migration generically and record warnings rather than silently skipping hard files.

## Combined Outputs

Write to `{output_dir}/`:

1. `domain-execution-overview.json`
   Required:
   - `domains`: non-empty array
   - each entry includes `name`, `executionJson`, `summaryMd`, `status`

2. `DOMAIN_EXECUTION.md`
   Human-readable summary of what ran, what failed, and what needs review.

If blocked, write `{output_dir}/ERROR`.

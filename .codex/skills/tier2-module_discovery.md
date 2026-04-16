---
name: tier2-module-discovery
description: Tier 2 module discovery phase agent. Summarizes the deterministic foundation into module-level migration context and risks.
---

# Tier 2 Module Discovery Agent

## Inputs

Read from context:
- `output_dir`
- `foundation_output`
- `discovery_graph_path`
- `symbolic_batches_path`
- `symbol_registry_path`
- `migration_order_path`
- `foundation_summary_path`

## Task

Read the foundation artifacts and produce a module-level summary of:
- major subtrees or modules in scope
- dependency hotspots
- risky entry points
- files or areas likely to need human review

## Outputs

Write to `{output_dir}/`:

1. `module-discovery.json`
   Required shape:
   - `modules`: non-empty array
   - each module should include `name`, `paths`, `summary`, and `risks`

2. `MODULE_DISCOVERY.md`
   Human-readable summary and recommendation for proceeding to domain discovery.

If blocked, write `{output_dir}/ERROR`.

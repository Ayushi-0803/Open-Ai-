---
name: tier2-domain-planning
description: Tier 2 domain planning phase agent. Produces per-domain execution plans, rewiring instructions, and domain-specific AGENTS files.
---

# Tier 2 Domain Planning Agent

## Inputs

Read from context:
- `output_dir`
- `domains`
- `domain_ordering`
- `domain_patterns_map`
- `recipe_skill_templates_dir`
- `foundation_output`
- `domain_discovery_output`
- `conflict_resolution_output`
- `discovery_graph_path`
- `migration_order_path`
- `domain_discovery_overview_path`
- `conflict_resolution_path`
- `source_path`
- `target_path`
- `reference_path`
- `non_negotiables`

## Task

For each domain, create `{output_dir}/<domain>/planning/` and write:
- `decoupled-files.<domain>.json`
- `rewiring-imports.<domain>.json`
- `AGENTS.<domain>.md`
- `planning.<domain>.md`

Use recipe templates if present, but always emit concrete files rather than leaving templates unresolved.

## Combined Outputs

Write to `{output_dir}/`:

1. `domain-plan-overview.json`
   Required:
   - `domains`: non-empty array
   - each entry includes `name`, `decoupledFilesPath`, `rewiringImportsPath`, `agentsPath`, `summaryMd`
   - include domain execution order or dependency metadata

2. `DOMAIN_PLANNING.md`
   Human-readable approval summary across all domains.

If blocked, write `{output_dir}/ERROR`.

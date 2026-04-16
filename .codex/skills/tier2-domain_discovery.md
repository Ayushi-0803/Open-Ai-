---
name: tier2-domain-discovery
description: Tier 2 domain discovery phase agent. Classifies symbols into domains and writes per-domain discovery artifacts plus a combined overview.
---

# Tier 2 Domain Discovery Agent

## Inputs

Read from context:
- `output_dir`
- `domains`
- `domain_ordering`
- `domain_patterns_map`
- `recipe_skill_templates_dir`
- `foundation_output`
- `module_discovery_output`
- `discovery_graph_path`
- `symbolic_batches_path`
- `symbol_registry_path`
- `migration_order_path`
- `module_discovery_path`

## Task

Classify the codebase into the configured domains.

Use all available evidence:
- deterministic foundation artifacts
- module discovery summary
- recipe pattern files when present
- actual source files when needed

For each domain, create `{output_dir}/<domain>/discovery/` and write:
- `discovery.<domain>.json`
- `discovery.<domain>.md`

The JSON should include discovered symbols/files, rationale, shared/internal classification where possible, and notable risks.

Then write the combined artifacts in `{output_dir}/`:

1. `domain-discovery-overview.json`
   Required:
   - `domains`: non-empty array
   - each entry includes `name`, `symbolCount`, `discoveryJson`, `summaryMd`

2. `DOMAIN_DISCOVERY.md`
   Summarize coverage, gaps, and domain boundaries.

Update `symbol-registry.json` if you can do so cleanly; otherwise record unresolved ownership questions in the overview.

If blocked, write `{output_dir}/ERROR`.

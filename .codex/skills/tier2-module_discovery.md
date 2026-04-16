---
name: tier2-module-discovery
description: Tier 2 module discovery phase agent. Summarizes the deterministic foundation into module-level migration context and risks.
---

# Tier 2 Module Discovery Agent

## Deterministic First

The orchestrator prebuilds:
- `{output_dir}/module-discovery.json`
- `{output_dir}/MODULE_DISCOVERY.md`

Treat those files as the authoritative schema baseline. Do not replace them with a new format.

## Inputs

Read from context:
- `output_dir`
- `foundation_output`
- `discovery_graph_path`
- `symbolic_batches_path`
- `symbol_registry_path`
- `migration_order_path`
- `foundation_summary_path`

Read these files before editing anything:
- `{output_dir}/module-discovery.json`
- `{output_dir}/MODULE_DISCOVERY.md`

## Task

1. Verify that the prebuilt module grouping is plausible against the foundation artifacts.
2. Refine summaries and risks where the deterministic builder was too shallow.
3. Preserve machine-readable keys exactly.
4. If you change facts in markdown, keep them consistent with `module-discovery.json`.

## Required JSON Contract

`module-discovery.json` must remain:

```json
{
  "summary": {
    "totalModules": 0,
    "totalFiles": 0
  },
  "modules": [
    {
      "name": "string",
      "paths": ["string"],
      "summary": {
        "fileCount": 0,
        "highComplexityFiles": 0,
        "internalImportEdges": 0,
        "externalPackages": ["string"]
      },
      "risks": ["string"]
    }
  ]
}
```

## Output Rules

- Keep `module-discovery.json` machine-readable and valid JSON.
- Keep `MODULE_DISCOVERY.md` short and approval-oriented.
- If the deterministic prebuild is fundamentally wrong, repair it in place.
- If blocked, write `{output_dir}/ERROR`.

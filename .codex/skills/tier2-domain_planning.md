---
name: tier2-domain-planning
description: Tier 2 domain planning phase agent. Produces per-domain execution plans, rewiring instructions, and domain-specific AGENTS files.
---

# Tier 2 Domain Planning Agent

## Deterministic First

The orchestrator prebuilds, for every domain:
- `decoupled-files.<domain>.json`
- `rewiring-imports.<domain>.json`
- `AGENTS.<domain>.md`
- `planning.<domain>.md`

It also prebuilds:
- `{output_dir}/domain-plan-overview.json`
- `{output_dir}/DOMAIN_PLANNING.md`

Your job is to refine those artifacts without breaking their schema or path references.

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

## Run Control

When present in context, use:
- `issue_ledger_path`
- `phase_issue_report_path`

Use the ledger as the shared source of truth for cross-domain constraints and repairs. If a domain plan cannot be made truthful with the current inputs, record the gap in `{phase_issue_report_path}` before writing `{output_dir}/ERROR`.

## Required Per-Domain Contracts

`decoupled-files.<domain>.json`:

```json
{
  "domain": "string",
  "executionOrder": 0,
  "dependsOnDomains": ["string"],
  "ownedFiles": ["string"],
  "sharedFiles": [
    {
      "path": "string",
      "domains": ["string"]
    }
  ],
  "targetCandidates": [
    {
      "sourcePath": "string",
      "targetCandidates": ["string"]
    }
  ],
  "summary": {
    "ownedFileCount": 0,
    "sharedFileCount": 0,
    "crossDomainImportCount": 0
  }
}
```

`rewiring-imports.<domain>.json`:

```json
{
  "domain": "string",
  "dependsOnDomains": ["string"],
  "plannedImports": [
    {
      "sourcePath": "string",
      "sourceDomain": "string",
      "dependencyPath": "string",
      "dependencyDomain": "string",
      "rewriteKind": "cross-domain-import",
      "targetFileCandidates": ["string"],
      "targetDependencyCandidates": ["string"],
      "resolvedTargetFile": "string|null",
      "resolvedDependencyTarget": "string|null",
      "safeRewrite": false,
      "notes": ["string"]
    }
  ],
  "summary": {
    "totalRewrites": 0,
    "safeRewriteCandidates": 0
  }
}
```

## Required Overview Contract

`domain-plan-overview.json` must remain:

```json
{
  "summary": {
    "totalDomains": 0,
    "orderedDomains": ["string"]
  },
  "domains": [
    {
      "name": "string",
      "executionOrder": 0,
      "dependsOnDomains": ["string"],
      "decoupledFilesPath": "/abs/path",
      "rewiringImportsPath": "/abs/path",
      "agentsPath": "/abs/path",
      "summaryMd": "/abs/path"
    }
  ]
}
```

## Output Rules

- Preserve absolute paths in the overview.
- Do not leave templates unresolved.
- If a domain has no files, still emit empty but valid per-domain planning artifacts.
- Keep `AGENTS.<domain>.md` concrete, not aspirational.
- If blocked, write `{output_dir}/ERROR`.

---
name: tier2-domain-discovery
description: Tier 2 domain discovery phase agent. Classifies symbols into domains and writes per-domain discovery artifacts plus a combined overview.
---

# Tier 2 Domain Discovery Agent

## Deterministic First

The orchestrator prebuilds:
- `{output_dir}/domain-discovery-overview.json`
- `{output_dir}/DOMAIN_DISCOVERY.md`
- `{output_dir}/<domain>/discovery/discovery.<domain>.json`
- `{output_dir}/<domain>/discovery/discovery.<domain>.md`

Use those files as the baseline. Repair or enrich them in place. Do not invent different filenames.

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

## Run Control

When present in context, use:
- `issue_ledger_path`
- `phase_issue_report_path`

Use the ledger as the shared source of truth for blockers and domain-boundary disputes. If ownership cannot be assigned truthfully, record the evidence in `{phase_issue_report_path}` before writing `{output_dir}/ERROR`.

## Task

1. Check each domain’s prebuilt ownership claims against the deterministic foundation.
2. Tighten borderline ownership cases, rationale, and risk notes.
3. Preserve overview paths and directory layout.
4. Keep discovery JSONs aligned with `domain-discovery-overview.json`.

## Required Per-Domain JSON Contract

Each `discovery.<domain>.json` must remain:

```json
{
  "domain": "string",
  "summary": {
    "ownedFileCount": 0,
    "sharedCandidateCount": 0,
    "ownedSymbolCount": 0,
    "crossDomainDependencyCount": 0
  },
  "ownedFiles": ["string"],
  "ownedSymbols": [
    {
      "symbol": "string",
      "path": "string",
      "complexity": "string"
    }
  ],
  "sharedCandidates": ["string"],
  "crossDomainDependencies": [
    {
      "targetDomain": "string",
      "paths": ["string"]
    }
  ],
  "rationale": [
    {
      "path": "string",
      "reasons": ["string"]
    }
  ],
  "risks": ["string"]
}
```

## Required Overview Contract

`domain-discovery-overview.json` must remain:

```json
{
  "summary": {
    "totalDomains": 0,
    "totalClaimedFiles": 0,
    "sharedFileCount": 0
  },
  "domains": [
    {
      "name": "string",
      "symbolCount": 0,
      "fileCount": 0,
      "sharedCandidateCount": 0,
      "discoveryJson": "/abs/path",
      "summaryMd": "/abs/path"
    }
  ]
}
```

## Output Rules

- Never remove a configured domain from the overview without replacing it with a truthful empty-domain artifact.
- Preserve absolute paths in overview JSON.
- Keep markdown concise and approval-oriented.
- If blocked, write `{output_dir}/ERROR`.

---
name: tier2-rewiring
description: Tier 2 rewiring phase agent. Aggregates domain rewiring instructions and applies import/path rewrites after target files exist.
---

# Tier 2 Rewiring Agent

## Deterministic First

The orchestrator prebuilds:
- `{output_dir}/rewiring-batches.json`
- `{output_dir}/rewiring-summary.json`
- `{output_dir}/REWIRING.md`

Edit those files in place. Keep the same top-level keys.

## Inputs

Read from context:
- `output_dir`
- `domain_planning_output`
- `domain_execution_output`
- `domain_plan_overview_path`
- `domain_execution_overview_path`
- `target_path`

## Run Control

When present in context, use:
- `issue_ledger_path`
- `phase_issue_report_path`

Use the ledger as the run-level source of truth for unsafe or ambiguous rewrites. If rewiring is blocked, record the evidence in `{phase_issue_report_path}` before writing `{output_dir}/ERROR`.

## Task

1. Review the deterministic rewiring aggregation.
2. Apply only safe, clearly justified rewrites.
3. Record skipped or risky rewrites explicitly.

## Required Contracts

`rewiring-batches.json` must contain:

```json
{
  "summary": {
    "totalBatches": 0,
    "safeRewriteCandidates": 0,
    "appliedRewriteCount": 0,
    "manualReviewCount": 0
  },
  "globalRewriteMap": [
    {
      "domain": "string",
      "sourcePath": "string",
      "dependencyPath": "string",
      "dependencyDomain": "string",
      "resolvedTargetFile": "string|null",
      "resolvedDependencyTarget": "string|null",
      "safeRewrite": false
    }
  ],
  "batches": [
    {
      "id": "string",
      "domain": "string",
      "targetFile": "string|null",
      "dependencyTarget": "string|null",
      "status": "ready|manual-review",
      "rewrite": {}
    }
  ]
}
```

`rewiring-summary.json` must contain:

```json
{
  "status": "ready|needs-review",
  "appliedEdits": [
    {
      "targetFile": "string",
      "from": "string",
      "to": "string"
    }
  ],
  "remainingManualWork": [
    {
      "sourcePath": "string",
      "dependencyPath": "string",
      "reason": "string"
    }
  ]
}
```

## Output Rules

- Keep applied edits and manual work mutually understandable.
- Do not mark a rewrite safe unless the target mapping is unambiguous.
- If blocked, write `{output_dir}/ERROR`.

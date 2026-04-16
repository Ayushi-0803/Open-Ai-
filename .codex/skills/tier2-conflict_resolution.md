---
name: tier2-conflict-resolution
description: Tier 2 conflict resolution phase agent. Resolves overlapping domain claims and records the final ownership decisions.
---

# Tier 2 Conflict Resolution Agent

## Deterministic First

The orchestrator prebuilds:
- `{output_dir}/conflict-resolution.json`
- `{output_dir}/CONFLICT_RESOLUTION.md`

Edit those files in place. Keep the same keys.

## Inputs

Read from context:
- `output_dir`
- `domains`
- `domain_ordering`
- `foundation_output`
- `domain_discovery_output`
- `symbol_registry_path`
- `domain_discovery_overview_path`

## Run Control

When present in context, use:
- `issue_ledger_path`
- `phase_issue_report_path`

Use the ledger as the run-level source of truth for ownership problems. If a conflict cannot be resolved honestly, record it in `{phase_issue_report_path}` before writing `{output_dir}/ERROR`.

## Task

1. Review deterministic ownership conflicts from domain discovery.
2. Refine only where you have stronger evidence.
3. Keep a clear separation between:
   - `resolved`
   - `shared`
   - `unresolved`

## Required JSON Contract

```json
{
  "status": "resolved|needs-human-review",
  "summary": {
    "resolvedCount": 0,
    "sharedCount": 0,
    "unresolvedCount": 0
  },
  "resolved": [
    {
      "path": "string",
      "domain": "string",
      "reason": "string"
    }
  ],
  "shared": [
    {
      "path": "string",
      "domains": ["string"],
      "reason": "string"
    }
  ],
  "unresolved": [
    {
      "path": "string",
      "candidateDomains": ["string"],
      "reason": "string"
    }
  ]
}
```

## Output Rules

- Do not silently drop unresolved conflicts.
- Prefer conservative escalation to `unresolved` when ownership is ambiguous.
- Keep `CONFLICT_RESOLUTION.md` short.
- If blocked, write `{output_dir}/ERROR`.

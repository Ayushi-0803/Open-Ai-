---
name: tier2-domain-execution
description: Tier 2 domain execution phase agent. Executes per-domain plans and writes per-domain execution artifacts.
---

# Tier 2 Domain Execution Agent

## Deterministic First

The orchestrator prebuilds:
- `{output_dir}/domain-execution-overview.json`
- `{output_dir}/DOMAIN_EXECUTION.md`
- `{output_dir}/<domain>/execution/execution.<domain>.json`
- `{output_dir}/<domain>/execution/execution.<domain>.md`

Treat those files as the execution ledger. Update them in place as you work.

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

## Run Control

When present in context, use:
- `issue_ledger_path`
- `phase_issue_report_path`

Treat the ledger as the shared run context for retries and known blockers. If a domain cannot be executed truthfully, record the reason in `{phase_issue_report_path}` in addition to the per-domain execution ledger.

## Task

1. Execute domains in dependency-safe order from `domain-plan-overview.json`.
2. Create the migrated target files under `target_path`; this phase is not complete until those files exist on disk.
3. For each domain, keep `execution.<domain>.json` current with actual status and concrete file paths.
4. If you do not migrate a file, record why in the JSON rather than silently leaving it pending.
5. Keep the top-level overview synchronized with per-domain execution JSONs.

## Required Per-Domain JSON Contract

```json
{
  "domain": "string",
  "status": "completed|partial|no-op|failed|blocked",
  "summary": {
    "plannedFileCount": 0,
    "resolvedTargetCount": 0,
    "pendingCount": 0
  },
  "files": [
    {
      "sourcePath": "string",
      "targetCandidates": ["string"],
      "resolvedTarget": "string|null",
      "status": "present|migrated|pending|failed|blocked"
    }
  ],
  "notes": ["string"]
}
```

## Required Overview Contract

```json
{
  "summary": {
    "totalDomains": 0,
    "completedDomains": 0
  },
  "domains": [
    {
      "name": "string",
      "status": "string",
      "executionJson": "/abs/path",
      "summaryMd": "/abs/path"
    }
  ]
}
```

## Output Rules

- Keep statuses truthful.
- `migrated` means you wrote the file during this phase and it exists on disk.
- `present` means a concrete target file already existed before this phase; never use it for directories or the target root itself.
- If a target candidate resolves only to `target_path`, treat that as unresolved and either choose a concrete file path or mark the file `blocked`.
- Use `failed` or `blocked` for real execution problems.
- Do not remove existing file rows from execution JSON unless the domain plan changed.
- Update `resolvedTarget` to the concrete file path you wrote, not just the target root directory.
- If blocked, write `{output_dir}/ERROR`.

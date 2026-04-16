---
name: tier2-conflict-resolution
description: Tier 2 conflict resolution phase agent. Resolves overlapping domain claims and records the final ownership decisions.
---

# Tier 2 Conflict Resolution Agent

## Inputs

Read from context:
- `output_dir`
- `domains`
- `domain_ordering`
- `foundation_output`
- `domain_discovery_output`
- `symbol_registry_path`
- `domain_discovery_overview_path`

## Task

Review all domain discovery outputs and resolve cross-domain conflicts.

Produce a final decision set covering:
- symbols/files that belong to exactly one domain
- intentionally shared items
- unresolved items that must remain human-supervised

## Outputs

Write to `{output_dir}/`:

1. `conflict-resolution.json`
   Required:
   - `status`
   - `resolved`
   - `shared`
   - `unresolved`

2. `CONFLICT_RESOLUTION.md`
   Short human-readable summary of what changed and what remains risky.

If blocked, write `{output_dir}/ERROR`.

---
name: migration
description: Alias of /migrate. Starts the same agentic code migration workflow through the deterministic manifest + orchestrator pipeline.
---

# Migration Alias

This command is the `/migration` alias for `/migrate`.

Use the exact same workflow, constraints, manifest rules, tiering rules, approval behavior, and orchestrator handoff defined in:

- `.codex/commands/migrate.md`

Operational intent:

1. collect migration configuration
2. validate prerequisites
3. write `migration-manifest.json`
4. create artifact directories
5. launch `.codex/scripts/orchestrator.py`
6. monitor approvals in conversation

Critical rule:

Do not invent a second workflow. Behave exactly like `/migrate`, only under the command name `/migration`.

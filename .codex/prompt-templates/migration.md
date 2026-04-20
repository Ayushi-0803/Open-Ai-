---
description: Start the migration framework for this repo or the nested Open-Ai- repo
argument-hint: [SOURCE=<path>] [TARGET=<path>] [RECIPE=<id-or-path>]
---

Start the migration workflow.

Resolution rule:

1. If `./.codex/commands/migrate.md` exists and `./.codex/scripts/orchestrator.py` exists, use this repo as the framework root.
2. Otherwise, if `./Open-Ai-/.codex/commands/migrate.md` exists and `./Open-Ai-/.codex/scripts/orchestrator.py` exists, use `Open-Ai-/` as the framework root.
3. Follow the migration setup flow defined by that framework's `migrate.md`.

Behavior:

- collect source description
- collect target description
- collect source path
- collect target path
- collect recipe
- determine tier
- validate prerequisites
- write `migration-manifest.json`
- create artifact directories
- launch the framework orchestrator
- monitor approval gates in conversation

If arguments are provided, treat them as strong hints:

- `SOURCE=$SOURCE`
- `TARGET=$TARGET`
- `RECIPE=$RECIPE`

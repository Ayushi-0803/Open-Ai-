---
name: migrate
description: Start an agentic code migration. Collect configuration, write the manifest, and launch the deterministic orchestrator.
---

# Migrate

This Claude command mirrors the repo's Codex migration entry point.

Use the exact same workflow, constraints, tiering rules, manifest rules, approval behavior, and orchestrator handoff defined in:

- `.codex/commands/migrate.md`

Operational intent:

1. collect migration configuration
2. validate prerequisites
3. write `migration-manifest.json`
4. create artifact directories
5. launch `.codex/scripts/orchestrator.py`
6. monitor approvals in conversation

Critical rule:

Do not invent a second workflow. Behave like the primary migration entry point defined in `.codex/commands/migrate.md`.

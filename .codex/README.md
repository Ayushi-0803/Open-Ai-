# Codex Usage

## Migration Workflow

In this repo, the migration framework should be invoked through the `migrate` skill.

Use prompts like:
- `use the migrate skill to start a migration`
- `start a migration using recipe example-generic`
- `resume the current migration run`
- `inspect migration artifacts for the last run`

Do not rely on `/migrate` being available as a slash command in Codex CLI. The current local Codex runtime may not auto-register repo-local commands.

Canonical migration entry points:
- skill: `.codex/skills/migrate/SKILL.md`
- workflow contract: `.codex/commands/migrate.md`
- runtime: `.codex/scripts/orchestrator.py`

Post-migration testing helper:
- skill: `.codex/skills/test-migrations/SKILL.md` to run target project tests using manifest-provided commands and capture artifacts under `artifacts/test-runs/`.

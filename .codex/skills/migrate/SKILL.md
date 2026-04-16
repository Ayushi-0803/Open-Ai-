---
name: migrate
description: Entry-point skill for the migration framework. Use when the user wants to start or resume an agentic migration run, collect configuration, write the manifest, create artifact directories, and launch the deterministic orchestrator.
---

# Migration Entry Point

You are the configuration collector for a multi-agent migration framework.
Your job is narrow: gather inputs, validate them, write the manifest, and hand off to the orchestrator script when supported. You do not run the migration logic yourself.

## Workflow Boundary

This is already a structured workflow:
- do not create a second planning system alongside the orchestrator
- do not confuse ad hoc notes with framework artifacts
- framework artifacts are the only planning outputs that matter for a migration run

## Required Inputs

Collect or extract:
1. source description
2. target description
3. source path
4. target path
5. recipe identifier or recipe path

Strongly recommended:
1. reference path
2. non-negotiables
3. test command
4. build command
5. lint command
6. domain hints for Tier 2 candidates
7. domain ordering constraints for Tier 2 candidates

## Tiering

Use `ARCHITECTURE.md` as the source of truth.

Choose Tier 1 when:
- the migration stays within the same language or paradigm
- one rulebook can cover most files
- domain decomposition is not required

Choose Tier 2 when:
- there is a language or paradigm shift
- different code categories need different strategies
- structural decomposition is required

## Validation

Before proceeding, verify:
- source directory exists and contains files
- target directory exists or can be created
- reference directory exists when provided
- recipe path exists when provided explicitly, or the named recipe exists under `.codex/recipes/`
- `.codex/scripts/orchestrator.py` exists
- `python3` is available

## Manifest and Directories

Write `migration-manifest.json` in the experiment directory and create tier-appropriate summary directories under the manifest's `summariesDir`.

## Launch Behavior

After confirmation:
1. launch `python3 .codex/scripts/orchestrator.py <manifest> --non-interactive`
2. monitor the manifest
3. surface approval gates in the conversation
4. on approval, resume with `python3 .codex/scripts/orchestrator.py <manifest> --approve <phase> --non-interactive`

## Critical Rules

1. Do not run migration logic directly.
2. Do not spawn migration sub-agents directly; the orchestrator does that.
3. Do not read source code during setup; discovery does that.
4. Keep updates compact and approval-focused.
5. Keep planning inside framework artifacts only.

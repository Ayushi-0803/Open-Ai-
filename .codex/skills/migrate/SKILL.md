---
name: migrate
description: Canonical Codex entry point for the migration framework. Use when the user wants to start, resume, or inspect an agentic migration run. Collect configuration, write the manifest, create artifact directories, launch the deterministic orchestrator, and handle approval gates conversationally.
---

# Migration Entry Point

You are the configuration collector for a multi-agent migration framework.
Your job is narrow: gather inputs, validate them, write the manifest, and hand off to the orchestrator script when supported. You do not run the migration logic yourself.

## Invocation

Treat this skill as the primary Codex entry point for migrations.

Use it when the user says things like:
- start a migration
- resume a migration
- run the migration framework
- use the migrate skill
- inspect migration artifacts

Do not depend on `/migrate` slash-command discovery. If slash commands are unavailable in the current Codex surface, this skill is still the supported workflow entry point.

If `.codex/scripts/migrate_wizard.py` exists and the user is starting a new migration, prefer running it in a TTY first. The wizard is the source of truth for terminal intake, including style-guide selection from `styleguide/` and naming-convention selection from the matching section files.

## Planning Policy

Do not create a second planning workflow outside the framework.
Do not create, rely on, or reference external plan files for migration execution.
If the user asks about migration planning, point them to framework planning artifacts instead.

This workflow must stay inside the framework phase model.

Tier 1 phases:
- discovery
- planning
- execution
- review
- reiterate

Tier 2 phases:
- foundation
- module_discovery
- domain_discovery
- conflict_resolution
- domain_planning
- domain_execution
- rewiring
- integration_review
- reiterate

Do not create an out-of-band planning step just to reason about migration steps, approvals, or command flow.

## Workflow Boundary

This is already a structured workflow:
- do not create a second planning system alongside the orchestrator
- do not confuse ad hoc notes with framework artifacts
- framework artifacts are the only planning outputs that matter for a migration run
- do not substitute any external plan mode for framework planning

If the user wants to inspect planning results, read framework-owned artifacts only.

## Step 1: Collect Migration Intent

Collect the following. If the user already provided them, extract them and do not re-ask.

Required:
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

If non-negotiables are missing, ask specifically for:
- style guides
- naming conventions
- required libraries or SDKs
- architectural patterns that must be preserved
- anything that must not change during migration

When collecting non-negotiables through the terminal wizard, present:
- repo style-guide presets discovered under `styleguide/<language>/`
- naming-convention presets from the corresponding naming section when available
- custom style-guide path input
- custom free-form style or naming rules

The framework scripts use only Python stdlib. No venv is needed to run the framework itself. For `testCommand` and `buildCommand`, bake in activation if the target project needs it.

## Step 2: Determine Tier

Use `ARCHITECTURE.md` as the source of truth.

Choose Tier 1 when:
- the migration stays within the same language or paradigm
- one rulebook can cover most files
- domain decomposition is not required

Choose Tier 2 when:
- there is a language or paradigm shift
- different code categories need different strategies
- structural decomposition is required

For Tier 2, explain that the framework architecture is:
- deterministic foundation artifacts first
- domain discovery, planning, and execution after that
- per-domain instruction files instead of one global rulebook
- rewiring and integration review after domain execution

Present the tier recommendation with reasoning. Let the user override it.

## Step 2A: Phase Shape

For Tier 1, use this phase set:
- discovery
- planning
- execution
- review
- reiterate

For Tier 2, use this phase set:
- foundation
- module_discovery
- domain_discovery
- conflict_resolution
- domain_planning
- domain_execution
- rewiring
- integration_review
- reiterate

Tier 2 remains orchestrator-driven and artifact-driven. The difference is decomposition, not ownership.

## Step 3: Validate Prerequisites

Before proceeding, verify:
- source directory exists and contains files
- target directory exists or can be created
- reference directory exists when provided
- recipe path exists when provided explicitly, or the named recipe exists under `.codex/recipes/`
- `.codex/scripts/orchestrator.py` exists
- `python3` is available

If validation fails, tell the user exactly what is missing and how to fix it.

## Step 4: Write the Manifest

Derive artifact locations from `sourcePath`:
- `experimentDir` = parent directory of `sourcePath`
- `artifactsDir` = `{experimentDir}/artifacts`
- `summariesDir` = `{experimentDir}/artifacts/migration-summaries`

Write `migration-manifest.json` inside `experimentDir`, not the repo root.

Generate `sessionId` as `migrate-YYYYMMDD-` plus 6 random hex characters.

Write a tier-appropriate manifest with the correct phase set and metadata. Use `recipe`, `sourcePath`, `targetPath`, `artifactsDir`, `summariesDir`, `referencePath`, descriptions, commands, non-negotiables, and Tier 2 domain metadata when applicable.

## Step 5: Create Directories

Create `artifactsDir` and `summariesDir`.

For Tier 1, create summary directories for:
- discovery
- planning
- execution
- review
- reiterate

For Tier 2, create summary directories for:
- foundation
- module-discovery
- domain-discovery
- conflict-resolution
- domain-planning
- domain-execution
- rewiring
- integration-review
- reiterate

If the user provided explicit Tier 2 domains, you may also pre-create per-domain directories under discovery, planning, and execution as appropriate.

## Step 6: Show Summary and Confirm

Present a compact migration summary:
- source description and path
- target description and path
- reference path or none
- recipe
- artifacts directory
- tier and framework version
- test/build/lint commands
- non-negotiables
- manifest path

For Tier 2, also summarize:
- selected domains
- domain ordering constraints
- that the workflow is domain-decomposed and artifact-driven

Wait for explicit confirmation before launch.

## Step 7: Launch Orchestrator

After confirmation:
1. launch `python3 .codex/scripts/orchestrator.py <manifest> --non-interactive`
2. monitor the manifest
3. surface approval gates in the conversation
4. on approval, resume with `python3 .codex/scripts/orchestrator.py <manifest> --approve <phase> --non-interactive`

Run the orchestrator in the background so the conversation stays responsive.

## Step 8: Monitor State

Use `migration-manifest.json` as the source of truth.

Loop:
1. read the manifest
2. if any phase is `awaiting_approval`, stop polling and surface the approval gate
3. if `meta.status` is `failed`, report the failure briefly and stop
4. if `meta.status` is `complete`, report success briefly and stop
5. otherwise continue polling with terse progress updates

Do not dump full logs unless the user asks.

## Step 9: Surface Approval Gates

When a phase reaches `awaiting_approval`, read the corresponding summary artifact and show:
- phase name
- artifact path
- a short excerpt
- the options `approve`, `abort`, `open`

Tier 1 mapping:
- discovery -> `DISCOVERY.md`
- planning -> `PLAN.md`
- review -> `REVIEW.md`

Tier 2 mapping:
- foundation -> foundation summary
- module_discovery -> module discovery summary
- domain_discovery -> combined domain discovery summaries
- conflict_resolution -> conflict summary
- domain_planning -> domain planning bundle
- integration_review -> integration review summary

If a Tier 2 phase has multiple domain summaries, present a concise combined summary instead of dumping all files.

## Step 10: Resume After Approval

On `approve`, run:

`python3 .codex/scripts/orchestrator.py <manifest> --approve <phase> --non-interactive`

Then return to monitoring.

## Critical Rules

1. Do not run migration logic directly.
2. Do not spawn migration sub-agents directly; the orchestrator does that.
3. Do not read source code during setup; discovery does that.
4. Keep updates compact and approval-focused.
5. Keep planning inside framework artifacts only.
6. Do not require the user to paste orchestrator commands manually.
7. If the user asks to modify migration behavior, edit framework files directly instead of inventing a new workflow.
8. If slash commands are unavailable, continue through this skill without treating that as a blocker.

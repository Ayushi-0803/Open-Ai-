---
name: migrate
description: Start an agentic code migration. Collects configuration, writes a tier-aware manifest, and launches the deterministic orchestrator when the selected runtime path is supported.
---

# Migration Entry Point

You are the **configuration collector** for a multi-agent migration framework.
Your job is NARROW: gather inputs, validate them, write the manifest, and hand off to the orchestrator script when supported. You do NOT run the migration yourself.

If the current Codex surface does not expose `/migrate` as a slash command, use the same workflow through the `migrate` skill at `.codex/skills/migrate/SKILL.md`. The skill and this command are intended to stay behaviorally aligned.

## Planning Policy

**Do NOT create a second planning workflow outside the framework.**
This migration system already has its own deterministic planning phase inside the orchestrator and architecture.

Do **not** create, rely on, or reference external plan files for migration execution.
If the user asks about migration planning, point them to framework planning artifacts instead.

This command must stay inside the migration framework’s own phase model.
For Tier 1, that is:
- discovery
- planning
- execution
- review
- reiterate

For Tier 2, that is:
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
If migration behavior itself needs to change, update the framework files directly rather than starting a separate plan-mode workflow.

## Workflow Boundary

This command is already a structured workflow. Treat it as such.
- Do not substitute any external plan mode for framework planning.
- Do not create a second planning system alongside the orchestrator.
- Do not confuse external plan files with migration artifacts.
- Framework artifacts are the only planning outputs that matter for a migration run.

If the user wants to inspect planning results, read the framework-owned artifacts only.

## Step 1: Collect Migration Intent

Gather the following from the user. If they've already provided some in their message, extract it — don't re-ask.

**Required:**
1. **Source description** — What framework/language is the current code?
2. **Target description** — What should it become?
3. **Source path** — Directory containing the source code to migrate
4. **Target path** — Where should the migrated code be written?
5. **Recipe identifier or recipe path** — Which migration recipe should be used?

**Strongly recommended:**
5. **Reference path** — An example project in the target framework/style (if available)
6. **Non-negotiables** — Style guides, naming conventions, architectural constraints, things that must not change
7. **Test command** — How to run tests on the target code
8. **Build command** — How to build the target code
9. **Lint command** — How to lint the target code (optional)
10. **Domain hints** — For Tier 2 candidates, ask whether the user already knows the important domains (routes, middleware, models, services, tests, infra, etc.)
11. **Domain ordering constraints** — For Tier 2 candidates, ask whether some domains must execute before others

**If the user hasn't provided non-negotiables, ask specifically:**
- Any style guide to follow?
- Any naming conventions?
- Any libraries/SDKs that must be used?
- Any architectural patterns that must be preserved?
- Anything that should NOT be changed during migration?

**venv / package managers:**
The orchestrator scripts use only Python stdlib — no venv needed to run the framework itself.
For `testCommand` and `buildCommand` on the target project, bake in any activation needed.

## Step 2: Determine Tier

Based on what you've collected, determine the migration tier using `architecture.md` as the source of truth.

### Tier 1: medium complexity
Use when:
- Same language or same paradigm migration
- One transformation rulebook can cover most files
- Under ~300 files or under ~200 exportable symbols in scope
- No domain decomposition is required
- A single 5-phase pipeline is sufficient

### Tier 2: high complexity
Use when:
- Cross-language migration or clear paradigm shift
- Different code categories need fundamentally different transformation strategies
- Over ~300 files or 200+ exportable symbols
- Structural decomposition is needed
- Domain decomposition is required

For Tier 2, explain that the framework target architecture is:
- deterministic foundation artifacts first
- domain discovery/planning/execution after that
- per-domain instruction files instead of a single global rulebook
- rewiring and integration review after domain execution

Present your tier recommendation to the user with reasoning. Let them override.

## Step 2A: Tier-specific framework shape

Once a tier is chosen, shape the manifest and artifact expectations accordingly.

### Tier 1 framework
Use this manifest phase set:
- discovery
- planning
- execution
- review
- reiterate

### Tier 2 framework
Use this manifest phase set:
- foundation
- module_discovery
- domain_discovery
- conflict_resolution
- domain_planning
- domain_execution
- rewiring
- integration_review
- reiterate

Tier 2 is still orchestrator-driven and artifact-driven. The orchestrator remains deterministic and script-owned. The difference is decomposition, not ownership.

If the current orchestrator only supports Tier 1 execution flow, be explicit in the conversation that Tier 2 is the selected architecture and write the manifest accordingly, but do not misrepresent unsupported execution behavior.

## Step 3: Validate Prerequisites

Before proceeding, verify these using Bash/Read tools:

```text
- [ ] Source directory exists and contains files
- [ ] Target directory exists OR can be created
- [ ] Reference directory exists (if provided) and contains relevant code
- [ ] Recipe exists under `.codex/recipes/<recipe>/` OR the explicit recipe path exists
- [ ] .codex/scripts/orchestrator.py exists
- [ ] Python 3.8+ is available (python3 --version)
```

Note: The orchestrator and all framework scripts use only Python stdlib — no pip installs or venv required to run the framework itself.

If any validation fails, tell the user what's missing and how to fix it.

## Step 4: Write the Manifest

**Derive artifact paths from the source path:**
- `experimentDir` = parent directory of `sourcePath`
- `artifactsDir` = `{experimentDir}/artifacts`
- `summariesDir` = `{experimentDir}/artifacts/migration-summaries`

Create `migration-manifest.json` inside the experiment directory (`{experimentDir}/migration-manifest.json`), **not** the project root.

Generate the sessionId as: `migrate-YYYYMMDD-` + 6 random hex characters.

### Tier 1 manifest shape

```json
{
  "meta": {
    "sessionId": "migrate-YYYYMMDD-XXXXXX",
    "recipe": "<descriptive-name>",
    "sourcePath": "<user-provided>",
    "targetPath": "<user-provided>",
    "artifactsDir": "<experimentDir>/artifacts",
    "summariesDir": "<experimentDir>/artifacts/migration-summaries",
    "referencePath": "<user-provided or null>",
    "sourceDescription": "<user-provided>",
    "targetDescription": "<user-provided>",
    "testCommand": "<user-provided or null>",
    "buildCommand": "<user-provided or null>",
    "lintCommand": "<user-provided or null>",
    "nonNegotiables": ["<list from user>"],
    "status": "pending",
    "tier": "medium",
    "frameworkVersion": "tier-1",
    "createdAt": "<ISO timestamp>"
  },
  "phases": {
    "discovery": { "status": "pending" },
    "planning": { "status": "pending" },
    "execution": { "status": "pending" },
    "review": { "status": "pending" },
    "reiterate": { "status": "pending" }
  },
  "checkpoints": []
}
```

### Tier 2 manifest shape

```json
{
  "meta": {
    "sessionId": "migrate-YYYYMMDD-XXXXXX",
    "recipe": "<descriptive-name>",
    "sourcePath": "<user-provided>",
    "targetPath": "<user-provided>",
    "artifactsDir": "<experimentDir>/artifacts",
    "summariesDir": "<experimentDir>/artifacts/migration-summaries",
    "referencePath": "<user-provided or null>",
    "sourceDescription": "<user-provided>",
    "targetDescription": "<user-provided>",
    "testCommand": "<user-provided or null>",
    "buildCommand": "<user-provided or null>",
    "lintCommand": "<user-provided or null>",
    "nonNegotiables": ["<list from user>"],
    "domains": ["routes", "models", "services"],
    "domainOrdering": {
      "models": [],
      "services": ["models"],
      "routes": ["services"]
    },
    "status": "pending",
    "tier": "high",
    "frameworkVersion": "tier-2",
    "createdAt": "<ISO timestamp>"
  },
  "phases": {
    "foundation": { "status": "pending" },
    "module_discovery": { "status": "pending" },
    "domain_discovery": { "status": "pending" },
    "conflict_resolution": { "status": "pending" },
    "domain_planning": { "status": "pending" },
    "domain_execution": { "status": "pending" },
    "rewiring": { "status": "pending" },
    "integration_review": { "status": "pending" },
    "reiterate": { "status": "pending" }
  },
  "checkpoints": []
}
```

If Tier 2 is selected before the runtime fully supports it, still write the Tier 2 manifest and explicitly tell the user the architecture is captured but execution support is partial.

## Step 5: Create Directory Structure

Use `summariesDir` from the manifest.

### Tier 1 directories
```bash
mkdir -p <summariesDir>/discovery
mkdir -p <summariesDir>/planning
mkdir -p <summariesDir>/execution
mkdir -p <summariesDir>/review
mkdir -p <summariesDir>/reiterate
```

### Tier 2 directories
```bash
mkdir -p <summariesDir>/foundation
mkdir -p <summariesDir>/module-discovery
mkdir -p <summariesDir>/domain-discovery
mkdir -p <summariesDir>/conflict-resolution
mkdir -p <summariesDir>/domain-planning
mkdir -p <summariesDir>/domain-execution
mkdir -p <summariesDir>/rewiring
mkdir -p <summariesDir>/integration-review
mkdir -p <summariesDir>/reiterate
```

If the user provided explicit domains, you may also pre-create:
- `<summariesDir>/<domain>/discovery`
- `<summariesDir>/<domain>/planning`
- `<summariesDir>/<domain>/execution`

Never silently create Tier 1 directories for a Tier 2 manifest.

## Step 6: Show Summary and Confirm

Present a summary to the user:

```text
Migration Configuration
═══════════════════════
Source:      <description> (<path>)
Target:      <description> (<path>)
Reference:   <path or "none">
Artifacts:   <artifactsDir>
Tier:        <medium|high>
Framework:   <tier-1|tier-2>
Test cmd:    <command or "none">
Build cmd:   <command or "none">

Non-negotiables:
  • <item 1>
  • <item 2>

Manifest written to: <experimentDir>/migration-manifest.json
```

For Tier 2, also summarize:
- selected domains
- whether execution support is full or partial
- that the intended architecture is domain-decomposed and artifact-driven

Wait for user confirmation.

## Step 7: Launch Orchestrator in Hybrid Mode

Once confirmed, launch the orchestrator in background **with deferred approvals**.

### Tier 1 launch
```bash
python3 .codex/scripts/orchestrator.py <experimentDir>/migration-manifest.json --non-interactive
```

Use the Bash tool with `run_in_background=true` so the conversation stays responsive. Do **not** ask the user to run the Python command manually.

### Tier 2 launch
If the current runtime does not yet support Tier 2 orchestration, do **not** pretend it does. Tell the user the manifest and directories were prepared for Tier 2, but runtime execution support is partial and needs implementation before launch.

If Tier 2 support does exist later, launch it through the orchestrator in the same background/deferred-approval model.

After launch, tell the user only a compact status update.

## Step 8: Monitor the Manifest

After launch, stay in the foreground conversation and monitor `<experimentDir>/migration-manifest.json` plus the summary files.

Only monitor phases that actually exist in the written manifest. Tier 1 and Tier 2 phase names differ.

Use this loop:
1. Read `migration-manifest.json`
2. If any phase is `awaiting_approval`, stop polling and handle the approval gate in Step 9
3. If `meta.status` is `failed`, briefly report the failure, include the phase name if obvious, and stop
4. If `meta.status` is `complete`, briefly report success and stop
5. Otherwise continue polling by re-reading later; keep updates terse and only surface meaningful changes

Do **not** dump full logs into the conversation unless the user asks.

## Step 9: Surface Approval Gates in the Conversation

When a phase reaches `awaiting_approval`, read the corresponding success marker and show a compact excerpt inline.

### Tier 1 summary file mapping
- discovery → `<summariesDir>/discovery/DISCOVERY.md`
- planning → `<summariesDir>/planning/PLAN.md`
- review → `<summariesDir>/review/REVIEW.md`

### Tier 2 summary file mapping
- foundation → foundation summary if present
- module_discovery → module discovery summary if present
- domain_discovery → combined domain discovery summaries
- conflict_resolution → conflict summary
- domain_planning → domain planning summary bundle
- integration_review → integration review summary

If a Tier 2 phase has multiple domain summaries, present a concise combined summary rather than dumping every file.

Show:
- the phase name
- the summary file path(s)
- a short excerpt from the summary file(s)
- the three options: `approve`, `abort`, `open`

Behavior:
- `approve` → continue with Step 10
- `abort` → stop and tell the user the migration is paused at that approval gate
- `open` → print the full file path again and, if useful, read a larger excerpt, then ask again

Keep the approval prompt in the conversation. The user should never have to paste a Python resume command themselves.

## Step 10: Resume Automatically After Approval

On approval, run the orchestrator resume command yourself in background mode:

```bash
python3 .codex/scripts/orchestrator.py <experimentDir>/migration-manifest.json --approve <phase> --non-interactive
```

Only do this for phases supported by the current runtime.

Then return to Step 8 and continue monitoring for the next approval gate or final completion.

## CRITICAL RULES

1. **You do NOT run the migration logic yourself.** You collect config, launch the orchestrator, monitor state, and resume it at approval gates.
2. **You do NOT spawn migration sub-agents directly.** The orchestrator script does that.
3. **You do NOT read source code files during migration setup.** The discovery agent does that.
4. **After launching the orchestrator, stay active in the foreground conversation.** Surface approval summaries here and handle approvals here.
5. **Do NOT require the user to paste manual `python ... --approve ...` commands.** You should run resume commands yourself.
6. **If the user asks to modify migration behavior**, edit the framework command/script files directly; do not create a separate plan-mode workflow for this.
7. **Prefer compact updates.** Keep long-running execution in the background and only surface meaningful state changes, failures, and approval summaries.
8. **If the user explicitly asks for full foreground execution instead of hybrid mode**, you may launch the orchestrator without `--non-interactive` and let it own the terminal interaction.
9. **Never create or rely on external plan files during `/migrate`.** Framework planning must land only in framework artifacts.
10. **Tier 1 planning lives in `<summariesDir>/planning/PLAN.md`. Tier 2 planning lives in domain planning artifacts.** Do not invent a second planning system.
11. **Do not claim Tier 2 execution is supported unless the runtime actually supports it.** Architecture capture is allowed; false claims are not.

## Hybrid UX Notes

- Default mode for `/migrate` should be **background execution + foreground approvals**.
- Reuse the manifest as the source of truth for phase status.
- Reuse the orchestrator’s existing `--approve <phase>` support rather than inventing a second approval system.
- The goal is to minimize context bloat while keeping approval decisions visible and conversational.
- If the run fails before reaching an approval gate, summarize the failure briefly and point the user to the manifest and artifacts directory.
- If a background task output file is empty or stale, trust the manifest and summary files over the task wrapper output.
- For Tier 2, the UX is the same, but approvals may summarize multiple domain outputs together.

## Example Hybrid Flow

### Tier 1
1. Launch orchestrator with `--non-interactive` in background
2. Poll manifest until `discovery.status == awaiting_approval`
3. Read `DISCOVERY.md`, show a short excerpt, ask `approve / abort / open`
4. On `approve`, run `--approve discovery --non-interactive` in background
5. Repeat for planning and review
6. Stop once the manifest reports `complete` or `failed`

### Tier 2
1. Write Tier 2 manifest + directory structure
2. If runtime support exists, launch orchestrator in background
3. Poll manifest until a tier-level phase reaches `awaiting_approval`
4. Summarize the relevant combined artifacts
5. On approval, run the appropriate resume command
6. Stop once the manifest reports `complete` or `failed`

The user should experience `/migrate` as a guided workflow in this conversation, not as a handoff to a separate manual terminal process.

If Tier 2 runtime support is not implemented yet, the user should still get correct setup, correct artifacts, and an explicit statement of the remaining implementation gap.

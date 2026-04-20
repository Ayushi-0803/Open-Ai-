# Architecture Summary

## What this repo is

This repo is a **migration framework**, not a migrated app.

Its job is to run a guided, artifact-driven pipeline that moves a codebase from one language/framework to another through a command named `/migrate`.

The design splits responsibility into two parts:

- **Deterministic Python control plane**
- **LLM worker phases with strict artifact contracts**

In exact terms:

```text
User -> /migrate -> manifest -> orchestrator -> phase agents -> artifacts -> approvals -> next phase
```

The repo is small, but the architecture is strong:

- command layer defines workflow rules
- orchestrator owns state and sequencing
- deterministic builders create stable machine-readable inputs
- LLM skills interpret those inputs and produce summaries/plans/code
- validators gate every phase before the next one starts

## One-screen mental model

```text
                 ┌──────────────────────────────┐
                 │ .codex/commands/migrate.md   │
                 │ setup contract + UX rules    │
                 └──────────────┬───────────────┘
                                │
                                v
                 ┌──────────────────────────────┐
                 │ migration-manifest.json      │
                 │ single source of run state   │
                 └──────────────┬───────────────┘
                                │
                                v
                 ┌──────────────────────────────┐
                 │ .codex/scripts/orchestrator.py│
                 │ deterministic state machine   │
                 └───────┬───────────────┬──────┘
                         │               │
                         │               │ validates / checkpoints
                         v               v
          ┌──────────────────────┐   ┌──────────────────────┐
          │ deterministic builders│   │ artifact validator   │
          │ discovery/planning/   │   │ required files + JSON│
          │ foundation/parity     │   │ contract checks      │
          └──────────┬────────────┘   └──────────────────────┘
                     │
                     v
          ┌────────────────────────────────────────────┐
          │ agent_runner.py                            │
          │ Codex / Claude Code / Cursor subprocesses  │
          └──────────┬─────────────────────────────────┘
                     │
                     v
          ┌────────────────────────────────────────────┐
          │ phase skills                               │
          │ discovery / planning / execution / review  │
          │ reiterate / tier-2 domain phases           │
          └──────────┬─────────────────────────────────┘
                     │
                     v
          ┌────────────────────────────────────────────┐
          │ artifacts/migration-summaries/...          │
          │ markdown summaries + machine JSON outputs  │
          └────────────────────────────────────────────┘
```

## The real product shape

This is the real repo shape:

```text
Open-Ai-/
├── .codex/commands/
│   └── migrate.md
├── .codex/scripts/
│   ├── orchestrator.py
│   ├── manifest.py
│   ├── agent_runner.py
│   ├── discovery_builder.py
│   ├── planning_builder.py
│   ├── tier2_foundation_builder.py
│   ├── validate_artifacts.py
│   ├── diff_scorer.py
│   └── recipe_verify_runner.py
├── .codex/skills/
│   ├── migrate/SKILL.md
│   ├── discovery/SKILL.md
│   ├── planning/SKILL.md
│   ├── execution/SKILL.md
│   ├── review/SKILL.md
│   ├── reiterate/SKILL.md
│   └── tier2-*.md
└── .codex/recipes/
    └── example-generic/
```

Meaning:

- `commands/` = user-facing workflow contract
- `scripts/` = runtime engine
- `skills/` = per-phase agent instructions
- `recipes/` = migration-specific templates, patterns, and verification hooks

## Core runtime flow

### 1. `/migrate` is a configuration collector

`[migrate.md](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/commands/migrate.md)` does not do migration itself.

It does four things:

1. collect source, target, paths, recipe, constraints
2. choose Tier 1 or Tier 2
3. write `migration-manifest.json`
4. launch the orchestrator in background/non-interactive mode

This is important: the command is a **front door**, not the engine.

### 2. The manifest is the system state

`[manifest.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/manifest.py)` treats `migration-manifest.json` as the single source of truth.

It stores:

- run metadata
- selected tier/framework version
- per-phase status
- timestamps
- checkpoints
- artifact pointers

Exact intent:

```text
No hidden state.
No in-memory-only workflow.
Resume is manifest-driven.
```

### 3. The orchestrator is the control plane

`[orchestrator.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/orchestrator.py)` is the architectural center.

It owns:

- phase definitions
- phase ordering
- tier selection at runtime
- context assembly for each agent
- deterministic pre-build steps
- artifact validation
- approval gates
- resume after approval
- retries
- git checkpoints

Short version:

```text
orchestrator.py = operating system of the migration framework
```

### 4. Builders create hard facts before agents think

The repo intentionally avoids giving the LLM raw repo chaos first.

Instead it builds machine-readable artifacts:

- `[discovery_builder.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/discovery_builder.py)`
  - file inventory
  - dependency graph
  - export index
  - dynamic risk report
  - dependency shards
- `[planning_builder.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/planning_builder.py)`
  - dependency-safe batch order
  - deterministic risk assignments
  - human review queue
- `[tier2_foundation_builder.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/tier2_foundation_builder.py)`
  - symbol registry
  - migration layers
  - symbolic batches
  - inferred domains
- `[recipe_verify_runner.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/recipe_verify_runner.py)`
  - stable parity report from recipe hooks
- `[diff_scorer.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/diff_scorer.py)`
  - heuristic migration quality scoring

Architecture principle:

```text
deterministic first
LLM second
approval third
```

### 5. Skills are phase workers

The skill files define what each LLM worker is allowed to do and write.

Tier 1 phases:

```text
discovery -> planning -> execution -> review -> reiterate
```

Tier 2 phases:

```text
foundation
-> module_discovery
-> domain_discovery
-> conflict_resolution
-> domain_planning
-> domain_execution
-> rewiring
-> integration_review
-> reiterate
```

The skills are not generic prompts. They are **contract prompts**:

- required inputs
- required outputs
- critical rules
- success marker file

### 6. Validators enforce artifact contracts

`[validate_artifacts.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/validate_artifacts.py)` is a key safety layer.

Every phase must produce the right files and minimal JSON structure before the run can continue.

That means the system is not trusting agent prose alone.

It is checking:

- file existence
- non-empty outputs
- required JSON keys
- per-phase structural shape

## Tier 1 vs Tier 2

### Tier 1

Use case:

- medium complexity migrations
- one global rulebook can guide execution
- no deep domain decomposition needed

Operating model:

```text
one repo
one AGENTS.md
one batch plan
one execution phase
```

### Tier 2

Use case:

- cross-language or paradigm-shift migrations
- different domains need different strategies
- domain ownership and rewiring matter

Operating model:

```text
deterministic foundation
-> discover domains
-> resolve overlaps
-> create per-domain AGENTS files
-> execute domain by domain
-> rewire cross-domain imports
-> run integration review
```

This is the main architectural step up in the repo.

## Why the design is good

### Good decision 1: strict separation of concerns

```text
command     = collect config
manifest    = state
orchestrator= control
builders    = deterministic facts
skills      = phase intelligence
validator   = contract enforcement
recipes     = migration-specific extension point
```

That is clean architecture.

### Good decision 2: agents do not own sequencing

The LLM never owns the workflow.

The Python orchestrator owns:

- when a phase starts
- what inputs it receives
- when it stops
- whether it is approved
- whether outputs are valid

This reduces hallucinated workflow drift.

### Good decision 3: artifacts are first-class products

Each phase produces both:

- machine-readable JSON
- human-readable markdown

So the framework supports both:

- automation
- human oversight

### Good decision 4: runtime abstraction exists

`[agent_runner.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/agent_runner.py)` can spawn:

- Codex
- Claude Code
- Cursor

So the framework logic is more portable than the worker runtime.

## Important repo truths

### Truth 1: this repo is mostly framework, not app code

Someone reading it should not expect:

- business logic
- frontend/backend product modules
- deployable application service

They should expect:

- migration workflow infrastructure
- orchestration logic
- prompt contracts
- artifact schemas

### Truth 2: the orchestrator is big

`[orchestrator.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/orchestrator.py)` is ~3393 lines.

That means the system is powerful, but a lot of behavior is centralized in one file.

Architecturally this is both:

- a strength: easy to find the control logic
- a risk: too much policy in one script

### Truth 3: recipe support is real but still thin

There is only one example recipe:

- `[recipe.json](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/recipes/example-generic/recipe.json)`

The extension point exists, but the recipe ecosystem is not mature yet.

## Phase data flow

```text
Tier 1

source repo
  |
  v
discovery_builder.py
  -> dep-graph.json
  -> file-manifest.json
  -> symbol-index.json
  -> dynamic-risk-report.json
  -> DISCOVERY.md
  |
  v
planning_builder.py + planning skill
  -> planning-input.json
  -> risk-policy.json
  -> migration-batches.json
  -> planning-overview.json
  -> AGENTS.md
  -> PLAN.md
  |
  v
execution skill
  -> migrated target files
  -> batch-*-results.json
  -> execution-summary.json
  -> EXECUTION.md
  |
  v
review skill + diff_scorer + recipe_verify_runner
  -> review-results.json
  -> validation-report.json
  -> parity-results.json
  -> REVIEW.md
  |
  v
reiterate skill
  -> retries on failed files
  -> learned pattern proposals
  -> reiterate-results.json
  -> agents-md.patch.json
  -> REITERATE.md
```

## Tier 2 data flow

```text
Tier 2

source repo
  |
  v
tier2_foundation_builder.py
  -> FOUNDATION.md
  -> foundation-summary.json
  -> discovery.graph.json
  -> symbolic-batches.json
  -> symbol-registry.json
  -> migration-order.json
  |
  v
module_discovery
  |
  v
domain_discovery
  |
  v
conflict_resolution
  |
  v
domain_planning
  -> AGENTS.<domain>.md
  -> rewiring-imports.<domain>.json
  -> planning.<domain>.md
  |
  v
domain_execution
  |
  v
rewiring
  |
  v
integration_review
  |
  v
reiterate
```

## Repo map by importance

### Highest-value files

- `[.codex/scripts/orchestrator.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/orchestrator.py)`  
  Main engine. Read this first if you want real behavior.

- `[.codex/commands/migrate.md](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/commands/migrate.md)`  
  User workflow contract for `/migrate`.

- `[.codex/scripts/manifest.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/manifest.py)`  
  State model.

- `[.codex/scripts/validate_artifacts.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/validate_artifacts.py)`  
  Defines what “done” really means per phase.

- `[.codex/skills/*](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/skills)`  
  Defines worker contracts.

### Support files

- `[.codex/scripts/discovery_builder.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/discovery_builder.py)`
- `[.codex/scripts/planning_builder.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/planning_builder.py)`
- `[.codex/scripts/tier2_foundation_builder.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/tier2_foundation_builder.py)`
- `[.codex/scripts/agent_runner.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/agent_runner.py)`
- `[.codex/scripts/diff_scorer.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/diff_scorer.py)`
- `[.codex/scripts/recipe_verify_runner.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/recipe_verify_runner.py)`

## Exact architectural summary

If someone asks, "What is this repo?" the shortest exact answer is:

```text
This repo is a deterministic, artifact-driven, multi-agent migration framework.
It uses /migrate to collect configuration, writes a manifest, runs a Python
orchestrator, feeds bounded context to phase-specific LLM workers, validates
their outputs, and gates progress through approval checkpoints.
```

## Current architectural gaps

These are the main gaps visible from the repo itself:

1. `ARCHITECTURE.md` is referenced by the command/skill docs, but the file does not exist.
2. `[README.md](/Users/harshit/Desktop/Hackathin/Open-Ai-/README.md)` is effectively empty, so first-contact repo understanding is poor.
3. `orchestrator.py` is very large, so control policy is centralized and harder to evolve safely.
4. Recipe coverage is minimal; the framework shape is ahead of the recipe library.
5. There are no visible tests in this nested repo for the migration runtime itself.

## Recommended reading order

```text
1. .codex/commands/migrate.md
2. .codex/scripts/orchestrator.py
3. .codex/scripts/manifest.py
4. .codex/scripts/validate_artifacts.py
5. .codex/scripts/discovery_builder.py
6. .codex/scripts/planning_builder.py
7. .codex/scripts/tier2_foundation_builder.py
8. .codex/skills/
9. .codex/recipes/example-generic/
```

## Clone and use `/migration`

This is the simple human flow.

Important Codex note:

```text
Current Codex custom slash commands are loaded from ~/.codex/prompts/
and are invoked as /prompts:<name>, not bare /migration.
```

### Step 1: Clone the repo

```bash
git clone <your-repo-url>
cd Open-Ai-
```

### Step 2: Know which files matter

- `.codex/commands/`
- `.claude/commands/`
- `.codex/scripts/`
- `.codex/skills/`
- `.codex/recipes/`

The important command files are:

- `/migrate` comes from `[.codex/commands/migrate.md](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/commands/migrate.md)`
- `/migration` comes from `[.codex/commands/migration.md](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/commands/migration.md)`
- Claude also has:
  - `[.claude/commands/migrate.md](/Users/harshit/Desktop/Hackathin/Open-Ai-/.claude/commands/migrate.md)`
  - `[.claude/commands/migration.md](/Users/harshit/Desktop/Hackathin/Open-Ai-/.claude/commands/migration.md)`

### Step 3: Open the repo in your tool

Choose one:

- Codex
- Claude Code
- Cursor

### Step 4: Type `/`

For current Codex custom prompts, type `/prompts:`.

You want to see:

```text
/prompts:migration
```

If `/prompts:migration` shows up, the setup is working.

### Step 5: If needed, tweak the model

You usually do not need to change framework code.

The easiest way is to keep the repo as-is and choose the model when the orchestrator runs.

Examples:

```bash
python3 .codex/scripts/orchestrator.py ./migration-manifest.json --runtime codex --model gpt-5.4
python3 .codex/scripts/orchestrator.py ./migration-manifest.json --runtime claude-code --model <your-claude-model>
python3 .codex/scripts/orchestrator.py ./migration-manifest.json --runtime cursor --model <your-cursor-model>
```

If you want to change the default model inside the repo, edit `[agent_runner.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/agent_runner.py)` where the default model is set.

### Step 6: Start using `/migration`

Once the prompt appears in the slash menu, a human can do this:

1. type `/`
2. select `prompts:migration`
3. answer the setup questions
4. confirm source path, target path, recipe, and constraints
5. let the orchestrator run
6. approve each review gate when asked

### Simple setup by tool

#### Codex

This repo is already wired for Codex first.

Human steps:

1. open the repo in Codex
2. restart Codex after installing the prompt
3. type `/prompts:`
4. confirm `migration` is visible
5. select `/prompts:migration`

Codex uses custom prompts from `~/.codex/prompts/`, so installing the prompt there is the important step.

#### Claude Code

This repo now ships a repo-local Claude command tree too.

Human steps:

1. open the repo in Claude Code
2. type `/`
3. confirm `migration` is visible
4. select `/migration`

If your Claude setup expects skill files under `.claude/skills/`, copy the needed skill files there. The command files already exist in this repo.

#### Cursor

This repo supports Cursor as a worker runtime in `[agent_runner.py](/Users/harshit/Desktop/Hackathin/Open-Ai-/.codex/scripts/agent_runner.py)`, but it does not ship a repo-local Cursor slash-command layer.

Human steps:

1. open the repo in Cursor
2. check whether your Cursor setup supports repo-local slash commands
3. if yes, add a `migration` command wrapper in that command location
4. if no, run the framework through the orchestrator and use Cursor only as the worker runtime

### If `/prompts:migration` does not show up in Codex

Do these checks in order:

```text
1. confirm the repo is opened at Open-Ai-/
2. confirm the prompt file exists:
   - ~/.codex/prompts/migration.md
3. restart Codex
4. type /prompts: again
```

### Lowest-risk tweak rule

Only tweak:

1. command file name/location
2. runtime flag
3. model flag
4. recipe files

Do not tweak:

1. phase names
2. artifact names
3. manifest structure
4. validator rules

## Bottom line

This repo is not "code migration scripts".

It is a **migration operating framework** with:

- a command front door
- a manifest-based state model
- a deterministic Python control plane
- LLM workers constrained by artifact contracts
- human approvals at critical gates
- Tier 1 and Tier 2 operating modes

Best single-sentence description:

```text
An orchestrated migration platform that converts source repos through deterministic analysis, phase-specific AI workers, and artifact-validated approval gates.
```

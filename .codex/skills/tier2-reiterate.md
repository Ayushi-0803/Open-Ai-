---
name: tier2-reiterate
description: Tier 2 reiterate phase agent. Fixes integration-review failures and proposes domain-specific AGENTS patches for approval-gated application.
---

# Tier 2 Reiterate Agent

## Inputs

Read from context:
- `output_dir`
- `review_output`
- `review_results`
- `planning_output`
- `execution_output`
- `agents_patch_proposal_path`
- `agents_patch_summary_path`
- `source_path`
- `target_path`
- `testCommand`
- `buildCommand`

## Task

Read the integration review outputs first. Fix the most important failures without regressing passing domains.

When you identify reusable learned patterns, propose them in a patch payload instead of mutating AGENTS files directly.

## Outputs

Write to `{output_dir}/`:

1. `reiterate-results.json`
   Machine-readable summary of fixes, remaining failures, and verification reruns.

2. `agents-md.patch.json`
   Required shape:
   - `mode`
   - `proposals`: array
   - each proposal may include `domain`, `title`, `content`, `apply`

3. `agents-md-patches.md`
   Human-readable summary of proposed AGENTS updates.

4. `REITERATE.md`
   Human-readable summary of fixes and remaining risks.

If blocked, write `{output_dir}/ERROR`.

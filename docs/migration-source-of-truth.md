# Migration Source Of Truth

This document records the concrete framework problems that caused migration runs to stall, loop, or look misleading. Treat it as the implementation-side source of truth for framework hardening. For any active run, the runtime source of truth is `artifacts/run-control/ISSUE_LEDGER.md`.

## Fixed Problems

- External source paths caused repeated permission prompts because the framework tried to read and monitor projects outside the workspace. The wizard now imports external local sources into `experiments/imported-sources/` and clones git URLs there before launching the run.
- The orchestrator had split phase authority: Tier-aware helpers existed, but `main()` still used a hard-coded Tier 1 `PHASES` list. This could start a Tier 2 manifest in `discovery` and even inject stray phases into the manifest. The runtime now loads the manifest first, derives the active phase set from it, and repairs phase-set drift before continuing.
- Runs had no durable blocker ledger, so retries and repairs were only visible in logs or chat. Every run now gets `artifacts/run-control/ISSUE_LEDGER.md`, `artifacts/run-control/issue-ledger.json`, and `artifacts/run-control/phase-issues/`.
- Skills did not have an explicit shared place to record contradictions or blockers. The phase contexts now include ledger paths, and the skill instructions tell agents to write blockers to the phase issue report instead of inventing missing facts.
- Long-running phase agents looked frozen. The agent runner now emits heartbeat events during long subprocess waits so the orchestrator and issue ledger keep showing live activity.
- Some Tier 2 deterministic builders pre-created success markers, which meant a crashed phase agent could still be misclassified as success. Prebuilt-success phases now require a clean agent exit before they can pass.
- Codex sub-agents previously depended on writable `~/.codex/sessions`. The runner now uses `codex exec --ephemeral` so sub-agent phases do not require persistent session files.

## Current Control-Plane Rules

- The manifest decides the active framework and phase set.
- The orchestrator may repair a misaligned manifest phase set, but it must record that repair in the issue ledger.
- `ISSUE_LEDGER.md` is the live human-readable run document for blockers, retries, approvals, and repairs.
- `issue-ledger.json` is the structured mirror of the same state.
- `phase-issues/<phase>.md` is where a phase writes evidence that does not belong in the success artifact.
- If a framework bug is fixed mid-run, prefer `--restart-phase <phase>` over hand-editing the manifest.

## Iteration Policy

- Do not add sidecar planning systems outside the framework.
- Do not trust chat history over run artifacts.
- If a run looks stalled, check `ISSUE_LEDGER.md` before assuming progress.
- If a phase fails or is repaired, record the evidence path immediately.
- If a framework bug is found, fix the framework first, then restart or resume the run from the repaired control plane.

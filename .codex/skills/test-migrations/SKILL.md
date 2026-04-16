---
name: test-migrations
description: Run post-migration tests on the converted code produced by the migrate skill. Uses the migration manifest as the source of truth for paths and commands, captures artifacts, and reports pass/fail succinctly.
---

# Test Migrations Skill

Use this after the migration framework has produced converted code (Tier 1 or Tier 2) and you need to validate it with the target project's test/build commands.

## Inputs to Gather (reuse migrate manifest)
- `manifestPath` (default: `{cwd}/migration-manifest.json`)
- `testCommand` (prefer the value in `meta.testCommand`; prompt only if missing)
- Optional overrides: `buildCommand`, `lintCommand`, env activation (e.g., `nvm use`, `. ./venv/bin/activate`)
- Desired scope: full suite vs. smoke subset

## Preflight
1. Load the manifest. Extract `meta.targetPath`, `meta.sourcePath`, `meta.artifactsDir`, `meta.summariesDir`, `meta.sessionId`, and `meta.testCommand`.
2. Choose working dir:
   - `targetPath` if present; otherwise `sourcePath` (in-place migration).
3. Validate:
   - working dir exists and is readable
   - test command known (from manifest or user)
   - if a build/lint command is required before tests, confirm/skip explicitly

## Execution Steps
1. Move to the working dir.
2. If activation is needed, run it first (e.g., `direnv allow && direnv exec . <cmd>`, `source .venv/bin/activate`, `nvm use`, `poetry shell`). Do not invent installs; ask before running package installs.
3. Optional: run build/lint if specified in manifest or requested.
4. Run tests with the resolved `testCommand`. Keep output streaming but also tee to a log under `{artifactsDir}/test-runs/<sessionId>/test-output.log`.
5. Capture exit code, duration, and coverage file locations (if produced).

## Artifacts to Write
Under `{artifactsDir}/test-runs/<sessionId>/` create:
- `TEST_RUN.md` — brief summary (command, exit code, duration, pass/fail, coverage paths if any)
- `test-output.log` — full console output
- `context.json` — `{ "workingDir": "...", "testCommand": "...", "buildCommand": "...", "lintCommand": "...", "timestamp": "..." }`

## Reporting Back to the User
- If pass: share the command used, duration, and location of `TEST_RUN.md`.
- If fail: share exit code and the top offending test names/stack traces (first ~40 lines), and point to `test-output.log`.
- If no test command is available: ask for one explicitly; suggest common defaults based on repo signals (package.json -> `npm test`, pytest -> `pytest`, Go -> `go test ./...`) but do not run without confirmation.

## Safety and Boundaries
- Do not modify source files while running this skill.
- Do not change the manifest structure. If you must record a test run, write artifacts only to `artifactsDir/test-runs/<sessionId>/`.
- Keep logs concise in-chat; rely on artifact paths for full output.
- If the project lacks tests, report that plainly and stop.

# Planning Approval Summary

## Scope

- Total deterministic files: 3
- Total batches: 2
- Review distribution: 1 auto, 1 supervised, 1 human
- Ordering contract: preserved exactly from `planning-input.json`
- Risk contract: preserved exactly from `planning-input.json`
- Ordering exceptions: none
- Risk exceptions: none

This plan covers only the deterministic planning set. Discovery explicitly shows that the real stylelint repository is much larger, so this artifact should be treated as a safe execution contract for the 3 covered files, not as a full migration inventory for the overall Rust port.

## Batch Breakdown

### Batch 1: `Dependency depth 0`

- Files:
  - `types/stylelint/index.d.ts` (`human`)
  - `types/stylelint/type-test.ts` (`supervised`)
- Why it comes first:
  - `types/stylelint/index.d.ts` is the public API contract and documents the option, result, warning, plugin, formatter, utility, and reference shapes that the Rust facade must preserve.
  - `types/stylelint/type-test.ts` validates how consumers actually access that API, including `require('stylelint')`, dynamic `import('stylelint')`, `resolveConfig(...)`, `lint(...)`, utility helpers, and plugin creation.
  - Putting both files in the first batch ensures execution defines the compatibility boundary before touching trailing test fixtures.

### Batch 2: `Tests`

- Files:
  - `lib/utils/__tests__/fixtures/index.js` (`auto`)
- Why it comes second:
  - It is a test-domain fixture and the deterministic strategy is `dependency-depth with tests last`.
  - The fixture has no independent migration value before the public API and compatibility contract are established.
  - The file is intentionally empty, so execution risk is low once batch 1 has fixed the target test and compatibility structure.

## Why This Ordering Is Dependency-Safe

- The deterministic batch order from `planning-input.json` is already dependency-safe for the covered files.
- The public API declaration file and type-parity test define the compatibility surface first.
- The fixture file is scheduled after that surface exists, which matches both the recipe rule `tests-last` and the source semantics.
- No deterministic dependency edges required an override.

## Human Review Queue

- `types/stylelint/index.d.ts`
  - Reason: no direct test coverage
  - Reason: high complexity
  - Review focus:
    - `PublicApi` shape parity for `.lint`, `.rules`, `.formatters`, `.createPlugin`, `.resolveConfig`, `.utils`, and `.reference`
    - `LinterOptions`, `LinterResult`, `LintResult`, `Warning`, and `EditInfo` semantic parity
    - preservation of autofix, plugin support, shareable config behavior, and config-resolution inputs

## Execution Notes

- `AGENTS.md` instructs execution to preserve the observable API facade from `lib/index.mjs`, including CommonJS compatibility via `module.exports`.
- Lazy-loading semantics in `lib/rules/index.mjs` and `lib/formatters/index.mjs` are recorded as observable behaviors even though those files are outside the deterministic 3-file batch set.
- The fixture file `lib/utils/__tests__/fixtures/index.js` is present in the sampled source tree and is intentionally empty. Execution must preserve that emptiness if the fixture is recreated in the Rust target test harness.
- Use the provided target root verbatim: `experiemtns/stylint/migrated`.

## Assumptions And Risks

- Assumption: no `reference_path` was provided, so target-style conventions come from `styleguide/rust` and the recipe only.
- Assumption: the execution agent will use this plan only for the deterministic 3-file scope and will not infer repository-wide completeness from it.
- Risk: discovery artifacts are partial. The formal inventory covers 3 files, while `DISCOVERY.md` shows a much larger codebase with lazy rule loading, formatter loading, config discovery, parser switching, plugins, and embedded-style extraction.
- Risk: `types/stylelint/index.d.ts` is a high-risk compatibility document; simplifying it would cause downstream behavior drift even if Rust internals compile cleanly.
- Risk: `types/stylelint/type-test.ts` intentionally exercises CommonJS and dynamic import behavior. Treating those as incidental rather than contractual would break public API compatibility.

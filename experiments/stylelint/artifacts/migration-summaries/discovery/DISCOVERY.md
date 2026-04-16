# Discovery Summary

## Source Codebase Overview

- Source: `experiments/stylelint/current`
- Target: `experiemtns/stylint/migrated`
- Source description: stylelint, a CSS linter with built-in rules, autofix, plugins, shareable configs, CSS-like language support, and embedded style extraction.
- Target description: Rust reimplementation with behavior parity.
- Non-negotiables:
  - Preserve all current functionality and observable behavior.
  - Preserve autofix support.
  - Preserve plugin support and shareable config support.
  - Preserve support for CSS-like languages including SCSS, Sass, Less, and SugarSS.
  - Preserve extraction of embedded styles from HTML, Markdown, and CSS-in-JS.

The deterministic discovery base is incomplete. The provided `dep-graph.json` and `file-manifest.json` cover only 3 files, the symbol index is empty, and the single dependency shard also contains only those 3 files. Bounded source sampling shows the real repository is much larger, with 968 files under `lib/`, 146 built-in rule directories, 469 `lib/` test files, 41 system-test files, and a standard CLI/API/docs/scripts layout.

This means the deterministic artifacts are usable as the formal source of truth for the covered files, but insufficient as a standalone migration inventory. The remainder of this summary uses bounded source sampling to explain the architecture and migration risks without pretending the deterministic graph is complete.

## Architecture Overview

Stylelint is organized as a layered Node.js ESM codebase:

1. **Interface layer**
   - `bin/stylelint.mjs` is the CLI entrypoint.
   - `lib/cli.mjs` parses flags and translates them into linter options.
   - `lib/index.mjs` exposes the public API: `lint`, `rules`, `formatters`, `createPlugin`, `resolveConfig`, utilities, and a PostCSS plugin.
   - `lib/postcssPlugin.mjs` integrates stylelint into PostCSS pipelines.
   - `lib/formatters/` contains built-in output formatters.

2. **Core lint engine**
   - `lib/standalone.mjs` orchestrates file globbing, ignore handling, caching, formatting, suppression handling, and return-value assembly.
   - `lib/lintSource.mjs` resolves config, obtains a PostCSS result, computes reference roots, executes rule logic, and reports disable/suppression state.
   - `lib/getPostcssResult.mjs` parses either source code or files, switching to `postcss-safe-parser` when lax fix mode is enabled.
   - `lib/rules/index.mjs` lazily loads built-in rules and exposes them as a map-like public API.
   - `lib/reference/` contains the large static reference datasets that rules depend on.

3. **Integration/config layer**
   - `lib/createStylelint.mjs` creates the linter instance and config explorers.
   - `lib/getConfigForFile.mjs` and `lib/augmentConfig.mjs` perform config discovery, override application, path absolutization, extends/plugin/customSyntax resolution, and rule normalization.
   - `lib/utils/resolveSilent.mjs` handles package/path resolution, including Yarn PnP compatibility.
   - `lib/utils/getCustomSyntax.mjs`, formatter loading, and cached imports rely on dynamic module resolution.
   - File cache and suppressions logic are integrated into the standalone flow.

4. **Tests and type surface**
   - `lib/rules/*/__tests__/index.mjs` contains per-rule behavior tests.
   - `lib/__tests__` covers integration paths such as CLI, globs, syntax handling, plugins, reference files, and CommonJS/ESM interop.
   - `system-tests/` covers end-to-end runtime scenarios.
   - `types/stylelint/index.d.ts` and `types/stylelint/type-test.ts` define and validate the public TypeScript surface.

## Dependency Graph Highlights

### Deterministic graph

- Deterministic files: 3
- Entry points: none captured
- Circular dependencies: none captured
- External packages: none captured
- Symbol index: empty
- Dynamic-risk report: 1 flagged file, `types/stylelint/type-test.ts`

### What bounded source sampling adds

- Public entrypoints are clearly `bin/stylelint.mjs`, `lib/index.mjs`, `lib/cli.mjs`, `lib/standalone.mjs`, `lib/postcssPlugin.mjs`, and `lib/resolveConfig.mjs`.
- The codebase is dependency-dense around config resolution, parser/syntax loading, rule execution, and formatters, but the deterministic graph does not capture those edges.
- The runtime architecture is centered on PostCSS parsing plus a large rule registry and reference-data layer.
- The only deterministic dynamic-risk finding is in `types/stylelint/type-test.ts`, but runtime sampling shows meaningful dynamic loading in:
  - `lib/rules/index.mjs` for lazy rule loading
  - `lib/formatters/index.mjs` for lazy formatter loading
  - `lib/cli.mjs` and utility loaders for custom formatter and plugin/module imports
  - `lib/getPostcssResult.mjs` for safe-parser switching
  - config augmentation and custom syntax resolution

## Pattern Catalog

### Framework patterns

- ESM-first Node.js package with `.mjs` modules and an explicit CLI binary.
- PostCSS-centered parsing and AST traversal.
- `cosmiconfig`-driven config discovery and extension.
- `globby` and ignore-file based file selection.
- `meow` CLI argument parsing.

### Architectural patterns

- Lazy-loaded registry pattern for built-in rules.
  - Count: 146 built-in rule directories, all exposed through `lib/rules/index.mjs`.
- Plugin object pattern for third-party rules.
  - `createPlugin()` returns `{ ruleName, rule }`.
- Public API aggregation pattern in `lib/index.mjs`.
  - One composite export for linting, rules, formatters, config resolution, utilities, and references.
- Config augmentation pipeline.
  - Absolutize paths, merge extends, apply overrides, resolve plugins/custom syntaxes/reference files, normalize rules, validate language options.
- File-oriented orchestration around a core lint engine.
  - CLI -> standalone -> createStylelint/getConfigForFile -> lintSource -> lintPostcssResult.

### Common idioms

- Rule implementation template:
  - `const ruleName`
  - `const messages = ruleMessages(...)`
  - `const meta = { url: ... }`
  - validate options
  - traverse/report via PostCSS nodes
  - attach `ruleName`, `messages`, and `meta` to the exported function
- Rule test template:
  - `testRule({ ruleName, config, accept, reject, ... })`
- Lazy dynamic import for optional or numerous modules.
  - Observed `await import(` occurrences in `lib/`: 7
- Frequent custom syntax coverage.
  - Observed `customSyntax:` occurrences in `lib/` and `system-tests/`: 184
- Atomic output writing for fix/report persistence.
  - Observed `writeFileAtomic(` usage in `lib/`: 2

### Counted pattern instances

- Built-in rule directories: 146
- Built-in rule directories with `__tests__/index.mjs`: 146
- Built-in formatters: 6
- `lib/` files: 968
- `lib/` test files: 469
- All detected test files in repository: 479
- System-test files: 41

## Test Coverage

### Deterministic manifest coverage

- Files covered by deterministic manifest: 3
- Files with mapped tests: 1
- Files without mapped tests: 2
- Covered files with higher migration attention:
  - `types/stylelint/index.d.ts` has no mapped test file.
  - `types/stylelint/type-test.ts` is itself a type-level validation file, not a runtime parity suite.

### Observed repository test posture

- The repository test structure is strong.
- Every built-in rule directory sampled at the top level has a matching `__tests__/index.mjs`.
- There are dedicated integration tests for CLI, syntax handling, plugins, globs, reference files, and CommonJS/ESM interoperability.
- `system-tests/` adds end-to-end cases.
- `types/stylelint/type-test.ts` protects the public API typing surface.
- `README.md` states the project has roughly 15k unit tests; use that as a directional claim from project docs, not as a deterministic count.

### Commands

- Current source package test flow:
  - `npm test`
  - `npm run test-jest`
  - `npm run test-node`
  - `npm run lint`
  - `npm run lint:types`
- Target verification commands from migration context:
  - `cargo build`
  - `cargo test`
  - `cargo clippy --all-targets --all-features -- -D warnings`

## Reference Project Analysis

No `reference_path` was provided in the context, so there is no target-project convention analysis for routes, handlers, middleware, config, or tests.

## CI/CD And Infrastructure

### CI/CD

- GitHub Actions workflows are present under `.github/workflows/`.
- `ci.yml` runs:
  - reusable lint workflow
  - reusable test workflow across Node.js 20, 22, and 24
  - OS matrix across Ubuntu, Windows, and macOS
  - a dedicated coverage job on Node.js 24
  - a dedicated Yarn PnP runtime test path
  - spellcheck
- Release automation is present via reusable workflows in `release.yml`, `release-pr.yml`, and related workflow files.
- Coverage uploads are configured via Codecov.
- Dependabot configuration is present.

### Build and environment configuration

- Core project config files:
  - `package.json`
  - `package-lock.json`
  - `tsconfig.json`
  - `eslint.config.mjs`
  - `jest.setup.mjs`
  - `jest.setupAfterEnv.mjs`
  - `.npmrc`
  - `.editorconfig`
  - `.codespellrc`
  - `.gitignore`
  - `codecov.yml`
- Node engine requirement in `package.json`: `>=20.19.0`
- Packaging/export model:
  - binary entrypoint via `bin/stylelint.mjs`
  - package export map with types and default runtime export
  - `./lib/utils/*` subpath export

### Docker and runtime infrastructure

- No `Dockerfile`, `docker-compose`, or `.env*` template files were found at shallow repository depth.
- This appears to be a library/tooling package rather than a deployable service.

## Risk Assessment

### High risk

- **Incomplete deterministic inventory**
  - The formal discovery artifacts under-represent the true migration surface.
  - Planning must not batch work strictly from the current `dep-graph.json` and `file-manifest.json`.

- **Config resolution and module loading**
  - Behavior includes config file discovery, extends merging, plugin loading, custom syntax loading, path absolutization, and Yarn PnP support.
  - This is highly behavioral and ecosystem-dependent.

- **Parser and syntax compatibility**
  - The Rust target must preserve CSS parsing plus custom syntax support for SCSS, Sass, Less, SugarSS, HTML/Markdown embedded styles, and CSS-in-JS extraction.
  - The current implementation relies on PostCSS-compatible syntax modules and document-aware parsing behavior.

- **Autofix and edit-info parity**
  - Fix mode changes parser choice.
  - Output writing, computed edit info, and fix/no-fix return-shape behavior are observable API features.

- **Rule-engine parity**
  - 146 built-in rules plus large reference datasets and rich tests imply a large semantic surface.

### Medium risk

- **CommonJS/ESM interoperability**
  - Public API deliberately supports `require(ESM)` interoperability.
  - The type tests and dedicated runtime tests cover this behavior.

- **Suppressions, disables, and reporting**
  - The linter tracks multiple disable-report modes and suppression persistence.

- **Public API and type surface**
  - `types/stylelint/index.d.ts` is large and likely encodes behavior consumers depend on, even if the Rust port changes internal architecture.

### Lower risk

- **Formatter implementations**
  - Important for parity, but structurally simpler than parser/config/rule execution.

## Recommended Migration Order

Follow the recipe domain ordering, but adapt it to stylelint’s real architecture:

1. **Core**
   - Define Rust AST/parsing boundary and result model.
   - Port rule contract abstractions, warning/report structures, disable range tracking, and reference-data access.
   - Establish autofix and edit-info data structures early, even if not fully implemented at first.

2. **Integration**
   - Recreate config loading semantics, extends merging, override matching, ignore handling, cache behavior, custom syntax abstraction, plugin loading model, and suppression persistence.
   - Design explicit adapters for embedded-style extraction and CSS-like syntax support.
   - Preserve Yarn PnP/module-resolution observable behavior where user-facing.

3. **Interface**
   - Rebuild public API equivalents for linting, config resolution, formatter selection, plugin registration, and CLI behavior.
   - Port built-in formatter outputs and output-file behavior.

4. **Tests**
   - Translate rule tests into parity suites.
   - Port system tests and type/API compatibility checks into Rust-focused contract tests and black-box fixtures.
   - Keep the existing JS implementation available as an oracle for differential testing while the Rust engine matures.

## Migration Recommendation

Use the current JS implementation as a behavioral oracle instead of attempting a direct file-by-file translation. The architecture is regular enough to support systematic porting, but the migration will fail if it starts from CLI or formatter surfaces before the core parsing/config/rule semantics and syntax-compatibility contracts are nailed down.

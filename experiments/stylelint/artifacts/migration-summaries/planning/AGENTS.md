# Stylelint Rust Migration Execution Guide

## Migration Context

- Source: `experiments/stylelint/current`
- Target root: `experiemtns/stylint/migrated`
- Planning scope in this artifact set: 3 deterministic files carried forward from `planning-input.json`
- Source system: stylelint Node.js ESM package with public API, lazy rule/formatter loading, plugin support, autofix support, type-level API contracts, and fixtures used by tests
- Target system: Rust reimplementation that preserves current stylelint functionality and observable behavior
- Deterministic discovery is partial. `DISCOVERY.md` and `dep-graph.json` show that the formal inventory covers only 3 files even though the real repository is much larger. Execution must treat this plan as authoritative for ordering and risk, but not as proof that the overall migration surface is only 3 files.

## Non-Negotiables

- Follow the Rust style guide at `styleguide/rust`.
- Preserve all current functionality and observable behavior.
- Preserve autofix support.
- Preserve plugin support and shareable config support.
- Preserve support for CSS-like languages including SCSS, Sass, Less, and SugarSS.
- Preserve extraction of embedded styles from HTML, Markdown, and CSS-in-JS.
- Preserve the deterministic batch order and risk tiers from `planning-input.json`.
- Do not silently broaden scope beyond the files assigned in each batch.

## Deterministic Batch Contract

- `batch-1` must execute before `batch-2`.
- `types/stylelint/index.d.ts` remains `human` risk.
- `types/stylelint/type-test.ts` remains `supervised` risk.
- `lib/utils/__tests__/fixtures/index.js` remains `auto` risk.
- No ordering or risk overrides were approved in planning.

## Concrete Pattern Mappings

### Pattern: `public-api-types`

Source file:
- `experiments/stylelint/current/types/stylelint/index.d.ts`

Observed source examples:

```ts
export type PublicApi = PostCSS.PluginCreator<PostcssPluginOptions> & {
	lint: (options: LinterOptions) => Promise<LinterResult>;
	rules: { readonly [name in keyof CoreRules]: Promise<CoreRules[name]> };
	formatters: Formatters;
	createPlugin: (ruleName: string, rule: Rule) => Plugin;
	resolveConfig: (
		filePath: string,
		options?: Pick<LinterOptions, 'cwd' | 'config' | 'configBasedir' | 'configFile'>,
	) => Promise<Config | undefined>;
	utils: Utils;
	reference: {
		longhandSubPropertiesOfShorthandProperties: LonghandSubPropertiesOfShorthandProperties;
	};
};
```

```ts
export type LinterOptions = {
	files?: OneOrMany<string>;
	globbyOptions?: GlobbyOptions;
	cache?: boolean;
	cacheLocation?: string;
	code?: string;
	config?: Config;
	configFile?: string;
	configBasedir?: string;
	cwd?: string;
	customSyntax?: CustomSyntax;
	formatter?: FormatterType | Formatter;
	fix?: boolean | FixMode;
	computeEditInfo?: boolean;
	allowEmptyInput?: boolean;
	quiet?: boolean;
	validate?: boolean;
};
```

```ts
export type Warning = {
	line: number;
	column: number;
	endLine?: number;
	endColumn?: number;
	fix?: EditInfo;
	rule: string;
	severity: Severity;
	text: string;
	url?: string;
	stylelintType?: StylelintWarningType;
};
```

Required after-state mapping:
- Map the public TypeScript contract into a Rust-facing API surface plus a compatibility layer, not into unrelated Rust-only types.
- Preserve the top-level facade shape exposed by `lib/index.mjs`: linting entrypoint, rule registry, formatter registry, plugin creation, config resolution, utilities, and reference data.
- Preserve async semantics where the source contract is async. `lint` and `resolveConfig` are promise-based and must remain asynchronous at the compatibility boundary.
- Preserve option/result field names and semantics unless there is an explicitly documented compatibility shim.
- Preserve autofix edit information semantics represented by `EditInfo` and `Warning.fix`.

Suggested target layout:
- `experiemtns/stylint/migrated/crates/stylelint_types/src/public_api.rs`
- `experiemtns/stylint/migrated/crates/stylelint_types/src/options.rs`
- `experiemtns/stylint/migrated/crates/stylelint_types/src/results.rs`

### Pattern: `type-parity-test`

Source file:
- `experiments/stylelint/current/types/stylelint/type-test.ts`

Observed source examples:

```ts
import stylelint = require('stylelint');

import('stylelint').then((module) => {
	module.default({
		code: '',
		codeFilename: '',
	});
});
```

```ts
stylelint.resolveConfig('path').then((config) => stylelint.lint({ config }));

stylelint
	.resolveConfig('path', {
		config: { ...options, fix: false },
		configBasedir: 'path',
		configFile: 'path',
		cwd: 'path',
	})
	.then((config) => stylelint.lint({ config }));
```

```ts
const messages = stylelint.utils.ruleMessages(ruleName, {
	problem: 'This a rule problem message',
	warning: (reason) => `This is not allowed because ${reason}`,
	withNarrowedParam: (mixinName: string) => `Mixin not allowed: ${mixinName}`,
});

stylelint.createPlugin(ruleName, testRule as Rule);
```

Required after-state mapping:
- Recreate these assertions as Rust-backed compatibility tests rather than dropping them because they are type-only.
- Keep both module access shapes under test: CommonJS `require('stylelint')` compatibility and dynamic `import('stylelint')`.
- Preserve the chain `resolveConfig(...) -> lint({ config })`.
- Preserve utility surface behavior for `ruleMessages`, `validateOptions`, `checkAgainstRule`, and `report`.
- Preserve plugin creation surface and message typing expectations as compatibility requirements, even if Rust internals use traits or enums.

Suggested target layout:
- `experiemtns/stylint/migrated/tests/type_surface_parity.rs`
- `experiemtns/stylint/migrated/tests/node_compat/type_surface.mjs`

### Pattern: `esm-cjs-interop-check`

Source files:
- `experiments/stylelint/current/types/stylelint/type-test.ts`
- `experiments/stylelint/current/lib/index.mjs`

Observed source examples:

```js
const stylelint = Object.assign(postcssPlugin, {
	lint: standalone,
	rules,
	formatters,
	createPlugin,
	resolveConfig,
	_createLinter: createStylelint,
	utils: {
		report,
		ruleMessages,
		validateOptions,
		checkAgainstRule,
	},
	reference: {
		longhandSubPropertiesOfShorthandProperties,
	},
});

export default stylelint;
export { stylelint as 'module.exports' };
```

Required after-state mapping:
- Preserve a single default-export-like facade with CommonJS compatibility at the package boundary.
- Do not split the API into multiple unrelated crates or executables without a JS compatibility shim that recreates the same import surface.
- Preserve the observable shape of `module.default`, `require('stylelint')`, and top-level members such as `.lint`, `.rules`, `.formatters`, `.utils`, `.reference`.

Suggested target layout:
- `experiemtns/stylint/migrated/bindings/node/index.mjs`
- `experiemtns/stylint/migrated/bindings/node/package.json`
- `experiemtns/stylint/migrated/crates/stylelint_node/src/lib.rs`

### Pattern: `test-file`

Source file:
- `experiments/stylelint/current/lib/utils/__tests__/fixtures/index.js`

Observed source example:

```js

```

Related real test context:

```js
const fixtureModuleA = path.join(dirname, 'fixtures/module-a.mjs');
const fixtureModuleB = path.join(dirname, 'fixtures/module-b.mjs');
const first = cachedImport(fixtureModuleA);
const second = cachedImport(fixtureModuleA);
expect(first).toBe(second);
```

Required after-state mapping:
- Preserve fixture-driven tests that validate lazy import and module-cache behavior.
- Keep empty fixture files empty when emptiness is the test condition.
- Do not replace fixture-based behavior checks with mocked-only tests if that would stop exercising filesystem/module loading semantics.

Suggested target layout:
- `experiemtns/stylint/migrated/tests/fixtures/lib/utils/index.js`
- `experiemtns/stylint/migrated/tests/node_compat/cached_import.mjs`

## Import And Module Mappings

- `types/stylelint/index.d.ts`
  - Source role: public API and compatibility contract
  - Target modules: `crates/stylelint_types/src/public_api.rs`, `crates/stylelint_types/src/options.rs`, `crates/stylelint_types/src/results.rs`
  - Keep these imports conceptually explicit in Rust:
    - PostCSS-facing syntax/result concepts
    - globby/config discovery options
    - config, formatter, rule, warning, and reference-data types

- `types/stylelint/type-test.ts`
  - Source role: compatibility assertions for import modes, plugin creation, config resolution, utils, and readonly references
  - Target modules: `tests/type_surface_parity.rs`, `tests/node_compat/type_surface.mjs`
  - Rewire imports so the compatibility tests target the Rust-backed JS facade, not internal Rust modules directly

- `lib/utils/__tests__/fixtures/index.js`
  - Source role: fixture asset
  - Target location: `tests/fixtures/lib/utils/index.js`
  - Keep test fixtures imported from tests, not from production runtime code

## Runtime Behaviors That Must Stay Observable

- Lazy rule loading in `lib/rules/index.mjs`:

```js
rule = import(`./${ruleName}/index.mjs`).then((m) => m.default);
```

- Lazy formatter loading in `lib/formatters/index.mjs`:

```js
get json() {
	return import('./jsonFormatter.mjs').then((m) => m.default);
}
```

- CLI entrypoint behavior in `bin/stylelint.mjs`:

```js
import cli from '../lib/cli.mjs';
cli(process.argv.slice(2));
```

Execution implication:
- Even though these files are outside the deterministic 3-file batch set, workers implementing compatibility layers for the planned files must not break these runtime behaviors.

## Known Pitfalls

- The deterministic inventory is incomplete. Do not infer that the total migration surface is only the 3 planned files.
- `symbol-index.json` is empty. Lack of symbol data is not evidence that there are no exported contracts to preserve.
- `types/stylelint/index.d.ts` is high-risk because it is a large compatibility contract, not because it contains runtime logic. Treat it as behavior documentation for the API boundary.
- `types/stylelint/type-test.ts` contains dynamic `import()` and CommonJS `require()` on purpose. Do not rewrite away those scenarios.
- `lib/utils/__tests__/fixtures/index.js` is an empty fixture. Do not "clean it up" by adding content.
- The target root in the provided context is `experiemtns/stylint/migrated`. Use that exact root unless the orchestrator explicitly corrects it.
- No `reference_path` was provided. Do not invent target-project conventions beyond the provided Rust style guide and the recipe constraints.

## Verification Hooks For Execution

- Required target commands after execution:
  - `cargo build`
  - `cargo test`
  - `cargo clippy --all-targets --all-features -- -D warnings`
- Recipe-provided optional checks:
  - `bash verify/api-contract.sh`
  - `python3 verify/smoke.py`
- For this plan, execution should additionally verify:
  - public API facade parity for `.lint`, `.rules`, `.formatters`, `.createPlugin`, `.resolveConfig`, `.utils`, `.reference`
  - CommonJS and dynamic-import compatibility
  - autofix edit-info preservation
  - readonly/reference-object behavior for shorthand property metadata

## Constraints On What Execution Must Not Do

- Do not reorder batches.
- Do not downgrade risk tiers.
- Do not remove CommonJS compatibility from the public API facade.
- Do not replace lazy rule/formatter loading with eager loading unless a compatibility layer preserves the same observable behavior.
- Do not drop plugin support, shareable config support, custom syntax support, autofix, or embedded-style extraction.
- Do not collapse test fixtures into mocked data where filesystem/module-loading behavior matters.
- Do not change empty fixtures into non-empty files.
- Do not silently fix the target-root spelling in artifact outputs.
- Do not treat missing symbol-index data as permission to simplify the public API.

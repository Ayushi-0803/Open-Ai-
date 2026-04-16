# Python Style Guide

This document is the canonical Python style guide for this repository.

## 1. Baseline Rules

- Use 4 spaces per indentation level.
- Use spaces, never tabs.
- Target a maximum line width of 80 characters unless a narrow exception makes a
  longer line materially clearer.
- Do not use semicolons to join statements.
- Prefer implicit line joining inside parentheses, brackets, and braces over
  backslash continuations.
- Avoid trailing whitespace.
- Keep vertical whitespace intentional; use blank lines to separate concepts, not
  to create noise.

## 2. Imports And Module Structure

### Imports

- Keep imports at the top of the file, after the module docstring.
- Group imports in this order:
  - `from __future__` imports
  - standard library imports
  - third-party imports
  - repository-local imports
- Keep one import per line, except concise imports from `typing` or
  `collections.abc`.
- Prefer absolute imports over relative imports.
- Import modules and packages rather than reaching directly for many leaf
  symbols, unless a direct import materially improves readability.
- Remove unused imports promptly.

### Modules

- Use `lower_with_under.py` names for Python modules.
- Keep related top-level functions and classes together in one module.
- Add a module docstring when the file defines production code or exported
  behavior.
- Keep executable entrypoint logic under `if __name__ == "__main__":`.

## 3. Naming

### Casing

- Use `lower_with_under` for modules, packages, functions, methods, variables,
  and parameters.
- Use `CapWords` for classes.
- Use `UPPER_CASE_WITH_UNDERSCORES` for constants.
- Use exception names ending in `Error`.

### Naming quality

- Prefer descriptive names over abbreviations.
- Avoid single-letter names outside short loops, comprehensions, mathematical
  notation, or common exception/file-handle conventions like `e` and `f`.
- Avoid names that redundantly encode the type, such as `user_list` or
  `id_to_name_dict`, unless the distinction is genuinely useful.
- Use a single leading underscore for internal helpers and internal attributes.
- Avoid double-underscore name mangling unless it is genuinely required.

## 4. Formatting And Layout

### General formatting

- Do not vertically align tokens across lines.
- Use trailing commas in multiline literals, imports, calls, and signatures when
  it improves diffs and formatting stability.
- Break long signatures one parameter per line.
- Align closing brackets with the opening statement, not with visual alignment.
- Prefer guard clauses and early returns to deep nesting.

### Statements and expressions

- Keep to one statement per line.
- Use conditional expressions sparingly and only when both branches stay simple.
- Keep comprehensions readable; switch to a loop once branching or side effects
  get nontrivial.
- Prefer named functions over complex lambdas.

## 5. Docstrings And Comments

### Docstrings

- Use triple double quotes for all docstrings.
- Add docstrings for public modules, public APIs, and non-obvious functions or
  classes.
- Start docstrings with a one-line summary sentence.
- For functions and methods, document arguments, return values, raised
  exceptions, and side effects when they matter to callers.
- Keep implementation detail out of docstrings unless it affects how callers use
  the API.

### Comments

- Use comments to explain intent, invariants, edge cases, and tradeoffs.
- Do not write comments that merely restate the code.
- Keep inline comments rare and precise.
- Use `TODO:` comments only for bounded follow-up work, and include a stable
  issue or context reference when possible.

## 6. Typing And APIs

### Type annotations

- Add type annotations to public functions, methods, and important module-level
  values.
- Use annotations to clarify code that is hard to understand or prone to type
  mistakes.
- Prefer modern built-in generic syntax such as `list[str]` and `dict[str, int]`
  when supported by the project runtime.
- Use explicit `X | None` for nullable values.
- Do not add legacy type comments in new code.

### API design

- Keep public APIs explicit and unsurprising.
- Prefer plain functions and simple classes over framework-like helper layers.
- Use properties only when attribute-style access is genuinely the clearest API.
- Do not hide expensive work behind a trivial-looking accessor.

## 7. Error Handling And Resource Management

### Exceptions

- Raise built-in exceptions when they express the failure clearly.
- Define custom exceptions only when callers need a stable, domain-specific
  error.
- Never use bare `except:`.
- Catch broad exceptions only to re-raise, translate, log and fail safely, or
  establish a deliberate isolation boundary.
- Do not use `assert` for runtime data validation or essential control flow.

### Resources

- Use `with` for files, sockets, locks, database handles, and similar stateful
  resources whenever possible.
- Make resource ownership and cleanup obvious.
- If a resource cannot be managed with a context manager, document its lifetime
  expectations clearly.

## 8. Testing

- Name tests after observable behavior.
- Prefer deterministic tests over tests that depend on time, randomness, network
  state, or process-global state.
- Cover success, failure, and edge cases.
- Keep test setup local and readable.
- Use plain `assert` freely in pytest-style tests.

## 9. Review Checklist

- Is the code formatted consistently and within the line-length policy?
- Are imports absolute, grouped correctly, and free of dead entries?
- Are names descriptive and conventionally cased?
- Are public interfaces typed and documented where needed?
- Are exceptions specific and resource lifetimes explicit?
- Is the control flow straightforward to follow?

# Code Formatting and Naming

This section defines the required formatting baseline and naming conventions for
Python code in this repository.

## Formatting Baseline

- Use 4 spaces per indentation level.
- Never use tabs for indentation.
- Keep lines at or under 80 characters unless an allowed exception is clearly
  more readable.
- Prefer implicit line joining inside parentheses, brackets, and braces.
- Do not use backslashes for ordinary line continuation.
- Avoid trailing whitespace.
- Do not align tokens vertically across multiple lines.

## Imports

- Put imports at the top of the file after the module docstring.
- Group imports in this order:
  - `from __future__` imports
  - standard library
  - third-party
  - local repository imports
- Keep imports lexicographically ordered within a group when practical.
- Use one import per line, except concise imports from `typing` and
  `collections.abc`.
- Prefer absolute imports.

Example:

```python
from __future__ import annotations

import dataclasses
import pathlib
from collections.abc import Iterable, Sequence

from pydantic import BaseModel

from myproject.runtime import state
from myproject.runtime.handlers import load_handler
```

## Whitespace and layout

- Use a single space around assignments, comparisons, and boolean operators.
- Do not add spaces inside parentheses, brackets, or braces.
- Do not add spaces before call parentheses or subscription brackets.
- Keep one logical statement per line.
- Use blank lines to separate major sections, not every small block.

## Naming Conventions

### Standard casing

- `lower_with_under` for modules, packages, functions, methods, local variables,
  attributes, and parameters.
- `CapWords` for classes.
- `UPPER_CASE_WITH_UNDERSCORES` for constants.
- `Error` suffix for exception classes.

### Good names

- Prefer names that communicate meaning, not storage shape.
- Avoid vague names such as `data`, `obj`, `thing`, `helper`, or `manager`
  unless the surrounding scope makes the meaning obvious.
- Avoid abbreviations unless they are standard in the domain.
- Keep boolean names readable in conditions: `is_ready`, `has_errors`,
  `should_retry`.

### Internal names

- Use a single leading underscore for module-private helpers and internal
  attributes.
- Avoid double-underscore name mangling by default.

### File naming

- Name Python files with `lower_with_under.py`.
- Never use dashes in module or package names.

## Function and class layout

- Keep short functions compact.
- Break long function signatures so each parameter has its own line.
- Keep decorators directly above the function or class they modify.
- Prefer smaller helper functions over large nested blocks.

Example:

```python
def build_report(
    records: Sequence[Record],
    include_archived: bool,
    output_dir: pathlib.Path,
) -> Report:
    if not records:
        raise ValueError("records must not be empty")

    return Report(records, include_archived=include_archived, output_dir=output_dir)
```

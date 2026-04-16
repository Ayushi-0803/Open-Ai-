# Typing and Docstrings

Typing and documentation should make Python code easier to use without forcing a
reader to reverse-engineer behavior from implementation details.

## Type annotations

- Annotate public functions, methods, and important module-level constants or
  variables.
- Add annotations to internal code when type information improves readability or
  catches real classes of mistakes.
- Prefer built-in generic syntax such as `list[str]`, `dict[str, int]`, and
  `tuple[int, ...]` when the supported runtime allows it.
- Use explicit `X | None` for nullable values.
- Do not add new `# type:` comments in source code.
- Use annotated assignments when inference is unclear.

Example:

```python
def load_users(path: pathlib.Path) -> list[User]:
    users: list[User] = []
    ...
    return users
```

## Type aliases

- Use `CapWords` for public aliases.
- Use a leading underscore for module-private aliases.
- Introduce aliases when a repeated type is too complex to read inline.

Example:

```python
from typing import TypeAlias

UserRow: TypeAlias = tuple[str, int, bool]
```

## Forward references and circularity

- Prefer `from __future__ import annotations` when it simplifies forward
  references.
- Treat typing-driven circular imports as a design smell and refactor when
  practical.
- Use `if TYPE_CHECKING:` sparingly.

## Docstring baseline

- Use `"""triple double quotes"""`.
- Start with a one-line summary sentence ending in punctuation.
- Use a blank line before longer explanatory text.
- Keep the summary caller-focused rather than implementation-focused.

## Function docstrings

- Public and non-obvious functions should have docstrings.
- Document the calling contract, return value, raised exceptions, and meaningful
  side effects.
- Use sections such as `Args:`, `Returns:`, and `Raises:` when they add value.
- Omit sections that only repeat obvious information from a clear signature.

Example:

```python
def fetch_config(path: pathlib.Path) -> Config:
    """Loads application configuration from disk.

    Args:
        path: The configuration file location.

    Returns:
        The parsed configuration object.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file contents are invalid.
    """
```

## Class and module docstrings

- Production modules should start with a docstring describing their purpose.
- Public classes should have a docstring that describes what the instance
  represents.
- Document public attributes when they are part of the class contract.
- Test-module docstrings are optional unless they need setup or execution notes.

## Comments vs docstrings

- Use docstrings for caller-facing contracts.
- Use comments for implementation notes, invariants, and local reasoning.
- Do not move implementation commentary into docstrings unless it affects API
  usage.

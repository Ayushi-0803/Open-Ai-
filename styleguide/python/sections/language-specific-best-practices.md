# Language-Specific Best Practices

Python is flexible enough to make both good and bad patterns look easy. This
section captures the idioms that should shape everyday implementation work.

## Imports and package boundaries

- Prefer absolute imports so the origin of a symbol is obvious.
- Import modules when that keeps ownership of names clearer than importing many
  leaf symbols.
- Keep package boundaries stable; avoid import tricks that depend on incidental
  `sys.path` behavior.

## Control flow

- Prefer straightforward `if`, `for`, and helper functions over compressed
  one-liners.
- Use guard clauses to keep the happy path left-aligned.
- Use comprehensions for simple transformations, not for multi-step business
  logic.
- Prefer named local functions or ordinary functions over dense lambdas.

## Functions and APIs

- Keep function signatures explicit.
- Use keyword arguments for parameters whose meaning is not obvious positionally.
- Return values should have stable shape and semantics.
- Prefer a small number of focused functions over large multifunction helpers.

## Classes and data modeling

- Use classes when state and behavior belong together.
- Prefer dataclasses or small explicit classes over unstructured dictionaries for
  domain objects with stable fields.
- Use enums instead of booleans when there are multiple meaningful modes.
- Keep invariants close to construction time.

## Properties and access patterns

- Use `@property` only for cheap, unsurprising access.
- Do not hide network calls, disk access, heavy computation, or mutation behind
  property access.
- Prefer methods when the operation has meaningful cost or side effects.

## Typing

- Annotate public APIs and important internal seams.
- Add annotations where they reduce ambiguity or prevent recurrent mistakes.
- Prefer modern syntax such as `str | None` over older `Optional[str]` when the
  supported runtime allows it.
- Use type aliases for complex repeated types.

## Resource management

- Use context managers for closeable resources.
- Keep the lifetime of files, sockets, locks, and database connections narrow and
  explicit.
- If a resource spans multiple layers, make ownership clear in the API.

## Logging

- Use structured, specific log messages.
- Prefer lazy logging argument interpolation over preformatted strings.
- Make log messages match the actual failure or state transition.

## Testing

- Write tests against public behavior.
- Prefer fixtures and builders that keep setup obvious.
- Avoid hidden shared mutable state between tests.
- Keep tests deterministic and isolated.

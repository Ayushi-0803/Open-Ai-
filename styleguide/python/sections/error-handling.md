# Error Handling

Python makes it easy to ignore failure modes. This section defines how errors
should be surfaced and handled in this codebase.

## Core Rules

- Use exceptions for exceptional conditions, not silent sentinel values.
- Raise built-in exception types when they express the problem accurately.
- Introduce custom exceptions only when callers need to distinguish domain
  failures reliably.
- Never use bare `except:`.
- Do not catch `Exception` unless you are re-raising, translating, logging at a
  boundary, or protecting an isolation point such as a worker loop.

## Validation and assertions

- Validate inputs with ordinary conditionals and explicit exceptions.
- Do not rely on `assert` for runtime preconditions or critical application
  logic.
- Use `assert` in tests and for internal invariants that are not required for
  normal program correctness.

Prefer:

```python
def connect(minimum_port: int) -> int:
    if minimum_port < 1024:
        raise ValueError("minimum_port must be at least 1024")
    return _connect(minimum_port)
```

Avoid:

```python
def connect(minimum_port: int) -> int:
    assert minimum_port >= 1024
    return _connect(minimum_port)
```

## Exception design

- End custom exception names with `Error`.
- Inherit from the most specific useful built-in base class.
- Avoid repetitive names such as `storage.StorageError`.
- Keep exception hierarchies shallow unless callers genuinely need more detail.

## Raising and propagating

- Raise errors as close as possible to the actual failure.
- Preserve the original exception when the lower-level failure remains useful.
- Add context when crossing I/O, parsing, persistence, or network boundaries.
- Keep error messages specific and mechanically searchable.

Prefer:

```python
raise ValueError(f"invalid retry_count: {retry_count}")
```

Over:

```python
raise ValueError("something went wrong")
```

## Logging and recovery

- Log at the boundary where an error becomes operationally relevant.
- Avoid logging and re-raising at many layers unless the duplication is
  intentional.
- Distinguish expected operational failures from programmer mistakes.
- Retry only for clearly transient failures.

## Resource cleanup

- Use `with` statements for files, sockets, and similar resources.
- Ensure partial failures still leave resources in a safe state.
- Prefer `finally` only when a context manager is not the better fit.

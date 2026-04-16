# Common Pitfalls and Gotchas

This section highlights the failure modes and review comments that show up most
often in Python code.

## Mutable defaults

- Never use mutable objects such as `[]`, `{}`, or `set()` as default argument
  values.
- Use `None` and create the mutable value inside the function instead.

Bad:

```python
def add_tag(tag: str, tags: list[str] = []) -> list[str]:
    tags.append(tag)
    return tags
```

Better:

```python
def add_tag(tag: str, tags: list[str] | None = None) -> list[str]:
    if tags is None:
        tags = []
    tags.append(tag)
    return tags
```

## Broad exception handling

- Avoid catching exceptions you cannot handle meaningfully.
- Do not suppress failures silently.
- Catch the narrowest useful exception type.

## Hidden import behavior

- Do not depend on implicit relative imports or ambient `sys.path` quirks.
- Prefer absolute package paths so imports are stable across environments.

## Overusing comprehensions and lambdas

- Do not force complex branching, mutation, or side effects into a comprehension.
- Switch to a regular loop when the logic stops being immediately readable.
- Prefer a named helper over a lambda with tricky control flow.

## Weak names

- Avoid names that encode too little meaning, especially in broad scopes.
- Rename temporary values once they persist beyond a very local block.

## Resource leaks

- Do not rely on object destruction to close files, sockets, or other handles.
- Use context managers and keep resource ownership obvious.

## Misusing properties

- Do not hide expensive work, mutation, or I/O behind attribute access.
- If an operation can fail or has cost, prefer a method.

## Type drift

- Avoid leaving public interfaces untyped while internal helper code becomes more
  complex.
- Do not use `Any` as an easy escape hatch unless the flexibility is deliberate.

## TODO sprawl

- Avoid anonymous TODOs with no issue, owner context, or trigger condition.
- Write TODOs so a later reader can tell when and why the code should change.

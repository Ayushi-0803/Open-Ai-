# Language-Specific Best Practices

Rust rewards code that makes ownership, invariants, and control flow explicit. This section captures the idioms that should shape everyday implementation work.

## Ownership and Borrowing

- Borrow when the callee does not need ownership.
- Accept `&str` instead of `&String`, `&[T]` instead of `&Vec<T>`, and `&Path` or `AsRef<Path>` instead of `&PathBuf` when possible.
- Take ownership only when you must consume, transform, or store the value.
- Keep borrow scopes tight to reduce borrow-checker friction and make mutation easier to reason about.
- Avoid cloning to silence compiler errors unless the clone is clearly the right ownership boundary.

Prefer:

```rust
fn parse_name(input: &str) -> Result<Name, ParseError> {
    // ...
}
```

Avoid:

```rust
fn parse_name(input: &String) -> Result<Name, ParseError> {
    // ...
}
```

## Model Invariants In Types

- Use enums to represent meaningful state machines.
- Use newtypes when raw primitives are too easy to misuse.
- Use dedicated structs instead of tuples when fields have distinct meaning.
- Prevent invalid combinations at construction time instead of checking repeatedly later.

Prefer:

```rust
pub enum JobState {
    Queued,
    Running { started_at: Instant },
    Finished { exit_code: i32 },
}
```

Over:

```rust
pub struct JobState {
    running: bool,
    started_at: Option<Instant>,
    exit_code: Option<i32>,
}
```

## Traits, Generics, and Dynamic Dispatch

- Use generics when the implementation benefits from static dispatch or caller flexibility.
- Use trait objects when they simplify APIs and the indirection is acceptable.
- Do not parameterize everything by default.
- Keep bounds readable; move noisy constraints into `where` clauses.
- Prefer associated types when they communicate a fixed relationship better than extra generic parameters.

## API Design

- Make the easy path the correct path.
- Keep constructors explicit about required inputs.
- Use builders when optional parameters would otherwise produce unreadable constructors.
- Return borrowed data when possible and owned data when necessary.
- Keep public APIs smaller than internal APIs.

## Pattern Matching and Control Flow

- Prefer `match` when exhaustiveness matters.
- Prefer `if let` or `let ... else` for focused extraction of one pattern.
- Use guard clauses and early returns to keep the happy path left-aligned.
- Avoid deeply nested control flow when a small helper function would clarify intent.

Example:

```rust
let Some(token) = maybe_token else {
    return Err(AuthError::MissingToken);
};
```

## Iterators and Collections

- Prefer iterator adapters when they improve clarity without obscuring control flow.
- Use a simple `for` loop when side effects, branching, or mutation are central.
- Avoid collecting into temporary containers unless the materialized collection is actually needed.
- Choose collection types based on semantics and access patterns.

## Async Rust

- Keep `.await` points visible and intentional.
- Avoid borrowing data across `.await` unless lifetimes are obviously sound and readable.
- Do not hold mutex guards across `.await`.
- Make cancellation behavior explicit for long-running tasks, streams, and background workers.
- Prefer structured concurrency and explicit shutdown paths for spawned tasks.

## Unsafe Code

- Avoid `unsafe` unless a safe alternative is demonstrably insufficient.
- Keep `unsafe` blocks as small as possible.
- Document the invariants that make the `unsafe` operation valid.
- Wrap `unsafe` internals in a safe API that enforces those invariants.

Required pattern:

```rust
// SAFETY: `ptr` originates from a valid allocation of `len` initialized bytes,
// and this function never reads beyond that range.
unsafe { std::slice::from_raw_parts(ptr, len) }
```

## Testing

- Test behavior, not incidental implementation structure.
- Use table-driven tests when multiple inputs map to the same rule.
- Keep integration tests focused on public behavior.
- Prefer deterministic fixtures over hidden global setup.
- Validate error paths and edge cases, not just success paths.

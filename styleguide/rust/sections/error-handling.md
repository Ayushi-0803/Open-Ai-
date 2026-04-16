# Error Handling

Rust makes failure explicit. This section defines how recoverable and unrecoverable errors should be expressed in this codebase.

## Core Rules

- Use `Result<T, E>` for recoverable errors.
- Use `Option<T>` only when absence is expected and not itself an error.
- Use `panic!` only for broken invariants, programmer errors, unreachable states, or startup failures where the process cannot continue safely.
- Prefer `?` for propagation.
- Add context where an error crosses a subsystem boundary.

## Designing Error Types

### Application code

- Use domain-specific error enums.
- Include enough structure to drive logging, metrics, retries, and user-facing behavior.
- Preserve the source error when it helps diagnosis.

Example:

```rust
#[derive(Debug, thiserror::Error)]
pub enum SyncError {
    #[error("config is invalid: {0}")]
    InvalidConfig(String),
    #[error("database operation failed")]
    Database {
        #[source]
        source: sqlx::Error,
    },
    #[error("upstream request timed out after {timeout_ms}ms")]
    Timeout { timeout_ms: u64 },
}
```

### Library code

- Expose stable, intentional error variants.
- Avoid embedding incidental implementation detail in public contracts.
- Prefer typed errors over raw strings for anything callers may need to inspect.

## Propagation and Context

- Propagate leaf errors with `?` when the current layer adds no useful context.
- Add context at boundaries such as file I/O, parsing, RPC, database access, task execution, and external integrations.
- Keep context messages specific enough to identify the failed operation.

Prefer:

```rust
let config = std::fs::read_to_string(path)
    .map_err(|err| LoadError::ReadConfig {
        path: path.to_path_buf(),
        source: err,
    })?;
```

Over:

```rust
let config = std::fs::read_to_string(path)?;
```

when the file path or operation matters for diagnosis.

## `unwrap`, `expect`, and Assertions

- Do not use `unwrap` in ordinary production paths.
- Use `expect` only when crashing is intentional and the message explains the invariant.
- Prefer `debug_assert!` for expensive checks that are mainly for developer validation.
- Prefer `assert!` when violating the condition would make continued execution unsound or invalid for tests.

Good:

```rust
let runtime = tokio::runtime::Runtime::new()
    .expect("failed to create Tokio runtime during process startup");
```

Bad:

```rust
let runtime = tokio::runtime::Runtime::new().unwrap();
```

## Converting Between Error Layers

- Use `From` or `#[from]` when the conversion is straightforward and semantically correct.
- Do not erase detail too early.
- Convert low-level errors into domain errors at the boundary where the domain meaning becomes clear.

## Logging and User Messages

- Do not rely on error strings as the only diagnostic surface.
- Attach structured fields in logs when possible.
- Keep internal diagnostic detail separate from user-facing copy if the audience differs.
- Ensure error messages are actionable for operators and understandable for callers.

## Retriable vs Terminal Errors

- Distinguish transient failures from permanent ones when retry logic exists.
- Avoid blind retries for validation or invariant failures.
- Propagate timeout, overload, and temporary network conditions in a way that enables policy decisions.

## Async and Task Errors

- Join handles and background tasks should surface failures deliberately.
- Avoid silently dropping task results.
- Distinguish task cancellation, timeout, and execution failure.
- Preserve enough context to identify which task failed and why.

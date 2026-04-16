# Code Formatting and Naming

This section covers the required formatting baseline and naming conventions for Rust code in this repository.

## Formatting Baseline

- Use `rustfmt` as the source of truth for mechanical formatting.
- Use 4 spaces per indentation level.
- Never use tabs for indentation.
- Keep lines at or under 100 characters unless a longer line is materially clearer and formatter output makes shortening unreasonable.
- Prefer block indentation over visual alignment.
- Use trailing commas in multiline lists.
- Avoid trailing whitespace.
- Use zero or one blank line between related items; do not create vertical whitespace noise.

## Imports

- Keep imports grouped by source:
  - standard library
  - third-party crates
  - local crate imports
- Keep imports deterministic and easy to scan.
- Remove dead imports rather than leaving them for later cleanup.
- Prefer concise grouped imports over repetitive single-item lines when readability improves.

Example:

```rust
use std::path::{Path, PathBuf};
use std::sync::Arc;

use serde::Deserialize;

use crate::config::Settings;
use crate::runtime::Handle;
```

## Attributes

- Put each attribute on its own line.
- Prefer outer attributes.
- Keep long attribute argument lists multiline with one item per line when they no longer read cleanly inline.
- Preserve `derive` ordering when it matters semantically.

Example:

```rust
#[derive(Debug, Clone, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TaskState {
    Pending,
    Running,
    Completed,
}
```

## Comments and Documentation

- Prefer `//` comments over `/* ... */`.
- Prefer `///` docs over block doc comments.
- Write comments to explain intent, invariants, edge cases, or non-obvious tradeoffs.
- Do not write comments that mirror the code token-by-token.
- Keep comment lines compact and readable.

Good:

```rust
// Keep the previous generation alive until all readers have swapped over.
swap_generations();
```

Bad:

```rust
// Call swap_generations here.
swap_generations();
```

## Naming Conventions

### Use the standard Rust casing model

- `snake_case` for functions, methods, modules, variables, and fields.
- `UpperCamelCase` for structs, enums, traits, and enum variants.
- `SCREAMING_SNAKE_CASE` for constants and statics.
- Short lowercase names for lifetimes, typically `'a`, `'ctx`, `'src`.

### Prefer semantic names

- Name values after meaning, not implementation detail.
- Prefer `request_deadline` over `ts`.
- Prefer `retry_policy` over `config2`.
- Prefer `user_id` over `uid` unless `uid` is a domain-standard term.

### Constructor and conversion names

- Use `new` for the primary constructor.
- Use `default` only when `Default` is genuinely correct and unsurprising.
- Use `from_*` or `From` for infallible conversions.
- Use `try_from_*` or `TryFrom` for fallible conversions.
- Use `as_*` for borrowed or cheap views.
- Use `into_*` for consuming conversions.
- Use `to_*` for non-consuming conversions that may allocate.

### Boolean names

- Prefer names that read naturally in conditions: `is_ready`, `has_capacity`, `can_retry`, `should_flush`.
- Avoid ambiguous booleans like `flag`, `status`, or `check`.

### Trait names

- Use trait names that express capability or role: `Encoder`, `Cache`, `Retryable`.
- Avoid vague trait names like `Helper`, `Manager`, or `Utils`.

## Layout Guidance

### Functions

- Keep small pure functions compact.
- Break function signatures across lines once arguments or bounds become hard to scan.
- Prefer a `where` clause when bounds become long or numerous.

Example:

```rust
pub fn build_client<T>(
    config: &ClientConfig,
    transport: T,
) -> Client<T>
where
    T: Transport + Send + Sync + 'static,
{
    Client { config: config.clone(), transport }
}
```

### Match expressions

- Use a trailing comma for each multiline arm.
- Expand complex match arms into blocks.
- Keep simple arms concise.

Example:

```rust
match event {
    Event::Created(id) => handle_create(id),
    Event::Deleted(id) => {
        audit_delete(id);
        remove(id)
    }
}
```

### Literals and builders

- Keep small literals inline.
- Expand structs, arrays, and chained builders vertically once arguments become nontrivial.

Example:

```rust
let request = Request {
    tenant_id,
    retry_policy: RetryPolicy::bounded(3),
    timeout: Duration::from_secs(2),
};
```

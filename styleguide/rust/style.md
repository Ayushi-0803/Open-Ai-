# Rust Style Guide

This document is the canonical Rust style guide for this repository.

## 1. Baseline Rules

- Format code with `rustfmt`.
- Use 4-space indentation.
- Use spaces, never tabs.
- Target a maximum line width of 100 characters.
- Prefer block indentation over visual indentation.
- Use trailing commas in multiline comma-separated constructs.
- Avoid trailing whitespace.
- Separate related statements with at most one blank line.

## 2. Naming And API Shape

### General naming

- Modules, functions, variables, and lifetime parameters should use `snake_case`.
- Types, traits, and enum variants should use `UpperCamelCase`.
- Constants and statics should use `SCREAMING_SNAKE_CASE`.
- Type parameters should be short, conventional, and meaningful. Prefer `T`, `E`, `K`, `V`, `S`, or a domain-specific name when it improves clarity.
- Avoid abbreviations unless they are universally understood in Rust or in the domain.

### Function and method naming

- Use verbs for side-effecting functions: `parse_config`, `write_snapshot`, `refresh_cache`.
- Use noun-like names for accessors and pure queries: `len`, `capacity`, `status`, `config`.
- Use `new` for the primary constructor.
- Use `with_*` for builder-style value customization.
- Use `into_*` for consuming conversions.
- Use `as_*` for cheap borrowed views.
- Use `to_*` for potentially allocating conversions that keep the original value.

### Traits and types

- Use trait names that describe capabilities: `Serialize`, `Display`, `Fetcher`, `RetryPolicy`.
- Avoid stutter: prefer `http::Client` over `http::HttpClient` unless the extra word disambiguates something real.
- Use domain terms consistently. If the project says "tenant", do not alternate with "account" or "workspace" unless they are distinct concepts.

## 3. Formatting Conventions

### Imports

- Group imports logically.
- Prefer one `use` tree per module area rather than scattered single-item imports.
- Keep imports stable and easy to scan.
- Remove unused imports promptly.

Example:

```rust
use std::collections::{BTreeMap, HashSet};
use std::sync::Arc;

use tokio::sync::RwLock;

use crate::config::AppConfig;
use crate::service::TaskRunner;
```

### Attributes and comments

- Put each attribute on its own line.
- Prefer outer doc comments (`///`) over block doc comments.
- Put doc comments before attributes only when required by syntax; otherwise keep docs directly attached to the item they describe.
- Prefer line comments over block comments.
- Write comments as complete sentences when they explain behavior, invariants, or tradeoffs.
- Do not restate what the code already makes obvious.

### Expressions

- Prefer multiline formatting once a construct stops being obviously readable on one line.
- Keep closures short when used inline; move larger logic into a named function or block.
- Prefer `match` over dense nested `if` / `else if` chains when multiple structured cases exist.
- Use early returns and guard clauses to reduce nesting.

### Structs, enums, and literals

- Use trailing commas for multiline struct definitions, enum variants, match arms, arrays, and argument lists.
- Keep small literals on one line when they remain easy to read.
- Expand literals vertically once fields become nontrivial.

## 4. Language-Specific Best Practices

### Ownership and borrowing

- Prefer borrowing over cloning when ownership transfer is unnecessary.
- Accept `&str`, `&[T]`, and trait bounds like `AsRef<Path>` when callers should not need to allocate.
- Take ownership when the function naturally consumes the value or must store it.
- Keep mutable borrows short and localized.

### Data modeling

- Use structs and enums to make invalid states hard to represent.
- Prefer enums over booleans when there are multiple semantic modes.
- Encode invariants in types where practical.
- Avoid exposing raw tuples for data with named meaning; use a struct.

### Traits and generics

- Use generics when the caller benefits from flexibility.
- Prefer trait objects when dynamic dispatch simplifies the API and the overhead is acceptable.
- Keep trait bounds close to where they matter. If bounds become noisy, move them into a `where` clause.
- Do not over-generalize prematurely.

### Builders and constructors

- Use constructors for required fields.
- Use builders for complex configuration with many optional fields.
- Validate invariants before constructing a publicly visible value.
- Keep builder defaults explicit and unsurprising.

### Testing

- Keep unit tests near the code they verify when practical.
- Name tests after behavior, not implementation details.
- Cover success, edge, and failure cases.
- Prefer deterministic tests; avoid time, randomness, and global state unless explicitly controlled.

## 5. Error Handling

### General rules

- Prefer `Result` over panics for recoverable failures.
- Reserve `panic!`, `unwrap`, and `expect` for invariant violations, impossible states, tests, prototypes, or process-fatal startup failures.
- Add context when propagating errors across abstraction boundaries.
- Use domain-specific error types for library code and externally consumed components.

### `unwrap` and `expect`

- Avoid `unwrap` in production paths.
- Prefer `expect` over `unwrap` when a crash is intentional and the message materially improves debugging.
- Keep `expect` messages specific and actionable.

Bad:

```rust
let config = std::fs::read_to_string(path).unwrap();
```

Better:

```rust
let config = std::fs::read_to_string(path)
    .expect("failed to read application config during startup");
```

### Error types

- Use enums for domain errors.
- Preserve source errors when they add debugging value.
- Avoid leaking low-level implementation details through public error APIs unless those details are part of the contract.
- Keep user-facing messages separate from internal diagnostic context where needed.

### Propagation

- Prefer `?` for straightforward propagation.
- Add context at boundaries such as I/O, parsing, RPC, DB, or task orchestration layers.
- Return early on errors rather than burying control flow in deep nesting.

## 6. Common Pitfalls And Gotchas

### Ownership surprises

- Watch for accidental clones introduced to satisfy the borrow checker.
- Avoid holding references across `.await` unless the borrowed data clearly lives long enough.
- Do not return references to temporary values.

### Concurrency issues

- Do not hold a mutex lock across expensive work or `.await`.
- Prefer message passing or scoped ownership over shared mutable state.
- Keep async functions cancellation-safe where possible.

### Collection misuse

- Do not allocate `String` or `Vec` values when a borrowed form is sufficient.
- Choose collection types based on access patterns, not habit.
- Avoid repeated linear scans in hot paths if indexing or precomputation is more appropriate.

### Visibility and API drift

- Default to the narrowest visibility that works.
- Do not make fields `pub` when accessor methods or constructors preserve invariants better.
- Keep public APIs stable and intentional.

## 7. Performance

### General approach

- Start with simple, correct code.
- Optimize only after measuring.
- Prefer algorithmic improvements over micro-optimizations.

### Allocation and copying

- Avoid unnecessary clones and temporary allocations.
- Reuse buffers in tight loops or repeated processing paths.
- Prefer iterators and borrowed views when they reduce copies without harming clarity.

### Async and concurrency

- Keep spawned tasks purposeful and bounded.
- Avoid over-parallelizing small workloads.
- Be deliberate about synchronization primitives and lock granularity.

### Data structures

- Choose `Vec` by default for ordered contiguous data.
- Use `HashMap` for fast key lookup, `BTreeMap` when ordering matters, and specialized structures only when there is a demonstrated need.
- Prefer small, cache-friendly layouts over fragmented designs when performance matters.

## 8. Review Checklist

- Is the code `rustfmt`-clean?
- Are names idiomatic and unambiguous?
- Are ownership and borrowing choices clear?
- Are recoverable failures modeled with `Result`?
- Are panics justified?
- Are comments documenting invariants rather than narrating syntax?
- Are async, locking, and allocation choices reasonable?
- Does the implementation encode important invariants in types?

## 9. Section References

- [Code Formatting and Naming](/Users/thrishul.reddy/Open-Ai-/styleguide/rust/sections/code-formatting-and-naming.md)
- [Language-Specific Best Practices](/Users/thrishul.reddy/Open-Ai-/styleguide/rust/sections/language-specific-best-practices.md)
- [Error Handling](/Users/thrishul.reddy/Open-Ai-/styleguide/rust/sections/error-handling.md)
- [Common Pitfalls and Gotchas](/Users/thrishul.reddy/Open-Ai-/styleguide/rust/sections/common-pitfalls-and-gotchas.md)
- [Performance](/Users/thrishul.reddy/Open-Ai-/styleguide/rust/sections/performance.md)

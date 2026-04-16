# Common Pitfalls and Gotchas

This section highlights failure modes and non-obvious mistakes that frequently appear in Rust code reviews.

## Borrow Checker Workarounds That Hide Design Problems

- Avoid cloning or wrapping everything in `Arc<Mutex<_>>` just to satisfy the borrow checker.
- If ownership feels awkward, reconsider the API boundary or data flow first.
- Break large functions into smaller steps when long-lived borrows create friction.

## Holding Locks Too Long

- Do not hold `Mutex`, `RwLock`, or similar guards across `.await`.
- Avoid doing blocking I/O or expensive computation while holding a lock.
- Copy or extract the needed data, release the guard, then continue the expensive work.

Bad:

```rust
let mut guard = state.lock().await;
let result = client.fetch(&guard.url).await?;
guard.last_value = Some(result);
```

Better:

```rust
let url = {
    let guard = state.lock().await;
    guard.url.clone()
};

let result = client.fetch(&url).await?;

let mut guard = state.lock().await;
guard.last_value = Some(result);
```

## Accidental Allocation and Cloning

- Watch for `to_string`, `to_vec`, `clone`, and `collect` in hot or repeated paths.
- Prefer borrowed inputs and iterator pipelines that do not materialize unnecessary intermediates.
- Measure before complicating the code, but do not ignore obviously repeated allocations.

## Misusing `Option` and `Result`

- Use `Option` for missing data, not for silently swallowing real failure.
- Do not convert a rich error into `None` unless the caller truly does not need to know why it failed.
- Avoid nested `Option<Result<_>>` or `Result<Option<_>>` APIs unless the state space is genuinely required and clearly documented.

## Public API Overexposure

- Default to private fields and functions.
- Avoid making internals `pub` solely to ease tests; restructure the code instead.
- Preserve invariants through constructors, smart constructors, or methods rather than unrestricted field mutation.

## Lifetime and Reference Mistakes

- Do not return references to temporaries.
- Be cautious with self-referential patterns; they are rarely the right choice in safe Rust.
- Prefer owned data or indices/handles when references would outlive the source container awkwardly.

## Async Footguns

- Avoid blocking calls inside async functions unless they are deliberately offloaded.
- Be explicit when spawning detached tasks; hidden fire-and-forget work is a maintenance risk.
- Ensure shutdown paths wait for important background work or cancel it intentionally.

## Panics in Library Code

- Library code should not panic on caller-controlled input.
- Validate inputs and return typed errors instead.
- Treat panic as a last resort for broken internal invariants, not input validation.

## Overusing Clever Abstractions

- Avoid macros, blanket generics, and trait indirection when a straightforward function would be easier to read and maintain.
- Do not chase maximal generic reuse at the cost of debuggability.
- Prefer local clarity over abstract elegance.

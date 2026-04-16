# Performance

Performance guidance should produce faster code without making the codebase fragile or opaque. Optimize deliberately.

## General Rules

- Make code correct first.
- Measure before optimizing.
- Favor improvements that reduce algorithmic complexity, allocations, contention, or unnecessary I/O.
- Reject micro-optimizations that make the code meaningfully harder to understand unless profiling proves they matter.

## Allocation Discipline

- Prefer borrowing over cloning when it keeps ownership straightforward.
- Reuse buffers in repeated or streaming workloads.
- Avoid formatting strings, collecting iterators, or building temporary vectors when a borrowed or streaming path works.
- Reserve capacity when the target size is known or tightly bounded.

Example:

```rust
let mut out = Vec::with_capacity(records.len());
for record in records {
    out.push(transform(record));
}
```

## Choosing Data Structures

- Default to `Vec` for sequential data.
- Use `HashMap` for key lookup when ordering does not matter.
- Use `BTreeMap` or `BTreeSet` when deterministic ordering is part of the behavior.
- Prefer compact representations when data is hot and accessed frequently.

## Iteration and Control Flow

- Use iterator chains for clear transformations.
- Switch to explicit loops when it reduces allocations, improves branching clarity, or avoids awkward closures.
- Avoid repeated scans of the same collection in hot paths when indexing or precomputation is cheaper.

## Strings and Bytes

- Distinguish text from bytes deliberately.
- Avoid converting between `String`, `&str`, `Vec<u8>`, and `&[u8]` more than necessary.
- Prefer byte-oriented APIs when the data is not guaranteed to be UTF-8 text.

## Async and Concurrency Performance

- Do not spawn tasks for trivial work.
- Bound concurrency when work fans out to external services, storage, or CPU-heavy operations.
- Minimize shared mutable state and lock contention.
- Choose synchronization primitives based on access patterns, not familiarity.

## Copying, Moves, and Clones

- Cloning cheap handles like `Arc` is often fine; cloning large owned payloads repeatedly is not.
- Be explicit about large or repeated clones in reviews.
- Prefer moves when values naturally flow forward through the function.

## I/O and Serialization

- Batch small I/O operations when possible.
- Stream large payloads instead of materializing them wholesale.
- Avoid repeated parse/serialize cycles when data can remain in a structured form longer.

## Benchmarking and Profiling

- Benchmark realistic workloads.
- Profile before and after meaningful changes.
- Document non-obvious performance tradeoffs in code comments when the implementation looks more complex than the naive version.

## When Not To Optimize

- Do not replace a readable implementation with a lower-level one based only on intuition.
- Do not optimize cold code without evidence.
- Do not obscure invariants or safety guarantees in pursuit of small wins.

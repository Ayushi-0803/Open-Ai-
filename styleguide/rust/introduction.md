# Rust Style Guide Introduction

This guide defines the expected Rust coding style for this codebase.

It is intentionally opinionated. The default should be to follow standard Rust conventions, rely on `rustfmt` for mechanical formatting, and write code that feels unsurprising to an experienced Rust developer.

## Goals

- Keep code easy to read, review, and maintain.
- Minimize stylistic debate by preferring established Rust community conventions.
- Preserve correctness first, then optimize for ergonomics and performance.
- Favor patterns that work well with the Rust compiler, Clippy, and `rustfmt`.

## Primary Sources

This guide is based on the official Rust style guide and idiomatic Rust practices. When this document and automated tooling disagree, prefer:

1. Correctness.
2. `rustfmt` output for formatting.
3. `clippy` recommendations when they improve clarity or safety.
4. The more conservative, easier-to-read choice.

## How To Use This Guide

- Read [style.md](/Users/thrishul.reddy/Open-Ai-/styleguide/rust/style.md) for the complete policy.
- Use the documents in [sections](/Users/thrishul.reddy/Open-Ai-/styleguide/rust/sections) for topic-specific guidance.
- Treat examples as normative unless there is a stronger reason to preserve readability or API stability.

## Core Principles

### Prefer standard tooling

Run `rustfmt` and keep formatting changes mechanical. Do not hand-format code in ways that fight the formatter.

### Prefer clarity over cleverness

Use explicit, readable code before compact but opaque constructs. Rust gives many expressive tools; use them carefully.

### Make ownership visible

Write APIs and implementations so borrowing, mutation, lifetimes, and error propagation are easy to follow.

### Keep unsafe rare and isolated

Use `unsafe` only when necessary, minimize its scope, and document the invariants it relies on.

### Optimize after measurement

Avoid speculative complexity. Start with simple, correct code and optimize based on profiling, allocation behavior, and real bottlenecks.

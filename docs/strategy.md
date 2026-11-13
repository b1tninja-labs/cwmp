# Strategy

The completeness matrix is [../ROADMAP.md](../ROADMAP.md). This document is *why* the rows
are ordered the way they are, and the rules that order has to respect.

## The constitution

1. **The core is the specification implementation.** `cwmp/` holds codecs, state machines
   and the vocabulary of cwmp. New core code appears when a document defines the
   behaviour, or when an ordering rule with no document earns an explicit convention label.
2. **Sans-IO before sockets.** Anything decidable from data plus a clock is implemented
   without touching a socket, so every timeout, retry and rollover is testable without
   sleeping or networking.
3. **Dependency-free by default.** An exception needs a sentence in README.md explaining why
   the rule was broken, and a floor with no ceiling.
4. **Positioning is correctness and legibility, not throughput.** The incumbents in this
   corner are usually stale, untyped, or welded to a product. This is the implementation that
   says how it knows what it claims.
5. **Every answer carries its provenance.** Verified or cached, which document, refused or
   believed. An answer without provenance is a guess with a confident type.

## The three tiers

| Tier | Home | Contents | Rule |
|---|---|---|---|
| Core | `cwmp/` | codecs, state machines, policy objects | RFC-cited or convention-labelled |
| Apps | `cwmp/apps/` | reusable assemblies that compose core | no new protocol surface |
| Examples | `examples/` | one runnable script per use case | configures; never restates logic |

## Interface grammar

One engine, three drives, never parallel implementations:

- **await** -- the native asyncio surface.
- **blocking** -- a facade owning a private loop, so a call from inside a caller's running
  loop works instead of deadlocking.
- **callback** -- plain callables, no third-party promise type.

## Naming

One string everywhere: the distribution, the import and the console script. A name that
means one thing in the installer, in `import` and on `PATH` is the only arrangement that
cannot surprise anyone, and it is also why this project does not sit one edit away from a
project that already exists.

## Decisions

- **One hardened XML reader (2026-11-13).** `cwmp` does not carry its own XML parser. It declares
  `devicespy` as a runtime dependency, resolved from the sibling checkout until devicespy
  publishes (`pythonpath` and `mypy_path` in `pyproject.toml`, a checkout step in CI), and
  `cwmp.envelope` reads every envelope through `devicespy.xmlsafe.parse`. The standard library
  alone is enough for the parser; the dependency exists to keep one copy of security-critical code.
- **SOAP 1.1, not 1.2.** TR-069 Amendment 6 Corrigendum 1, section 3.5, defines SOAP 1.1 as the
  encoding syntax; a SOAP 1.2 envelope is refused with a reason.

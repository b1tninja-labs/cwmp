# Specification completeness -- and the roadmap it implies

This is the project's north star: every protocol obligation cwmp could plausibly take on,
with an honest status against the code at `HEAD`. It is blunt about gaps on purpose. A
roadmap that overstates its coverage is not a plan, it is marketing.

**The honesty rule:** a row may read `[ok]` only when a named test would fail if the
behaviour regressed. Reading the code and agreeing with it is not enough. That is how
"decoded but never sent" quietly becomes "implemented".

Legend: `[ok]` implemented and pinned by a named test -- `[part]` partial, with what is
missing stated -- `[ ]` not implemented -- `[no]` deliberate non-goal.

Update the affected row in the same commit that changes the behaviour. A row and its test
drift apart within one release, and the document becomes useless exactly when it is needed.

## 1. Obligations

| Obligation | Spec | Status | Where |
|---|---|---|---|
| `envelope.encode_envelope()` | TR-069 Annex 2 | `[ ]` | `tests/test_obligations.py::encode_envelope` |
| `envelope.decode_envelope()` | TR-069 Annex 2 | `[ ]` | `tests/test_obligations.py::decode_envelope` |
| `methods.build_inform()` | TR-069 | `[ ]` | `tests/test_obligations.py::build_inform` |
| `methods.set_parameter_values()` | TR-069 | `[ ]` | `tests/test_obligations.py::set_parameter_values` |
| `session.handle_session()` | TR-069, RFC 9110 | `[ ]` | `tests/test_obligations.py::handle_session` |
| `endpoint.run_inform()` | TR-069 | `[ ]` | `tests/test_obligations.py::run_inform` |
| `datamodel.resolve_path()` | TR-181 | `[ ]` | `tests/test_obligations.py::resolve_path` |
| `datamodel.coerce_value()` | TR-181 | `[ ]` | `tests/test_obligations.py::coerce_value` |
| `auth.digest_challenge()` | RFC 9110 | `[ ]` | `tests/test_obligations.py::digest_challenge` |
| `transfer.build_download()` | TR-069 | `[ ]` | `tests/test_obligations.py::build_download` |

## 2. Milestones

- M1 hardened SOAP envelope codec, with an entity-expansion and depth bomb test
- M2 RPC method classes and fault codes against a captured CPE session
- M3 ACS session engine with Digest auth and keep-alive
- M4 CPE endpoint able to complete a real Inform against the ACS in the same repo
- M5 data model tree with wildcards, instance add and delete
- M6 file transfer and connection request, then publication: 0.1.0

Every milestone is accepted by its rows above flipping to `[ok]` with a named test, not by
the code existing. Coverage in `pyproject.toml` ratchets in the same commit.

## 3. Errata watch

- Outside the RFC series, so there is no errata mechanism to consult: pin the exact TR revision in every docstring and test, and record it in docs/research.md.
- The ACS URL a CPE learns usually arrives from DHCP option 43 or a DHCPv6 vendor option, so leasespy is the natural partner and the two must agree on the encoding.

## 4. Deliberate non-goals

| Non-goal | Status | Revisit when |
|---|---|---|
| a web UI, ticket system or firmware repository: an ACS product composes those, this is the protocol | `[no]` | a named document requires it |
| business provisioning logic beyond the data model | `[no]` | a named document requires it |
| USP transport in the first release, only the seam that will allow it | `[no]` | a named document requires it |

## 5. Open questions

- which TR revision is the baseline, and how the chosen revision is pinned in tests

## 6. Publication checklist

- [ ] every `[ ]` row above either `[ok]` or moved to a named later milestone
- [ ] `docs/research.md` claims re-verified and the dated ones either promoted or deleted
- [ ] interoperability evidence recorded in `docs/` against a non-Python implementation
- [ ] `tools/check_dist.py` proves the wheel ships the fixtures the README promises
- [ ] version 0.1.0 tagged, trusted publisher configured, README badges uncommented

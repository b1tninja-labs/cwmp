# Specification completeness -- and the roadmap it implies

This is the project's north star: every protocol obligation cwmp could plausibly take on,
with an honest status against the code at `HEAD`. It is blunt about gaps on purpose. A
roadmap that overstates its coverage is not a plan, it is marketing.

**The honesty rule:** a row may read `[ok]` only when a named test would fail if the
behaviour regressed. Reading the code and agreeing with it is not enough. That is how
"decoded but never sent" quietly becomes "implemented".

Legend: `[ok]` implemented and pinned by a named test -- `[part]` partial, with what is
missing stated -- `[ ]` not implemented -- `[no]` deliberate non-goal.

A Where cell marked `(to be written)` names the test that will pin the row once it exists; no
such test has been written yet, and the row cannot leave `[ ]` until it has. The Milestone
column places the row on the ladder in section 2, and `-` means it is not placed yet.

Update the affected row in the same commit that changes the behaviour. A row and its test
drift apart within one release, and the document becomes useless exactly when it is needed.

## 1. Obligations

| Obligation | Spec | Status | Where | Milestone |
|---|---|---|---|---|
| `envelope.encode_envelope()` | TR-069 Annex 2 | `[ ]` | `tests/test_obligations.py::test_encode_envelope` (to be written) | M1 |
| `envelope.decode_envelope()` | TR-069 Annex 2 | `[ ]` | `tests/test_obligations.py::test_decode_envelope` (to be written) | M1 |
| `methods.build_inform()` | TR-069 | `[ ]` | `tests/test_obligations.py::test_build_inform` (to be written) | M2 |
| `methods.set_parameter_values()` | TR-069 | `[ ]` | `tests/test_obligations.py::test_set_parameter_values` (to be written) | M2 |
| `session.handle_session()` | TR-069, RFC 9110 | `[ ]` | `tests/test_obligations.py::test_handle_session` (to be written) | M3 |
| `endpoint.run_inform()` | TR-069 | `[ ]` | `tests/test_obligations.py::test_run_inform` (to be written) | M4 |
| `datamodel.resolve_path()` | TR-181 | `[ ]` | `tests/test_obligations.py::test_resolve_path` (to be written) | M5 |
| `datamodel.coerce_value()` | TR-181 | `[ ]` | `tests/test_obligations.py::test_coerce_value` (to be written) | M5 |
| `auth.digest_challenge()` | RFC 7616 sec. 3.3 | `[ ]` | `tests/test_obligations.py::test_digest_challenge` (to be written) | M3 |
| `transfer.build_download()` | TR-069 | `[ ]` | `tests/test_obligations.py::test_build_download` (to be written) | M6 |

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

- TR-069 is outside the RFC series, so there is no errata mechanism to consult: pin the exact TR revision in every docstring and test, and record it in docs/research.md.
- RFC 7616 carries 1 verified erratum, 4495 (Editorial, sec. 3.9.1): the example password is "Circle of Life" with a lower-case o, which matters to anyone reproducing the sec. 3.9.1 example as a test vector.
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

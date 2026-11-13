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
| `envelope.encode_envelope()` | TR-069 Amendment 6 Corrigendum 1 section 3.5, Annex A | `[ ]` | `tests/test_obligations.py::test_encode_envelope` (to be written) | M1 |
| `envelope.decode_envelope()` | TR-069 Amendment 6 Corrigendum 1 section 3.5, Annex A | `[ok]` | `tests/test_envelope.py::test_decode_rpc_request`, `tests/test_envelope.py::test_decode_fault`, `tests/test_envelope.py::test_soap12_envelope_is_refused`, `tests/test_envelope.py::test_internal_entity_declaration_refused` | M1 |
| `methods.build_inform()` | TR-069 | `[ ]` | `tests/test_obligations.py::test_build_inform` (to be written) | M2 |
| `methods.set_parameter_values()` | TR-069 | `[ ]` | `tests/test_obligations.py::test_set_parameter_values` (to be written) | M2 |
| `session.handle_session()` | TR-069, RFC 9110, RFC 6265 | `[ ]` | `tests/test_obligations.py::test_handle_session` (to be written) | M3 |
| `endpoint.run_inform()` | TR-069 | `[ ]` | `tests/test_obligations.py::test_run_inform` (to be written) | M4 |
| `datamodel.resolve_path()` | TR-181 | `[ ]` | `tests/test_obligations.py::test_resolve_path` (to be written) | M5 |
| `datamodel.coerce_value()` | TR-181 | `[ ]` | `tests/test_obligations.py::test_coerce_value` (to be written) | M5 |
| `auth.digest_challenge()` | RFC 7616 sec. 3.3 | `[ ]` | `tests/test_obligations.py::test_digest_challenge` (to be written) | M3 |
| `transfer.build_download()` | TR-069 | `[ ]` | `tests/test_obligations.py::test_build_download` (to be written) | M6 |
| `auth.digest_challenge()` is independent of everything else: do it first after the spine | RFC 7616 sec. 3.3 | `[ ]` | (to be written) | M3 |
| HTTP encoding: POST, Content-Type text/xml, empty POST meaning no more requests; sessions and cookies; Digest and Basic; compression and the 415 case | TR-069 sections 3.4.1 to 3.4.7, RFC 9110, RFC 6265, RFC 7617 | `[ ]` | (to be written) | M3 |
| SOAP rules not yet covered: `type` attribute rule for anySimpleType, `soap-enc:arrayType` arrays with unprefixed members | TR-069 section 3.5 | `[ ]` | (to be written) | M1 |
| `envelope.encode_envelope()` fault encoding: no fault in answer to a response or to a fault | TR-069 section 3.5 | `[ ]` | (to be written) | M1 |
| SOAP headers HoldRequests, SessionTimeout, SupportedCWMPVersions, UseCWMPVersion: semantics beyond decoding (section 3.7.1.3 and the version negotiation) | TR-069 section 3.5 Table 4 | `[ ]` | (to be written) | M3 |
| Inform split in two: DeviceId, Event list and ParameterList; then retry counts and the session retry policy | TR-069 Annex A, section 3.2.1.1 | `[ ]` | (to be written) | M2 |
| fault-code table (CPE 9000 range, ACS 8000 range) as data | TR-069 Annex A.5 | `[ ]` | (to be written) | M2 |
| connection request: HTTP GET with Digest, zero-length response; ACS discovery | TR-069 sections 3.1, 3.2.2 | `[ ]` | (to be written) | M6 |
| `datamodel.resolve_path()` split: path grammar, partial paths ending in a dot, wildcards, instance alias | TR-069 Annex A.2, TR-181 | `[ ]` | (to be written) | M5 |
| TLS policy through `ssl`: TLS 1.2 or later per section 3.3, current spec RFC 9846 | TR-069 section 3.3, RFC 9846 | `[ ]` | (to be written) | M3 |
| fixtures: captures from a CPE or GenieACS under the owner's control, committed with provenance; otherwise envelopes written for the tests from the structure the TR states, never copied | design | `[ ]` | (to be written) | M2 |
| spine repair: SOAP 1.1, section 3.5 and Annex A, current revision and RFC successors recorded in README and rfc-map; the projecthub generator data (`shells/data/naming.py`) still carries "Annex 2" and "SOAP 1.2" | design | `[ ]` | (to be written) | M1 |
| TR-069 data-model XML published in the Broadband Forum's GitHub repositories (BroadbandForum organisation: the `cwmp-data-models` XSDs named in Annex A.6 and the data-model XML for TR-181 and TR-098): fetch, pin by commit, and use as a primarysource collection | TR-069 Annex A.6, TR-106, TR-181 | `[ ]` | (to be written) | - |
| `primarysource` collection `bbf-datamodel`: parse the data-model XML (objects, parameters, types, access) with devicespy.xmlsafe into a structured table for `datamodel` | TR-106 | `[ ]` | (to be written) | - |

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

- TR-069 is outside the RFC series, so there is no errata mechanism to consult: pin the exact TR revision in every docstring and test, and record it in docs/research.md. Pinned 2026-11-13: TR-069 Issue 1 Amendment 6 Corrigendum 1, June 2020, CWMP 1.4, https://www.broadband-forum.org/pdfs/tr-069-1-6-1.pdf.
- The TR cites RFC 7230, RFC 7231, RFC 7235 and RFC 5246, all obsolete: implement against RFC 9110, RFC 9112 and RFC 9846, and cite the TR's own wording for the obligation.
- RFC 7616 carries 1 verified erratum, 4495 (Editorial, sec. 3.9.1): the example password is "Circle of Life" with a lower-case o, which matters to anyone reproducing the sec. 3.9.1 example as a test vector.
- The ACS URL a CPE learns usually arrives from DHCP option 43 or a DHCPv6 vendor option, so leasespy is the natural partner and the two must agree on the encoding.

## 4. Deliberate non-goals

| Non-goal | Status | Revisit when |
|---|---|---|
| a web UI, ticket system or firmware repository: an ACS product composes those, this is the protocol | `[no]` | a named document requires it |
| business provisioning logic beyond the data model | `[no]` | a named document requires it |
| USP transport in the first release, only the seam that will allow it | `[no]` | a named document requires it |

## 5. Open questions

- closed 2026-11-13: the baseline is TR-069 Amendment 6 Corrigendum 1 (CWMP 1.4); tests name it in their docstrings
- the Forum's licence allows use but not modification: tests may hold envelopes written for them and captures with provenance, never the report's text

## 6. Publication checklist

- [ ] every `[ ]` row above either `[ok]` or moved to a named later milestone
- [ ] `docs/research.md` claims re-verified and the dated ones either promoted or deleted
- [ ] interoperability evidence recorded in `docs/` against a non-Python implementation
- [ ] `tools/check_dist.py` proves the wheel ships the fixtures the README promises
- [ ] version 0.1.0 tagged, trusted publisher configured, README badges uncommented

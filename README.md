# cwmp

<!-- PyPI badges go live with the first release. Until then a version badge renders
     "no version" on the landing page, which reads as a defect rather than a date, so
     the badges stay commented out until the tag exists.
-->

**Pre-alpha shell.** The package surface, the obligation matrix and the CI gates exist.
No protocol behaviour is implemented: every public function raises `NotImplementedError`,
and the test suite records that rather than hiding it. Read
[ROADMAP.md](ROADMAP.md) before depending on any of it.

cwmp -- TR-069 CWMP for ACS and CPE

CWMP is how almost every customer premises device on earth is configured, and Python cannot speak it. GenieACS, the serious open source ACS, is Node.js; on PyPI the name tr069 is a registered but empty squat, acs belongs to Azure Container Service, pyacs is an oceanographic sensor library, and inform is a logging utility. Meanwhile the provisioning chain is already half built in Python: DHCP hands the CPE its ACS URL, cwmp takes it from there. This is a deliberately non-IETF project: the specification lives at the Broadband Forum, so every claim below cites a document number that must be re-verified against the Forum's current revision before it reaches code.

## The gap, with a date

PyPI was queried on 2026-11-05 for this name and for every neighbouring project. Landscape
claims rot quickly: two projects in this portfolio shipped within five days of the survey,
which is why the table below carries dates instead of adjectives.

| Project | Version | Last release | Why it is not this project |
|---|---|---|---|
| tr069 | - | - | registered but empty on PyPI: a squat that blocks the obvious name |
| GenieACS | - | - | the reference open source ACS, written in Node.js |
| acs, pyacs, inform | - | - | Azure tooling, an ocean sensor library and a logging utility |

What this project intends to add:

- SOAP 1.1 RPC codec that refuses hostile XML: no DTDs, no external entities, bounded depth
- CWMP session engine: Inform, RPC method dispatch, fault codes, keep-alive and the session retry policy
- HTTP Digest authentication on both sides, since most CPE ship nothing else
- parameter path tree with wildcards, instance addition and deletion, typed constraints
- both endpoints: an ACS side that can manage a real device and a CPE side to test against

## Specification spine

Status and publication dates below were read from the RFC Editor record on 2026-11-13 and from the Forum's own PDF. A
section number is cited only where that section was read in full; everything else cites the
document, which is the honest grain size for a plan. See [docs/rfc-map.md](docs/rfc-map.md).

| Document | Status | Published | What it gives this project |
|---|---|---|---|
| TR-069 Issue 1 Amendment 6 Corrigendum 1 (June 2020, CWMP 1.4) | Broadband Forum, In Force; supersedes TR-069 Amendment 6. https://www.broadband-forum.org/pdfs/tr-069-1-6-1.pdf, read 2026-11-13 | 2020-06 | the protocol: Inform, RPC methods (Annex A), SOAP use (section 3.5), sessions (3.4), TLS (3.3). The licence allows implementing it but not modifying it, so no text of it is copied here |
| SOAP 1.1 (W3C Note, 2000-05-08) | the TR's own normative reference [12]; section 3.5 requires its envelope and serialization namespaces | 2000-05-08 | the envelope and encoding rules the RPC layer obeys |
| TR-181 (Device:2) | Broadband Forum; the amendment used for fixtures is not yet pinned (secondary sources say Amendment 21, unverified) | - | the data model object and parameter tree |
| TR-098 (InternetGatewayDevice) | Broadband Forum, not re-checked | - | the model most deployed CPE still exposes |
| TR-369 (USP) | Broadband Forum, not re-checked | - | the WebSocket successor; a roadmap target, not a first release |
| RFC 9110 | Internet Standard (STD 97), obsoletes RFC 7231 and RFC 7235 | 2022-06 | HTTP semantics under the transport, including authentication |
| RFC 9112 | Internet Standard (STD 99), obsoletes RFC 7230, updated by RFC 9931 | 2022-06 | HTTP/1.1 message syntax; the TR still cites RFC 7230 and RFC 7231 |
| RFC 7616 | Proposed Standard, current | 2015-09 | HTTP Digest access authentication, which obsoletes RFC 2617 |
| RFC 7617 | Proposed Standard, current | 2015-09 | the Basic scheme the TR allows (section 3.4.4) |
| RFC 6265 | Proposed Standard, current, 5 verified errata | 2011-04 | cookies, which CWMP sessions rely on |
| RFC 9846 | Proposed Standard, current | 2026-07 | TLS 1.3; obsoletes RFC 8446 and RFC 5246, which the TR cites as its TLS reference |

### Errata watch

- TR-069 is outside the RFC series, so there is no errata mechanism to consult: pin the exact TR revision in every docstring and test, and record it in docs/research.md.
- RFC 7616 carries 1 verified erratum, 4495 (Editorial, sec. 3.9.1): the example password is "Circle of Life" with a lower-case o, which matters to anyone reproducing the sec. 3.9.1 example as a test vector.
- The ACS URL a CPE learns usually arrives from DHCP option 43 or a DHCPv6 vendor option, so leasespy is the natural partner and the two must agree on the encoding.

## Module layout

| Module | Responsibility |
|---|---|
| `envelope` | SOAP 1.1 envelope codec with XML hardening (TR-069 section 3.5, Annex A) |
| `methods` | one class per RPC method, request and response (TR-069) |
| `session` | ACS session state, authentication and fault handling (TR-069) |
| `endpoint` | CPE side: inform, connection request, method dispatch (TR-069) |
| `datamodel` | object tree, parameter paths, types and constraints (TR-181, TR-098) |
| `auth` | HTTP Digest challenge and response (RFC 7616, TR-069) |
| `transfer` | TransferFile, Download and Upload with resumable semantics (TR-069) |
| `clock` | periodic inform, session timeout and connection request retry |

## What it does not do

- a web UI, ticket system or firmware repository: an ACS product composes those, this is the protocol
- business provisioning logic beyond the data model
- USP transport in the first release, only the seam that will allow it


## Install

```bash
git clone https://github.com/b1tninja/cwmp.git
cd cwmp
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\\Scripts\\Activate.ps1
pip install -e ".[dev]"
```

Not published to PyPI yet. The name is reserved for this repository's trusted publisher at
the moment of the first release.

## Development

All four gates must pass, on Linux and Windows alike:

```bash
ruff check . && ruff format --check .
mypy cwmp tests
pytest -q --cov
python -O -m pytest -q
```

The last line is the one that matters most in a protocol library. `-O` strips `assert`, and a
parser whose bounds checks were asserts stops being a parser under production flags. Wire
paths raise named exceptions; asserts belong in tests and nowhere else.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

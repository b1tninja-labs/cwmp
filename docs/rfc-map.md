# Where every claim in this repository comes from

| Document | Status | Published | Verified against the publisher record on |
|---|---|---|---|
| TR-069 Issue 1 Amendment 6 Corrigendum 1 (June 2020, CWMP 1.4), https://www.broadband-forum.org/pdfs/tr-069-1-6-1.pdf | In Force on the Forum's library page; supersedes Amendment 6. 276 pages. The Terms of Use grant a licence to implement and distribute conforming products but not to modify or create derivative works of the report, so its text is never vendored here. Section 3.5 "Use of SOAP" and Annex A "RPC Methods" are the SOAP and RPC anchors; there is **no "Annex 2"** (annexes are lettered A to O) | 2020-06 | 2026-11-13 (the PDF itself, text extracted) |
| SOAP 1.1, W3C Note, https://www.w3.org/TR/2000/NOTE-SOAP-20000508/ | the TR's normative reference [12]; **the TR uses SOAP 1.1, not 1.2** (envelope namespace http://schemas.xmlsoap.org/soap/envelope/) | 2000-05-08 | 2026-11-13 |
| TR-181 (Device:2) | Broadband Forum. The data model is read from the published XML, not the PDF: Device:2.22 (`tr-181-2-22-0-cwmp-full.xml`, 5,425,272 bytes, sha256 d331ed729226d86b6ee426531eda823289f363fa1a6e4b445531fad79dc581d7) and `tr-106-types.xml` (21,157 bytes, sha256 68237466c70b9f48ea647878af65d54c16a42e45d2ef2ba5f6e4a1042e0484a1), both from https://cwmp-data-models.broadband-forum.org/, where Device:2.22 is the newest on the index. Licence read in each file header: a Broadband Forum copyright notice and a BSD-3-Clause-style licence (redistribution and use with the notice retained; copyright only, patents are the Forum IPR policy's); the site states no other terms. The files are fetched by `tools/fetch_bbf.py` into a cache outside the repository and are not vendored | 2025 (file headers) | 2026-11-13 |
| TR-098 (InternetGatewayDevice) | Broadband Forum; not re-checked | - | not verified at the publisher |
| TR-369 (USP) | Broadband Forum; not re-checked (secondary source: Amendment 5) | - | not verified at the publisher |
| RFC 9110 | Internet Standard (STD 97), current; obsoletes RFC 7230 in part, RFC 7231, RFC 7235; 6 verified errata | 2022-06 | 2026-11-13 |
| RFC 9112 | Internet Standard (STD 99), current; obsoletes RFC 7230; updated by RFC 9931; 2 verified errata | 2022-06 | 2026-11-13 |
| RFC 7230, RFC 7231, RFC 7235 | **OBSOLETE**, cited by the TR as its HTTP references [6], [7], [8]. Successors: RFC 7230 by RFC 9110 and RFC 9112; RFC 7231 and RFC 7235 by RFC 9110. Cite the TR's wording, implement against 9110 and 9112 | 2014-06 | 2026-11-13 |
| RFC 7616 | Proposed Standard, current, obsoletes RFC 2617; 1 verified erratum (4495) | 2015-09 | 2026-11-13 |
| RFC 7617 | Proposed Standard, current, obsoletes RFC 2617; 0 verified errata (1 on file) | 2015-09 | 2026-11-13 |
| RFC 6265 | Proposed Standard, current, obsoletes RFC 2965; 5 verified errata | 2011-04 | 2026-11-13 |
| RFC 5246 | **OBSOLETE**, the TR's TLS 1.2 reference [14]. Obsoleted by RFC 8446 and RFC 9846; the current TLS spec is **RFC 9846** (2026-07), which obsoletes RFC 8446 | 2008-08 | 2026-11-13 |
| RFC 8446 | **OBSOLETE**, obsoleted by RFC 9846 | 2018-08 | 2026-11-13 |
| RFC 7568 | Proposed Standard, current, updated by RFC 8996; the TR cites it to forbid SSL 3.0 | 2015-06 | 2026-11-13 |
| RFC 7525, RFC 6125, RFC 4122 | cited by the TR or its companions; **OBSOLETE**: RFC 7525 by RFC 9325, RFC 6125 by RFC 9525, RFC 4122 by RFC 9562 | - | 2026-11-13 (RFC 4122 per the RFC 9562 record) |

TR-069 sections read in full on 2026-11-13 from the pinned PDF (sha256 21622e4a...ba115): 3.5, A.2.1, A.2.2, A.2.4, A.3.2.3, A.3.3.1, A.5 (Tables 4, 12, 20 to 22, 37 to 40, 87, 88). Nothing from them is copied; `cwmp/faults.py` holds the numbers and this library's own short names.

Citation rules, in the order they most often get broken:

1. Cite the document. A secondary write-up is a lead, not a source.
2. A section number is cited only if that section was read in full.
3. Errata are checked at each milestone freeze, not once at the start.
4. Where a claim came from a body outside the RFC series, that body is named here.

Re-verify with the RFC library rather than memory: `info('RFCnnnn')` for current status, `errata('RFCnnnn')` for corrections, and `read('RFCnnnn', view='normative')` for the MUST and SHOULD statements that become obligation rows.

"""The CWMP fault-code table as data (TR-069 Amendment 6 Corrigendum 1, Annex A.5, Tables 87 and 88).

The Technical Report's licence does not allow its text to be copied, so this module holds only the
numbers, a short identifier of this library's own wording for each, and the SOAP ``faultcode`` the
table's Type column assigns. The report's descriptions stay in the report. The table was read from the
PDF on 2026-11-13 (sha256 21622e4a...ba115).

Table 87 lists CPE codes 9000 to 9032 and the vendor range 9800 to 9899; Table 88 lists ACS codes 8000
to 8006 and the vendor range 8800 to 8899. The Type column says which SOAP ``faultcode`` a fault of that
number carries: ``Client`` or ``Server`` (section 3.5 requires one of the two).

A note for whoever cites this: the footnote under Table 87 and Table 88 sends the reader to section 3.4.7
for the Type rule, but section 3.4.7 of this revision is HTTP compression; the faultcode rule is in
section 3.5. The numbering in the footnote looks stale, so cite section 3.5.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ACS_FAULTS",
    "CPE_FAULTS",
    "FaultEntry",
    "is_acs_code",
    "is_cpe_code",
    "lookup",
    "soap_faultcode",
]


@dataclass(frozen=True)
class FaultEntry:
    """One row of Table 87 or 88: ``side`` is ``cpe`` or ``acs``, ``kind`` ``Client`` or ``Server``."""

    code: int
    name: str
    kind: str
    side: str


def _table(side: str, rows: tuple[tuple[int, str, str], ...]) -> dict[int, FaultEntry]:
    return {code: FaultEntry(code, name, kind, side) for code, name, kind in rows}


CPE_FAULTS: dict[int, FaultEntry] = _table(
    "cpe",
    (
        (9000, "method-not-supported", "Server"),
        (9001, "request-denied", "Server"),
        (9002, "internal-error", "Server"),
        (9003, "invalid-arguments", "Client"),
        (9004, "resources-exceeded", "Server"),
        (9005, "invalid-parameter-name", "Client"),
        (9006, "invalid-parameter-type", "Client"),
        (9007, "invalid-parameter-value", "Client"),
        (9008, "non-writable-parameter", "Client"),
        (9009, "notification-rejected", "Server"),
        (9010, "download-failure", "Server"),
        (9011, "upload-failure", "Server"),
        (9012, "file-server-authentication-failure", "Server"),
        (9013, "unsupported-transfer-protocol", "Server"),
        (9014, "multicast-join-failure", "Server"),
        (9015, "file-server-contact-failure", "Server"),
        (9016, "file-access-failure", "Server"),
        (9017, "download-incomplete", "Server"),
        (9018, "file-corrupted", "Server"),
        (9019, "file-authentication-failure", "Server"),
        (9020, "outside-time-window", "Client"),
        (9021, "cancel-not-permitted", "Client"),
        (9022, "invalid-uuid-format", "Server"),
        (9023, "unknown-execution-environment", "Server"),
        (9024, "disabled-execution-environment", "Server"),
        (9025, "du-execution-environment-mismatch", "Server"),
        (9026, "duplicate-deployment-unit", "Server"),
        (9027, "system-resources-exceeded", "Server"),
        (9028, "unknown-deployment-unit", "Server"),
        (9029, "invalid-deployment-unit-state", "Server"),
        (9030, "downgrade-not-permitted", "Server"),
        (9031, "version-not-specified", "Server"),
        (9032, "version-already-exists", "Server"),
    ),
)
ACS_FAULTS: dict[int, FaultEntry] = _table(
    "acs",
    (
        (8000, "method-not-supported", "Server"),
        (8001, "request-denied", "Server"),
        (8002, "internal-error", "Server"),
        (8003, "invalid-arguments", "Client"),
        (8004, "resources-exceeded", "Server"),
        (8005, "retry-request", "Server"),
        (8006, "acs-version-incompatible", "Server"),
    ),
)

_CPE_VENDOR = range(9800, 9900)
_ACS_VENDOR = range(8800, 8900)


def is_cpe_code(code: int) -> bool:
    return code in CPE_FAULTS or code in _CPE_VENDOR


def is_acs_code(code: int) -> bool:
    return code in ACS_FAULTS or code in _ACS_VENDOR


def lookup(code: int) -> FaultEntry | None:
    """The table row for ``code``, or None for a vendor-defined or unknown code."""
    return CPE_FAULTS.get(code) or ACS_FAULTS.get(code)


def soap_faultcode(code: int) -> str:
    """``Client`` or ``Server`` for a tabulated code. A vendor-defined code has no Type in the table
    (it shows "-"), so it raises ``ValueError`` and the caller must choose; an unknown code does too."""
    found = lookup(code)
    if found is None:
        raise ValueError(f"fault code {code} has no Type in Tables 87 and 88")
    return found.kind

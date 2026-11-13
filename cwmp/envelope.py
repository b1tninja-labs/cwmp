"""SOAP 1.1 envelope codec with XML hardening (TR-069 Amendment 6 Corrigendum 1, section 3.5).

The document is the Broadband Forum's TR-069 "CPE WAN Management Protocol", Issue 1 Amendment 6
Corrigendum 1, June 2020, CWMP version 1.4 (https://www.broadband-forum.org/pdfs/tr-069-1-6-1.pdf,
read 2026-11-13). Section 3.5 "Use of SOAP" defines SOAP 1.1 as the encoding syntax and Annex A
carries the RPC methods and their XML schema. The text of the Technical Report is not reproduced
here; its licence does not allow modification.

``decode_envelope`` reads an envelope through ``devicespy.xmlsafe`` and returns either an
:class:`Envelope` (an RPC request or response) or a :class:`Fault`. Prefixes are arbitrary, so
every match is on a namespace URI. ``encode_envelope`` is not implemented yet and raises.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from devicespy import xmlsafe

from .errors import EnvelopeError, XmlRefused

if TYPE_CHECKING:
    from typing import Any

    Rpc = Any  # placeholder: give it a real type in the milestone that needs it
    SessionContext = Any  # placeholder: give it a real type in the milestone that needs it

__all__ = [
    "MAX_BYTES",
    "SOAP_ENC_NS",
    "SOAP_ENV_NS",
    "Envelope",
    "Fault",
    "Headers",
    "ParameterFault",
    "UnknownHeader",
    "decode_envelope",
    "encode_envelope",
]

#: SOAP 1.1 envelope and serialization namespaces, TR-069 section 3.5.
SOAP_ENV_NS = "http://schemas.xmlsoap.org/soap/envelope/"
SOAP_ENC_NS = "http://schemas.xmlsoap.org/soap/encoding/"
#: The SOAP 1.2 envelope namespace, named only so that it is refused with a clear reason.
_SOAP12_ENV_NS = "http://www.w3.org/2003/05/soap-envelope"
#: Annex A.6 lists urn:dslforum-org:cwmp-1-0, -1-1 and -1-2 (versions 1.2, 1.3 and 1.4 all use
#: -1-2), and section 3.5 calls a given namespace identifier "only an example": any
#: urn:dslforum-org:cwmp-1-N is accepted and the matched URI is exposed to the caller.
_CWMP_NS = re.compile(r"urn:dslforum-org:cwmp-1-[0-9]+")
_KNOWN_HEADERS = frozenset(
    {
        "ID",
        "HoldRequests",
        "NoMoreRequests",
        "SessionTimeout",
        "SupportedCWMPVersions",
        "UseCWMPVersion",
    }
)

#: Section 3.5 requires 32768 bytes to be accepted; a megabyte leaves room for large Informs.
MAX_BYTES = 1_048_576
_MAX_DEPTH = 64
_MAX_ELEMENTS = 100_000


@dataclass(frozen=True)
class UnknownHeader:
    """A SOAP header this decoder does not understand, reported rather than dropped."""

    name: str
    must_understand: bool


@dataclass(frozen=True)
class Headers:
    """The CWMP SOAP headers of an envelope; ``known`` maps local name to text value."""

    id: str | None = None
    hold_requests: bool | None = None
    no_more_requests: bool | None = None
    known: dict[str, str] = field(default_factory=dict)
    unknown: tuple[UnknownHeader, ...] = ()


@dataclass(frozen=True)
class ParameterFault:
    """One ``SetParameterValuesFault`` entry: the parameter in error and why."""

    name: str
    code: int
    string: str


@dataclass(frozen=True)
class Fault:
    """A CWMP fault response: ``soap:Fault`` whose ``detail`` holds ``cwmp:Fault``."""

    code: int
    string: str
    parameter_faults: tuple[ParameterFault, ...]
    faultcode: str
    cwmp_namespace: str
    headers: Headers = field(default_factory=Headers)


@dataclass(frozen=True)
class Envelope:
    """An RPC request or response: the method element and its CWMP headers."""

    method: str
    body: ET.Element
    cwmp_namespace: str
    headers: Headers = field(default_factory=Headers)

    @property
    def id(self) -> str | None:
        return self.headers.id


def encode_envelope(rpc: Rpc, session: SessionContext) -> bytes:
    """Pending behaviour defined by TR-069 Amendment 6 Corrigendum 1, section 3.5.

    Not implemented yet. See the ``envelope.encode_envelope()`` row in ROADMAP.md; this
    stub raises on purpose so nothing downstream mistakes it for working code.
    """
    raise NotImplementedError(
        "encode_envelope() is not implemented: TR-069 Amendment 6 Corrigendum 1 section 3.5"
    )


def _children(element: ET.Element, uri: str, local: str) -> list[ET.Element]:
    return [c for c in element if xmlsafe.localname(c.tag) == (uri, local)]


def _text(element: ET.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def _int(element: ET.Element | None, what: str) -> int:
    text = _text(element)
    if not text.isascii() or not text.isdigit():
        raise EnvelopeError(f"{what} is not a number")
    return int(text)


def _bool(text: str, what: str) -> bool:
    if text in ("0", "false"):
        return False
    if text in ("1", "true"):
        return True
    raise EnvelopeError(f"{what} is not a boolean")


def _headers(header: ET.Element | None) -> Headers:
    if header is None:
        return Headers()
    known: dict[str, str] = {}
    unknown: list[UnknownHeader] = []
    for child in header:
        uri, local = xmlsafe.localname(child.tag)
        must = child.get("{" + SOAP_ENV_NS + "}mustUnderstand", "0").strip() in ("1", "true")
        if _CWMP_NS.fullmatch(uri) and local in _KNOWN_HEADERS:
            known[local] = _text(child)
        else:
            unknown.append(UnknownHeader(child.tag, must))
    hold = _bool(known["HoldRequests"], "HoldRequests") if "HoldRequests" in known else None
    nomore = _bool(known["NoMoreRequests"], "NoMoreRequests") if "NoMoreRequests" in known else None
    return Headers(known.get("ID"), hold, nomore, known, tuple(unknown))


def _decode_fault(fault: ET.Element, headers: Headers) -> Fault:
    faultcode = _text(next((c for c in fault if c.tag == "faultcode"), None))
    if faultcode.rsplit(":", 1)[-1] not in ("Client", "Server"):
        raise EnvelopeError("faultcode is neither Client nor Server")
    if _text(next((c for c in fault if c.tag == "faultstring"), None)) != "CWMP fault":
        raise EnvelopeError('faultstring is not "CWMP fault"')
    details = [c for c in fault if c.tag == "detail"]
    if len(details) != 1:
        raise EnvelopeError("a fault needs exactly one detail element")
    cwmp = [c for c in details[0] if xmlsafe.localname(c.tag)[1] == "Fault"]
    if len(cwmp) != 1 or not _CWMP_NS.fullmatch(xmlsafe.localname(cwmp[0].tag)[0]):
        raise EnvelopeError("detail does not hold exactly one cwmp:Fault")
    body = cwmp[0]
    namespace = xmlsafe.localname(body.tag)[0]
    code = _int(next((c for c in body if c.tag == "FaultCode"), None), "FaultCode")
    string = _text(next((c for c in body if c.tag == "FaultString"), None))
    faults = []
    for entry in (c for c in body if c.tag == "SetParameterValuesFault"):
        faults.append(
            ParameterFault(
                _text(next((c for c in entry if c.tag == "ParameterName"), None)),
                _int(next((c for c in entry if c.tag == "FaultCode"), None), "FaultCode"),
                _text(next((c for c in entry if c.tag == "FaultString"), None)),
            )
        )
    return Fault(code, string, tuple(faults), faultcode, namespace, headers)


def decode_envelope(raw: bytes, *, max_bytes: int = MAX_BYTES) -> Envelope | Fault:
    """Decode a SOAP 1.1 CWMP envelope per TR-069 Amendment 6 Corrigendum 1, section 3.5.

    Returns an :class:`Envelope` for an RPC request or response, or a :class:`Fault`. The XML is
    read by ``devicespy.xmlsafe.parse`` (no DTD, no entities, bounded size and depth). Raises
    :class:`EnvelopeError` for anything else, never an empty or placeholder result: SOAP 1.2,
    zero or several Body elements, a body that is not one CWMP element, or a malformed fault.
    ``max_bytes`` must be at least 32768, the size section 3.5 says both sides must accept.
    Headers this decoder does not know are reported in ``headers.unknown``, not dropped.
    """
    try:
        root = xmlsafe.parse(
            raw,
            max_bytes,
            max_depth=_MAX_DEPTH,
            max_elements=_MAX_ELEMENTS,
            ignore_processing_instructions=True,
        )
    except xmlsafe.XmlRefused as error:
        raise XmlRefused(error.reason) from None
    uri, local = xmlsafe.localname(root.tag)
    if uri == _SOAP12_ENV_NS:
        raise EnvelopeError("SOAP 1.2 is not CWMP: TR-069 section 3.5 specifies SOAP 1.1")
    if (uri, local) != (SOAP_ENV_NS, "Envelope"):
        raise EnvelopeError("root is not a SOAP 1.1 Envelope")
    headers = _children(root, SOAP_ENV_NS, "Header")
    bodies = _children(root, SOAP_ENV_NS, "Body")
    if len(bodies) != 1:
        raise EnvelopeError(f"an Envelope must contain exactly one Body, found {len(bodies)}")
    if len(headers) > 1:
        raise EnvelopeError("an Envelope may contain at most one Header")
    parsed = _headers(headers[0] if headers else None)
    entries = list(bodies[0])
    if len(entries) != 1:
        raise EnvelopeError(f"a CWMP Body holds exactly one element, found {len(entries)}")
    entry = entries[0]
    entry_uri, entry_local = xmlsafe.localname(entry.tag)
    if (entry_uri, entry_local) == (SOAP_ENV_NS, "Fault"):
        return _decode_fault(entry, parsed)
    if not _CWMP_NS.fullmatch(entry_uri):
        raise EnvelopeError("the Body element is not in a CWMP namespace")
    return Envelope(entry_local, entry, entry_uri, parsed)

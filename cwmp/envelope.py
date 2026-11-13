"""SOAP 1.1 envelope codec with XML hardening (TR-069 Amendment 6 Corrigendum 1, section 3.5).

The document is the Broadband Forum's TR-069 "CPE WAN Management Protocol", Issue 1 Amendment 6
Corrigendum 1, June 2020, CWMP version 1.4 (https://www.broadband-forum.org/pdfs/tr-069-1-6-1.pdf,
read 2026-11-13). Section 3.5 "Use of SOAP" defines SOAP 1.1 as the encoding syntax and Annex A
carries the RPC methods and their XML schema. The text of the Technical Report is not reproduced
here; its licence does not allow modification.

``decode_envelope`` reads an envelope through ``devicespy.xmlsafe`` and returns either an
:class:`Envelope` (an RPC request or response) or a :class:`Fault`. Prefixes are arbitrary, so
every match is on a namespace URI. ``encode_envelope`` writes the same shapes back, refusing what
section 3.5 and Table 4 forbid.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from devicespy import xmlsafe

from .errors import EncodeError, EnvelopeError, XmlRefused

if TYPE_CHECKING:
    pass


__all__ = [
    "DEFAULT_CWMP_NS",
    "MAX_BYTES",
    "SOAP_ENC_NS",
    "SOAP_ENV_NS",
    "Arg",
    "Envelope",
    "Fault",
    "Headers",
    "ParameterFault",
    "Rpc",
    "SessionContext",
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


_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_XSD_NS = "http://www.w3.org/2001/XMLSchema"
#: The default namespace: Annex A.6 says versions 1.2, 1.3 and 1.4 all use cwmp-1-2.
DEFAULT_CWMP_NS = "urn:dslforum-org:cwmp-1-2"
_NCNAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
_TYPE_REF = re.compile(r"(?:xsd|cwmp|soap-enc):[A-Za-z_][A-Za-z0-9_.-]*")
_BAD_XML = re.compile("[^\t\n\r -퟿-�\U00010000-\U0010ffff]")
_MIN_SESSION_TIMEOUT = 30


@dataclass(frozen=True)
class Arg:
    """One element inside an RPC method element, named without a namespace prefix.

    Section 3.5: the CWMP schema's elementFormDefault is "unqualified", so only the method element and the
    header elements carry the CWMP namespace and an argument never does. ``text`` and ``children`` are
    exclusive. ``xsi_type`` (``xsd:string``) is written as an ``xsi:type`` attribute; ``any_simple`` marks
    an element the schema types ``anySimpleType``, which MUST carry one (section 3.5; Table 12 in A.2.1).
    ``array_type`` makes the element a SOAP array of that member type (``cwmp:ParameterValueStruct``,
    ``xsd:string``); every child is then a member and must be named as the member type without a prefix.
    """

    name: str
    text: str | None = None
    children: tuple[Arg, ...] = ()
    xsi_type: str | None = None
    any_simple: bool = False
    array_type: str | None = None


@dataclass(frozen=True)
class Rpc:
    """A method call or response: ``method`` is the element name (``GetParameterNames``,
    ``GetParameterNamesResponse``), in the CWMP namespace."""

    method: str
    arguments: tuple[Arg, ...] = ()


@dataclass(frozen=True)
class SessionContext:
    """What the encoder needs that is not in the RPC: the namespace, the headers, and who is sending.

    ``sender`` is ``cpe`` or ``acs``; Table 4 restricts HoldRequests to the ACS, SessionTimeout and
    SupportedCWMPVersions to a CPE's Inform, and UseCWMPVersion to an ACS's InformResponse, so those
    headers are refused unless ``sender`` says they are allowed. ``in_reply_to`` is ``request``,
    ``response`` or ``fault`` and must be ``request`` to encode a fault, which may answer a request only.
    """

    id: str | None = None
    namespace: str = DEFAULT_CWMP_NS
    sender: str | None = None
    hold_requests: bool | None = None
    session_timeout: int | None = None
    supported_versions: tuple[str, ...] | None = None
    use_version: str | None = None
    in_reply_to: str | None = None


def _escape(text: str, what: str) -> str:
    if _BAD_XML.search(text):
        raise EncodeError(f"{what} holds a character XML 1.0 cannot carry")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _name(text: str, what: str) -> str:
    if not _NCNAME.fullmatch(text):
        raise EncodeError(f"{what} {text[:40]!r} is not an XML name")
    return text


def _arg(arg: Arg, depth: int) -> str:
    if depth > _MAX_DEPTH:
        raise EncodeError("arguments are nested too deeply")
    name = _name(arg.name, "argument name")
    if arg.text is not None and arg.children:
        raise EncodeError(f"argument {name} has both text and children")
    attrs = ""
    if arg.any_simple and arg.xsi_type is None:
        raise EncodeError(f"argument {name} is anySimpleType and needs an xsi:type (section 3.5)")
    if arg.xsi_type is not None:
        if not _TYPE_REF.fullmatch(arg.xsi_type):
            raise EncodeError(
                f"xsi:type {arg.xsi_type[:40]!r} needs a xsd:, cwmp: or soap-enc: prefix"
            )
        attrs += f' xsi:type="{arg.xsi_type}"'
    if arg.array_type is not None:
        if not _TYPE_REF.fullmatch(arg.array_type):
            raise EncodeError(
                f"arrayType {arg.array_type[:40]!r} needs a prefix (section 3.5 note)"
            )
        member = arg.array_type.split(":", 1)[1]
        for child in arg.children:
            if child.name != member:
                raise EncodeError(
                    f"array {name}: a member is named for its type {member!r} (section 3.5), not {child.name!r}"
                )
        attrs += f' soap-enc:arrayType="{arg.array_type}[{len(arg.children)}]"'
    inner = _escape(arg.text, f"argument {name}") if arg.text is not None else ""
    inner += "".join(_arg(child, depth + 1) for child in arg.children)
    if not inner and not attrs:
        return f"<{name}/>"
    return f"<{name}{attrs}>{inner}</{name}>"


def _header(session: SessionContext, method: str | None) -> str:
    out = ""
    if session.id is not None:
        out += f'<cwmp:ID soap-env:mustUnderstand="1">{_escape(session.id, "ID")}</cwmp:ID>'
    if session.hold_requests is not None:
        if session.sender != "acs":
            raise EncodeError("HoldRequests is sent by an ACS only (Table 4)")
        flag = "1" if session.hold_requests else "0"
        out += f'<cwmp:HoldRequests soap-env:mustUnderstand="1">{flag}</cwmp:HoldRequests>'
    if session.session_timeout is not None:
        if session.sender != "cpe" or method != "Inform":
            raise EncodeError("SessionTimeout is sent by a CPE, in an Inform, only (Table 4)")
        if session.session_timeout < _MIN_SESSION_TIMEOUT:
            raise EncodeError("SessionTimeout must be 30 seconds or greater (Table 4)")
        timeout = session.session_timeout
        out += f'<cwmp:SessionTimeout soap-env:mustUnderstand="0">{timeout}</cwmp:SessionTimeout>'
    if session.supported_versions is not None:
        if session.sender != "cpe" or method != "Inform" or not session.supported_versions:
            raise EncodeError(
                "SupportedCWMPVersions is a CPE's, in an Inform, and not empty (Table 4)"
            )
        listing = _escape(",".join(session.supported_versions), "SupportedCWMPVersions")
        out += f'<cwmp:SupportedCWMPVersions soap-env:mustUnderstand="0">{listing}</cwmp:SupportedCWMPVersions>'
    if session.use_version is not None:
        if session.sender != "acs" or method != "InformResponse":
            raise EncodeError("UseCWMPVersion is an ACS's, in an InformResponse, only (Table 4)")
        version = _escape(session.use_version, "UseCWMPVersion")
        out += f'<cwmp:UseCWMPVersion soap-env:mustUnderstand="1">{version}</cwmp:UseCWMPVersion>'
    return f"<soap-env:Header>{out}</soap-env:Header>" if out else ""


def _fault_body(fault: Fault) -> str:
    if fault.faultcode.rsplit(":", 1)[-1] not in ("Client", "Server"):
        raise EncodeError("faultcode is neither Client nor Server (section 3.5)")
    details = (
        f"<FaultCode>{int(fault.code)}</FaultCode>"
        f"<FaultString>{_escape(fault.string, 'FaultString')}</FaultString>"
    )
    for entry in fault.parameter_faults:
        details += (
            "<SetParameterValuesFault>"
            f"<ParameterName>{_escape(entry.name, 'ParameterName')}</ParameterName>"
            f"<FaultCode>{int(entry.code)}</FaultCode>"
            f"<FaultString>{_escape(entry.string, 'FaultString')}</FaultString>"
            "</SetParameterValuesFault>"
        )
    return (
        f"<soap-env:Fault><faultcode>{fault.faultcode}</faultcode><faultstring>CWMP fault</faultstring>"
        f"<detail><cwmp:Fault>{details}</cwmp:Fault></detail></soap-env:Fault>"
    )


def encode_envelope(rpc: Rpc | Fault, session: SessionContext) -> bytes:
    """Encode an RPC call, response or fault as a SOAP 1.1 envelope (TR-069 Amendment 6 Corrigendum 1, 3.5).

    Prefixes are fixed (``soap-env``, ``soap-enc``, ``xsd``, ``xsi``, ``cwmp``) and declared on the root, as
    the section's own example does; the CWMP namespace is ``session.namespace``, which must match
    ``urn:dslforum-org:cwmp-1-N``. The result is UTF-8 with an XML declaration. Raises
    :class:`EncodeError` rather than emit anything the section forbids: a fault in answer to anything
    but a request, a header Table 4 does not allow from this sender, an anySimpleType without a type, an
    array member named other than its type, a character XML 1.0 cannot carry.
    """
    if not _CWMP_NS.fullmatch(session.namespace):
        raise EncodeError("the CWMP namespace must be urn:dslforum-org:cwmp-1-N (Annex A.6)")
    method: str | None
    if isinstance(rpc, Fault):
        if session.in_reply_to != "request":
            raise EncodeError("a fault response answers a SOAP request only (section 3.5)")
        body = _fault_body(rpc)
        method = None
    else:
        method = _name(rpc.method, "method name")
        inner = "".join(_arg(arg, 0) for arg in rpc.arguments)
        body = f"<cwmp:{method}>{inner}</cwmp:{method}>" if inner else f"<cwmp:{method}/>"
    root = (
        f'<soap-env:Envelope xmlns:soap-enc="{SOAP_ENC_NS}" xmlns:soap-env="{SOAP_ENV_NS}"'
        f' xmlns:xsd="{_XSD_NS}" xmlns:xsi="{_XSI_NS}" xmlns:cwmp="{session.namespace}">'
    )
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"{root}{_header(session, method)}<soap-env:Body>{body}</soap-env:Body></soap-env:Envelope>"
    )
    return text.encode("utf-8")


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

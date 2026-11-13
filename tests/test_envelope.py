"""decode_envelope against TR-069 Amendment 6 Corrigendum 1 (June 2020, CWMP 1.4), section 3.5.

The envelopes below were written for these tests from the structure that section states. They are
not copied from the Technical Report, whose licence does not allow derivative works.
"""

from __future__ import annotations

import time

import pytest

from cwmp.envelope import Envelope, Fault, ParameterFault, decode_envelope
from cwmp.errors import EnvelopeError, XmlRefused

ENV = "http://schemas.xmlsoap.org/soap/envelope/"


def rpc(prefix: str = "soap", cwmp: str = "c", ns: str = "urn:dslforum-org:cwmp-1-2") -> bytes:
    return (
        f'<{prefix}:Envelope xmlns:{prefix}="{ENV}" xmlns:{cwmp}="{ns}">'
        f'<{prefix}:Header><{cwmp}:ID {prefix}:mustUnderstand="1">1234</{cwmp}:ID></{prefix}:Header>'
        f"<{prefix}:Body><{cwmp}:GetParameterNames>"
        "<ParameterPath>Device.</ParameterPath><NextLevel>0</NextLevel>"
        f"</{cwmp}:GetParameterNames></{prefix}:Body></{prefix}:Envelope>"
    ).encode()


FAULT = f"""<soap:Envelope xmlns:soap="{ENV}" xmlns:cwmp="urn:dslforum-org:cwmp-1-0">
  <soap:Header><cwmp:ID soap:mustUnderstand="1">77</cwmp:ID></soap:Header>
  <soap:Body><soap:Fault>
    <faultcode>Client</faultcode><faultstring>CWMP fault</faultstring>
    <detail><cwmp:Fault><FaultCode>9000</FaultCode><FaultString>Method not supported</FaultString>
    </cwmp:Fault></detail>
  </soap:Fault></soap:Body></soap:Envelope>""".encode()

SPV_FAULT = f"""<soap:Envelope xmlns:soap="{ENV}" xmlns:cwmp="urn:dslforum-org:cwmp-1-2">
  <soap:Body><soap:Fault>
    <faultcode>soap:Server</faultcode><faultstring>CWMP fault</faultstring>
    <detail><cwmp:Fault><FaultCode>9003</FaultCode><FaultString>Invalid arguments</FaultString>
      <SetParameterValuesFault>
        <ParameterName>
          Device.A.B
        </ParameterName><FaultCode>9007</FaultCode><FaultString>bad</FaultString>
      </SetParameterValuesFault>
      <SetParameterValuesFault>
        <ParameterName>Device.C</ParameterName><FaultCode>9007</FaultCode>
        <FaultString>too long</FaultString>
      </SetParameterValuesFault>
    </cwmp:Fault></detail>
  </soap:Fault></soap:Body></soap:Envelope>""".encode()


def wrap(body: str, header: str = "", extra: str = "") -> bytes:
    head = f"<soap:Header>{header}</soap:Header>" if header else ""
    return (
        f'<soap:Envelope xmlns:soap="{ENV}" xmlns:cwmp="urn:dslforum-org:cwmp-1-2">'
        f"{head}<soap:Body>{body}</soap:Body>{extra}</soap:Envelope>"
    ).encode()


def test_decode_rpc_request():
    result = decode_envelope(rpc())
    assert isinstance(result, Envelope)
    assert result.method == "GetParameterNames"
    assert result.id == "1234"
    assert result.cwmp_namespace == "urn:dslforum-org:cwmp-1-2"
    assert result.body[0].text == "Device."
    assert result.headers.unknown == ()


def test_decode_fault():
    result = decode_envelope(FAULT)
    assert isinstance(result, Fault)
    assert (result.code, result.string, result.parameter_faults) == (
        9000,
        "Method not supported",
        (),
    )
    assert result.faultcode == "Client"
    assert result.headers.id == "77"
    assert result.cwmp_namespace == "urn:dslforum-org:cwmp-1-0"


def test_decode_setparametervalues_fault_lists_each_parameter():
    result = decode_envelope(SPV_FAULT)
    assert isinstance(result, Fault)
    assert result.code == 9003
    assert result.parameter_faults == (
        ParameterFault("Device.A.B", 9007, "bad"),
        ParameterFault("Device.C", 9007, "too long"),
    )


def test_prefix_is_irrelevant():
    a = decode_envelope(rpc("soap", "c"))
    b = decode_envelope(rpc("s", "zz"))
    assert isinstance(a, Envelope)
    assert isinstance(b, Envelope)
    assert (a.method, a.id, a.cwmp_namespace) == (b.method, b.id, b.cwmp_namespace)
    assert a.body.tag == b.body.tag


@pytest.mark.parametrize("version", ["urn:dslforum-org:cwmp-1-0", "urn:dslforum-org:cwmp-1-2"])
def test_cwmp_namespace_is_exposed(version):
    result = decode_envelope(rpc(ns=version))
    assert isinstance(result, Envelope)
    assert result.cwmp_namespace == version


def test_foreign_body_namespace_is_refused():
    with pytest.raises(EnvelopeError):
        decode_envelope(rpc(ns="urn:example:other"))


def test_soap12_envelope_is_refused():
    doc = b'<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"><e:Body/></e:Envelope>'
    with pytest.raises(EnvelopeError, match=r"SOAP 1.1"):
        decode_envelope(doc)


def test_non_envelope_root_is_refused():
    with pytest.raises(EnvelopeError):
        decode_envelope(b"<html/>")


def test_two_bodies_refused():
    doc = wrap("<cwmp:Reboot/>", extra="<soap:Body><cwmp:Reboot/></soap:Body>")
    with pytest.raises(EnvelopeError, match="exactly one Body"):
        decode_envelope(doc)


def test_no_body_refused():
    doc = f'<soap:Envelope xmlns:soap="{ENV}"><soap:Header/></soap:Envelope>'.encode()
    with pytest.raises(EnvelopeError, match="exactly one Body"):
        decode_envelope(doc)


def test_empty_or_two_element_body_refused():
    with pytest.raises(EnvelopeError):
        decode_envelope(wrap(""))
    with pytest.raises(EnvelopeError):
        decode_envelope(wrap("<cwmp:Reboot/><cwmp:Reboot/>"))


def test_doctype_refused():
    with pytest.raises(XmlRefused):
        decode_envelope(b"<!DOCTYPE x>" + rpc())


def test_internal_entity_declaration_refused():
    bomb = (
        b'<!DOCTYPE l [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">'
        b'<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]>'
    ) + rpc().replace(b"Device.", b"&c;")
    start = time.perf_counter()
    with pytest.raises(XmlRefused):
        decode_envelope(bomb)
    assert time.perf_counter() - start < 1.0


def test_external_entity_refused(tmp_path):
    secret = tmp_path / "hosts"
    secret.write_text("SECRET")
    doc = (f'<!DOCTYPE x [<!ENTITY e SYSTEM "{secret.as_uri()}">]>').encode() + rpc().replace(
        b"Device.", b"&e;"
    )
    with pytest.raises(XmlRefused):
        decode_envelope(doc)


def test_parameter_entity_refused():
    doc = b'<!DOCTYPE x [<!ENTITY % p SYSTEM "http://127.0.0.1:9/p"> %p;]>' + rpc()
    with pytest.raises(XmlRefused):
        decode_envelope(doc)


def test_depth_bomb_refused():
    doc = b"<a>" * 65 + b"</a>" * 65
    with pytest.raises(XmlRefused, match="nesting"):
        decode_envelope(doc)


def test_size_limit_refused():
    with pytest.raises(XmlRefused):
        decode_envelope(rpc() + b" " * 10, max_bytes=len(rpc()) + 9)


def test_32768_byte_envelope_accepted():
    padding = "x" * (32768 - len(rpc()) - len("<Pad></Pad>") - 12)
    doc = rpc().replace(b"<NextLevel>", b"<Pad>" + padding.encode() + b"</Pad><NextLevel>")
    assert len(doc) >= 32700
    doc += b" " * (32768 - len(doc))
    assert len(doc) == 32768
    assert isinstance(decode_envelope(doc), Envelope)


def test_processing_instruction_is_ignored():
    # Section 3.5 lets a receiver ignore processing instructions.
    assert isinstance(decode_envelope(b"<?pi x?>" + rpc()), Envelope)


def test_truncated_xml_refused():
    with pytest.raises(XmlRefused):
        decode_envelope(rpc()[:-10])


def test_invalid_utf8_refused():
    with pytest.raises(XmlRefused):
        decode_envelope(rpc().replace(b"Device.", b"\xff\xfe"))


def test_mustunderstand_unknown_header_is_reported():
    header = (
        '<x:Vendor xmlns:x="urn:example:v" soap:mustUnderstand="1">1</x:Vendor>'
        '<cwmp:HoldRequests soap:mustUnderstand="1">1</cwmp:HoldRequests>'
    )
    result = decode_envelope(wrap("<cwmp:Reboot/>", header))
    assert isinstance(result, Envelope)
    assert [(h.name, h.must_understand) for h in result.headers.unknown] == [
        ("{urn:example:v}Vendor", True)
    ]
    assert result.headers.hold_requests is True


def test_bad_boolean_header_refused():
    with pytest.raises(EnvelopeError):
        decode_envelope(wrap("<cwmp:Reboot/>", "<cwmp:HoldRequests>maybe</cwmp:HoldRequests>"))


@pytest.mark.parametrize(
    "fault",
    [
        "<faultcode>Other</faultcode><faultstring>CWMP fault</faultstring>",
        "<faultcode>Client</faultcode><faultstring>nope</faultstring>",
        "<faultcode>Client</faultcode><faultstring>CWMP fault</faultstring>",
        "<faultcode>Client</faultcode><faultstring>CWMP fault</faultstring><detail/>",
    ],
)
def test_malformed_fault_refused(fault):
    with pytest.raises(EnvelopeError):
        decode_envelope(wrap(f"<soap:Fault>{fault}</soap:Fault>"))


def test_non_numeric_fault_code_refused():
    doc = FAULT.replace(b"9000", b"nine")
    with pytest.raises(EnvelopeError, match="FaultCode"):
        decode_envelope(doc)


def test_decode_never_returns_an_empty_envelope():
    for raw in (b"", b"   ", b"<a/>"):
        with pytest.raises(EnvelopeError):
            decode_envelope(raw)

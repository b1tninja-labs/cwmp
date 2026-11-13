"""encode_envelope, the fault table and the Inform split, against TR-069 Amendment 6 Corrigendum 1.

Expected shapes come from section 3.5 (envelope, headers in Table 4, arrays, faults), A.2.1 Table 12
(anySimpleType), A.3.3.1 Tables 37 to 40 (Inform) and A.5 Tables 87 and 88 (fault codes). The envelopes
here are produced by the encoder and read back by the decoder or by ElementTree; none is copied from the
report.
"""

from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET

import pytest

from cwmp import faults
from cwmp.envelope import (
    Arg,
    Envelope,
    Fault,
    ParameterFault,
    Rpc,
    SessionContext,
    decode_envelope,
    encode_envelope,
)
from cwmp.errors import EncodeError
from cwmp.methods import (
    DeviceId,
    Event,
    ParameterValue,
    build_inform,
    event_array_arg,
    inform_response,
)

ENV = "http://schemas.xmlsoap.org/soap/envelope/"
ENC = "http://schemas.xmlsoap.org/soap/encoding/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
CWMP = "urn:dslforum-org:cwmp-1-2"
DEVICE = DeviceId("Example Co", "00A0C9", "Router", "SN0001")
NOW = dt.datetime(2026, 11, 13, 6, 30, 0, tzinfo=dt.timezone(dt.timedelta(hours=-8)))
MUST = f"{{{ENV}}}mustUnderstand"


def parse(raw: bytes) -> ET.Element:
    return ET.fromstring(raw)  # noqa: S314


def test_encode_envelope_round_trips_through_the_decoder():
    rpc = Rpc("GetParameterNames", (Arg("ParameterPath", "Device."), Arg("NextLevel", "0")))
    result = decode_envelope(encode_envelope(rpc, SessionContext(id="1234")))
    assert isinstance(result, Envelope)
    assert (result.method, result.id, result.cwmp_namespace) == ("GetParameterNames", "1234", CWMP)
    assert [(c.tag, c.text) for c in result.body] == [
        ("ParameterPath", "Device."),
        ("NextLevel", "0"),
    ]
    assert result.headers.unknown == ()


def test_arguments_are_unqualified_and_the_method_is_in_the_cwmp_namespace():
    root = parse(encode_envelope(Rpc("Reboot", (Arg("CommandKey", "k"),)), SessionContext()))
    method = root.find(f"{{{ENV}}}Body/{{{CWMP}}}Reboot")
    assert method is not None
    assert method[0].tag == "CommandKey"


def test_id_header_must_be_understood():
    root = parse(encode_envelope(Rpc("Reboot"), SessionContext(id="a<b")))
    header = root.find(f"{{{ENV}}}Header/{{{CWMP}}}ID")
    assert header is not None
    assert header.text == "a<b"
    assert header.get(MUST) == "1"


def test_table_4_headers_and_their_senders():
    cpe = SessionContext(sender="cpe", session_timeout=45, supported_versions=("1.0", "1.4"))
    root = parse(encode_envelope(Rpc("Inform"), cpe))
    timeout = root.find(f"{{{ENV}}}Header/{{{CWMP}}}SessionTimeout")
    versions = root.find(f"{{{ENV}}}Header/{{{CWMP}}}SupportedCWMPVersions")
    assert timeout is not None
    assert timeout.text == "45"
    assert timeout.get(MUST) == "0"
    assert versions is not None
    assert versions.text == "1.0,1.4"
    assert versions.get(MUST) == "0"
    acs = SessionContext(sender="acs", hold_requests=True, use_version="1.4")
    root = parse(encode_envelope(Rpc("InformResponse"), acs))
    hold = root.find(f"{{{ENV}}}Header/{{{CWMP}}}HoldRequests")
    use = root.find(f"{{{ENV}}}Header/{{{CWMP}}}UseCWMPVersion")
    assert hold is not None
    assert hold.text == "1"
    assert hold.get(MUST) == "1"
    assert use is not None
    assert use.text == "1.4"
    assert use.get(MUST) == "1"


@pytest.mark.parametrize(
    ("method", "session"),
    [
        ("Inform", SessionContext(sender="acs", session_timeout=45)),
        ("GetRPCMethods", SessionContext(sender="cpe", session_timeout=45)),
        ("Inform", SessionContext(sender="cpe", session_timeout=29)),
        ("Inform", SessionContext(sender="cpe", supported_versions=())),
        ("GetRPCMethods", SessionContext(sender="cpe", supported_versions=("1.4",))),
        ("InformResponse", SessionContext(sender="cpe", use_version="1.4")),
        ("Inform", SessionContext(sender="acs", use_version="1.4")),
        ("Reboot", SessionContext(sender="cpe", hold_requests=True)),
        ("Reboot", SessionContext(hold_requests=True)),
    ],
)
def test_headers_table_4_forbids_are_refused(method, session):
    with pytest.raises(EncodeError):
        encode_envelope(Rpc(method), session)


def test_any_simple_type_needs_a_type_attribute():
    with pytest.raises(EncodeError, match="anySimpleType"):
        encode_envelope(Rpc("X", (Arg("Value", "1", any_simple=True),)), SessionContext())
    typed = Arg("Value", "code12345", xsi_type="xsd:string", any_simple=True)
    root = parse(encode_envelope(Rpc("X", (typed,)), SessionContext()))
    value = root.find(f"{{{ENV}}}Body/{{{CWMP}}}X/Value")
    assert value is not None
    assert value.get(f"{{{XSI}}}type") == "xsd:string"
    with pytest.raises(EncodeError, match="prefix"):
        encode_envelope(Rpc("X", (Arg("V", "1", xsi_type="string"),)), SessionContext())


def test_array_members_are_named_for_their_type_and_unqualified():
    methods = Arg(
        "MethodList",
        children=(Arg("string", "GetRPCMethods"), Arg("string", "Inform")),
        array_type="xsd:string",
    )
    root = parse(encode_envelope(Rpc("GetRPCMethodsResponse", (methods,)), SessionContext()))
    listing = root.find(f"{{{ENV}}}Body/{{{CWMP}}}GetRPCMethodsResponse/MethodList")
    assert listing is not None
    assert listing.get(f"{{{ENC}}}arrayType") == "xsd:string[2]"
    assert [c.tag for c in listing] == ["string", "string"]
    bad = Arg("MethodList", children=(Arg("item", "x"),), array_type="xsd:string")
    with pytest.raises(EncodeError, match="named for its type"):
        encode_envelope(Rpc("X", (bad,)), SessionContext())
    with pytest.raises(EncodeError, match="prefix"):
        encode_envelope(Rpc("X", (Arg("L", array_type="string"),)), SessionContext())


def test_fault_round_trips_and_carries_the_fixed_faultstring():
    parameter_faults = (ParameterFault("Device.A.B", 9007, "bad & worse"),)
    fault = Fault(9003, "Invalid arguments", parameter_faults, "Client", CWMP)
    raw = encode_envelope(fault, SessionContext(id="77", in_reply_to="request"))
    result = decode_envelope(raw)
    assert isinstance(result, Fault)
    assert (result.code, result.string, result.faultcode) == (9003, "Invalid arguments", "Client")
    assert result.parameter_faults == parameter_faults
    assert result.headers.id == "77"
    assert result.cwmp_namespace == CWMP
    assert b"<faultstring>CWMP fault</faultstring>" in raw


@pytest.mark.parametrize("reply", [None, "response", "fault"])
def test_no_fault_in_answer_to_a_response_or_a_fault(reply):
    fault = Fault(9002, "x", (), "Server", CWMP)
    with pytest.raises(EncodeError, match="request"):
        encode_envelope(fault, SessionContext(in_reply_to=reply))


def test_fault_needs_client_or_server():
    fault = Fault(9002, "x", (), "Receiver", CWMP)
    with pytest.raises(EncodeError, match="Client nor Server"):
        encode_envelope(fault, SessionContext(in_reply_to="request"))


def test_encoder_refuses_what_xml_cannot_carry():
    with pytest.raises(EncodeError, match="cannot carry"):
        encode_envelope(Rpc("X", (Arg("A", "bell\x07"),)), SessionContext())
    with pytest.raises(EncodeError, match="not an XML name"):
        encode_envelope(Rpc("X", (Arg("a b", "1"),)), SessionContext())
    with pytest.raises(EncodeError, match="not an XML name"):
        encode_envelope(Rpc("X><evil"), SessionContext())
    with pytest.raises(EncodeError, match="namespace"):
        encode_envelope(Rpc("X"), SessionContext(namespace="urn:example:other"))
    with pytest.raises(EncodeError, match="both text and children"):
        encode_envelope(Rpc("X", (Arg("A", "t", (Arg("B"),)),)), SessionContext())


def test_injection_in_text_is_escaped_not_interpreted():
    raw = encode_envelope(Rpc("X", (Arg("A", "</A><B/>&amp;"),)), SessionContext())
    result = decode_envelope(raw)
    assert isinstance(result, Envelope)
    assert result.body[0].text == "</A><B/>&amp;"
    assert len(result.body) == 1


def test_fault_code_table_tables_87_and_88():
    assert sorted(faults.CPE_FAULTS) == list(range(9000, 9033))
    assert sorted(faults.ACS_FAULTS) == list(range(8000, 8007))
    assert faults.soap_faultcode(9003) == "Client"
    assert faults.soap_faultcode(9002) == "Server"
    assert faults.soap_faultcode(9005) == "Client"
    assert faults.soap_faultcode(9009) == "Server"
    assert faults.soap_faultcode(8003) == "Client"
    assert faults.soap_faultcode(8005) == "Server"
    assert faults.soap_faultcode(9020) == "Client"
    assert faults.soap_faultcode(9022) == "Server"
    assert faults.is_cpe_code(9850)
    assert faults.is_acs_code(8899)
    assert not faults.is_cpe_code(9100)
    assert not faults.is_acs_code(9000)
    with pytest.raises(ValueError, match="no Type"):
        faults.soap_faultcode(9850)  # vendor-defined: the table shows no Type


def test_inform_is_split_into_device_id_events_and_parameter_list():
    inform = build_inform(
        DEVICE,
        [Event("0 BOOTSTRAP"), Event("1 BOOT"), Event("M Reboot", "key1")],
        current_time=NOW,
        parameters=[ParameterValue("Device.DeviceInfo.SoftwareVersion", "1.2.3")],
        retry_count=2,
    )
    raw = encode_envelope(inform, SessionContext(id="1", sender="cpe", supported_versions=("1.4",)))
    body = parse(raw).find(f"{{{ENV}}}Body/{{{CWMP}}}Inform")
    assert body is not None
    assert [c.tag for c in body] == [
        "DeviceId",
        "Event",
        "MaxEnvelopes",
        "CurrentTime",
        "RetryCount",
        "ParameterList",
    ]
    device = body.find("DeviceId")
    assert device is not None
    assert [c.tag for c in device] == ["Manufacturer", "OUI", "ProductClass", "SerialNumber"]
    events = body.find("Event")
    assert events is not None
    assert events.get(f"{{{ENC}}}arrayType") == "cwmp:EventStruct[3]"
    assert [e.findtext("EventCode") for e in events] == ["0 BOOTSTRAP", "1 BOOT", "M Reboot"]
    assert events[2].findtext("CommandKey") == "key1"
    assert body.findtext("MaxEnvelopes") == "1"
    assert body.findtext("RetryCount") == "2"
    assert body.findtext("CurrentTime") == "2026-11-13T06:30:00-08:00"
    plist = body.find("ParameterList")
    assert plist is not None
    assert plist.get(f"{{{ENC}}}arrayType") == "cwmp:ParameterValueStruct[1]"
    value = plist[0].find("Value")
    assert value is not None
    assert value.get(f"{{{XSI}}}type") == "xsd:string"
    decoded = decode_envelope(raw)
    assert isinstance(decoded, Envelope)
    assert decoded.method == "Inform"


def test_inform_limits_come_from_tables_37_to_40():
    with pytest.raises(EncodeError, match="OUI"):
        build_inform(DeviceId("m", "00a0c9", "p", "s"), [], current_time=NOW)
    with pytest.raises(EncodeError, match="Manufacturer"):
        build_inform(DeviceId("m" * 65, "00A0C9", "p", "s"), [], current_time=NOW)
    with pytest.raises(EncodeError, match="CommandKey"):
        build_inform(DEVICE, [Event("1 BOOT", "k" * 33)], current_time=NOW)
    with pytest.raises(EncodeError, match="time-zone"):
        build_inform(DEVICE, [], current_time=dt.datetime(2026, 1, 1))
    with pytest.raises(EncodeError, match="RetryCount"):
        build_inform(DEVICE, [], current_time=NOW, retry_count=-1)


def test_more_than_64_events_discards_the_oldest_method_events():
    events = [
        Event("M Reboot", "old"),
        *(Event(f"X {i}") for i in range(63)),
        Event("M Download", "new"),
    ]
    arg = event_array_arg(events)
    assert len(arg.children) == 64
    keys = [c.children[1].text for c in arg.children]
    assert "old" not in keys
    assert "new" in keys
    with pytest.raises(EncodeError, match="no method-related"):
        event_array_arg([Event(f"X {i}") for i in range(65)])


def test_inform_response_carries_max_envelopes_one():
    result = decode_envelope(encode_envelope(inform_response(), SessionContext(id="1")))
    assert isinstance(result, Envelope)
    assert result.method == "InformResponse"
    assert result.body[0].tag == "MaxEnvelopes"
    assert result.body[0].text == "1"

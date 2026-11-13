"""GetParameterNames as an RPC (TR-069 Amendment 6 Corrigendum 1, A.3.2.3, Tables 20 to 22).

The data model and instances are those of ``tests/test_get_parameter_names.py``; the envelopes are encoded and read
back through the library's own codec, and the expected names are the specification's example for ``Device.Hosts.``.
"""

from __future__ import annotations

import pytest
from test_get_parameter_names import HOSTS_ALL, MODEL

from cwmp.datamodel import load_model
from cwmp.envelope import (
    Envelope,
    Fault,
    SessionContext,
    decode_envelope,
    encode_envelope,
)
from cwmp.errors import EncodeError, EnvelopeError
from cwmp.instances import InstanceTree, ParameterInfo
from cwmp.methods import (
    answer_get_parameter_names,
    get_parameter_names_request,
    get_parameter_names_response,
    parse_get_parameter_names,
)

REQUEST_CTX = SessionContext(id="7", sender="acs")
REPLY_CTX = SessionContext(id="7", sender="cpe", in_reply_to="request")


def make_tree() -> InstanceTree:
    return InstanceTree(load_model(MODEL), ["Device.Hosts.Host.1."])


def roundtrip(rpc, ctx):
    return decode_envelope(encode_envelope(rpc, ctx))


def test_get_parameter_names_rpc():
    request = roundtrip(get_parameter_names_request("Device.Hosts.", False), REQUEST_CTX)
    assert isinstance(request, Envelope)
    assert parse_get_parameter_names(request) == ("Device.Hosts.", False)
    top = roundtrip(get_parameter_names_request("", True), REQUEST_CTX)
    assert isinstance(top, Envelope)
    assert parse_get_parameter_names(top) == ("", True)

    answer = answer_get_parameter_names(make_tree(), "Device.Hosts.", False)
    response = roundtrip(answer, REPLY_CTX)
    assert isinstance(response, Envelope)
    assert response.method == "GetParameterNamesResponse"
    members = list(response.body[0])
    assert [m.findtext("Name") for m in members] == HOSTS_ALL
    # Table 22: Name then Writable; the model's own access says AddObject is not allowed on Host here
    assert all(m.findtext("Writable") in ("0", "1") for m in members)
    assert [c.tag for c in members[0]] == ["Name", "Writable"]


def test_array_type_counts_the_members():
    raw = encode_envelope(
        get_parameter_names_response(
            [ParameterInfo("Device.", False), ParameterInfo("Device.X", True)]
        ),
        REPLY_CTX,
    )
    assert b"cwmp:ParameterInfoStruct[2]" in raw
    assert b"<Writable>1</Writable>" in raw


def test_the_9005_and_9003_faults_are_encoded_and_decoded():
    tree = make_tree()
    missing = answer_get_parameter_names(tree, "Device.Nope.", False)
    assert isinstance(missing, Fault)
    assert (missing.code, missing.faultcode) == (9005, "SOAP-ENV:Client")
    decoded = roundtrip(missing, REPLY_CTX)
    assert isinstance(decoded, Fault)
    assert decoded.code == 9005
    # NextLevel true with a parameter name is 9003, but an invalid path is 9005 first
    leaf = answer_get_parameter_names(tree, "Device.Hosts.HostNumberOfEntries", True)
    assert isinstance(leaf, Fault)
    assert leaf.code == 9003
    leaf_back = roundtrip(leaf, REPLY_CTX)
    assert isinstance(leaf_back, Fault)
    assert leaf_back.code == 9003


def test_9004_only_for_next_level_false_over_the_limit():
    tree = make_tree()
    over = answer_get_parameter_names(tree, "Device.Hosts.", False, max_parameters=3)
    assert isinstance(over, Fault)
    assert (over.code, over.faultcode) == (9004, "SOAP-ENV:Server")
    # "If NextLevel is true the CPE MUST NOT return the 9004 fault code in any case."
    ok = answer_get_parameter_names(tree, "Device.Hosts.", True, max_parameters=0)
    assert not isinstance(ok, Fault)
    assert not isinstance(
        answer_get_parameter_names(tree, "Device.Hosts.", False, max_parameters=len(HOSTS_ALL)),
        Fault,
    )


def test_request_arguments_are_checked():
    with pytest.raises(EncodeError):
        get_parameter_names_request("a" * 257, False)
    with pytest.raises(EncodeError):
        get_parameter_names_response([ParameterInfo("a" * 257, False)])
    other = decode_envelope(encode_envelope(get_parameter_names_response([]), REPLY_CTX))
    assert isinstance(other, Envelope)
    with pytest.raises(EnvelopeError):
        parse_get_parameter_names(other)
    bad = encode_envelope(get_parameter_names_request("Device.", False), REQUEST_CTX).replace(
        b">0</NextLevel>", b">maybe</NextLevel>"
    )
    parsed = decode_envelope(bad)
    assert isinstance(parsed, Envelope)
    with pytest.raises(EnvelopeError):
        parse_get_parameter_names(parsed)

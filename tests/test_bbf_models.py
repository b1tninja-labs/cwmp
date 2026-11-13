"""load_model, resolve_path and coerce_value against the Broadband Forum's published Device:2.22 files.

The files are fetched by ``tools/fetch_bbf.py`` into a cache outside the repository (``$CWMP_DATA_CACHE``, else
the user cache directory), pinned there by sha256 and size. Every test here skips, loudly, when the cache is
absent or a file does not match its pin; the synthetic models in ``test_datamodel.py`` pin the same behaviour
without the network. Nothing from the files is copied into the repository.

The counts asserted below were measured on 2026-11-13 from ``tr-181-2-22-0-cwmp-full.xml`` (sha256 d331ed72...,
5,425,272 bytes) by reading the XML directly, not through ``load_model``.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from devicespy import xmlsafe

from cwmp.datamodel import (
    UNKNOWN_TIME,
    CoerceError,
    DataModel,
    ObjectDef,
    ParameterDef,
    PathError,
    coerce_value,
    load_model,
    resolve_path,
    resolve_syntax,
)

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "fetch_bbf.py"
_spec = importlib.util.spec_from_file_location("fetch_bbf", _TOOL)
assert _spec is not None
assert _spec.loader is not None
fetch_bbf = importlib.util.module_from_spec(_spec)
sys.modules["fetch_bbf"] = fetch_bbf
_spec.loader.exec_module(fetch_bbf)

FULL = "tr-181-2-22-0-cwmp-full.xml"
TYPES = "tr-106-types.xml"


def _cached(name: str) -> bytes:
    root = fetch_bbf.cache_dir()
    pin = next(p for p in fetch_bbf.PINS if p.name == name)
    problem = fetch_bbf.check(root / name, pin)
    if problem is not None:
        pytest.skip(f"SKIPPED LOUDLY: {name} in {root}: {problem}; run tools/fetch_bbf.py")
    return (root / name).read_bytes()


@pytest.fixture(scope="module")
def real() -> DataModel:
    return load_model(_cached(TYPES), _cached(FULL))


@pytest.fixture(scope="module")
def full_only() -> DataModel:
    return load_model(_cached(FULL))


def test_the_pins_agree_with_primarysources_catalogue():
    # primarysource's bbf catalogue lists the same Device:2.22 file at its pinned commit.
    pin = next(p for p in fetch_bbf.PINS if p.name == FULL)
    assert pin.sha256 == "d331ed729226d86b6ee426531eda823289f363fa1a6e4b445531fad79dc581d7"
    assert pin.size == 5425272


def test_load_model_counts_match_the_xml_read_directly(real):
    root = xmlsafe.parse(
        _cached(FULL),
        16 << 20,
        max_depth=64,
        max_elements=2_000_000,
        ignore_processing_instructions=True,
    )
    model = next(c for c in root if c.tag == "model")
    objects = [o for o in model if o.tag == "object"]
    parameters = [p for o in objects for p in o if p.tag == "parameter"]
    assert (len(objects), len(parameters)) == (1029, 8638)
    assert real.model == "Device:2.22"
    assert len(real.objects) == 1029
    assert len(real.parameters) == 8638
    assert [o.path for o in real.roots] == ["Device."]


def test_a_multi_instance_object_is_exactly_one_that_ends_in_a_placeholder(real):
    multi = [o for o in real.objects.values() if o.multi]
    assert len(multi) == 524
    assert all(o.path.endswith(".{i}.") for o in multi)
    assert not any(o.max_entries == 1 for o in multi)
    assert all(o.path.endswith(".{i}.") for o in real.objects.values() if o.access == "readWrite")


def test_every_parameter_has_a_type_and_every_named_type_resolves(real):
    assert all(p.syntax is not None for p in real.parameters.values())
    for name, syntax in real.data_types.items():
        assert resolve_syntax(real, syntax).base in {
            "string",
            "int",
            "unsignedInt",
            "long",
            "unsignedLong",
            "boolean",
            "dateTime",
            "base64",
            "hexBinary",
            "decimal",
        }, name
    for parameter in real.parameters.values():
        assert parameter.syntax is not None
        resolve_syntax(real, parameter.syntax)


def test_the_types_file_with_its_entities_equals_the_flattened_types(real):
    # tr-106-types.xml spells its patterns with &octet; and friends; the full file has them already written out.
    types = load_model(_cached(TYPES))
    full = load_model(_cached(FULL))
    assert len(types.data_types) == 26
    for name in (
        "IPv4Address",
        "IPv4Prefix",
        "MACAddress",
        "UUID",
        "IEEE_EUI64",
        "ZigBeeNetworkAddress",
    ):
        assert types.data_types[name].patterns, name
        assert types.data_types[name].patterns == full.data_types[name].patterns, name
        assert not any("&" in p for p in types.data_types[name].patterns)
    assert (types.data_types["IPv4Address"].patterns[1]).startswith("((25[0-5]|2[0-4][0-9]|[01]?")


def test_a_changed_types_file_is_refused_not_parsed():
    raw = _cached(TYPES)
    with pytest.raises(xmlsafe.XmlForbidden):
        load_model(raw.replace(b"&octet;", b"&octet;&octet;", 1)[:-1] + b"\n")


def test_resolve_path_on_instances_aliases_and_wildcards(real):
    found = resolve_path(real, "Device.IP.Interface.1.IPv4Address.2.IPAddress")[0]
    assert found.kind == "parameter"
    assert found.instances == ("1", "2")
    assert isinstance(found.definition, ParameterDef)
    assert found.definition.path == "Device.IP.Interface.{i}.IPv4Address.{i}.IPAddress"
    assert found.definition.syntax is not None
    assert found.definition.syntax.base == "IPv4Address"
    alias = resolve_path(real, "Device.WiFi.SSID.[guest].Enable")[0]
    assert alias.alias
    assert alias.definition.path == "Device.WiFi.SSID.{i}.Enable"
    wild = resolve_path(real, "Device.Hosts.Host.*.IPAddress")[0]
    assert wild.wildcard
    table = resolve_path(real, "Device.Hosts.Host.")[0]
    assert isinstance(table.definition, ObjectDef)
    assert table.definition.multi
    assert resolve_path(real, "Device.Hosts.Host.3.")[0].definition is table.definition
    assert [r.path for r in resolve_path(real, "")] == ["Device."]
    for bad in (
        "Device.NoSuchThing.",
        "Device.IP.Interface.x.Enable",
        "Device.IP.Interface.0.Enable",
    ):
        with pytest.raises(PathError):
            resolve_path(real, bad)
    with pytest.raises(PathError, match="names an object"):
        resolve_path(real, "Device.DeviceInfo")


def test_every_template_path_in_the_published_model_resolves_back_to_itself(real):
    for template, definition in real.objects.items():
        path = template.replace("{i}", "7")
        assert resolve_path(real, path)[0].definition is definition, template
    for template, parameter in real.parameters.items():
        path = template.replace("{i}", "7")
        assert resolve_path(real, path)[0].definition is parameter, template
        wild = template.replace("{i}", "*")
        assert resolve_path(real, wild)[0].definition is parameter, template
        alias = template.replace("{i}", "[a]")
        assert resolve_path(real, alias)[0].definition is parameter, template


def test_defaults_the_model_states_coerce_to_their_own_types(real):
    root = xmlsafe.parse(
        _cached(FULL),
        16 << 20,
        max_depth=64,
        max_elements=2_000_000,
        ignore_processing_instructions=True,
    )
    model = next(c for c in root if c.tag == "model")
    checked = 0
    for obj in model:
        if obj.tag != "object":
            continue
        for parameter in obj.findall("parameter"):
            default = parameter.find("syntax/default")
            if default is None or default.get("type") != "object":
                continue
            definition = real.parameters[obj.get("name", "") + parameter.get("name", "")]
            text = default.get("value", "")
            assert definition.syntax is not None
            if definition.syntax.is_list:
                # the published files write a list's default in square brackets, which is not the wire form
                assert text.startswith("[")
                assert text.endswith("]")
                text = text[1:-1]
            coerce_value(definition, text, model=real)
            checked += 1
    assert checked == 1262


# TR-181 Device:2.22 gives these two unsignedInt parameters a range that starts at -1, which no unsignedInt
# (Table 12: 0 to 4294967295) can carry. coerce_value keeps the type's own bounds, so -1 is refused for them.
_NEGATIVE_UNSIGNED = {
    "Device.Routing.Router.{i}.IPv4Forwarding.{i}.MTU",
    "Device.Routing.Router.{i}.IPv6Forwarding.{i}.MTU",
}


def test_every_range_in_the_published_model_is_enforced_at_both_ends(real):
    tested = 0
    for parameter in real.parameters.values():
        assert parameter.syntax is not None
        syntax = resolve_syntax(real, parameter.syntax)
        if syntax.is_list or syntax.base not in ("int", "unsignedInt") or not syntax.ranges:
            continue
        if parameter.path in _NEGATIVE_UNSIGNED:
            assert syntax.ranges[0] == (-1, -1)
            with pytest.raises(CoerceError):
                coerce_value(parameter, "-1", model=real)
            coerce_value(parameter, str(syntax.ranges[1][0]), model=real)
            continue
        for low, high in syntax.ranges:
            if low is not None:
                coerce_value(parameter, str(low), model=real)
            if high is not None:
                coerce_value(parameter, str(high), model=real)
        lows = [low for low, _ in syntax.ranges]
        highs = [high for _, high in syntax.ranges]
        if len(syntax.ranges) == 1 and None not in lows and None not in highs:
            with pytest.raises(CoerceError):
                coerce_value(parameter, str(highs[0] + 1), model=real)
            with pytest.raises(CoerceError):
                coerce_value(parameter, str(lows[0] - 1), model=real)
        tested += 1
    assert tested > 600


def test_named_types_from_the_published_model(real):
    def parameter(path: str) -> ParameterDef:
        return resolve_path(real, path)[0].definition  # type: ignore[return-value]

    address = parameter("Device.IP.Interface.1.IPv4Address.1.IPAddress")
    assert coerce_value(address, "192.168.1.1", model=real) == "192.168.1.1"
    assert coerce_value(address, "", model=real) == ""
    for bad in ("256.1.1.1", "1.2.3", "::1", "1.2.3.4.5", "a.b.c.d"):
        with pytest.raises(CoerceError):
            coerce_value(address, bad, model=real)
    mac = parameter("Device.Ethernet.Interface.1.MACAddress")
    assert coerce_value(mac, "00:1a:2B:3c:4D:5e", model=real) == "00:1a:2B:3c:4D:5e"
    with pytest.raises(CoerceError):
        coerce_value(mac, "00-1a-2b-3c-4d-5e", model=real)
    counter = parameter("Device.Ethernet.Interface.1.Stats.BytesSent")
    assert coerce_value(counter, "18446744073709551615", model=real) == 2**64 - 1
    with pytest.raises(CoerceError):
        coerce_value(counter, "18446744073709551616", model=real)
    status = parameter("Device.Ethernet.Interface.1.Status")
    assert coerce_value(status, "Up", model=real) == "Up"
    with pytest.raises(CoerceError):
        coerce_value(status, "up", model=real)


def test_datetime_parameters_of_the_published_model(real):
    updated = parameter = real.parameters["Device.Time.CurrentLocalTime"]
    assert coerce_value(updated, "2026-11-13T12:30:45Z", model=real) == datetime(
        2026, 11, 13, 12, 30, 45, tzinfo=UTC
    )
    assert coerce_value(parameter, "0001-01-01T00:00:00Z", model=real) == UNKNOWN_TIME
    assert coerce_value(parameter, "0001-01-03T03:04:05", model=real) == timedelta(
        days=2, hours=3, minutes=4, seconds=5
    )
    with pytest.raises(CoerceError):
        coerce_value(parameter, "2026-11-13T12:30:45", model=real)


def test_a_list_parameter_of_the_published_model(real):
    servers = real.parameters["Device.PPP.Interface.{i}.IPCP.DNSServers"]
    assert coerce_value(servers, "1.1.1.1,8.8.8.8", model=real) == ["1.1.1.1", "8.8.8.8"]
    with pytest.raises(CoerceError):
        coerce_value(servers, "1.1.1.1,8.8.8.8,9.9.9.9", model=real)
    with pytest.raises(CoerceError):
        coerce_value(servers, "1.1.1.1,nope", model=real)


def test_the_flattened_file_alone_is_a_complete_model(full_only, real):
    assert set(full_only.parameters) == set(real.parameters)
    assert set(full_only.objects) == set(real.objects)

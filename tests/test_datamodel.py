"""resolve_path against a data model in the Broadband Forum's XML layout.

The model below is written for these tests in the shape of the cwmp-data-models files (a ``dm:document``
holding a ``component`` and a ``model``); it is not a copy of any published file, and the published TR-181
files have not been read by this suite (ROADMAP.md). Path rules are those of TR-069 Amendment 6
Corrigendum 1, A.2.2 (instance identifiers), A.2.4 (wildcards) and A.3.2.3 (partial paths).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from devicespy import xmlsafe

from cwmp.datamodel import (
    UNKNOWN_TIME,
    CoerceError,
    DataModel,
    ObjectDef,
    ParameterDef,
    PathError,
    children,
    coerce_value,
    load_model,
    resolve_path,
)

COMPONENT = b"""<?xml version="1.0" encoding="UTF-8"?>
<dm:document xmlns:dm="urn:broadband-forum-org:cwmp:datamodel-1-8" spec="urn:example:test-1-0">
  <component name="IP">
    <object name="Device.IP." access="readOnly" minEntries="1" maxEntries="1">
      <parameter name="Enable" access="readWrite"><syntax><boolean/></syntax></parameter>
      <parameter name="InterfaceNumberOfEntries" access="readOnly">
        <syntax><unsignedInt/></syntax>
      </parameter>
    </object>
    <object name="Device.IP.Interface.{i}." access="readWrite" minEntries="0" maxEntries="unbounded">
      <parameter name="Alias" access="readWrite"><syntax><string><size maxLength="64"/></string></syntax></parameter>
      <parameter name="Status" access="readOnly">
        <syntax><string><enumeration value="Up"/><enumeration value="Down"/></string></syntax>
      </parameter>
      <parameter name="MTU" access="readWrite">
        <syntax><unsignedInt><range minInclusive="64" maxInclusive="65535"/></unsignedInt></syntax>
      </parameter>
    </object>
    <object name="Device.IP.Interface.{i}.IPv4Address.{i}." access="readWrite">
      <parameter name="IPAddress" access="readWrite"><syntax><dataType ref="IPAddress"/></syntax></parameter>
    </object>
  </component>
</dm:document>"""

MODEL = b"""<?xml version="1.0" encoding="UTF-8"?>
<dm:document xmlns:dm="urn:broadband-forum-org:cwmp:datamodel-1-8" spec="urn:example:test-1-0">
  <dataType name="IPAddress"><string><size maxLength="45"/></string></dataType>
  <model name="Device:2.0">
    <object name="Device." access="readOnly" minEntries="1" maxEntries="1">
      <parameter name="InterfaceStackNumberOfEntries" access="readOnly"><syntax><unsignedInt/></syntax></parameter>
    </object>
    <component ref="IP"/>
  </model>
</dm:document>"""


@pytest.fixture(scope="module")
def tree() -> DataModel:
    return load_model(COMPONENT, MODEL)


def test_load_model_reads_objects_parameters_and_types(tree):
    assert tree.model == "Device:2.0"
    assert "Device.IP.Interface.{i}." in tree.objects
    assert tree.objects["Device.IP.Interface.{i}."].multi
    assert not tree.objects["Device.IP."].multi
    assert tree.objects["Device.IP."].max_entries == 1
    mtu = tree.parameters["Device.IP.Interface.{i}.MTU"]
    assert mtu.access == "readWrite"
    assert mtu.syntax is not None
    assert (mtu.syntax.base, mtu.syntax.minimum, mtu.syntax.maximum) == ("unsignedInt", 64, 65535)
    status = tree.parameters["Device.IP.Interface.{i}.Status"]
    assert status.syntax is not None
    assert status.syntax.enumeration == ("Up", "Down")
    address = tree.parameters["Device.IP.Interface.{i}.IPv4Address.{i}.IPAddress"]
    assert address.syntax is not None
    assert address.syntax.base == "IPAddress"
    assert tree.data_types["IPAddress"].max_length == 45
    assert [o.path for o in tree.roots] == ["Device."]


def test_resolve_path_parameter_with_instance_number(tree):
    (hit,) = resolve_path(tree, "Device.IP.Interface.3.MTU")
    assert hit.kind == "parameter"
    assert isinstance(hit.definition, ParameterDef)
    assert hit.definition.path == "Device.IP.Interface.{i}.MTU"
    assert hit.instances == ("3",)
    assert not hit.alias
    assert not hit.wildcard
    (nested,) = resolve_path(tree, "Device.IP.Interface.3.IPv4Address.12.IPAddress")
    assert nested.instances == ("3", "12")


def test_partial_paths_end_with_a_dot_and_address_objects(tree):
    (top,) = resolve_path(tree, "Device.")
    assert top.kind == "object"
    assert isinstance(top.definition, ObjectDef)
    (row,) = resolve_path(tree, "Device.IP.Interface.3.")
    assert row.definition.path == "Device.IP.Interface.{i}."
    assert row.instances == ("3",)
    (table,) = resolve_path(tree, "Device.IP.Interface.")  # the multi-instance node itself
    assert table.definition.path == "Device.IP.Interface.{i}."
    assert table.instances == ()
    assert [r.path for r in resolve_path(tree, "")] == ["Device."]
    with pytest.raises(PathError, match="names an object"):
        resolve_path(tree, "Device.IP.Interface.3")


def test_instance_alias_and_wildcard_are_optional_forms(tree):
    (aliased,) = resolve_path(tree, "Device.IP.Interface.[cpe-1].MTU")
    assert aliased.alias
    assert aliased.instances == ("[cpe-1]",)
    (mixed,) = resolve_path(tree, "Device.IP.Interface.[a].IPv4Address.2.IPAddress")
    assert mixed.alias
    assert not mixed.wildcard
    (wild,) = resolve_path(tree, "Device.IP.Interface.*.IPv4Address.")
    assert wild.wildcard
    assert wild.instances == ("*",)
    (wild2,) = resolve_path(tree, "Device.IP.Interface.*.IPv4Address.*.IPAddress")
    assert wild2.instances == ("*", "*")
    with pytest.raises(PathError, match="Aliases are not enabled"):
        resolve_path(tree, "Device.IP.Interface.[a].MTU", aliases=False)
    with pytest.raises(PathError, match="wildcards are not enabled"):
        resolve_path(tree, "Device.IP.Interface.*.MTU", wildcards=False)


def test_the_wildcard_may_not_be_the_last_part_or_stand_for_a_non_instance(tree):
    # the report's own invalid examples (A.2.4): wildcard last, wildcard not replacing an instance
    with pytest.raises(PathError, match="last part"):
        resolve_path(tree, "Device.IP.Interface.*.")
    with pytest.raises(PathError, match="last part"):
        resolve_path(tree, "Device.IP.Interface.*")
    with pytest.raises(PathError, match="not a valid node name"):
        resolve_path(tree, "Device.IP.Interface.1.*.IPAddress")


@pytest.mark.parametrize(
    "path",
    [
        "Device.IP.Interface.0.MTU",
        "Device.IP.Interface.-1.MTU",
        "Device.IP.Interface.abc.MTU",
        "Device.IP.Interface.[].MTU",
        "Device.IP.Interface.[a.MTU",
        "Device.IP.Interface.[a]x.MTU",
        "Device.IP.Interface.4294967296.MTU",
        "Device..IP.",
        "Device.IP.Interface.1.Nope",
        "Nope.",
        ".",
        "Device.IP.Interface.1.MTU.",
        "Device.IP.Enable.1",
        "Device IP.",
    ],
)
def test_malformed_or_unknown_paths_are_refused(tree, path):
    with pytest.raises(PathError):
        resolve_path(tree, path)


def test_a_path_name_is_at_most_256_characters(tree):
    with pytest.raises(PathError, match="string"):
        resolve_path(tree, "Device." + "A" * 260)
    resolve_path(tree, "Device.IP.Interface.4294967295.MTU")  # the largest unsignedInt


def test_children_lists_next_level_nodes_once_per_table(tree):
    names = sorted(c.path for c in children(tree, "Device.IP."))
    assert names == [
        "Device.IP.Enable",
        "Device.IP.Interface.{i}.",
        "Device.IP.InterfaceNumberOfEntries",
    ]
    inner = sorted(c.path for c in children(tree, "Device.IP.Interface.{i}."))
    assert "Device.IP.Interface.{i}.IPv4Address.{i}." in inner
    assert "Device.IP.Interface.{i}.MTU" in inner
    with pytest.raises(PathError):
        children(tree, "Device.IP.Interface.")


def test_hostile_model_documents_are_refused_by_the_shared_reader():
    bomb = b'<!DOCTYPE d [<!ENTITY a "aaaa">]><dm:document xmlns:dm="urn:x">&a;</dm:document>'
    with pytest.raises(xmlsafe.XmlRefused):
        load_model(bomb)
    with pytest.raises(PathError, match="not a data-model document"):
        load_model(b"<html/>")
    with pytest.raises(xmlsafe.XmlRefused):
        load_model(COMPONENT, max_bytes=100)


SYNTHETIC_TYPES = b"""<?xml version="1.0" encoding="UTF-8"?>
<dm:document xmlns:dm="urn:broadband-forum-org:cwmp:datamodel-1-8" spec="urn:example:test-1-0">
  <dataType name="Base"><string><size maxLength="8"/><pattern value=""/><pattern value="[a-z]+"/></string></dataType>
  <dataType name="Derived" base="Base"><size maxLength="4"/></dataType>
  <dataType name="Alias" base="Derived"/>
  <dataType name="Loop1" base="Loop2"/>
  <dataType name="Loop2" base="Loop1"/>
  <model name="Device:2.0">
    <object name="Device." access="readOnly">
      <parameter name="B" access="readWrite"><syntax><boolean/></syntax></parameter>
      <parameter name="I" access="readWrite"><syntax><int><range minInclusive="-5" maxInclusive="5"/></int></syntax></parameter>
      <parameter name="U" access="readWrite"><syntax><unsignedInt/></syntax></parameter>
      <parameter name="L" access="readWrite"><syntax><unsignedLong/></syntax></parameter>
      <parameter name="S" access="readWrite"><syntax><string><enumeration value="a"/><enumeration value="b"/></string></syntax></parameter>
      <parameter name="N" access="readWrite"><syntax><string><size minLength="2" maxLength="3"/></string></syntax></parameter>
      <parameter name="T" access="readWrite"><syntax><dateTime/></syntax></parameter>
      <parameter name="X" access="readWrite"><syntax><base64><size maxLength="4"/></base64></syntax></parameter>
      <parameter name="H" access="readWrite"><syntax><hexBinary/></syntax></parameter>
      <parameter name="D" access="readWrite"><syntax><decimal><range minInclusive="0" maxInclusive="1"/></decimal></syntax></parameter>
      <parameter name="List" access="readWrite"><syntax><list minItems="1" maxItems="3"/><unsignedInt/></syntax></parameter>
      <parameter name="Named" access="readWrite"><syntax><dataType ref="Alias"/></syntax></parameter>
      <parameter name="Loop" access="readWrite"><syntax><dataType ref="Loop1"/></syntax></parameter>
      <parameter name="Missing" access="readWrite"><syntax><dataType ref="Nope"/></syntax></parameter>
    </object>
  </model>
</dm:document>"""


@pytest.fixture(scope="module")
def typed() -> DataModel:
    return load_model(SYNTHETIC_TYPES)


def _coerce(typed: DataModel, name: str, value: object) -> object:
    return coerce_value(typed.parameters["Device." + name], value, model=typed)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1", True), ("true", True), ("0", False), ("false", False)],
)
def test_boolean_takes_the_four_values_of_table_12(typed, text, expected):
    assert _coerce(typed, "B", text) is expected


@pytest.mark.parametrize("text", ["", "TRUE", "True", "yes", "2", " 1", "1 "])
def test_boolean_refuses_everything_else(typed, text):
    with pytest.raises(CoerceError):
        _coerce(typed, "B", text)


def test_integer_ranges_are_the_types_and_the_models(typed):
    assert _coerce(typed, "I", "-5") == -5
    assert _coerce(typed, "I", "5") == 5
    for text in ("6", "-6", "1.0", "", "0x1", "1e2", chr(0x661)):
        with pytest.raises(CoerceError):
            _coerce(typed, "I", text)
    assert _coerce(typed, "U", "4294967295") == 4294967295
    for text in ("4294967296", "-1"):
        with pytest.raises(CoerceError):
            _coerce(typed, "U", text)
    assert _coerce(typed, "L", "18446744073709551615") == 2**64 - 1
    with pytest.raises(CoerceError):
        _coerce(typed, "L", "18446744073709551616")


def test_a_python_int_is_accepted_for_an_integer_but_a_bool_is_not(typed):
    assert _coerce(typed, "U", 7) == 7
    with pytest.raises(CoerceError):
        _coerce(typed, "U", True)
    with pytest.raises(CoerceError):
        _coerce(typed, "B", 1)
    assert _coerce(typed, "B", True) is True


def test_string_enumeration_and_size(typed):
    assert _coerce(typed, "S", "a") == "a"
    with pytest.raises(CoerceError):
        _coerce(typed, "S", "c")
    assert _coerce(typed, "N", "ab") == "ab"
    for text in ("a", "abcd"):
        with pytest.raises(CoerceError):
            _coerce(typed, "N", text)


def test_a_derived_type_inherits_and_narrows(typed):
    # Base allows 8 characters of [a-z]+ or empty; Derived narrows the length to 4; Alias adds nothing.
    assert _coerce(typed, "Named", "abcd") == "abcd"
    assert _coerce(typed, "Named", "") == ""
    for text in ("abcde", "AB"):
        with pytest.raises(CoerceError):
            _coerce(typed, "Named", text)


def test_unresolvable_and_circular_named_types_are_refused(typed):
    with pytest.raises(PathError, match="does not define"):
        _coerce(typed, "Missing", "x")
    with pytest.raises(PathError, match="derives from itself"):
        _coerce(typed, "Loop", "x")
    with pytest.raises(PathError, match="pass the model"):
        coerce_value(typed.parameters["Device.Named"], "x")


def test_datetime_forms_of_table_12(typed):
    utc = datetime(2026, 11, 13, 12, 30, 45, tzinfo=UTC)
    assert _coerce(typed, "T", "2026-11-13T12:30:45Z") == utc
    assert _coerce(typed, "T", "2026-11-13T12:30:45+00:00") == utc
    assert _coerce(typed, "T", "2026-11-13T12:30:45-00:00") == utc
    assert _coerce(typed, "T", "0001-01-01T00:00:00Z") == UNKNOWN_TIME
    # the example Table 12 gives: 2 days, 3 hours, 4 minutes and 5 seconds since boot
    assert _coerce(typed, "T", "0001-01-03T03:04:05") == timedelta(
        days=2, hours=3, minutes=4, seconds=5
    )
    for text in (
        "2026-11-13T12:30:45",  # untimezoned but not a relative time (year 1000 or more)
        "2026-11-13T12:30:45+01:00",  # not UTC
        "2026-11-13",
        "2026-13-13T12:30:45Z",
        "0001-02-30T00:00:00",
        "",
    ):
        with pytest.raises(CoerceError):
            _coerce(typed, "T", text)


def test_base64_and_hexbinary(typed):
    assert _coerce(typed, "X", "AQID") == b"\x01\x02\x03"
    with pytest.raises(CoerceError):
        _coerce(typed, "X", "AQIDBAU=")  # 5 bytes, the model allows 4 before encoding
    for text in ("A", "AQI", "A!ID"):
        with pytest.raises(CoerceError):
            _coerce(typed, "X", text)
    assert _coerce(typed, "H", "00ff") == b"\x00\xff"
    for text in ("0", "0g", "0x00"):
        with pytest.raises(CoerceError):
            _coerce(typed, "H", text)


def test_decimal_is_finite_and_in_range(typed):
    assert _coerce(typed, "D", "0.5") == Decimal("0.5")
    for text in ("2", "NaN", "Infinity", "abc"):
        with pytest.raises(CoerceError):
            _coerce(typed, "D", text)


def test_list_bounds_and_items(typed):
    assert _coerce(typed, "List", "1,2,3") == [1, 2, 3]
    for text in ("", "1,2,3,4", "1,x"):
        with pytest.raises(CoerceError):
            _coerce(typed, "List", text)


def test_a_parameter_without_a_type_is_refused():
    with pytest.raises(CoerceError, match="no type"):
        coerce_value(ParameterDef("Device.X", "readOnly", None), "1")

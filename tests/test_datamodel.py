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
    reference_path,
    resolve_path,
    resolve_syntax,
)
from cwmp.instances import InstanceTree

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


# --- TR-106 facets: step, size on hexBinary and lists, enumerationRef, pathRef (TR-106 Amendment 18, read raw) ---

FACETS = b"""<?xml version="1.0" encoding="UTF-8"?>
<dm:document xmlns:dm="urn:broadband-forum-org:cwmp:datamodel-1-8" spec="urn:example:test-1-0">
  <dataType name="Ethertype"><hexBinary><size minLength="2" maxLength="2"/></hexBinary></dataType>
  <dataType name="RowRef"><string><pathRef targetType="row" refType="strong"/></string></dataType>
  <model name="Device:2.0">
    <object name="Device." access="readOnly" minEntries="1" maxEntries="1">
      <parameter name="Stepped" access="readWrite">
        <syntax><int><range minInclusive="-125" maxInclusive="125" step="125"/></int></syntax>
      </parameter>
      <parameter name="SteppedFromTen" access="readWrite">
        <syntax><unsignedInt><range minInclusive="10" maxInclusive="40" step="10"/><range minInclusive="100" maxInclusive="100"/></unsignedInt></syntax>
      </parameter>
      <parameter name="Fraction" access="readWrite">
        <syntax><decimal><range minInclusive="0.5" maxInclusive="2" step="0.5"/></decimal></syntax>
      </parameter>
      <parameter name="Color" access="readWrite">
        <syntax><hexBinary><size minLength="3" maxLength="3"/></hexBinary></syntax>
      </parameter>
      <parameter name="Ether" access="readWrite"><syntax><dataType ref="Ethertype"/></syntax></parameter>
      <parameter name="Names" access="readWrite">
        <syntax><list><size maxLength="9"/></list><string><size maxLength="4"/></string></syntax>
      </parameter>
      <parameter name="Modes" access="readOnly">
        <syntax><list/><string/></syntax>
      </parameter>
      <parameter name="Chosen" access="readWrite">
        <syntax><string><enumerationRef targetParam="Modes" nullValue="None"/></string></syntax>
      </parameter>
      <parameter name="ChosenFar" access="readWrite">
        <syntax><list/><string><enumerationRef targetParam="#.Modes"/></string></syntax>
      </parameter>
    </object>
    <object name="Device.Box." access="readOnly" minEntries="1" maxEntries="1">
      <parameter name="ModeChoice" access="readWrite">
        <syntax><string><enumerationRef targetParam="#.Modes"/></string></syntax>
      </parameter>
      <parameter name="Ref" access="readWrite">
        <syntax><string><pathRef targetType="parameter" targetDataType="integer"/></string></syntax>
      </parameter>
      <parameter name="Number" access="readOnly"><syntax><unsignedInt/></syntax></parameter>
      <parameter name="Text" access="readOnly"><syntax><string/></syntax></parameter>
    </object>
    <object name="Device.Port.{i}." access="readWrite" minEntries="0" maxEntries="unbounded">
      <parameter name="Name" access="readWrite"><syntax><string/></syntax></parameter>
      <parameter name="Peer" access="readWrite">
        <syntax><string><pathRef targetParent="#.Port." targetType="row" refType="strong"/></string></syntax>
      </parameter>
      <parameter name="Elsewhere" access="readWrite">
        <syntax><string><pathRef targetParent=".Other." targetType="row"/></string></syntax>
      </parameter>
      <parameter name="Table" access="readWrite">
        <syntax><string><pathRef targetType="table"/></string></syntax>
      </parameter>
      <parameter name="Single" access="readWrite">
        <syntax><string><pathRef targetType="single"/></string></syntax>
      </parameter>
      <parameter name="Any" access="readWrite">
        <syntax><dataType ref="RowRef"/></syntax>
      </parameter>
    </object>
    <object name="Device.Other.{i}." access="readWrite" minEntries="0" maxEntries="unbounded">
      <parameter name="Name" access="readWrite"><syntax><string/></syntax></parameter>
    </object>
  </model>
</dm:document>"""


@pytest.fixture(scope="module")
def facets() -> DataModel:
    return load_model(FACETS)


def _facet(facets: DataModel, template: str, value: object, **kwargs: object) -> object:
    return coerce_value(facets.parameters[template], value, model=facets, **kwargs)  # type: ignore[arg-type]


def test_a_range_step_counts_from_the_minimum_of_the_range_it_is_in(facets):
    # TR-106 Table 4: "Value ranges and step (default step is 1)"
    for text in ("-125", "0", "125"):
        assert _facet(facets, "Device.Stepped", text) == int(text)
    for text in ("1", "-124", "62"):
        with pytest.raises(CoerceError, match="step"):
            _facet(facets, "Device.Stepped", text)
    with pytest.raises(CoerceError, match="range"):
        _facet(facets, "Device.Stepped", "250")
    # the step counts from the range's own minimum (10), and the second range has no step
    assert _facet(facets, "Device.SteppedFromTen", "30") == 30
    assert _facet(facets, "Device.SteppedFromTen", "100") == 100
    for text in ("15", "5", "50"):
        with pytest.raises(CoerceError):
            _facet(facets, "Device.SteppedFromTen", text)


def test_a_fractional_range_and_step_on_a_decimal_are_kept(facets):
    syntax = facets.parameters["Device.Fraction"].syntax
    assert syntax is not None
    assert syntax.ranges == ((Decimal("0.5"), 2),)
    assert syntax.steps == (Decimal("0.5"),)
    assert _facet(facets, "Device.Fraction", "1.5") == Decimal("1.5")
    for text in ("0.25", "0.4", "2.5"):
        with pytest.raises(CoerceError):
            _facet(facets, "Device.Fraction", text)


def test_tr106_types_and_list_size(facets):
    # TR-106 Table 4: the size facet of a hexBinary (or base64) refers to the actual value, not the encoded one
    assert _facet(facets, "Device.Color", "FF00aa") == b"\xff\x00\xaa"
    for text in ("FF00", "FF00AA00"):
        with pytest.raises(CoerceError, match="bytes"):
            _facet(facets, "Device.Color", text)
    assert _facet(facets, "Device.Ether", "888E") == b"\x88\x8e"
    with pytest.raises(CoerceError):
        _facet(facets, "Device.Ether", "888E00")
    # the list's own size counts the characters of the whole value, each item is held to the item size
    assert _facet(facets, "Device.Names", "ab,cd") == ["ab", "cd"]
    assert _facet(facets, "Device.Names", "abcd,abcd") == ["abcd", "abcd"]  # 9 characters
    with pytest.raises(CoerceError, match="list's size"):
        _facet(facets, "Device.Names", "abcd,abcd,e")
    with pytest.raises(CoerceError):
        _facet(facets, "Device.Names", "abcde")


def test_enumeration_ref_is_checked_against_the_value_of_the_named_parameter(facets):
    values = {"Device.Modes": "WPA,WPA2"}

    def choose(name: str, text: str, path: str) -> object:
        return _facet(facets, name, text, path=path, lookup=values.get)

    assert choose("Device.Chosen", "WPA2", "Device.Chosen") == "WPA2"
    assert choose("Device.Chosen", "None", "Device.Chosen") == "None"  # the facet's nullValue
    with pytest.raises(CoerceError, match="not among"):
        choose("Device.Chosen", "WEP", "Device.Chosen")
    with pytest.raises(CoerceError, match="not among"):
        choose("Device.Chosen", "", "Device.Chosen")  # no nullValue of "" is designated
    # a list-valued parameter checks every item; an empty list is the "none apply" answer
    assert choose("Device.ChosenFar", "WPA,WPA2", "Device.Box.Anything") == ["WPA", "WPA2"]
    assert choose("Device.ChosenFar", "", "Device.Box.Anything") == []
    with pytest.raises(CoerceError):
        choose("Device.ChosenFar", "WPA,WEP", "Device.Box.Anything")
    # a relative target reads from the object the parameter is in
    assert choose("Device.Box.ModeChoice", "WPA", "Device.Box.ModeChoice") == "WPA"
    with pytest.raises(CoerceError):
        choose("Device.Box.ModeChoice", "TKIP", "Device.Box.ModeChoice")
    # a target with no value cannot be checked against, and without lookup nothing is checked
    with pytest.raises(CoerceError, match="no value"):
        _facet(facets, "Device.Chosen", "WPA", path="Device.Chosen", lookup={}.get)
    assert _facet(facets, "Device.Chosen", "anything") == "anything"


def test_the_enumeration_ref_facet_survives_a_derived_type():
    model = load_model(
        b"""<dm:document xmlns:dm="urn:broadband-forum-org:cwmp:datamodel-1-8" spec="urn:x">
          <dataType name="Pick"><string><enumerationRef targetParam="Modes" nullValue="-"/></string></dataType>
          <dataType name="Pick2" base="Pick"/>
          <model name="Device:2.0"><object name="Device." access="readOnly">
            <parameter name="P" access="readWrite"><syntax><dataType ref="Pick2"/></syntax></parameter>
          </object></model></dm:document>"""
    )
    parameter = model.parameters["Device.P"]
    assert parameter.syntax is not None
    assert resolve_syntax(model, parameter.syntax).enumeration_target == "Modes"
    modes = {"Device.Modes": "a,b"}
    assert coerce_value(parameter, "b", model=model, path="Device.P", lookup=modes.get) == "b"
    with pytest.raises(CoerceError):
        coerce_value(parameter, "c", model=model, path="Device.P", lookup=modes.get)


@pytest.mark.parametrize(
    ("current", "target", "scope", "expected"),
    [
        # the four examples of TR-106 A.2.3.4 for the current object Device.LAN.DHCPOption.{i}.
        ("Device.LAN.DHCPOption.{i}.", "#.", "normal", "Device.LAN."),
        ("Device.LAN.DHCPOption.{i}.", "#.DHCPOption.", "normal", "Device.LAN.DHCPOption."),
        ("Device.LAN.DHCPOption.{i}.", "#.Stats.", "normal", "Device.LAN.Stats."),
        (
            "Device.LAN.DHCPOption.{i}.",
            "#.Stats.TotalBytesSent",
            "normal",
            "Device.LAN.Stats.TotalBytesSent",
        ),
        ("Device.LAN.DHCPOption.{i}.", "##.", "normal", "Device."),
        ("Device.LAN.DHCPOption.{i}.", "##.DeviceInfo.", "normal", "Device.DeviceInfo."),
        # the examples with "Device.LAN." as the current object
        ("Device.LAN.", "IPAddress", "normal", "Device.LAN.IPAddress"),
        ("Device.LAN.", "Stats.", "normal", "Device.LAN.Stats."),
        ("Device.LAN.", "#.DeviceInfo.", "normal", "Device.DeviceInfo."),
        # a full path, a leading dot, the empty path
        ("Device.LAN.", "Device.IP.", "normal", "Device.IP."),
        ("Device.LAN.", ".DeviceInfo.", "normal", "Device.DeviceInfo."),
        ("Device.LAN.", "", "normal", ""),
        # the other scopes
        ("Device.LAN.", "", "model", "Device."),
        ("Device.LAN.", ".IP.", "model", "Device.IP."),
        ("Device.LAN.", "", "object", "Device.LAN."),
        ("Device.LAN.", ".Stats.", "object", "Device.LAN.Stats."),
        ("Device.LAN.", "Device.X.", "absolute", "Device.X."),
        # instance numbers in the current object are carried by a relative path and climbed by a hash
        ("Device.A.3.B.", "C.", "normal", "Device.A.3.B.C."),
        ("Device.A.3.B.", "#.C.", "normal", "Device.A.3.C."),
        ("Device.A.3.B.", "##.C.", "normal", "Device.C."),
        # Device:2.22 writes a bare "#" or "##" for the object climbed to (two of its targetParent values)
        ("Device.A.{i}.B.{i}.", "#", "normal", "Device.A.{i}."),
        ("Device.A.{i}.B.{i}.", "##", "normal", "Device."),
    ],
)
def test_reference_paths_follow_the_scopes_of_tr106_a_2_3_4(current, target, scope, expected):
    assert reference_path(current, target, scope) == expected


@pytest.mark.parametrize(
    ("current", "target", "scope"),
    [
        ("Device.LAN.", "###.", "normal"),  # beyond the Root Object
        ("Device.LAN.", "##.", "normal"),  # also beyond: Device. has no parent
        ("Device.LAN.", "#.X", "model"),  # hashes only in the normal scope
        ("Device.LAN.", "#.X", "object"),
        ("Device.LAN.", "#X", "normal"),
        ("Device.LAN.", "X", "sideways"),
    ],
)
def test_reference_paths_refuse_what_the_rules_forbid(current, target, scope):
    with pytest.raises(PathError):
        reference_path(current, target, scope)


def test_path_ref_checks_target_type_parent_and_data_type(facets):
    instances = InstanceTree(facets, ["Device.Port.1.", "Device.Port.2.", "Device.Other.7."])
    mine = "Device.Port.1.Peer"

    def peer(text: str, **kwargs: object) -> object:
        return _facet(facets, "Device.Port.{i}.Peer", text, path=mine, **kwargs)

    assert peer("Device.Port.2.") == "Device.Port.2."
    assert peer("") == ""  # the null reference of a string (A.2.3.5)
    assert peer("Device.Port.2.", instances=instances) == "Device.Port.2."
    with pytest.raises(
        CoerceError, match="absent"
    ):  # a strong reference to a row that is not there
        peer("Device.Port.9.", instances=instances)
    assert peer("Device.Port.9.") == "Device.Port.9."  # without instance data it cannot be known
    for bad, why in (
        ("Device.Port.", "table"),  # the table, not a row
        ("Device.Port.2.Name", "parameter"),
        ("Device.Box.", "single"),
        ("Device.Other.7.", "targetParent"),  # a row, but not a child of Device.Port.
    ):
        with pytest.raises(CoerceError, match=why):
            peer(bad)
    with pytest.raises(CoerceError, match="references nothing"):
        peer("Device.Nowhere.1.")
    with pytest.raises(CoerceError, match="references nothing"):
        peer("Device.Port.0.")
    # a targetParent in the model scope: ".Other." is Device.Other.
    other = _facet(facets, "Device.Port.{i}.Elsewhere", "Device.Other.7.", path=mine)
    assert other == "Device.Other.7."
    with pytest.raises(CoerceError, match="targetParent"):
        _facet(facets, "Device.Port.{i}.Elsewhere", "Device.Port.1.", path=mine)
    # without the parameter's own path the parent cannot be resolved, and is not checked
    assert _facet(facets, "Device.Port.{i}.Elsewhere", "Device.Port.1.") == "Device.Port.1."
    # table, single and a named type carrying the facet
    assert _facet(facets, "Device.Port.{i}.Table", "Device.Other.") == "Device.Other."
    with pytest.raises(CoerceError):
        _facet(facets, "Device.Port.{i}.Table", "Device.Other.7.")
    assert _facet(facets, "Device.Port.{i}.Single", "Device.Box.") == "Device.Box."
    with pytest.raises(CoerceError):
        _facet(facets, "Device.Port.{i}.Single", "Device.Port.")
    assert _facet(facets, "Device.Port.{i}.Any", "Device.Port.1.") == "Device.Port.1."
    with pytest.raises(CoerceError, match="parameter"):
        _facet(facets, "Device.Port.{i}.Any", "Device.Port.1.Name")


def test_path_ref_target_data_type_follows_the_builtin_hierarchy(facets):
    ref = facets.parameters["Device.Box.Ref"]
    assert coerce_value(ref, "Device.Box.Number", model=facets) == "Device.Box.Number"
    with pytest.raises(CoerceError, match="integer"):
        coerce_value(ref, "Device.Box.Text", model=facets)
    with pytest.raises(CoerceError, match="parameter"):
        coerce_value(ref, "Device.Box.", model=facets)


def test_an_instance_tree_checks_its_paths_against_the_model(facets):
    tree = InstanceTree(facets, ["Device.Port.3.", "Device.Port.1."])
    assert tree.numbers("Device.Port.") == [1, 3]
    assert tree.exists("Device.Port.3.Name")
    assert not tree.exists("Device.Port.2.Name")
    assert tree.exists("Device.Port.")  # the table exists whether or not it has rows
    assert not tree.exists("Device.Nowhere.")
    for bad in ("Device.Port.", "Device.Box.", "Device.Port.x.", "Device.Port.1.Name."):
        with pytest.raises(PathError):
            InstanceTree(facets, [bad])

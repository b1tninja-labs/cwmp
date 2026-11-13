"""Nested-bracket lists, ``instanceRef`` and the Table 9 derivation rules (TR-106 Issue 1 Amendment 18, 3.2.2,
A.2.3.1, A.2.3.7 Table 7, A.2.3.8 Table 9, read from the PDF with sha256 f616d9a0...4864e).

The models here are written for these tests in the shape of the published files. The real-data check at the end
reads the Device:2.22 file from the cache and skips loudly when it is absent.
"""

from __future__ import annotations

import pytest

from cwmp.datamodel import (
    CoerceError,
    InstanceRef,
    check_derivation,
    coerce_value,
    load_model,
    split_list,
)
from cwmp.instances import InstanceTree

MODEL = b"""<?xml version="1.0" encoding="UTF-8"?>
<dm:document xmlns:dm="urn:broadband-forum-org:cwmp:datamodel-1-8" spec="urn:example:test-1-0">
  <dataType name="Pair"><list minItems="2" maxItems="2"/><int/></dataType>
  <dataType name="Name64"><string><size maxLength="64"/></string></dataType>
  <dataType name="Name32" base="Name64"><size maxLength="32"/></dataType>
  <dataType name="Name128" base="Name64"><size maxLength="128"/></dataType>
  <dataType name="Level"><unsignedInt><range minInclusive="0" maxInclusive="10"/></unsignedInt></dataType>
  <dataType name="Level5" base="Level"><range minInclusive="0" maxInclusive="5"/></dataType>
  <dataType name="Level20" base="Level"><range minInclusive="0" maxInclusive="20"/></dataType>
  <dataType name="AnyRef"><string><pathRef targetType="any"/></string></dataType>
  <dataType name="ObjectRef" base="AnyRef"><pathRef targetType="object"/></dataType>
  <dataType name="ParamRef" base="ObjectRef"><pathRef targetType="parameter"/></dataType>
  <model name="Device:2.0">
    <object name="Device." access="readOnly" minEntries="1" maxEntries="1">
      <parameter name="Weak" access="readWrite">
        <syntax><unsignedInt><instanceRef targetParent="Device.Port.{i}."/></unsignedInt></syntax>
      </parameter>
      <parameter name="Strong" access="readWrite">
        <syntax><unsignedInt><instanceRef targetParent="Device.Port." refType="strong"/></unsignedInt></syntax>
      </parameter>
      <parameter name="Signed" access="readWrite">
        <syntax><int><instanceRef targetParent="Device.Port." refType="strong"/></int></syntax>
      </parameter>
      <parameter name="Plain" access="readWrite">
        <syntax><list nestedBrackets="required"/><string/></syntax>
      </parameter>
      <parameter name="Flat" access="readWrite"><syntax><list/><string/></syntax></parameter>
      <parameter name="Complex" access="readWrite"><syntax><list minItems="1" maxItems="3" nestedBrackets="required"/><dataType ref="Pair"/></syntax></parameter>
    </object>
    <object name="Device.Port.{i}." access="readWrite" minEntries="0" maxEntries="unbounded"/>
  </model>
</dm:document>"""


@pytest.fixture(scope="module")
def model():
    return load_model(MODEL)


def param(model, name):
    return model.parameters[f"Device.{name}"]


def test_split_list_keeps_a_bracket_group_whole_and_trims_the_separator():
    assert split_list("a, b ,c") == ["a", "b", "c"]
    assert split_list("a,[b,c],d", nested_brackets=True) == ["a", "[b,c]", "d"]
    assert split_list("a,[b,c],d") == [
        "a",
        "[b",
        "c]",
        "d",
    ]  # a reader that did not know the syntax
    assert split_list("") == []
    assert split_list("[a,[b,c]],d", nested_brackets=True) == ["[a,[b,c]]", "d"]


@pytest.mark.parametrize("bad", ["[a", "a]", "[[a]", "a,[b,c"])
def test_split_list_refuses_unbalanced_brackets(bad):
    with pytest.raises(CoerceError, match="bracket"):
        split_list(bad, nested_brackets=True)


def test_nested_brackets_lists(model):
    # TR-106 3.2.2: "a,[b,c],d" is three items when the definition says nestedBrackets
    plain = param(model, "Plain")
    assert plain.syntax is not None
    assert plain.syntax.nested_brackets == "required"
    assert coerce_value(plain, "a,[b,c],d") == ["a", "[b,c]", "d"]
    flat = param(model, "Flat")
    assert coerce_value(flat, "a,[b,c],d") == ["a", "[b", "c]", "d"]
    pairs = param(model, "Complex")
    assert coerce_value(pairs, "[1,2],[3,4]", model=model) == [[1, 2], [3, 4]]
    # the percent-encoded form the same section gives for an inner list
    assert coerce_value(pairs, "1%2C2, [3,4]", model=model) == [[1, 2], [3, 4]]
    for bad, why in [
        ("[1,2],[3]", "shorter than 2"),
        ("[1,2,3]", "longer than 2"),
        ("[1,2", "never closed"),
        ("[1,2],[3,4],[5,6],[7,8]", "longer than 3"),
        ("[1,x]", "int"),
    ]:
        with pytest.raises(CoerceError):
            coerce_value(pairs, bad, model=model)
        del why


def test_instance_ref_is_parsed_and_the_null_reference_passes(model):
    weak = param(model, "Weak")
    assert weak.syntax is not None
    assert weak.syntax.instance_ref == InstanceRef("Device.Port.{i}.", "normal", "weak")
    strong = param(model, "Strong")
    assert strong.syntax is not None
    assert strong.syntax.instance_ref == InstanceRef("Device.Port.", "normal", "strong")
    assert coerce_value(strong, "0") == 0  # unsignedInt null reference (A.2.3.5)
    assert coerce_value(param(model, "Signed"), "-1") == -1  # int null reference
    assert coerce_value(weak, "7") == 7  # a weak reference is never checked for existence


def test_a_strong_instance_ref_must_name_an_existing_row(model):
    tree = InstanceTree(model, ["Device.Port.1.", "Device.Port.3."])
    strong = param(model, "Strong")
    path = "Device.Strong"
    assert coerce_value(strong, "3", path=path, instances=tree) == 3
    with pytest.raises(CoerceError, match="absent"):
        coerce_value(strong, "2", path=path, instances=tree)
    with pytest.raises(CoerceError, match="Instance Number"):
        coerce_value(param(model, "Signed"), "-5", path="Device.Signed", instances=tree)


def test_table_9_derivations_that_widen_are_reported(model):
    problems = check_derivation(model)
    assert any("Name128" in p and "size" in p for p in problems)
    assert any("Level20" in p and "range" in p for p in problems)
    assert not any("Name32" in p or "Level5" in p for p in problems)
    # AnyRef -> ObjectRef narrows (any to object); ObjectRef -> ParamRef widens beyond what object allows
    assert any("ParamRef" in p and "targetType" in p for p in problems)
    assert not any("ObjectRef:" in p for p in problems)
    assert len(problems) == 3


def test_every_derivation_in_the_published_model_narrows_its_base():
    from test_bbf_models import FULL, TYPES, _cached

    real = load_model(_cached(TYPES), _cached(FULL))
    derived = [n for n, s in real.data_types.items() if s.base in real.data_types]
    assert (
        len(derived) == 10
    )  # the alias, IP address, IP prefix and URI families; none widens its base
    assert check_derivation(real) == []
    nested = [
        p for p in real.parameters.values() if p.syntax and p.syntax.nested_brackets == "required"
    ]
    assert len(nested) == 9
    uer = real.parameters["Device.DSL.Diagnostics.SELTUER.UER"]
    assert coerce_value(uer, "[1,-2],[3,4]", model=real) == [[1, -2], [3, 4]]

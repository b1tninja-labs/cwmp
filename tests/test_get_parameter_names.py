"""GetParameterNames over instance data (TR-069 Amendment 6 Corrigendum 1, A.3.2.3, Tables 20 to 22).

The Device.Hosts model below is written for these tests in the shape of the cwmp-data-models files; its
parameter names are those the specification's own example lists (read from the PDF, sha256 21622e4a...ba115,
page 89), so the expected answers for ``Device.Hosts.`` with one Host instance are the specification's.
"""

from __future__ import annotations

import pytest

from cwmp.datamodel import DataModel, PathError, load_model
from cwmp.instances import InstanceTree, ParameterInfo, ParameterNamesError, get_parameter_names

MODEL = b"""<?xml version="1.0" encoding="UTF-8"?>
<dm:document xmlns:dm="urn:broadband-forum-org:cwmp:datamodel-1-8" spec="urn:example:test-1-0">
  <model name="Device:2.0">
    <object name="Device." access="readOnly" minEntries="1" maxEntries="1">
      <parameter name="HostsCount" access="readOnly"><syntax><unsignedInt/></syntax></parameter>
    </object>
    <object name="Device.Hosts." access="readOnly" minEntries="1" maxEntries="1">
      <parameter name="HostNumberOfEntries" access="readOnly"><syntax><unsignedInt/></syntax></parameter>
    </object>
    <object name="Device.Hosts.Host.{i}." access="readOnly" minEntries="0" maxEntries="unbounded">
      <parameter name="IPAddress" access="readOnly"><syntax><string/></syntax></parameter>
      <parameter name="AddressSource" access="readOnly"><syntax><string/></syntax></parameter>
      <parameter name="LeaseTimeRemaining" access="readOnly"><syntax><int/></syntax></parameter>
      <parameter name="MACAddress" access="readOnly"><syntax><string/></syntax></parameter>
      <parameter name="HostName" access="readOnly"><syntax><string/></syntax></parameter>
      <parameter name="InterfaceType" access="readOnly"><syntax><string/></syntax></parameter>
      <parameter name="Active" access="readOnly"><syntax><boolean/></syntax></parameter>
    </object>
    <object name="Device.IP." access="readOnly" minEntries="1" maxEntries="1"/>
    <object name="Device.IP.Interface.{i}." access="readWrite" minEntries="0" maxEntries="unbounded">
      <parameter name="Enable" access="readWrite"><syntax><boolean/></syntax></parameter>
      <parameter name="Name" access="readOnly"><syntax><string/></syntax></parameter>
    </object>
    <object name="Device.IP.Interface.{i}.Stats." access="readOnly" minEntries="1" maxEntries="1">
      <parameter name="BytesSent" access="readOnly"><syntax><unsignedLong/></syntax></parameter>
    </object>
    <object name="Device.IP.Interface.{i}.IPv4Address.{i}." access="readWrite" minEntries="0" maxEntries="unbounded">
      <parameter name="IPAddress" access="readWrite"><syntax><string/></syntax></parameter>
    </object>
    <object name="Device.Empty." access="readOnly" minEntries="0" maxEntries="1"/>
  </model>
</dm:document>"""

HOSTS_ALL = [
    "Device.Hosts.",
    "Device.Hosts.HostNumberOfEntries",
    "Device.Hosts.Host.",
    "Device.Hosts.Host.1.",
    "Device.Hosts.Host.1.IPAddress",
    "Device.Hosts.Host.1.AddressSource",
    "Device.Hosts.Host.1.LeaseTimeRemaining",
    "Device.Hosts.Host.1.MACAddress",
    "Device.Hosts.Host.1.HostName",
    "Device.Hosts.Host.1.InterfaceType",
    "Device.Hosts.Host.1.Active",
]


@pytest.fixture(scope="module")
def model() -> DataModel:
    return load_model(MODEL)


@pytest.fixture(scope="module")
def tree(model: DataModel) -> InstanceTree:
    return InstanceTree(
        model,
        [
            "Device.Hosts.Host.1.",
            "Device.IP.Interface.1.",
            "Device.IP.Interface.2.",
            "Device.IP.Interface.2.IPv4Address.1.",
            "Device.IP.Interface.2.IPv4Address.7.",
        ],
    )


def names(tree: InstanceTree, path: str, next_level: bool) -> list[str]:
    return [info.name for info in get_parameter_names(tree, path, next_level)]


def test_the_specifications_example_with_next_level_false(tree):
    # A.3.2.3: "if ParameterPath were "Device.Hosts.", the response would include the following"
    assert names(tree, "Device.Hosts.", False) == HOSTS_ALL


def test_the_specifications_example_with_next_level_true(tree):
    # A.3.2.3: HostNumberOfEntries and Host. only; the instances are one level further down
    assert names(tree, "Device.Hosts.", True) == [
        "Device.Hosts.HostNumberOfEntries",
        "Device.Hosts.Host.",
    ]
    assert names(tree, "Device.Hosts.Host.", True) == ["Device.Hosts.Host.1."]


def test_an_empty_path_with_next_level_true_lists_only_the_root(tree):
    # A.3.2.3: "if ParameterPath were empty, with NextLevel equal true, the response would list only Device."
    assert names(tree, "", True) == ["Device."]
    everything = names(tree, "", False)
    assert everything[0] == "Device."
    assert set(HOSTS_ALL) <= set(everything)
    assert "Device.IP.Interface.2.IPv4Address.7.IPAddress" in everything


def test_a_parameter_name_answers_with_itself_when_next_level_is_false(tree):
    assert get_parameter_names(tree, "Device.Hosts.Host.1.Active", False) == [
        ParameterInfo("Device.Hosts.Host.1.Active", False)
    ]


def test_instances_are_listed_in_numeric_order_with_their_children(tree):
    got = names(tree, "Device.IP.Interface.2.", False)
    assert got == [
        "Device.IP.Interface.2.",
        "Device.IP.Interface.2.Enable",
        "Device.IP.Interface.2.Name",
        "Device.IP.Interface.2.Stats.",
        "Device.IP.Interface.2.Stats.BytesSent",
        "Device.IP.Interface.2.IPv4Address.",
        "Device.IP.Interface.2.IPv4Address.1.",
        "Device.IP.Interface.2.IPv4Address.1.IPAddress",
        "Device.IP.Interface.2.IPv4Address.7.",
        "Device.IP.Interface.2.IPv4Address.7.IPAddress",
    ]
    # instance 1 has no IPv4Address rows: the table is still listed, empty (Table 21)
    assert names(tree, "Device.IP.Interface.1.", False)[-2:] == [
        "Device.IP.Interface.1.Stats.BytesSent",
        "Device.IP.Interface.1.IPv4Address.",
    ]
    assert names(tree, "Device.IP.Interface.1.IPv4Address.", True) == []


def test_an_empty_object_is_listed_and_has_no_next_level_children(tree):
    # Table 21: "This list MUST include any Objects that are currently empty", and "If NextLevel is true and
    # ParameterPath refers to an Object that is empty, this array MUST contain zero entries."
    assert "Device.Empty." in names(tree, "Device.", True)
    assert names(tree, "Device.Empty.", False) == ["Device.Empty."]
    assert names(tree, "Device.Empty.", True) == []


def test_writable_is_add_object_for_a_table_and_delete_object_for_an_instance(tree):
    by_name = {i.name: i.writable for i in get_parameter_names(tree, "Device.IP.", False)}
    assert by_name["Device.IP."] is False  # a single-instance object cannot be added
    assert by_name["Device.IP.Interface."] is True  # AddObject allowed
    assert by_name["Device.IP.Interface.1."] is True  # DeleteObject allowed
    assert by_name["Device.IP.Interface.1.Enable"] is True
    assert by_name["Device.IP.Interface.1.Name"] is False
    hosts = {i.name: i.writable for i in get_parameter_names(tree, "Device.Hosts.", False)}
    assert hosts["Device.Hosts.Host."] is False
    assert hosts["Device.Hosts.Host.1."] is False


def test_instance_wildcards_stand_for_every_existing_instance(tree):
    got = names(tree, "Device.IP.Interface.*.Stats.", False)
    assert got == [
        "Device.IP.Interface.1.Stats.",
        "Device.IP.Interface.1.Stats.BytesSent",
        "Device.IP.Interface.2.Stats.",
        "Device.IP.Interface.2.Stats.BytesSent",
    ]
    assert names(tree, "Device.IP.Interface.*.Stats.", True) == [
        "Device.IP.Interface.1.Stats.BytesSent",
        "Device.IP.Interface.2.Stats.BytesSent",
    ]
    assert names(tree, "Device.IP.Interface.*.IPv4Address.", True) == [
        "Device.IP.Interface.2.IPv4Address.1.",
        "Device.IP.Interface.2.IPv4Address.7.",
    ]
    assert names(tree, "Device.IP.Interface.*.Name", False) == [
        "Device.IP.Interface.1.Name",
        "Device.IP.Interface.2.Name",
    ]
    # a wildcard that matches nothing is not an invalid name
    assert names(tree, "Device.Hosts.Host.*.Active", False) == ["Device.Hosts.Host.1.Active"]
    assert names(tree, "Device.IP.Interface.1.IPv4Address.*.IPAddress", False) == []


def test_invalid_paths_earn_9005_and_a_parameter_with_next_level_9003(tree):
    # A.3.2.3: 9005 for a path that "does not exactly match a Parameter or Object name currently present";
    # 9003 "If NextLevel is true and ParameterPath is a Parameter name rather than a Partial Path Name"
    for path in (
        "Device.Nowhere.",
        "Device.Hosts.Host.2.",  # in the model, but no such instance
        "Device.Hosts.Host.2.Active",
        "Device.Hosts.Host",  # an object name without its dot
        "Device.Hosts.Host.1.Active.",
        "Device.IP.Interface.[a].",  # an alias is not looked up
        "Device.IP.Interface.0.",
        "Device.IP.Interface.*.",  # A.2.4: the wildcard may not be the last part of a path name
        "Device.IP.Interface.1.*.Name",  # A.2.4: it must replace an instance identifier
        "Device..",
        "x" * 257,
    ):
        for next_level in (False, True):
            with pytest.raises(ParameterNamesError) as raised:
                get_parameter_names(tree, path, next_level)
            assert raised.value.fault_code == 9005, path
    with pytest.raises(ParameterNamesError) as raised:
        get_parameter_names(tree, "Device.Hosts.Host.1.Active", True)
    assert raised.value.fault_code == 9003
    with pytest.raises(ParameterNamesError) as raised:  # wildcards the CPE does not support: 9005
        get_parameter_names(tree, "Device.IP.Interface.*.", False, wildcards=False)
    assert raised.value.fault_code == 9005
    assert isinstance(raised.value, PathError)


def test_a_tree_refuses_what_is_not_an_instance_of_the_model(model):
    for bad in (
        ["Device.IP.Interface.1.IPv4Address.1."],  # its parent row is not listed
        ["Device.IP.Interface."],  # the table
        ["Device.IP."],  # not multi-instance
        ["Device.Hosts.Host.x."],
    ):
        with pytest.raises(PathError):
            InstanceTree(model, bad)
    InstanceTree(model, ["Device.IP.Interface.1.IPv4Address.1.", "Device.IP.Interface.1."])

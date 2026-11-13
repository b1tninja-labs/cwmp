"""one class per RPC method, request and response (TR-069).

The Inform request is built from its three parts, each of which is also usable alone:

* ``device_id_arg``: the DeviceId structure (TR-069 Amendment 6 Corrigendum 1, Table 39 in A.3.3.1);
* ``event_array_arg``: the Event array, at most 64 EventStruct (Table 37, Table 40);
* ``parameter_list_arg``: the ParameterList array of ParameterValueStruct (Table 17).

``build_inform`` joins them in the order Table 37 gives. The limits come from the report's tables and are
refused rather than truncated, with the one exception the report itself makes: a CPE that must deliver more
than 64 events discards the oldest "M" (method-related) events. The report's text is not reproduced here.

Every other object in this module is a placeholder until the milestone named in ROADMAP.md lands. A stub
raises instead of returning a plausible empty value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import faults
from .envelope import DEFAULT_CWMP_NS, Arg, Envelope, Fault, Rpc
from .errors import EncodeError, EnvelopeError
from .instances import ParameterInfo, ParameterNamesError, get_parameter_names

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from .instances import InstanceTree

__all__ = [
    "DeviceId",
    "Event",
    "ParameterValue",
    "answer_get_parameter_names",
    "build_inform",
    "device_id_arg",
    "event_array_arg",
    "get_parameter_names_request",
    "get_parameter_names_response",
    "inform_response",
    "parameter_list_arg",
    "parse_get_parameter_names",
    "set_parameter_values",
]

_MAX_EVENTS = 64  # Table 37: EventStruct[64]
_OUI = re.compile(
    r"[0-9A-F]{6}"
)  # Table 39: six hexadecimal digits, upper case, leading zeros kept
_MAX_UNSIGNED_INT = 4294967295  # Table 12 in A.2.1


@dataclass(frozen=True)
class DeviceId:
    """DeviceIdStruct (Table 39): the four strings that identify the CPE."""

    manufacturer: str
    oui: str
    product_class: str
    serial_number: str


@dataclass(frozen=True)
class Event:
    """EventStruct (Table 40): ``code`` is an EventCode such as ``"1 BOOT"`` or ``"M Reboot"``."""

    code: str
    command_key: str = ""


@dataclass(frozen=True)
class ParameterValue:
    """ParameterValueStruct (Table 17): a path name and a value with its XML Schema type."""

    name: str
    value: str
    xsd_type: str = "xsd:string"


def _limited(text: str, limit: int, what: str) -> str:
    if len(text) > limit:
        raise EncodeError(f"{what} is longer than string({limit}) allows")
    return text


def device_id_arg(device: DeviceId) -> Arg:
    """The DeviceId argument: Manufacturer, OUI, ProductClass and SerialNumber, each within Table 39's limit."""
    if not _OUI.fullmatch(device.oui):
        raise EncodeError("OUI must be six upper-case hexadecimal digits (Table 39)")
    return Arg(
        "DeviceId",
        children=(
            Arg("Manufacturer", _limited(device.manufacturer, 64, "Manufacturer")),
            Arg("OUI", device.oui),
            Arg("ProductClass", _limited(device.product_class, 64, "ProductClass")),
            Arg("SerialNumber", _limited(device.serial_number, 64, "SerialNumber")),
        ),
    )


def event_array_arg(events: Sequence[Event]) -> Arg:
    """The Event argument. Table 37: more than 64 events is exceptional, and the CPE then discards the
    oldest "M" events; if that cannot bring the count to 64 this raises."""
    kept = list(events)
    while len(kept) > _MAX_EVENTS:
        oldest = next((i for i, e in enumerate(kept) if e.code.startswith("M ")), None)
        if oldest is None:
            raise EncodeError(
                "more than 64 events and no method-related event to discard (Table 37)"
            )
        del kept[oldest]
    members = tuple(
        Arg(
            "EventStruct",
            children=(
                Arg("EventCode", _limited(e.code, 64, "EventCode")),
                Arg("CommandKey", _limited(e.command_key, 32, "CommandKey")),
            ),
        )
        for e in kept
    )
    return Arg("Event", children=members, array_type="cwmp:EventStruct")


def parameter_list_arg(parameters: Sequence[ParameterValue]) -> Arg:
    """The ParameterList argument: ParameterValueStruct members whose Value is anySimpleType and so
    carries its xsi:type (section 3.5)."""
    members = tuple(
        Arg(
            "ParameterValueStruct",
            children=(
                Arg("Name", _limited(p.name, 256, "Name")),
                Arg("Value", p.value, xsi_type=p.xsd_type, any_simple=True),
            ),
        )
        for p in parameters
    )
    return Arg("ParameterList", children=members, array_type="cwmp:ParameterValueStruct")


def build_inform(
    device: DeviceId,
    events: Sequence[Event],
    *,
    current_time: datetime,
    parameters: Sequence[ParameterValue] = (),
    retry_count: int = 0,
) -> Rpc:
    """The Inform request (TR-069 Amendment 6 Corrigendum 1, Annex A.3.3.1, Table 37).

    MaxEnvelopes is always 1, the only value the report allows. ``current_time`` must carry its UTC
    offset: the report requires the CPE's local time zone offset to be included, so a naive datetime is
    refused. ``retry_count`` is an unsignedInt.
    """
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise EncodeError("CurrentTime must include the local time-zone offset (Table 37)")
    if not 0 <= retry_count <= _MAX_UNSIGNED_INT:
        raise EncodeError("RetryCount is an unsignedInt")
    return Rpc(
        "Inform",
        (
            device_id_arg(device),
            event_array_arg(events),
            Arg("MaxEnvelopes", "1"),
            Arg("CurrentTime", current_time.isoformat(timespec="seconds")),
            Arg("RetryCount", str(retry_count)),
            parameter_list_arg(parameters),
        ),
    )


def inform_response() -> Rpc:
    """The InformResponse (Table 38): MaxEnvelopes is 1 because this version of the protocol carries one
    envelope per message (TR-069 Amendment 6 Corrigendum 1, A.3.3.1)."""
    return Rpc("InformResponse", (Arg("MaxEnvelopes", "1"),))


def get_parameter_names_request(path: str, next_level: bool) -> Rpc:
    """The GetParameterNames request (TR-069 Amendment 6 Corrigendum 1, A.3.2.3, Table 20): ``ParameterPath``
    (string(256), empty for the top of the hierarchy) and ``NextLevel`` (boolean)."""
    return Rpc(
        "GetParameterNames",
        (
            Arg("ParameterPath", _limited(path, 256, "ParameterPath"), xsi_type="xsd:string"),
            Arg("NextLevel", "1" if next_level else "0", xsi_type="xsd:boolean"),
        ),
    )


def get_parameter_names_response(infos: Sequence[ParameterInfo]) -> Rpc:
    """The GetParameterNamesResponse (Tables 21 and 22): an array of ``ParameterInfoStruct`` holding ``Name``
    (string(256)) and ``Writable`` (boolean)."""
    members = tuple(
        Arg(
            "ParameterInfoStruct",
            children=(
                Arg("Name", _limited(i.name, 256, "Name")),
                Arg("Writable", "1" if i.writable else "0"),
            ),
        )
        for i in infos
    )
    return Rpc(
        "GetParameterNamesResponse",
        (Arg("ParameterList", children=members, array_type="cwmp:ParameterInfoStruct"),),
    )


def parse_get_parameter_names(request: Envelope) -> tuple[str, bool]:
    """``(ParameterPath, NextLevel)`` of a decoded GetParameterNames request; :class:`EnvelopeError` when the
    method is another one or an argument is missing, repeated or not a boolean (Table 20)."""
    if request.method != "GetParameterNames":
        raise EnvelopeError(f"not a GetParameterNames request: {request.method[:40]}")
    names = [c.tag for c in request.body]
    if names != ["ParameterPath", "NextLevel"]:
        raise EnvelopeError("GetParameterNames takes ParameterPath then NextLevel (Table 20)")
    path = (request.body[0].text or "").strip()
    flag = (request.body[1].text or "").strip()
    if flag not in ("0", "1", "true", "false"):
        raise EnvelopeError("NextLevel is not a boolean")
    if len(path) > 256:
        raise EnvelopeError("ParameterPath is string(256)")
    return path, flag in ("1", "true")


def answer_get_parameter_names(
    tree: InstanceTree,
    path: str,
    next_level: bool,
    *,
    max_parameters: int | None = None,
    namespace: str = DEFAULT_CWMP_NS,
) -> Rpc | Fault:
    """What a CPE answers a GetParameterNames with: the response, or the CPE fault the request earns.

    Fault 9005 is an invalid ParameterPath and 9003 is NextLevel true with a parameter name (A.3.2.3, after
    Table 22). 9004 (Resources Exceeded) is returned only when ``max_parameters`` is given, the answer is longer
    and NextLevel is false: the report forbids it with NextLevel true. Each fault carries the SOAP Type of
    Table 87 as its faultcode and the library's short name as FaultString.
    """

    def refuse(code: int) -> Fault:
        entry = faults.CPE_FAULTS[code]
        return Fault(code, entry.name, (), "SOAP-ENV:" + entry.kind, namespace)

    try:
        infos = get_parameter_names(tree, path, next_level)
    except ParameterNamesError as error:
        return refuse(error.fault_code)
    if max_parameters is not None and not next_level and len(infos) > max_parameters:
        return refuse(9004)
    return get_parameter_names_response(infos)


def set_parameter_values(params: dict) -> Rpc:
    """Pending behaviour defined by TR-069.

    Not implemented yet. See the ``methods.set_parameter_values()`` row in ROADMAP.md;
    this stub raises on purpose so nothing downstream mistakes it for working code.
    """
    raise NotImplementedError("set_parameter_values() is not implemented: TR-069")

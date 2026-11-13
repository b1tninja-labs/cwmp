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

from .envelope import Arg, Rpc
from .errors import EncodeError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

__all__ = [
    "DeviceId",
    "Event",
    "ParameterValue",
    "build_inform",
    "device_id_arg",
    "event_array_arg",
    "inform_response",
    "parameter_list_arg",
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


def set_parameter_values(params: dict) -> Rpc:
    """Pending behaviour defined by TR-069.

    Not implemented yet. See the ``methods.set_parameter_values()`` row in ROADMAP.md;
    this stub raises on purpose so nothing downstream mistakes it for working code.
    """
    raise NotImplementedError("set_parameter_values() is not implemented: TR-069")

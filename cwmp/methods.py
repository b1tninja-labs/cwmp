"""one class per RPC method, request and response (TR-069).

Every object in this module is a placeholder until the milestone named in ROADMAP.md lands. A
stub raises instead of returning a plausible empty value: a protocol library that silently
answers nothing is worse than one that refuses to answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

    DeviceIdentity = Any  # placeholder: give it a real type in the milestone that needs it
    Rpc = Any  # placeholder: give it a real type in the milestone that needs it

__all__ = [
    "build_inform",
    "set_parameter_values",
]


def build_inform(device: DeviceIdentity, events: list) -> Rpc:
    """Pending behaviour defined by TR-069.

    Not implemented yet. See the ``methods.build_inform()`` row in ROADMAP.md; this stub
    raises on purpose so nothing downstream mistakes it for working code.
    """
    raise NotImplementedError("build_inform() is not implemented: TR-069")


def set_parameter_values(params: dict) -> Rpc:
    """Pending behaviour defined by TR-069.

    Not implemented yet. See the ``methods.set_parameter_values()`` row in ROADMAP.md;
    this stub raises on purpose so nothing downstream mistakes it for working code.
    """
    raise NotImplementedError("set_parameter_values() is not implemented: TR-069")

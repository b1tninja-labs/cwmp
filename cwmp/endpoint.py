"""CPE side: inform, connection request, method dispatch (TR-069).

Every object in this module is a placeholder until the milestone named in ROADMAP.md lands. A
stub raises instead of returning a plausible empty value: a protocol library that silently
answers nothing is worse than one that refuses to answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

    DeviceIdentity = Any  # placeholder: give it a real type in the milestone that needs it
    Session = Any  # placeholder: give it a real type in the milestone that needs it

__all__ = [
    "run_inform",
]


async def run_inform(acs_url: str, identity: DeviceIdentity) -> Session:
    """Pending behaviour defined by TR-069.

    Not implemented yet. See the ``endpoint.run_inform()`` row in ROADMAP.md; this stub
    raises on purpose so nothing downstream mistakes it for working code.
    """
    raise NotImplementedError("run_inform() is not implemented: TR-069")

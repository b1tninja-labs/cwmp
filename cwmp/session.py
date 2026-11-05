"""ACS session state, authentication and fault handling (TR-069).

Every object in this module is a placeholder until the milestone named in ROADMAP.md lands. A
stub raises instead of returning a plausible empty value: a protocol library that silently
answers nothing is worse than one that refuses to answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

    AcsApp = Any  # placeholder: give it a real type in the milestone that needs it
    HttpRequest = Any  # placeholder: give it a real type in the milestone that needs it
    HttpResponse = Any  # placeholder: give it a real type in the milestone that needs it

__all__ = [
    "handle_session",
]


async def handle_session(request: HttpRequest, acs: AcsApp) -> HttpResponse:
    """Pending behaviour defined by TR-069, RFC 9110.

    Not implemented yet. See the ``session.handle_session()`` row in ROADMAP.md; this
    stub raises on purpose so nothing downstream mistakes it for working code.
    """
    raise NotImplementedError("handle_session() is not implemented: TR-069, RFC 9110")

"""object tree, parameter paths, types and constraints (TR-181, TR-098).

Every object in this module is a placeholder until the milestone named in ROADMAP.md lands. A
stub raises instead of returning a plausible empty value: a protocol library that silently
answers nothing is worse than one that refuses to answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

    DataModel = Any  # placeholder: give it a real type in the milestone that needs it
    Parameter = Any  # placeholder: give it a real type in the milestone that needs it

__all__ = [
    "coerce_value",
    "resolve_path",
]


def resolve_path(tree: DataModel, path: str) -> list:
    """Pending behaviour defined by TR-181.

    Not implemented yet. See the ``datamodel.resolve_path()`` row in ROADMAP.md; this
    stub raises on purpose so nothing downstream mistakes it for working code.
    """
    raise NotImplementedError("resolve_path() is not implemented: TR-181")


def coerce_value(parameter: Parameter, value: object) -> object:
    """Pending behaviour defined by TR-181.

    Not implemented yet. See the ``datamodel.coerce_value()`` row in ROADMAP.md; this
    stub raises on purpose so nothing downstream mistakes it for working code.
    """
    raise NotImplementedError("coerce_value() is not implemented: TR-181")

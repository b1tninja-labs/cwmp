"""Instance data over a data model, and GetParameterNames (TR-069 Amendment 6 Corrigendum 1, A.3.2.3).

A :class:`~cwmp.datamodel.DataModel` knows which objects *can* exist. An :class:`InstanceTree` adds which
instances of the multi-instance objects *do* exist, and :func:`get_parameter_names` answers a
GetParameterNames request from the two: Tables 20 to 22 and the example the section gives.

What the model cannot say is which parameters a particular CPE implements. A CPE lists "only Parameters and
Objects that are actually implemented" (Table 21), so this answers for a CPE that implements the whole model
it was given; pass a model cut down to what the device has to answer for less.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .datamodel import (
    MAX_PATH_LENGTH,
    DataModel,
    ObjectDef,
    ParameterDef,
    PathError,
    resolve_path,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "InstanceTree",
    "ParameterInfo",
    "ParameterNamesError",
    "get_parameter_names",
]

_PLACEHOLDER = "{i}"
INVALID_ARGUMENTS = 9003
INVALID_PARAMETER_NAME = 9005


class ParameterNamesError(PathError):
    """GetParameterNames is refused. ``fault_code`` is the CPE fault code the request earns: 9005 (Invalid
    Parameter Name) for a ParameterPath that matches nothing in the data model, 9003 (Invalid Arguments)
    for NextLevel true with a parameter name (Table 21 and the text after Table 22)."""

    def __init__(self, fault_code: int, reason: str) -> None:
        super().__init__(reason)
        self.fault_code = fault_code


@dataclass(frozen=True)
class ParameterInfo:
    """One ``ParameterInfoStruct`` (Table 22). ``name`` is a full Path Name for a parameter and a Partial Path
    Name, ending with a dot, for an object. ``writable`` is the model's access: for a parameter, whether it can
    be set; for a multi-instance object (table), whether AddObject can add instances; for one instance, whether
    DeleteObject can remove it; false for any other object."""

    name: str
    writable: bool


@dataclass
class InstanceTree:
    """The multi-instance object instances that exist, as full instance paths with a trailing dot
    (``Device.IP.Interface.1.``, ``Device.IP.Interface.1.IPv4Address.2.``).

    Each path is checked against ``model``: it must name an instance of a multi-instance object, carry
    Instance Numbers throughout, and sit under instances that exist. Parents may be listed after their
    children. Raises :class:`~cwmp.datamodel.PathError` otherwise."""

    model: DataModel
    instances: Iterable[str] = ()
    _paths: set[str] = field(init=False, default_factory=set)

    def __post_init__(self) -> None:
        paths = {p if p.endswith(".") else p + "." for p in self.instances}
        for path in paths:
            (hit,) = resolve_path(self.model, path, aliases=False, wildcards=False)
            definition = hit.definition
            if not isinstance(definition, ObjectDef) or not definition.multi:
                raise PathError(f"{path[:60]!r} is not an instance of a multi-instance object")
            if definition.path.count(_PLACEHOLDER) != len(hit.instances):
                raise PathError(f"{path[:60]!r} names a table, not an instance")
        for path in paths:
            nodes = path.rstrip(".").split(".")
            for end in range(1, len(nodes)):
                prefix = ".".join(nodes[: end + 1]) + "."
                if nodes[end].isdigit() and prefix not in paths:
                    raise PathError(
                        f"{path[:60]!r} is listed but its parent {prefix[:60]!r} is not"
                    )
        self._paths = paths

    def exists(self, path: str) -> bool:
        """Whether a Path Name names something that exists here: an instance in the tree, a single-instance
        object, a table or a parameter whose every instance in the path is in the tree."""
        try:
            (hit,) = resolve_path(self.model, path, aliases=False, wildcards=False)
        except PathError:
            return False
        nodes = path.rstrip(".").split(".")
        for end in range(len(nodes)):
            if nodes[end].isdigit() and ".".join(nodes[: end + 1]) + "." not in self._paths:
                return False
        return hit is not None

    def numbers(self, table: str) -> list[int]:
        """The Instance Numbers present under a table's instance path, ascending: ``Device.IP.Interface.`` or
        ``Device.IP.Interface.1.IPv4Address.``."""
        base = table if table.endswith(".") else table + "."
        found = []
        for path in self._paths:
            if path.startswith(base):
                node = path[len(base) :].split(".", 1)[0]
                if node.isdigit() and base + node + "." == path:
                    found.append(int(node))
        return sorted(found)


@dataclass(frozen=True)
class _Index:
    objects_by_parent: dict[str, list[ObjectDef]]
    parameters_by_object: dict[str, list[ParameterDef]]


def _parent_template(path: str) -> str:
    nodes = path.rstrip(".").split(".")
    cut = 2 if len(nodes) >= 2 and nodes[-1] == _PLACEHOLDER else 1
    nodes = nodes[:-cut]
    return ".".join(nodes) + "." if nodes else ""


def _index(model: DataModel) -> _Index:
    objects: dict[str, list[ObjectDef]] = {}
    for definition in model.objects.values():
        objects.setdefault(_parent_template(definition.path), []).append(definition)
    parameters: dict[str, list[ParameterDef]] = {}
    for parameter in model.parameters.values():
        parameters.setdefault(parameter.path.rsplit(".", 1)[0] + ".", []).append(parameter)
    return _Index(objects, parameters)


def _walk(
    index: _Index,
    tree: InstanceTree,
    template: str,
    actual: str,
    out: list[tuple[list[str], ParameterInfo]],
) -> None:
    """Append the object at ``actual`` (a path with Instance Numbers, whose model template is ``template``)
    and everything under it, each with its node list: parameters, then sub-objects, a table before its
    instances, in the model's order."""
    for parameter in index.parameters_by_object.get(template, []):
        name = actual + parameter.path[len(template) :]
        out.append((name.split("."), ParameterInfo(name, parameter.access == "readWrite")))
    for child in index.objects_by_parent.get(template, []):
        suffix = child.path[len(template) :]
        if not child.multi:
            name = actual + suffix
            out.append((name.rstrip(".").split("."), ParameterInfo(name, False)))
            _walk(index, tree, child.path, name, out)
            continue
        table = actual + suffix[: -len(_PLACEHOLDER) - 1]
        out.append(
            (table.rstrip(".").split("."), ParameterInfo(table, child.access == "readWrite"))
        )
        for number in tree.numbers(table):
            name = f"{table}{number}."
            out.append(
                (name.rstrip(".").split("."), ParameterInfo(name, child.access == "readWrite"))
            )
            _walk(index, tree, child.path, name, out)


def get_parameter_names(
    tree: InstanceTree,
    path: str,
    next_level: bool,
    *,
    wildcards: bool = True,
) -> list[ParameterInfo]:
    """The ``ParameterList`` a CPE answers GetParameterNames with (TR-069 Amendment 6 Corrigendum 1, A.3.2.3,
    Tables 20 to 22), for the instances in ``tree``.

    ``path`` is the ParameterPath: empty for the top of the hierarchy, a Partial Path Name ending with a dot,
    or a full parameter name; an instance wildcard ``*`` (A.2.4, optional, 3.6.2) stands for every existing
    instance when ``wildcards`` is true. With ``next_level`` false the answer is the named parameter or
    object and everything under it (an empty path: everything), with it true only the next-level children of
    the object; an object with no children, or no instances, gives an empty list. Objects are listed too,
    including those with no instances (Table 21), a table before its instances.

    Raises :class:`ParameterNamesError` with fault 9005 for a path that is not empty and matches no parameter
    or object currently present (or a wildcard where wildcards are off), and with fault 9003 for NextLevel true
    with a parameter name. An Instance Alias is not looked up, so an alias path is a 9005.
    """
    model = tree.model
    if len(path) > MAX_PATH_LENGTH:
        raise ParameterNamesError(INVALID_PARAMETER_NAME, "a ParameterPath is string(256) at most")
    if path != "":
        try:
            resolve_path(model, path, aliases=False, wildcards=wildcards)
        except PathError as error:
            raise ParameterNamesError(INVALID_PARAMETER_NAME, error.reason) from None
    everything: list[tuple[list[str], ParameterInfo]] = []
    index = _index(model)
    for root in model.roots:
        everything.append((root.path.rstrip(".").split("."), ParameterInfo(root.path, False)))
        _walk(index, tree, root.path, root.path, everything)
    wanted = path.rstrip(".").split(".") if path else []
    partial = path == "" or path.endswith(".")

    def matches(nodes: list[str]) -> bool:
        if len(nodes) < len(wanted):
            return False
        if not all(w == "*" or w == n for w, n in zip(wanted, nodes, strict=False)):
            return False
        if not partial:
            return len(nodes) == len(wanted)
        if next_level:
            return len(nodes) == len(wanted) + 1
        return True

    if "*" not in wanted and path != "" and not any(nodes == wanted for nodes, _ in everything):
        raise ParameterNamesError(
            INVALID_PARAMETER_NAME, f"{path[:60]!r} is not present in the CPE"
        )
    if next_level and path != "" and not path.endswith("."):
        # a name that is not there is 9005, taking precedence over 9003 (A.3.2.3, after Table 22)
        raise ParameterNamesError(
            INVALID_ARGUMENTS, "NextLevel is true and ParameterPath is a parameter name"
        )
    return [info for nodes, info in everything if matches(nodes)]

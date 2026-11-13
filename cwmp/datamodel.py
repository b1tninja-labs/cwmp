"""object tree, parameter paths, types and constraints (TR-181, TR-098).

``load_model`` reads Broadband Forum data-model XML (the ``dm:document`` files of the cwmp-data-models
repository, TR-106 format) through ``devicespy.xmlsafe``, the portfolio's one hardened XML reader, and builds
a :class:`DataModel` of object and parameter definitions keyed by their template path
(``Device.IP.Interface.{i}.Enable``). ``resolve_path`` then answers which definition a path name addresses.

The path rules are those of TR-069 Amendment 6 Corrigendum 1:

* a path name is dot-separated nodes; an object path and a partial path end with a dot, a parameter path does
  not, and an empty path is the top of the hierarchy (A.3.2.3, Table 20);
* where the model shows ``{i}`` the path carries an instance identifier: an Instance Number, a positive
  integer (A.2.2.1), an Instance Alias in square brackets, never empty (A.2.2.2, optional, 3.6.1), or an
  instance wildcard ``*`` (A.2.4, optional, 3.6.2) which may not be the last part of the path;
* a path name is a ``string(256)`` (Table 20).

The report is not reproduced here. The data-model file layout is read from the BBF files' own structure
(objects and parameters carrying ``name``, ``access`` and a ``syntax`` child).

``coerce_value`` checks a received value against the parameter's type, resolving named data types through
``resolve_syntax``. The model layout has been read against the published Device:2.22 file
(``tests/test_bbf_models.py``, which skips loudly when the cache is absent).
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING
from urllib.parse import unquote

from devicespy import xmlsafe

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET
    from collections.abc import Callable

    from .instances import InstanceTree

__all__ = [
    "MAX_MODEL_BYTES",
    "MAX_PATH_LENGTH",
    "UNKNOWN_TIME",
    "CoerceError",
    "DataModel",
    "InstanceRef",
    "ObjectDef",
    "ParameterDef",
    "PathError",
    "PathRef",
    "Resolved",
    "Syntax",
    "check_derivation",
    "children",
    "coerce_value",
    "load_model",
    "reference_path",
    "resolve_path",
    "resolve_syntax",
    "split_list",
]

MAX_MODEL_BYTES = 16 * 1024 * 1024
MAX_PATH_LENGTH = 256  # Table 20: ParameterPath is string(256)
_MAX_INSTANCE = 4294967295  # an Instance Number is a positive integer; unsignedInt bound (A.2.1)
_MAX_NODES = 400_000
_NODE = re.compile(r"[A-Za-z0-9_-]+")
_PLACEHOLDER = "{i}"
_SIMPLE_TYPES = frozenset(
    {
        "string",
        "int",
        "unsignedInt",
        "long",
        "unsignedLong",
        "boolean",
        "dateTime",
        "base64",
        "hexBinary",
        "decimal",
    }
)


Number = int | Decimal
Sizes = tuple[tuple[int | None, int | None], ...]


class PathError(ValueError):
    """A path name is malformed or does not address anything in the model; ``reason`` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class PathRef:
    """A ``pathRef`` facet (TR-106 A.2.3.7, Table 6): what a path-name value may reference. ``target_parent``
    holds the Path Names (``{i}`` is a wildcard) whose immediate children may be referenced, empty meaning
    anything, each read in ``target_parent_scope`` (``normal``, ``model``, ``object`` or ``absolute``, A.2.3.4);
    ``target_type`` is ``any``, ``parameter``, ``object``, ``single``, ``table`` or ``row``; ``target_data_type``
    limits a referenced parameter's type; ``ref_type`` is ``weak`` or ``strong`` (A.2.3.6)."""

    target_parent: tuple[str, ...] = ()
    target_parent_scope: str = "normal"
    target_type: str = "any"
    target_data_type: str = "any"
    ref_type: str = "weak"


@dataclass(frozen=True)
class InstanceRef:
    """An ``instanceRef`` facet (TR-106 A.2.3.7, Table 7): the value is the Instance Number of a row of the table
    ``target_parent`` names (no ``{i}`` and no instance identifiers), read in ``target_parent_scope`` (``normal``,
    ``model`` or ``object``, A.2.3.4); ``ref_type`` is ``weak`` or ``strong`` (A.2.3.6). The null reference is 0
    for unsignedInt and -1 for int (A.2.3.5)."""

    target_parent: str = ""
    target_parent_scope: str = "normal"
    ref_type: str = "weak"


@dataclass(frozen=True)
class Syntax:
    """A parameter's type as the data model writes it: ``base`` is a simple type name or the name of a
    ``dataType``; ``is_list`` marks a list-valued parameter; the restrictions are the model's own.

    ``min_length``, ``max_length``, ``minimum`` and ``maximum`` are the first ``size`` and ``range`` the model
    gives; ``sizes`` and ``ranges`` hold every one (a type may allow several lengths). ``patterns`` are the
    alternatives a string must match, ``enumeration_ref`` says the values are listed in another parameter
    (so no list is known here), ``min_items`` and ``max_items`` bound a list.

    ``steps`` is the ``step`` of each range, parallel to ``ranges`` (None where the model gives none, which
    means a step of 1). ``list_sizes`` is the ``size`` the model gives the list as a whole (TR-106 A.2.3.3,
    A.2.7.1); ``sizes`` bounds the items. ``enumeration_target``, ``enumeration_target_scope`` and
    ``enumeration_null`` are the ``enumerationRef`` facet's ``targetParam``, ``targetParamScope`` and
    ``nullValue`` (Table 8); ``path_ref`` is the ``pathRef`` facet."""

    base: str
    is_list: bool = False
    min_length: int | None = None
    max_length: int | None = None
    minimum: Number | None = None
    maximum: Number | None = None
    enumeration: tuple[str, ...] = ()
    default: str | None = None
    sizes: Sizes = ()
    ranges: tuple[tuple[Number | None, Number | None], ...] = ()
    patterns: tuple[str, ...] = ()
    min_items: int | None = None
    max_items: int | None = None
    enumeration_ref: bool = False
    steps: tuple[Number | None, ...] = ()
    list_sizes: Sizes = ()
    enumeration_target: str | None = None
    enumeration_target_scope: str = "normal"
    enumeration_null: str | None = None
    path_ref: PathRef | None = None
    nested_brackets: str | None = None
    """The ``list`` element's ``nestedBrackets`` attribute (A.2.3.1, A.2.7.1): ``required`` says an item that is
    itself a list is written in square brackets (3.2.2)."""
    instance_ref: InstanceRef | None = None


@dataclass(frozen=True)
class ObjectDef:
    """An object: ``path`` is the template with its trailing dot. ``multi`` is true for a multi-instance
    object, whose template ends ``.{i}.``."""

    path: str
    access: str
    multi: bool
    min_entries: int | None = None
    max_entries: int | None = None


@dataclass(frozen=True)
class ParameterDef:
    """A parameter: ``path`` is the full template path, ``access`` ``readOnly`` or ``readWrite``."""

    path: str
    access: str
    syntax: Syntax | None = None


@dataclass
class DataModel:
    """The definitions of one or more data-model files, merged."""

    model: str = ""
    objects: dict[str, ObjectDef] = field(default_factory=dict)
    parameters: dict[str, ParameterDef] = field(default_factory=dict)
    data_types: dict[str, Syntax] = field(default_factory=dict)

    @property
    def roots(self) -> list[ObjectDef]:
        """Top-level objects: those with a single node in their path, such as ``Device.``."""
        return [o for p, o in self.objects.items() if p.count(".") == 1]


@dataclass(frozen=True)
class Resolved:
    """What a path name addresses. ``path`` is the path as given; ``definition`` its model definition;
    ``instances`` the instance identifiers it carries, in order, as written (``"3"``, ``"[a]"``, ``"*"``).
    ``alias`` and ``wildcard`` say which optional addressing forms it uses."""

    path: str
    kind: str
    definition: ObjectDef | ParameterDef
    instances: tuple[str, ...] = ()
    alias: bool = False
    wildcard: bool = False


def _int(value: str | None) -> int | None:
    return int(value) if value is not None and value.lstrip("-").isdigit() else None


def _syntax(element: ET.Element) -> Syntax | None:
    syntax = next((c for c in element if c.tag == "syntax"), None)
    return None if syntax is None else _type_syntax(syntax)


def _number(value: str | None) -> Number | None:
    """An integer, or a finite Decimal for a fractional bound (a decimal type's range), else None."""
    if value is None:
        return None
    text = value.strip()
    if re.fullmatch(r"[+-]?[0-9]+", text):
        return int(text)
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _bounds(elements: list[ET.Element], low: str, high: str) -> Sizes:
    return tuple((_int(e.get(low)), _int(e.get(high))) for e in elements)


def _ranges(elements: list[ET.Element]) -> tuple[tuple[Number | None, Number | None], ...]:
    return tuple((_number(e.get("minInclusive")), _number(e.get("maxInclusive"))) for e in elements)


def _path_ref(element: ET.Element | None) -> PathRef | None:
    if element is None:
        return None
    return PathRef(
        tuple((element.get("targetParent") or "").split()),
        element.get("targetParentScope") or "normal",
        element.get("targetType") or "any",
        element.get("targetDataType") or "any",
        element.get("refType") or "weak",
    )


def _instance_ref(element: ET.Element | None) -> InstanceRef | None:
    if element is None:
        return None
    return InstanceRef(
        (element.get("targetParent") or "").strip(),
        element.get("targetParentScope") or "normal",
        element.get("refType") or "weak",
    )


def _type_syntax(syntax: ET.Element) -> Syntax | None:
    """The type held by a ``syntax`` element, or by a ``dataType`` element, which holds it directly.

    In the published files a list-valued type has an empty ``list`` element beside the type element (never
    around it), a derived ``dataType`` names its ``base`` and carries its restrictions as direct children,
    and a ``size`` or ``range`` may occur more than once, each an allowed alternative.
    """
    list_element = next((c for c in syntax if c.tag == "list"), None)
    typed = next((c for c in syntax if c.tag in _SIMPLE_TYPES or c.tag == "dataType"), None)
    if typed is None and list_element is not None:
        typed = next(
            (c for c in list_element if c.tag in _SIMPLE_TYPES or c.tag == "dataType"), None
        )
    if typed is not None:
        base = (
            (typed.get("ref") or typed.get("base") or "") if typed.tag == "dataType" else typed.tag
        )
        holder = typed
    elif syntax.tag == "dataType" and syntax.get("base"):
        base, holder = syntax.get("base", ""), syntax
    else:
        return None
    sizes = _bounds([c for c in holder if c.tag == "size"], "minLength", "maxLength")
    range_elements = [c for c in holder if c.tag == "range"]
    ranges = _ranges(range_elements)
    steps = tuple(_number(e.get("step")) for e in range_elements)
    list_sizes = (
        _bounds([c for c in list_element if c.tag == "size"], "minLength", "maxLength")
        if list_element is not None
        else ()
    )
    reference = next((c for c in holder if c.tag == "enumerationRef"), None)
    values = tuple(
        e.get("value", "") for e in holder.iter("enumeration") if e.get("value") is not None
    )
    patterns = tuple(e.get("value", "") for e in holder if e.tag == "pattern")
    default = next((c for c in syntax if c.tag == "default"), None)
    return Syntax(
        base,
        list_element is not None,
        sizes[0][0] if sizes else None,
        sizes[0][1] if sizes else None,
        ranges[0][0] if ranges else None,
        ranges[0][1] if ranges else None,
        values,
        default.get("value") if default is not None else None,
        sizes,
        ranges,
        patterns,
        _int(list_element.get("minItems")) if list_element is not None else None,
        _int(list_element.get("maxItems")) if list_element is not None else None,
        reference is not None,
        steps,
        list_sizes,
        reference.get("targetParam") if reference is not None else None,
        (reference.get("targetParamScope") or "normal") if reference is not None else "normal",
        reference.get("nullValue") if reference is not None else None,
        _path_ref(next((c for c in holder if c.tag == "pathRef"), None)),
        list_element.get("nestedBrackets") if list_element is not None else None,
        _instance_ref(next((c for c in holder if c.tag == "instanceRef"), None)),
    )


def _object_node(model: DataModel, element: ET.Element, prefix: str) -> None:
    raw = (element.get("name") or element.get("ref") or "").strip()
    if not raw:
        return
    path = raw if not prefix or raw.startswith(prefix) else prefix + raw
    if not path.endswith("."):
        path += "."
    if len(model.objects) + len(model.parameters) > _MAX_NODES:
        raise PathError("the data model has too many nodes")
    previous = model.objects.get(path)
    access = element.get("access") or (previous.access if previous else "readOnly")
    model.objects[path] = ObjectDef(
        path,
        access,
        path.endswith(_PLACEHOLDER + "."),
        _int(element.get("minEntries"))
        if element.get("minEntries")
        else (previous.min_entries if previous else None),
        _int(element.get("maxEntries"))
        if element.get("maxEntries")
        else (previous.max_entries if previous else None),
    )
    for child in element:
        name = child.get("name") or child.get("ref")
        if child.tag == "parameter" and name:
            full = path + name
            old = model.parameters.get(full)
            model.parameters[full] = ParameterDef(
                full,
                child.get("access") or (old.access if old else "readOnly"),
                _syntax(child) or (old.syntax if old else None),
            )


def load_model(*documents: bytes, max_bytes: int = MAX_MODEL_BYTES) -> DataModel:
    """Build a :class:`DataModel` from data-model XML documents, merged in the order given.

    Each document is read by ``devicespy.xmlsafe`` (no DTD, no entities, bounded size and depth). Objects
    and parameters are taken from the top-level ``component`` and ``model`` elements, a ``model``'s
    ``component`` children are included by name from the components loaded so far in any document, and a
    later ``object`` or ``parameter`` that refers to one already seen refines it. Raises
    :class:`xmlsafe.XmlRefused` for a hostile or malformed document and :class:`PathError` for one that is
    too large.
    """
    model = DataModel()
    components: dict[str, ET.Element] = {}
    roots = []
    for raw in documents:
        root = xmlsafe.parse(
            raw,
            max_bytes,
            max_depth=64,
            max_elements=2_000_000,
            ignore_processing_instructions=True,
        )
        if xmlsafe.localname(root.tag)[1] != "document":
            raise PathError("the root element is not a data-model document")
        roots.append(root)
        for child in root:
            if child.tag == "component" and child.get("name"):
                components.setdefault(child.get("name", ""), child)
            elif child.tag == "dataType" and child.get("name"):
                model.data_types[child.get("name", "")] = _type_syntax(child) or Syntax("string")

    def walk(container: ET.Element, prefix: str, depth: int) -> None:
        if depth > 16:
            raise PathError("components are nested too deeply")
        for child in container:
            if child.tag == "object":
                _object_node(model, child, prefix)
            elif child.tag == "component" and child.get("ref") in components:
                walk(components[child.get("ref", "")], child.get("path", prefix), depth + 1)

    for root in roots:
        for child in root:
            if child.tag == "model":
                model.model = child.get("name", model.model)
                walk(child, "", 0)
            elif child.tag == "component" and not any(m.tag == "model" for r in roots for m in r):
                walk(child, "", 0)
    return model


def _tokens(path: str) -> tuple[list[str], bool]:
    """Split a path into nodes, treating ``[alias]`` as one node; the flag says it ended with a dot."""
    nodes: list[str] = []
    position = 0
    ends_with_dot = path.endswith(".")
    body = path[:-1] if ends_with_dot else path
    while position <= len(body):
        if body.startswith("[", position):
            close = body.find("]", position)
            if close == -1:
                raise PathError("an Instance Alias has no closing bracket")
            nodes.append(body[position : close + 1])
            position = close + 1
            if position < len(body) and body[position] != ".":
                raise PathError("text follows an Instance Alias without a dot")
            position += 1
            continue
        stop = body.find(".", position)
        stop = len(body) if stop == -1 else stop
        nodes.append(body[position:stop])
        position = stop + 1
    return nodes, ends_with_dot


def _instance_kind(node: str, aliases: bool, wildcards: bool) -> str:
    if node == "*":
        if not wildcards:
            raise PathError("instance wildcards are not enabled (A.2.4 makes them optional)")
        return "wildcard"
    if node.startswith("["):
        if not aliases:
            raise PathError("Instance Aliases are not enabled (A.2.2.2 makes them optional)")
        if len(node) < 3 or "]" in node[1:-1] or "[" in node[1:-1]:
            raise PathError("an Instance Alias is never empty and holds no brackets (A.2.2.2)")
        return "alias"
    if node.isascii() and node.isdigit():
        if int(node) < 1 or int(node) > _MAX_INSTANCE:
            raise PathError(f"{node!r} is not an Instance Number, a positive integer (A.2.2.1)")
        return "number"
    raise PathError(f"{node[:30]!r} is not an instance identifier where the model has {{i}}")


def resolve_path(
    tree: DataModel, path: str, *, aliases: bool = True, wildcards: bool = True
) -> list[Resolved]:
    """Which definition a path name addresses, in a :class:`DataModel` (TR-181; TR-069 Amendment 6
    Corrigendum 1, A.2.2, A.2.4 and A.3.2.3).

    A path ending in a dot addresses an object, any other path a parameter, and the empty path the
    top-level objects. Instance identifiers are matched against ``{i}`` in the model: a positive integer,
    an ``[alias]`` when ``aliases`` is true, or ``*`` when ``wildcards`` is true and it is not the last
    part of the path. Nothing needs instance data: this answers about the model, not about which instances
    exist. Raises :class:`PathError` for a path that is malformed, too long, or addresses nothing.
    """
    if len(path) > MAX_PATH_LENGTH:
        raise PathError(f"a path name is string({MAX_PATH_LENGTH}) at most (Table 20)")
    if path == "":
        return [Resolved(o.path, "object", o) for o in tree.roots]
    nodes, partial = _tokens(path)
    template: list[str] = []
    instances: list[str] = []
    kinds: set[str] = set()
    for index, node in enumerate(nodes):
        last = index == len(nodes) - 1
        if node == "":
            raise PathError("a path name has an empty node")
        if _object_exists(tree, [*template, _PLACEHOLDER]):
            kinds.add(_instance_kind(node, aliases, wildcards))
            if node == "*" and last:
                raise PathError("the wildcard may not be the last part of a path name (A.2.4)")
            template.append(_PLACEHOLDER)
            instances.append(node)
            continue
        if not _NODE.fullmatch(node):
            raise PathError(f"{node[:30]!r} is not a valid node name")
        template.append(node)
    key = ".".join(template) + ("." if partial else "")
    found: ObjectDef | ParameterDef | None
    if partial:
        found = tree.objects.get(key) or tree.objects.get(key + _PLACEHOLDER + ".")
        kind = "object"
    else:
        found = tree.parameters.get(key)
        kind = "parameter"
        if found is None and key + "." in tree.objects:
            raise PathError(f"{path[:60]!r} names an object; an object path ends with a dot")
    if found is None:
        raise PathError(f"nothing in the model is named {key[:80]!r}")
    return [Resolved(path, kind, found, tuple(instances), "alias" in kinds, "wildcard" in kinds)]


def _object_exists(tree: DataModel, template: list[str]) -> bool:
    prefix = ".".join(template) + "."
    return prefix in tree.objects


def children(tree: DataModel, path: str) -> list[ObjectDef | ParameterDef]:
    """The next-level children, in the model, of the object a template path (``Device.IP.``) names: its
    parameters and its sub-objects, a multi-instance sub-object once (``Device.IP.Interface.{i}.``), the
    set GetParameterNames returns for NextLevel true, minus instances (A.3.2.3, Table 20)."""
    if path not in tree.objects:
        raise PathError(f"{path[:60]!r} is not an object in the model")
    out: list[ObjectDef | ParameterDef] = [
        p
        for key, p in tree.parameters.items()
        if key.startswith(path) and "." not in key[len(path) :]
    ]
    for key, obj in tree.objects.items():
        rest = key[len(path) :] if key.startswith(path) else ""
        if rest and re.fullmatch(r"[^.]+\.(?:\{i\}\.)?", rest):
            out.append(obj)
    return out


def _is_instance_node(node: str) -> bool:
    return node in (_PLACEHOLDER, "*") or node.isdigit() or (node[:1] == "[" and node[-1:] == "]")


def _parent_object(path: str) -> str:
    """The object a Path Name's object sits in; for an instance, the table's parent ("#." always means that,
    TR-106 A.2.3.4). Raises :class:`PathError` at the top of the hierarchy."""
    nodes = path.rstrip(".").split(".")
    cut = 2 if len(nodes) >= 2 and _is_instance_node(nodes[-1]) else 1
    nodes = nodes[:-cut]
    if not nodes:
        raise PathError("a leading hash goes beyond the Root Object (TR-106 A.2.3.4)")
    return ".".join(nodes) + "."


def reference_path(current: str, target: str, scope: str = "normal") -> str:
    """The full Path Name a reference's ``target`` names, read in ``scope`` from the object ``current``
    (TR-106 A.2.3.4, Table 5).

    ``current`` is the object the referring parameter sits in, as a template (``Device.LAN.DHCPOption.{i}.``)
    or with instance numbers. ``normal``: a path beginning with the Root Object's name is full, one beginning
    with a dot is relative to the Root Object, any other is relative to the current object and each leading
    ``#`` climbs to the parent object (``#.`` from an instance is the table's parent, not the table); the empty
    path is the top of the hierarchy (returned as ``""``). ``model`` is relative to the Root Object, ``object``
    to the current object, ``absolute`` is used as given; hashes are refused outside ``normal`` and beyond the
    Root Object. A Service Object or Mount Point is not modelled: the Root Object is the first node of
    ``current``. Raises :class:`PathError`.
    """
    if scope not in ("normal", "model", "object", "absolute"):
        raise PathError(f"{scope!r} is not a path name scope (TR-106 Table 5)")
    if scope == "absolute":
        return target
    here = current if current.endswith(".") else current + "."
    root = here.split(".", 1)[0] + "."
    hashes = len(target) - len(target.lstrip("#"))
    if hashes and scope != "normal":
        raise PathError("leading hash characters are permitted only in the normal scope")
    if scope == "model":
        return root + target.lstrip(".")
    if scope == "object":
        return here + target.lstrip(".")
    if target == "":
        return ""
    if target.split(".", 1)[0] + "." == root:
        return target
    if target.startswith("."):
        return root + target[1:]
    if hashes:
        rest = target[hashes:]
        if rest and not rest.startswith("."):
            raise PathError("leading hash characters are followed by a dot (TR-106 A.2.3.4)")
        base = here
        for _ in range(hashes):
            base = _parent_object(base)
        return (
            base + rest[1:]
        )  # a bare "#" or "##" names the climbed-to object, as Device:2.22 writes it
    return here + target


class CoerceError(ValueError):
    """A value does not fit its parameter's type; ``reason`` says which rule it broke."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


_INT_RANGES = {
    "int": (-(2**31), 2**31 - 1),
    "unsignedInt": (0, 2**32 - 1),
    "long": (-(2**63), 2**63 - 1),
    "unsignedLong": (0, 2**64 - 1),
}
_DATETIME = re.compile(
    r"(-?\d{4,})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})?"
)
UNKNOWN_TIME = datetime(1, 1, 1, tzinfo=UTC)  # 0001-01-01T00:00:00Z, "Unknown Time" (Table 12)
_MAX_RESOLVE_DEPTH = 16


def resolve_syntax(model: DataModel, syntax: Syntax) -> Syntax:
    """``syntax`` with a named ``dataType`` base replaced by the simple type it derives from.

    A derived type's own restriction (size, range, pattern, enumeration, list bounds) replaces the one it
    inherits; one it does not state is inherited. Raises :class:`PathError` for a type the model does not
    define or one that derives from itself.
    """
    chain = [syntax]
    seen: set[str] = set()
    while chain[-1].base not in _SIMPLE_TYPES:
        name = chain[-1].base
        if name in seen or len(chain) > _MAX_RESOLVE_DEPTH:
            raise PathError(f"data type {name!r} derives from itself")
        seen.add(name)
        parent = model.data_types.get(name)
        if parent is None:
            raise PathError(f"the model does not define data type {name!r}")
        chain.append(parent)
    merged = chain[-1]
    for derived in reversed(chain[:-1]):
        sizes = derived.sizes or merged.sizes
        ranges = derived.ranges or merged.ranges
        merged = Syntax(
            merged.base,
            merged.is_list or derived.is_list,
            sizes[0][0] if sizes else None,
            sizes[0][1] if sizes else None,
            ranges[0][0] if ranges else None,
            ranges[0][1] if ranges else None,
            derived.enumeration or merged.enumeration,
            derived.default if derived.default is not None else merged.default,
            sizes,
            ranges,
            derived.patterns or merged.patterns,
            derived.min_items if derived.min_items is not None else merged.min_items,
            derived.max_items if derived.max_items is not None else merged.max_items,
            derived.enumeration_ref or merged.enumeration_ref,
            derived.steps if derived.ranges else merged.steps,
            derived.list_sizes or merged.list_sizes,
            derived.enumeration_target if derived.enumeration_ref else merged.enumeration_target,
            derived.enumeration_target_scope
            if derived.enumeration_ref
            else merged.enumeration_target_scope,
            derived.enumeration_null if derived.enumeration_ref else merged.enumeration_null,
            derived.path_ref or merged.path_ref,
            derived.nested_brackets or merged.nested_brackets,
            derived.instance_ref or merged.instance_ref,
        )
    return merged


def _in_sizes(length: int, sizes: Sizes) -> bool:
    return not sizes or any(
        (low is None or length >= low) and (high is None or length <= high) for low, high in sizes
    )


def _check_range(number: Number, syntax: Syntax) -> None:
    """The model's ``range`` and ``step`` for a number (TR-106 A.2.3.3 Table 4: "Value ranges and step
    (default step is 1)"). A step counts from the range's minimum, or from zero for a range with no minimum.
    TR-106 does not say where a step counts from; the nine ranges with a step in Device:2.22 give the same
    answer from either, so the choice is this library's and is recorded in ROADMAP.md."""
    if not syntax.ranges:
        return
    inside = [
        index
        for index, (low, high) in enumerate(syntax.ranges)
        if (low is None or number >= low) and (high is None or number <= high)
    ]
    if not inside:
        raise CoerceError(f"{number} is outside the range the model gives")
    for index in inside:
        step = syntax.steps[index] if index < len(syntax.steps) else None
        low = syntax.ranges[index][0]
        if step is None or step <= 0 or (number - (low or 0)) % step == 0:
            return
    raise CoerceError(f"{number} is not on the step the model gives its range")


def _datetime(text: str) -> datetime | timedelta:
    """A TR-069 dateTime (Table 12): UTC, or an untimezoned relative-since-boot value with year below 1000."""
    found = _DATETIME.fullmatch(text)
    if found is None:
        raise CoerceError(f"{text[:40]!r} is not a dateTime")
    year, month, day, hour, minute, second = (int(found.group(i)) for i in range(1, 7))
    zone = found.group(8)
    if zone is None:
        if not 1 <= year < 1000:
            raise CoerceError(
                "an untimezoned dateTime is a relative time since boot, year below 1000 (Table 12)"
            )
        # the boot time is 0001-01-01T00:00:00, so 0001-01-03T03:04:05 is 2 days 3:04:05 after it
        try:
            return datetime(year, month, day, hour, minute, second) - datetime(1, 1, 1)
        except ValueError:
            raise CoerceError(f"{text[:40]!r} is not a dateTime") from None
    if zone not in ("Z", "-00:00", "+00:00"):
        raise CoerceError("a dateTime is UTC unless its definition says otherwise (Table 12)")
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=UTC)
    except ValueError:
        raise CoerceError(f"{text[:40]!r} is not a dateTime") from None


def _scalar(base: str, syntax: Syntax, text: str) -> object:
    if base == "string":
        if not _in_sizes(len(text), syntax.sizes):
            raise CoerceError(f"string of {len(text)} characters is outside the allowed length")
        if syntax.enumeration and text not in syntax.enumeration:
            raise CoerceError(f"{text[:40]!r} is not an enumerated value")
        if syntax.patterns and not any(_matches(pattern, text) for pattern in syntax.patterns):
            raise CoerceError(f"{text[:40]!r} matches none of the patterns")
        return text
    if base == "boolean":
        if text in ("1", "true"):
            return True
        if text in ("0", "false"):
            return False
        raise CoerceError(f"{text[:20]!r} is not a boolean: 0, 1, true or false (Table 12)")
    if base in _INT_RANGES:
        if not re.fullmatch(r"[+-]?[0-9]+", text):
            raise CoerceError(f"{text[:20]!r} is not an integer")
        number = int(text)
        low, high = _INT_RANGES[base]
        if not low <= number <= high:
            raise CoerceError(f"{number} is outside the range of {base}")
        _check_range(number, syntax)
        return number
    if base == "decimal":
        try:
            decimal = Decimal(text)
        except InvalidOperation:
            raise CoerceError(f"{text[:20]!r} is not a decimal") from None
        if not decimal.is_finite():
            raise CoerceError("a decimal is finite")
        _check_range(decimal, syntax)
        return decimal
    if base == "dateTime":
        return _datetime(text)
    if base == "base64":
        try:
            raw = base64.b64decode(text, validate=True)
        except ValueError:
            raise CoerceError("not Base64") from None
        if not _in_sizes(len(raw), syntax.sizes):
            raise CoerceError(f"{len(raw)} bytes are outside the allowed length before encoding")
        return raw
    if base == "hexBinary":
        if len(text) % 2 or not re.fullmatch(r"[0-9A-Fa-f]*", text):
            raise CoerceError("not hexBinary")
        octets = bytes.fromhex(text)
        # the size facet refers to the actual value, not the hex-encoded one (TR-106 A.2.3.3, Table 4)
        if not _in_sizes(len(octets), syntax.sizes):
            raise CoerceError(f"{len(octets)} bytes are outside the allowed length before encoding")
        return octets
    raise CoerceError(f"no coercion for type {base!r}")


def _matches(pattern: str, text: str) -> bool:
    try:
        return re.fullmatch(pattern, text) is not None
    except re.error:
        raise CoerceError(
            f"the model's pattern {pattern[:40]!r} is not one this reader understands"
        ) from None


@dataclass(frozen=True)
class _Context:
    model: DataModel | None
    path: str | None
    lookup: Callable[[str], str | None] | None
    instances: InstanceTree | None


_INTEGERS = frozenset({"int", "long", "unsignedInt", "unsignedLong"})
_ACCEPTS = {  # targetDataType -> the built-in types a referenced parameter may have (TR-106 Table 6)
    "integer": _INTEGERS,
    "decimal": _INTEGERS | {"decimal"},
    "long": frozenset({"long", "int"}),
    "unsignedLong": frozenset({"unsignedLong", "unsignedInt"}),
}


def _item(syntax: Syntax, text: str, context: _Context) -> object:
    typed = _scalar(syntax.base, syntax, text)
    if syntax.enumeration_target is not None:
        _check_enumeration_ref(syntax, text, context)
    if syntax.path_ref is not None and context.model is not None:
        _check_path_ref(syntax.path_ref, text, context)
    if syntax.instance_ref is not None:
        _check_instance_ref(syntax.instance_ref, typed, context)
    return typed


def _object_of(path: str) -> str:
    return path[: path.rindex(".") + 1] if "." in path else path


def _check_enumeration_ref(syntax: Syntax, text: str, context: _Context) -> None:
    """The value must be one of the items of the list-valued parameter the facet names, or its ``nullValue``
    (TR-106 A.2.3.7, Table 8). Only checked when the caller gives the parameter's own path and a ``lookup``."""
    if context.path is None or context.lookup is None:
        return
    if syntax.enumeration_null is not None and text == syntax.enumeration_null:
        return
    try:
        target = reference_path(
            _object_of(context.path),
            syntax.enumeration_target or "",
            syntax.enumeration_target_scope,
        )
    except PathError as error:
        raise CoerceError(f"the enumerationRef target cannot be read: {error.reason}") from None
    current = context.lookup(target)
    if current is None:
        raise CoerceError(f"{target[:80]} holds the valid values and has no value to check against")
    if text not in current.split(","):
        raise CoerceError(f"{text[:40]!r} is not among the values of {target[:80]}")


def _check_instance_ref(ref: InstanceRef, typed: object, context: _Context) -> None:
    """An Instance Number against an ``instanceRef`` facet (TR-106 A.2.3.7, Table 7). A value that is not
    the null reference (0 or -1, A.2.3.5) must be a positive Instance Number; for a strong reference, with the
    parameter's own ``path`` and an ``instances`` tree, the row ``targetParent`` names must exist. A weak
    reference is never checked for existence (A.2.3.6)."""
    if not isinstance(typed, int) or isinstance(typed, bool):
        raise CoerceError("an instanceRef value is an integer Instance Number")
    if typed in (0, -1):
        return
    if typed < 1:
        raise CoerceError(f"{typed} is not an Instance Number")
    if ref.ref_type != "strong" or context.instances is None or context.path is None:
        return
    try:
        table = reference_path(_object_of(context.path), ref.target_parent, ref.target_parent_scope)
    except PathError as error:
        raise CoerceError(
            f"instanceRef targetParent {ref.target_parent!r}: {error.reason}"
        ) from None
    if not context.instances.exists(f"{table.rstrip('.')}.{typed}."):
        raise CoerceError(
            f"{table.rstrip('.')}.{typed}. is a strong reference to an instance that is absent"
        )


def split_list(text: str, *, nested_brackets: bool = False) -> list[str]:
    """The items of a comma-separated list (TR-106 section 3.2.2): exactly one comma between items, whitespace
    around it belonging to the separator, and with ``nested_brackets`` a ``[...]`` group kept whole (one level of
    protection, which the caller removes). Raises :class:`CoerceError` for an unbalanced bracket, an empty
    item between two commas, or a bracket inside an unprotected item. An empty string is an empty list."""
    if text.strip() == "":
        return []
    items: list[str] = []
    depth = 0
    start = 0
    for i, c in enumerate(text):
        if nested_brackets and c == "[":
            depth += 1
        elif nested_brackets and c == "]":
            depth -= 1
            if depth < 0:
                raise CoerceError("a closing bracket with no opening one in a list value")
        elif c == "," and depth == 0:
            items.append(text[start:i].strip())
            start = i + 1
    if depth != 0:
        raise CoerceError("an opening bracket is never closed in a list value")
    items.append(text[start:].strip())
    return items


_TARGET_TYPES = {  # targetType -> the types it allows (a derived type may only take a subset)
    "any": {"parameter", "single", "table", "row"},
    "parameter": {"parameter"},
    "object": {"single", "table", "row"},
    "single": {"single"},
    "table": {"table"},
    "row": {"row"},
}


def _covered(inner: tuple[Number | None, Number | None], outer: Sizes | tuple) -> bool:
    low, high = inner
    for o_low, o_high in outer:
        if (o_low is None or (low is not None and low >= o_low)) and (
            o_high is None or (high is not None and high <= o_high)
        ):
            return True
    return False


def check_derivation(model: DataModel) -> list[str]:
    """The base type restriction of TR-106 A.2.3.8, Table 9, for the facets this reader holds: a derived
    ``dataType`` must not permit a value its base forbids. Checked: ``size`` and ``range`` (each interval of the
    derived type lies inside one interval of the base's, when the base states any), ``pathRef`` ``targetType``
    (the derived set of targets is a subset) and ``targetParent`` (when the base lists parents, the derived
    lists only some of them), and ``instanceRef`` ``targetParent`` unchanged. Not checked: ``enumeration`` and
    ``pattern`` (their rules need the values' descriptions and a regular-expression subset test), ``status``
    promotion and ``units``. Returns one sentence per violation, in the order of the model's ``dataType`` names;
    an empty list means none was found. A derived type whose base is a built-in type is not a derivation."""
    problems: list[str] = []
    for name, derived in model.data_types.items():
        base = model.data_types.get(derived.base)
        if base is None:
            continue
        for what, d_items, b_items in (
            ("size", derived.sizes, base.sizes),
            ("range", derived.ranges, base.ranges),
        ):
            if b_items:
                problems.extend(
                    f"{name}: {what} {item} is outside the base type {derived.base}'s {what}"
                    for item in d_items
                    if not _covered(item, b_items)
                )
        if derived.path_ref and base.path_ref:
            d, b = derived.path_ref, base.path_ref
            if not _TARGET_TYPES.get(d.target_type, set()) <= _TARGET_TYPES.get(
                b.target_type, set()
            ):
                problems.append(
                    f"{name}: targetType {d.target_type} permits targets {b.target_type} of {derived.base} does not"
                )
            if b.target_parent and not set(d.target_parent) <= set(b.target_parent):
                problems.append(f"{name}: targetParent is not narrower than {derived.base}'s")
        if (
            derived.instance_ref
            and base.instance_ref
            and derived.instance_ref.target_parent != base.instance_ref.target_parent
        ):
            problems.append(f"{name}: instanceRef targetParent differs from {derived.base}'s")
    return problems


def _template(path: str) -> str:
    return ".".join(_PLACEHOLDER if _is_instance_node(n) else n for n in path.split("."))


def _type_chain(model: DataModel, syntax: Syntax) -> set[str]:
    """Every type name a parameter's type is: its named data types and the built-in one under them."""
    names = {syntax.base}
    for _ in range(_MAX_RESOLVE_DEPTH):
        parent = model.data_types.get(syntax.base) if syntax.base not in _SIMPLE_TYPES else None
        if parent is None:
            break
        syntax = parent
        names.add(syntax.base)
    return names


def _check_path_ref(ref: PathRef, text: str, context: _Context) -> None:
    """A path-name value against a ``pathRef`` facet (TR-106 A.2.3.7, Table 6): what it names exists in the
    model and is of the right ``targetType``; with the parameter's own ``path`` its ``targetParent``; for a
    referenced parameter its ``targetDataType``; for a strong reference and an ``instances`` tree, that the
    row exists. The empty string is the null reference (A.2.3.5)."""
    model = context.model
    if model is None or text == "":
        return
    try:
        (hit,) = resolve_path(model, text, aliases=False, wildcards=False)
    except PathError as error:
        raise CoerceError(f"{text[:60]!r} references nothing: {error.reason}") from None
    definition = hit.definition
    template = definition.path
    kind = "parameter"
    if isinstance(definition, ObjectDef):
        kind = "single"
        if definition.multi:
            kind = "row" if template.count(_PLACEHOLDER) == len(hit.instances) else "table"
    ok = {
        "any": True,
        "parameter": kind == "parameter",
        "object": kind != "parameter",
        "single": kind == "single",
        "table": kind == "table",
        "row": kind == "row",
    }.get(ref.target_type)
    if ok is None:
        raise CoerceError(
            f"the model's targetType {ref.target_type!r} is not one this reader knows"
        )
    if not ok:
        raise CoerceError(f"{text[:60]!r} is a {kind}, and the reference takes {ref.target_type}")
    if ref.target_parent and context.path is not None:
        if kind == "parameter":
            container = template.rsplit(".", 1)[0] + "."
        elif kind == "row":
            container = template[: -len(_PLACEHOLDER) - 1]
        else:
            container = _parent_object(template)
        allowed = []
        for parent in ref.target_parent:
            try:
                resolved = reference_path(_object_of(context.path), parent, ref.target_parent_scope)
            except PathError as error:
                raise CoerceError(f"targetParent {parent!r}: {error.reason}") from None
            allowed.append(_template(resolved))
        if container not in allowed:
            raise CoerceError(f"{text[:60]!r} is not an immediate child of a targetParent")
    if (
        kind == "parameter"
        and ref.target_data_type != "any"
        and isinstance(definition, ParameterDef)
        and definition.syntax is not None
    ):
        accepted = _ACCEPTS.get(ref.target_data_type, frozenset({ref.target_data_type}))
        if not _type_chain(model, definition.syntax) & accepted:
            raise CoerceError(f"{text[:60]!r} is not a {ref.target_data_type} parameter")
    if (
        ref.ref_type == "strong"
        and context.instances is not None
        and not context.instances.exists(text)
    ):
        raise CoerceError(f"{text[:60]!r} is a strong reference to an instance that is absent")


def coerce_value(
    parameter: ParameterDef,
    value: object,
    *,
    model: DataModel | None = None,
    path: str | None = None,
    lookup: Callable[[str], str | None] | None = None,
    instances: InstanceTree | None = None,
) -> object:
    """Check ``value`` against the parameter's type in a TR-181 data model and return it typed.

    ``value`` is the text as received in a SOAP ``Value`` element (a ``bool`` or ``int`` already of the
    right Python type is accepted too). A named ``dataType`` (``IPv4Address``, ``Alias``) is looked up in
    ``model``, which is required when the parameter uses one. The result is ``bool`` for boolean, ``int``
    for int, unsignedInt, long and unsignedLong, ``Decimal`` for decimal, ``bytes`` for base64 and
    hexBinary, ``str`` for string, and for dateTime a UTC ``datetime`` or, for the untimezoned
    relative-since-boot form, a ``timedelta`` since boot; ``UNKNOWN_TIME`` is the value TR-069 reserves
    for "unknown or not applicable" (A.2.1, Table 12). A list-valued parameter takes its comma-separated
    text and returns a list of typed items, bounded by the list's ``minItems`` and ``maxItems``.

    What is checked: the type's own range (Table 12 gives int and unsignedInt; TR-106 Appendix I.4 gives
    long and unsignedLong), the model's ``size``, ``range`` with its ``step``, ``enumeration`` and
    ``pattern``. A ``size`` on base64 and hexBinary counts the decoded bytes, a ``size`` on the ``list``
    counts the characters of the whole value (TR-106 A.2.3.3, A.2.7.1; the unit of a list's size is this
    library's reading, see ROADMAP.md). With ``model`` given, a ``pathRef`` value must name something in the
    model of the right ``targetType`` and ``targetDataType``, and with the parameter's own instance ``path``
    also sit under a ``targetParent``; with ``instances`` a strong reference must name an instance that
    exists. An ``enumerationRef`` value is checked only when ``path`` and ``lookup`` (a function from a full
    Path Name to that parameter's current value, or None) are both given. ``instanceRef`` is checked as
    :func:`_check_instance_ref` says. A list whose ``nestedBrackets`` is ``required`` is split by
    :func:`split_list`, and when its item type is itself a list each item (a ``[...]`` group, or a
    percent-encoded one) is coerced as that list. Not checked: the "string defaults to 16 characters" rule, which Table 12 states for RPC arguments rather than
    data-model parameters. Raises :class:`CoerceError` for a value that does not fit and :class:`PathError` when a named type
    cannot be resolved.
    """
    syntax = parameter.syntax
    if syntax is None:
        raise CoerceError(f"{parameter.path} has no type in the model")
    if syntax.base not in _SIMPLE_TYPES:
        if model is None:
            raise PathError(f"{syntax.base!r} is a named data type; pass the model to resolve it")
        syntax = resolve_syntax(model, syntax)
    if isinstance(value, bool) and syntax.base == "boolean" and not syntax.is_list:
        return value
    if isinstance(value, int) and not isinstance(value, bool) and syntax.base in _INT_RANGES:
        value = str(value)
    if not isinstance(value, str):
        raise CoerceError(f"a {type(value).__name__} is not a TR-069 value; pass the text received")
    context = _Context(model, path, lookup, instances)
    if not syntax.is_list:
        return _item(syntax, value, context)
    if not _in_sizes(len(value), syntax.list_sizes):
        raise CoerceError(f"a list value of {len(value)} characters is outside the list's size")
    brackets = syntax.nested_brackets == "required"
    items = (
        split_list(value, nested_brackets=brackets)
        if brackets
        else (value.split(",") if value else [])
    )
    if syntax.min_items is not None and len(items) < syntax.min_items:
        raise CoerceError(f"a list of {len(items)} items is shorter than {syntax.min_items}")
    if syntax.max_items is not None and len(items) > syntax.max_items:
        raise CoerceError(f"a list of {len(items)} items is longer than {syntax.max_items}")
    if brackets:
        inner = model.data_types.get(parameter.syntax.base) if model and parameter.syntax else None
        if inner is not None and inner.is_list:
            return [
                coerce_value(
                    replace(parameter, syntax=inner),
                    item[1:-1] if item.startswith("[") and item.endswith("]") else unquote(item),
                    model=model,
                    path=path,
                    lookup=lookup,
                    instances=instances,
                )
                for item in items
            ]
    return [_item(syntax, item, context) for item in items]

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
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from devicespy import xmlsafe

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

__all__ = [
    "MAX_MODEL_BYTES",
    "MAX_PATH_LENGTH",
    "UNKNOWN_TIME",
    "CoerceError",
    "DataModel",
    "ObjectDef",
    "ParameterDef",
    "PathError",
    "Resolved",
    "Syntax",
    "children",
    "coerce_value",
    "load_model",
    "resolve_path",
    "resolve_syntax",
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


class PathError(ValueError):
    """A path name is malformed or does not address anything in the model; ``reason`` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Syntax:
    """A parameter's type as the data model writes it: ``base`` is a simple type name or the name of a
    ``dataType``; ``is_list`` marks a list-valued parameter; the restrictions are the model's own.

    ``min_length``, ``max_length``, ``minimum`` and ``maximum`` are the first ``size`` and ``range`` the model
    gives; ``sizes`` and ``ranges`` hold every one (a type may allow several lengths). ``patterns`` are the
    alternatives a string must match, ``enumeration_ref`` says the values are listed in another parameter
    (so no list is known here), ``min_items`` and ``max_items`` bound a list."""

    base: str
    is_list: bool = False
    min_length: int | None = None
    max_length: int | None = None
    minimum: int | None = None
    maximum: int | None = None
    enumeration: tuple[str, ...] = ()
    default: str | None = None
    sizes: tuple[tuple[int | None, int | None], ...] = ()
    ranges: tuple[tuple[int | None, int | None], ...] = ()
    patterns: tuple[str, ...] = ()
    min_items: int | None = None
    max_items: int | None = None
    enumeration_ref: bool = False


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


def _bounds(
    elements: list[ET.Element], low: str, high: str
) -> tuple[tuple[int | None, int | None], ...]:
    return tuple((_int(e.get(low)), _int(e.get(high))) for e in elements)


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
    ranges = _bounds([c for c in holder if c.tag == "range"], "minInclusive", "maxInclusive")
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
        any(c.tag == "enumerationRef" for c in holder),
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
        )
    return merged


def _in_ranges(number: int | Decimal, ranges: tuple[tuple[int | None, int | None], ...]) -> bool:
    return not ranges or any(
        (low is None or number >= low) and (high is None or number <= high) for low, high in ranges
    )


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
        if syntax.sizes and not any(
            (low is None or len(text) >= low) and (high is None or len(text) <= high)
            for low, high in syntax.sizes
        ):
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
        if not _in_ranges(number, syntax.ranges):
            raise CoerceError(f"{number} is outside the range the model gives")
        return number
    if base == "decimal":
        try:
            decimal = Decimal(text)
        except InvalidOperation:
            raise CoerceError(f"{text[:20]!r} is not a decimal") from None
        if not decimal.is_finite():
            raise CoerceError("a decimal is finite")
        if not _in_ranges(decimal, syntax.ranges):
            raise CoerceError(f"{decimal} is outside the range the model gives")
        return decimal
    if base == "dateTime":
        return _datetime(text)
    if base == "base64":
        try:
            raw = base64.b64decode(text, validate=True)
        except ValueError:
            raise CoerceError("not Base64") from None
        if syntax.sizes and not any(
            (low is None or len(raw) >= low) and (high is None or len(raw) <= high)
            for low, high in syntax.sizes
        ):
            raise CoerceError(f"{len(raw)} bytes are outside the allowed length before encoding")
        return raw
    if base == "hexBinary":
        if len(text) % 2 or not re.fullmatch(r"[0-9A-Fa-f]*", text):
            raise CoerceError("not hexBinary")
        return bytes.fromhex(text)
    raise CoerceError(f"no coercion for type {base!r}")


def _matches(pattern: str, text: str) -> bool:
    try:
        return re.fullmatch(pattern, text) is not None
    except re.error:
        raise CoerceError(
            f"the model's pattern {pattern[:40]!r} is not one this reader understands"
        ) from None


def coerce_value(
    parameter: ParameterDef, value: object, *, model: DataModel | None = None
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

    What is checked: the type's own range (Table 12 gives int and unsignedInt; long, unsignedLong,
    decimal and hexBinary come from TR-106, which this project has not read, so those use the XSD
    definitions), the model's ``size``, ``range``, ``enumeration`` and ``pattern``. Not checked: ``step``,
    ``enumerationRef``, ``pathRef``, hexBinary and list ``size``, and the "string defaults to 16
    characters" rule, which Table 12 states for RPC arguments rather than data-model parameters.
    Raises :class:`CoerceError` for a value that does not fit and :class:`PathError` when a named type
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
    if not syntax.is_list:
        return _scalar(syntax.base, syntax, value)
    items = value.split(",") if value else []
    if syntax.min_items is not None and len(items) < syntax.min_items:
        raise CoerceError(f"a list of {len(items)} items is shorter than {syntax.min_items}")
    if syntax.max_items is not None and len(items) > syntax.max_items:
        raise CoerceError(f"a list of {len(items)} items is longer than {syntax.max_items}")
    return [_scalar(syntax.base, syntax, item) for item in items]

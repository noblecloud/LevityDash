#!/usr/bin/env python
"""Discover Stateful subclasses and emit schemas/levity-dashboard.json.

Usage:
    poetry run gen-schema
    python -m tools.generate_schema

The generator walks every Stateful subclass that has a __tag__ (not Ellipsis,
None, or "Stateful"), introspects their __state_items__ ChainMap, converts
each StateProperty to a JSON Schema fragment, and assembles a discriminated
union schema keyed by tag name.

Non-Stateful value types are resolved via tools.schema_types.TYPE_MAP.
Stateful references (link= kwarg) are recursively expanded as $ref pointers.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bootstrap: ensure LevityDash can be imported from src/
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
WEATHERUNITS = REPO_ROOT.parent / "WeatherUnits" / "src"
sys.path.insert(0, str(SRC))
if WEATHERUNITS.exists():
    sys.path.insert(0, str(WEATHERUNITS))
elif (WEATHERUNITS.parent / "WeatherUnits").exists():
    sys.path.insert(0, str(WEATHERUNITS.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LEVITYDASH_CONFIG_DEBUG", "1")
os.environ.setdefault("LEVITY_BUILDING", "TRUE")

# TYPE_MAP is built lazily after LevityDash is imported (see generate())
from tools.schema_types import get_type_map


def _import_levity() -> None:
    """Trigger a minimal import of LevityDash so Stateful subclasses register."""
    import LevityDash  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_tag(tag: Any) -> str | None:
    if tag in {None, ..., "Stateful", "SharedOption"}:
        return None
    if isinstance(tag, str):
        return tag
    return None


def _python_type_to_json(py_types: tuple[type, ...]) -> dict:
    """Fallback JSON Schema for Python types not found in TYPE_MAP."""
    json_types = {str: "string", int: "integer", float: "number", bool: "boolean"}
    for t in py_types:
        if t in json_types:
            return {"type": json_types[t]}
        if t is type(None):
            continue
        if t is list:
            return {"type": "array", "items": {"type": "object"}}
        if t is dict:
            return {"type": "object"}
        if t is type:
            return {"type": "string"}
    return {"type": "string"}  # safest fallback


def _is_stateful_reference(prop) -> bool:
    """Check whether a StateProperty links to another Stateful subclass."""
    if getattr(getattr(prop, "_StateProperty__options", {}).get("link", False), "__state_items__", None):
        return True
    for ret in prop.returns:
        if isinstance(ret, type) and hasattr(ret, "__state_items__") and ret is not type:
            return True
    return False


def _extract_stateful_from_container(ret: type) -> type | None:
    """Check if a type is a container holding a Stateful element type."""
    origin = getattr(ret, "__origin__", None)
    if origin is not None:
        args = getattr(ret, "__args__", ())
        for arg in args:
            if isinstance(arg, type) and hasattr(arg, "__state_items__") and arg is not type:
                return arg
    # Check for TypedIterable (Stateful's custom iterable marker)
    subtype = getattr(ret, "__subtype__", None)
    if isinstance(subtype, tuple):
        for t in subtype:
            if isinstance(t, type) and hasattr(t, "__state_items__") and t is not type:
                return t
    elif isinstance(subtype, type) and hasattr(subtype, "__state_items__") and subtype is not type:
        return subtype
    return None


def _linked_type(prop) -> type | None:
    """Return the Stateful class linked by this property, if any."""
    # 1. Explicit link= kwarg
    linked_opt = getattr(prop, "_StateProperty__options", {}).get("link", False)
    if linked_opt and isinstance(linked_opt, type) and hasattr(linked_opt, "__state_items__"):
        return linked_opt

    # 2. Check returnsSpecial for generic aliases (e.g. List[ClockComponent])
    rets_special = getattr(prop, "returnsSpecial", None) or ()
    if isinstance(rets_special, type):
        rets_special = (rets_special,)
    for ret in rets_special:
        result = _extract_stateful_from_container(ret)
        if result is not None:
            return result

    # 3. Check regular returns for direct Stateful references
    for ret in prop.returns:
        if isinstance(ret, type) and hasattr(ret, "__state_items__") and ret is not type:
            return ret
        # Check if this is a GenericAlias with Stateful args
        result = _extract_stateful_from_container(ret)
        if result is not None:
            return result

    return None


# ---------------------------------------------------------------------------
# Core conversion
# ---------------------------------------------------------------------------

def _stateprop_to_schema(prop) -> dict:
    """Convert a single StateProperty to a JSON Schema fragment."""
    schema: dict[str, Any] = {}

    if prop.doc:
        schema["description"] = prop.doc

    # Resolve default
    if not prop.required and (dflt := prop.default) is not None and dflt is not ...:
        if isinstance(dflt, (bool, int, float, str)):
            schema["default"] = dflt
        elif isinstance(dflt, (list, dict)):
            try:
                json.dumps(dflt)
                schema["default"] = dflt
            except (TypeError, ValueError):
                pass

    # Stateful reference: emit a $ref or inline
    linked = _linked_type(prop)
    if linked is not None and linked.__name__ not in ("type", "Stateful"):
        ref_name = linked.__name__
        is_container = False
        rets_special = getattr(prop, "returnsSpecial", None) or ()
        if isinstance(rets_special, type):
            rets_special = (rets_special,)
        for ret in rets_special:
            subtype = getattr(ret, "__subtype__", None)
            if subtype is not None and hasattr(subtype, "__state_items__"):
                is_container = True
                break
        if not is_container:
            for ret in prop.returns:
                origin = getattr(ret, "__origin__", None)
                try:
                    if origin is not None and origin is list:
                        is_container = True
                        break
                except TypeError:
                    pass
        if is_container:
            schema["type"] = "array"
            schema["items"] = {"$ref": f"#/$defs/{ref_name}"}
        else:
            schema["$ref"] = f"#/$defs/{ref_name}"
        return schema

    # Check TYPE_MAP for each return type
    type_map = get_type_map()
    for ret in prop.returns:
        if ret is type(None):
            continue
        if ret in type_map:
            fragment = type_map[ret]
            if "$ref" in fragment:
                schema.update(fragment)
            elif "type" in fragment or "oneOf" in fragment or "anyOf" in fragment:
                merged = dict(schema)
                merged.pop("default", None)
                merged.update(fragment)
                if "default" in schema and "default" not in merged:
                    merged["default"] = schema["default"]
                schema = merged
            else:
                schema.update(fragment)
            break
    else:
        # Fallback to basic JSON type
        schema.update(_python_type_to_json(prop.returns))

    # Nullability
    if prop.allowNone:
        existing = schema.get("type")
        if existing and isinstance(existing, str):
            schema["type"] = [existing, "null"]
        elif existing and isinstance(existing, list) and "null" not in existing:
            schema["type"] = [*existing, "null"]

    return schema


def _class_to_schema(cls: type) -> dict:
    """Build a JSON Schema object for a Stateful subclass."""
    from LevityDash.lib.stateful import StateProperty

    properties: dict[str, dict] = {}
    required: list[str] = []

    items_map: dict = getattr(cls, "__state_items__", {})
    if not items_map:
        return {"type": "object", "properties": {}}

    for key, prop in items_map.items():
        if not isinstance(prop, StateProperty):
            continue
        if not bool(prop.actions & {"set"}):
            continue
        if key in ("type", "shared"):
            continue  # type is implicit in the compiled format, shared is internal

        prop_schema = _stateprop_to_schema(prop)
        # Use StateProperty's `key` for property output
        prop_key = prop.key if prop.key and isinstance(prop.key, str) else key
        properties[prop_key] = prop_schema

        if prop.required or (not prop.allowNone and not prop.hasDefault(cls)):
            required.append(prop_key)

    return {
        "type": "object",
        "properties": properties,
        "required": required if required else None,
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def _walk_stateful(cls: type) -> list[type]:
    """Recursively collect Stateful subclasses, deduplicating by id."""
    seen: set[int] = set()
    result: list[type] = []

    def _walk(c: type) -> None:
        if id(c) in seen:
            return
        seen.add(id(c))
        tag = getattr(c, "__tag__", None)
        tag = _resolve_tag(tag)
        if tag is not None:
            result.append(c)
        for sub in c.__subclasses__():
            _walk(sub)

    _walk(cls)
    return result


def _discover_modules() -> list[tuple[str, type]]:
    """Return sorted list of (tag, class) for every module-level Stateful subclass."""
    from LevityDash.lib.stateful import Stateful, StatefulMetaclass

    modules: list[tuple[str, type]] = []
    for cls in _walk_stateful(Stateful):
        tag = getattr(cls, "__tag__", None)
        tag = _resolve_tag(tag)
        if tag is None:
            continue
        modules.append((tag, cls))

    modules.sort(key=lambda x: x[0])
    return modules


# ---------------------------------------------------------------------------
# Schema assembly
# ---------------------------------------------------------------------------

def _build_one_of_entries(modules: list[tuple[str, type]]) -> list[dict]:
    """Build the oneOf entries for the discriminated root schema.

    Each entry is a single-key object where the key is the module tag
    and the value is the module's schema (referenced via $defs).
    """
    entries = []
    for tag, cls in modules:
        ref_name = cls.__name__
        entries.append({
            "type": "object",
            "properties": {
                tag: {"$ref": f"#/$defs/{ref_name}"},
            },
            "required": [tag],
            "additionalProperties": False,
        })

        # Also add a list variant for duplicate-type support
        entries.append({
            "type": "object",
            "properties": {
                tag: {
                    "type": "array",
                    "items": {"$ref": f"#/$defs/{ref_name}"},
                },
            },
            "required": [tag],
            "additionalProperties": False,
        })

    return entries


def _build_defs(modules: list[tuple[str, type]]) -> dict[str, dict]:
    """Build the $defs section with one entry per module class.

    Includes both tagged module types and any Stateful subclass they reference
    (e.g. Border, Display, DayAnnotations, etc.), even if those subclasses
    don't have a user-facing tag.
    """
    from LevityDash.lib.stateful import Stateful, StateProperty

    defs: dict[str, dict] = {}
    # Start with tagged modules
    pending: list[type] = [cls for _, cls in modules]
    seen: set[int] = set()

    # Collect all Stateful subclasses for potential inclusion
    all_stateful: dict[str, type] = {}
    for sub in Stateful.__subclasses__(deep=True):
        name = sub.__name__
        if name not in all_stateful:
            all_stateful[name] = sub

    while pending:
        cls = pending.pop()
        if id(cls) in seen:
            continue
        seen.add(id(cls))
        if cls.__name__ in defs:
            continue

        defs[cls.__name__] = _class_to_schema(cls)

        # Find any $ref in this class's properties and add referenced types
        for key, prop in getattr(cls, "__state_items__", {}).items():
            if not isinstance(prop, StateProperty):
                continue
            linked = _linked_type(prop)
            if linked is not None and linked.__name__ not in defs:
                pending.append(linked)
            # Also check for references in TYPE_MAP $ref
            for ret in prop.returns:
                type_map = get_type_map()
                if ret in type_map:
                    fragment = type_map[ret]
                    ref = fragment.get("$ref", "")
                    if ref.startswith("#/$defs/"):
                        ref_name = ref.split("/")[-1]
                        if ref_name in all_stateful and hasattr(all_stateful[ref_name], "__state_items__") and ref_name not in defs:
                            pending.append(all_stateful[ref_name])

    return defs


def _build_root_schema(modules: list[tuple[str, type]]) -> dict:
    """Assemble the complete JSON Schema document."""
    from LevityDash.lib.ui.Geometry import Geometry

    type_map = get_type_map()
    defs = _build_defs(modules)
    one_of = _build_one_of_entries(modules)

    # Extract shared type definitions from TYPE_MAP
    shared_defs = {}
    for py_type, fragment in type_map.items():
        name = getattr(py_type, "__name__", str(py_type))
        if name in ("str", "int", "float", "bool", "bytes"):
            continue
        shared_defs[name] = fragment

    schema: dict = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "https://levitydash.app/schemas/levity-dashboard.json",
        "title": "LevityDashboard",
        "description": "Schema for LevityDashboard .levity configuration files",
        "type": "object",
        "additionalProperties": False,
        "minProperties": 1,
        "patternProperties": {
            "^(?!type$|shared$).+$": {
                "oneOf": one_of,
            },
        },
        "$defs": {
            **defs,
            **shared_defs,
        },
    }

    return schema


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate() -> dict:
    """Discover modules and produce the full JSON Schema."""
    _import_levity()
    from LevityDash.lib.stateful import Stateful

    modules = _discover_modules()
    schema = _build_root_schema(modules)
    return schema


def write_schema(schema: dict, path: Path | None = None) -> Path:
    """Write the schema to disk, returning the output path."""
    if path is None:
        path = REPO_ROOT / "schemas" / "levity-dashboard.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema, indent=2, default=str))
    print(f"Wrote schema to {path}")
    return path


def main() -> None:
    schema = generate()
    write_schema(schema)


if __name__ == "__main__":
    main()

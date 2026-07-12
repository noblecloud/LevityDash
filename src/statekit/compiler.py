"""Custom YAML compiler for the statekit state/YAML format.

Transforms the human-friendly type-as-key format:
    stack:
      direction: Horizontal
      items:
        realtime.text:
          key: temp
        moon: {}
        realtime.text:
          key: humidity

Into the canonical compiled format:
    [{"type": "stack", "direction": "Horizontal", "items": [
        {"type": "realtime.text", "key": "temp"},
        {"type": "moon"},
        {"type": "realtime.text", "key": "humidity"}
    ]}]

The authoring format uses YAML mapping keys as module type tags,
eliminating the need for ``type:`` keys inside each module dict.
Duplicate keys at the same level (e.g. two ``realtime.text`` entries)
are allowed and produce multiple compiled items.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Custom YAML constructor: converts MappingNode with duplicate keys to a
# SequenceNode of single-key MappingNodes, but ONLY when the parent key is
# ``items`` (the one context where module-type keys appear).
# ---------------------------------------------------------------------------

_ITEMS_CONTEXT_KEY = "items"


def _preprocess_ast(node: yaml.Node, parent_key: str | None = None) -> yaml.Node:
    """Walk the YAML AST and restructure ``items`` mappings with duplicate keys.

    PyYAML's pure-Python parser stores all key-value pairs in
    ``MappingNode.value``, preserving duplicates.  If a mapping under the key
    ``items`` contains duplicate keys (module tags), we convert it to a
    ``SequenceNode`` of single-key ``MappingNode`` s so the constructor
    produces a list of ``{tag: config}`` objects rather than silently
    overwriting values.
    """
    if isinstance(node, yaml.MappingNode):
        keys = [
            item[0].value for item in node.value
            if hasattr(item[0], "value") and isinstance(item[0].value, str)
        ]
        has_dupes = len(keys) != len(set(keys))

        if parent_key == _ITEMS_CONTEXT_KEY and has_dupes:
            items: list[yaml.Node] = []
            for key_node, value_node in node.value:
                single = yaml.MappingNode(
                    tag="tag:yaml.org,2002:map",
                    value=[(key_node, value_node)],
                    start_mark=node.start_mark,
                    end_mark=node.end_mark,
                )
                items.append(single)
            seq = yaml.SequenceNode(
                tag="tag:yaml.org,2002:seq",
                value=items,
                start_mark=node.start_mark,
                end_mark=node.end_mark,
            )
            # Return the sequence and let the parent mapping reference it.
            # Since PyYAML construct_mapping iterates node.value tuples we can
            # substitute the whole mapping node for the parent.
            return seq

        # Recurse into children, passing the key down
        new_value: list[tuple[yaml.Node, yaml.Node]] = []
        for key_node, value_node in node.value:
            child_key = (
                key_node.value
                if hasattr(key_node, "value") and isinstance(key_node.value, str)
                else None
            )
            child_is_items = child_key == _ITEMS_CONTEXT_KEY

            processed = _preprocess_ast(value_node, parent_key=child_key)
            # If the result is a SequenceNode, we need to keep it attached to
            # the original key, not replace the MappingNode itself.
            new_value.append((key_node, processed))
        node.value = new_value

    elif isinstance(node, yaml.SequenceNode):
        for i, item in enumerate(node.value):
            node.value[i] = _preprocess_ast(item)

    return node


class ItemsLoader(yaml.SafeLoader):
    """YAML loader that handles type-as-key mappings in ``items`` contexts."""

    pass


def _construct_items_aware(loader: yaml.Loader, node: yaml.Node) -> Any:
    """Custom constructor that post-processes the constructed object.

    After normal construction, walk the result to convert type-keys in
    ``items``-context sequences into ``{"type": tag, ...}`` form.
    """
    result = loader.construct_mapping(node, deep=True)
    return result


ItemsLoader.add_constructor(
    "tag:yaml.org,2002:map", _construct_items_aware
)


def _postprocess(obj: Any, is_items: bool = False, known_tags: set[str] | None = None) -> Any:
    """Post-process the parsed Python structure.

    Recursively walks the object tree.  For dicts found inside an ``items``-
    context list, converts single-key entries (where the key is a known module
    type tag) into ``{"type": tag, ...}`` form.  If the single key is *not* a
    known tag (e.g. a measurement key inside a ``value-stack``), it is set as
    the ``key`` field instead, allowing the container's ``defaultType`` to
    supply the module type.
    """
    if known_tags is None:
        known_tags = set()

    if isinstance(obj, dict):
        # Is this a type-key entry (single key, no "type" field)?
        if is_items:
            keys = list(obj.keys())
            if len(keys) == 1 and "type" not in obj:
                tag = keys[0]
                config = obj[tag]
                if tag in known_tags:
                    # Known module tag → wrap as type
                    if isinstance(config, dict):
                        config["type"] = tag
                        return _postprocess(config, known_tags=known_tags)
                    elif isinstance(config, list):
                        return [
                            _postprocess(
                                {"type": tag, **(item if isinstance(item, dict) else {"_": item})},
                                known_tags=known_tags,
                            )
                            for item in config
                        ]
                    return obj
                else:
                    # Measurement key (value-stack shorthand) → set as "key"
                    if isinstance(config, dict):
                        config["key"] = tag
                        return _postprocess(config, known_tags=known_tags)
                    return obj

        return {
            k: _postprocess(v, is_items=(k == "items"), known_tags=known_tags)
            for k, v in obj.items()
        }

    elif isinstance(obj, list):
        return [_postprocess(item, is_items=True, known_tags=known_tags) for item in obj]

    return obj


# ---------------------------------------------------------------------------
# Compiler API
# ---------------------------------------------------------------------------

def compile_text(source: str) -> list[dict]:
    """Compile a LevityDash authoring format string to canonical compiled form.

    Steps:
    1. Parse with pure-Python YAML loader (preserves duplicate keys in AST)
    2. Transform the AST: ``items`` mappings with duplicate keys → sequences
    3. Construct the Python object tree
    4. Post-process: convert type-keys to ``{"type": tag, ...}`` form
    5. Return as a list of top-level modules
    """
    # Parse to AST nodes (pure Python, preserves duplicates)
    try:
        loader = yaml.compose(source)
    except yaml.error.YAMLError as exc:
        raise ValueError(f"Invalid YAML in authoring format: {exc}") from exc

    if loader is None:
        return []

    # Transform AST for items contexts
    loader = _preprocess_ast(loader)

    # Construct Python objects via SafeConstructor (no stream needed)
    constructed = _safe_construct_document(loader)

    # Wrap single object in list if needed (root should always be a mapping)
    if isinstance(constructed, dict):
        constructed = [constructed]

    # Retrieve known tags for value-stack measurement key detection
    known_tags = _build_known_tags_set()

    # Post-process type-keys → type: fields
    result: list[dict] = _postprocess(constructed, known_tags=known_tags)

    return result


def _safe_construct_document(loader: yaml.MappingNode) -> Any:
    """Construct a document from an AST node without a stream-backed Loader.

    PyYAML's ``SafeLoader(None).construct_document()`` fails because
    ``Reader.__init__`` eagerly reads the stream.  Instead we create a bare
    ``SafeConstructor`` with the minimal attrs needed for construction.
    """
    ctor = yaml.constructor.SafeConstructor()
    ctor.constructed_objects = {}
    ctor.recursive_objects = {}
    ctor.state_generators = []
    ctor.deep_construct = False
    return ctor.construct_document(loader)


def compile_file(path: Path | str) -> list[dict]:
    """Read a .levity file and compile it."""
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    return compile_text(source)


def compile_to_json(source: str | Path, indent: int = 2) -> str:
    """Compile and return the JSON string."""
    if isinstance(source, (str, Path)) and Path(source).is_file():
        data = compile_file(source)
    else:
        data = compile_text(str(source))
    return json.dumps(data, indent=indent, default=str)


def compile_and_cache(
    source_path: Path,
    cache_dir: Path | None = None,
) -> list[dict]:
    """Compile a .levity file and cache the result.

    The cache is written as ``<filename>.levity.json`` in *cache_dir* (defaults
    to ``~/.cache/LevityDash/compiled/``), keyed by mtime so it is
    automatically invalidated when the source changes.
    """
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "LevityDash" / "compiled"
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_path = cache_dir / f"{source_path.stem}.levity.json"
    src_mtime = source_path.stat().st_mtime

    # Return cached version if still fresh
    if cache_path.exists():
        try:
            cached: dict = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("_mtime") == src_mtime:
                return cached["data"]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    # Compile fresh
    data = compile_file(source_path)
    cache_payload = {"_mtime": src_mtime, "data": data}
    cache_path.write_text(
        json.dumps(cache_payload, indent=2, default=str),
        encoding="utf-8",
    )
    return data


def cache_path(source_path: Path) -> Path:
    """Return the expected cache path for a given source file."""
    return (
        Path.home() / ".cache" / "LevityDash" / "compiled" / f"{source_path.stem}.levity.json"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_known_tags_set() -> set[str]:
    """Return the set of known module tag strings.

    Tags are populated when Stateful subclasses with a ``tag=`` kwarg are
    defined.  Those subclasses live in LevityDash (not statekit itself), so
    this function tries to import LevityDash first to populate the tag set.
    Falls back to reading whatever is already registered in statekit.
    """
    try:
        import LevityDash  # noqa: F401 — populates __tags__ on the composed metaclass
    except Exception:
        return set()
    try:
        from LevityDash.lib.stateful import StatefulMetaclass
        tags = StatefulMetaclass.__tags__
        return {t for t in tags if isinstance(t, str)}
    except Exception:
        return set()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="LevityDash YAML compiler")
    parser.add_argument("files", nargs="+", type=Path, help=".levity files to compile")
    parser.add_argument("--cache", action="store_true", help="Use/update cache")
    parser.add_argument("--stdout", action="store_true", help="Print to stdout")
    args = parser.parse_args()

    for path in args.files:
        if args.cache:
            data = compile_and_cache(path)
        else:
            data = compile_file(path)

        output = json.dumps(data, indent=2, default=str)
        if args.stdout:
            print(output)
        else:
            compiled_path = path.with_suffix(".levity.json")
            compiled_path.write_text(output, encoding="utf-8")
            print(f"Compiled {path} -> {compiled_path}")


if __name__ == "__main__":
    main()

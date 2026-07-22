# qolkit

Small, dependency-free Python quality-of-life utilities. No domain concepts, no Qt — useful in any Python project. Extracted from LevityDash's `lib/utils/shared.py`, which re-exports everything here so existing consumers didn't change.

`statekit` depends on qolkit; qolkit depends on nothing (stdlib only) and never imports statekit or LevityDash back.

## What's inside

| module | exports |
|---|---|
| `sentinels` | `Unset`, `UnsetKwarg`, `OrUnset`, `IgnoreOr`, `Infix` — sentinel values and the infix-operator helper used to build `value \|OrUnset\| fallback`-style expressions |
| `mappings` | `DotDict` (dotted-key nested dict access), `DeepChainMap` (recursive `ChainMap` — nested mappings chain per-level), `get` (multi-key dict lookup with sentinel default), `sortDict`, `recursiveRemove`, `remove_empty_dicts` |
| `collections_` | `OrderedSet` (insertion-aware set; note: `add()` inserts at the *start* of iteration order), `Index` |
| `descriptors` | `classproperty` (replacement for the removed-in-3.13 `@classmethod @property` stack), `guarded_cached_property`, `clearCacheAttr` |

## Notes

- `DeepChainMap.__getitem__` wraps nested mapping values in new `DeepChainMap`s on access. If you're serializing one, flatten it first with `.to_dict()` — a raw `DeepChainMap` reaching a generic dumper will be silently stringified.
- Tests live in the parent repo at `tests/qolkit/` and are pure Python (`pytest tests/qolkit`).

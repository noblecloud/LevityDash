# statekit

A Qt-independent declarative state + YAML-persistence library. A class declares its saveable state as `StateProperty` attributes; statekit handles collecting that state into plain dicts, dumping/loading YAML, defaults, and deferred-action pooling during loads.

Extracted from LevityDash's `lib/stateful.py`. In LevityDash, `lib/stateful.py` remains as a thin Qt-aware facade: it composes `StatefulMetaclass` with Shiboken's `QObjectType` so `Stateful` classes can also be `QGraphicsObject` subclasses, and re-exports every consumer symbol — **inside LevityDash, import from `LevityDash.lib.stateful`, not from statekit directly.** Depends on `qolkit` only.

## The model

```python
from statekit import Stateful, StateProperty

class Widget(Stateful, tag='widget'):
    @StateProperty(default='untitled', key='name')
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = value

w = Widget()
w.name = 'hello'
w.state            # {'type': 'widget', 'name': 'hello'}
w.state = {'name': 'from-state'}   # applies values through the setters
```

A `StateProperty` is a property with extra, decorator-attachable hooks:

- `.setter` — required for writable state
- `.encode` / `.decode` — transform between the runtime value and its YAML-safe form
- `.condition` — decide whether the property is included in the emitted state
- `.factory` — construct a default child object (for properties holding other `Stateful`s)
- `.after`, `.update` — apply-order control and update hooks

`Stateful` subclasses declare a YAML `tag`; `StatefulDumper`/`StatefulLoader` (PyYAML-based) round-trip whole object trees to/from `.levity`-style YAML documents. `Default*` types (`DefaultTrue`, `DefaultInt`, `DefaultGroup`, …) give defaults identity-aware semantics so "still the default" values can be omitted from saves.

`ActionPool`/`defer` (in `statekit.actions`, exported here) batch and gate property applications while an object is loading — they intentionally live in statekit rather than qolkit because they require Stateful concepts (`is_loading`/`state_is_loading`).

## Module map

| module | contents |
|---|---|
| `core` | `StateProperty`, `Stateful`, `StatefulMetaclass`, `StatefulMixin`, `StatefulReferenceProperty` |
| `defaults` | the `Default*` family, `DefaultGroup`, `SourceType`, `isA` |
| `yaml` | `StatefulDumper`, `StatefulLoader`, `StatefulConstructor` |
| `data` | `StateData` |
| `actions` | `ActionPool`, `SubActionPool`, `defer`, `block_pools` |
| `introspect` | frame/type introspection helpers (`search_stack`, `makeType`, `Conditions`, …) |

## Gotchas

- **Encoders must emit plain types.** Anything reaching the dumper that isn't a plain dict/list/scalar gets silently `repr()`'d into the file by the generic object representor, corrupting the save. Flatten (`DeepChainMap.to_dict()`, unwrap measurement objects, …) in `.encode`.
- The metaclass is designed for cooperative composition (`super().__new__`) so frontends can mix in their own metaclasses (see LevityDash's `QStatefulMetaclass`).
- Tests live in the parent repo at `tests/statekit/` and are pure Python (`pytest tests/statekit`).

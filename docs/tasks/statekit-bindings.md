# statekit: validate with a reason, notify on change, bind to a value source

**Audit 2026-10-10: partly done.** The branch `feat/statekit-bindings` merged into `feat/value-sources` on 2026-10-04. Re-check items 1 to 3 against the code before you pick them up.

**Status:** open, actionable. Recorded 2026-10-04. Items 1 to 3 are in order; item 4 is later.
**Base:** `dev`. Step one: `git checkout -B feat/statekit-bindings dev`.
**Model:** suits `levity-worker` for item 1 alone. Items 2 and 3 want a design read first.

## Context

A survey of ipython/traitlets against `src/statekit` found four ideas worth
copying. They are ideas only. Do not add traitlets as a dependency. statekit
stays Qt-free and depends only on `qolkit`.

Today a bad value has no good path through statekit:

- `StateProperty.setState` runs the property's conditions. If one fails, the
  call returns and the value is dropped with no reason (`core.py:475`).
  `condition` itself returns a bool (`core.py:934`).
- The older kwargs check `__varifyKwargs` is defined (`core.py:172`) and its
  call is commented out (`core.py:591`).
- A value that passes no check reaches the setter. If the setter raises, the
  whole dashboard load aborts.

The setter fix in commit `fix(Stateful): clear _unset_keys_ even when a setter
raises` keeps an object usable after a raise. It does not stop the raise.

## Expected change

### 1. Validate with a reason

Source: traitlets `_validate` and `_cross_validate`, and the ordered
`Union.validate`.

Add `StateProperty.validate(owner, proposal) -> value`. It returns the value to
store, possibly coerced, or raises a `StateError` that carries the reason.
`setItemState` catches `StateError` per property, logs the item and the reason,
and skips that property. The rest of the item still loads.

The "number, else key, else expression" parse used by value-source keys
becomes one ordered decoder: try each form in turn, first match wins. This ties
to decision 5 in [value-sources.md](value-sources.md) (a missing input gives a
missing result): a failed validation is a skipped property, not an abort.

Keep `condition` working. It can wrap a bool result into a `StateError` with a
generic reason. Cost: low.

### 2. Notify only on a real change, with the old value

Source: traitlets compares old and new, and sends a change dict with `name`,
`old`, `new` and `owner`.

About 24 setters in `src/LevityDash` hand-roll `if value == self._x: return`
(for example `Realtime.py:207`). Add an opt-in `observe` hook. It fires only
when the new value differs from the old, receives the old value, and stays
muted while the owner loads. `after` stays as the load-time hook
(`core.py:505`).

statekit stores no values itself, so it has no old value to hand over. Read it
through the property's `fget`, guarded for the case where `fget` raises before
the first set. Cost: low to medium.

### 3. One-way binding, named `bind`

Source: traitlets `link` and `dlink`. statekit already uses `link` for a
Stateful reference (`core.py:553`, `core.py:1155`), so name this `bind`.

- A `ValueSource` protocol: `get()` and `subscribe(cb) -> unsubscribe`. A Number
  is a constant. A Key reads through the dispatcher. An Expression reads through
  its computed key.
- `Binding(source, setter, transform)` with `unlink()`.
- A property kind that releases its source when the value is replaced, and
  encodes the original text (not the resolved key) back to YAML.

This replaces the hand-rolled acquire and release in
`Realtime.py:197-239` (`acquireValueSource`, `_releaseKeySource`) and in
`Gauge.py:1911-2115` (marker and fill sources, `releaseSources` at `:3858`).

The hop onto the GUI thread belongs in the LevityDash facade
(`src/LevityDash/lib/stateful.py`), not in statekit. Cost: medium. Depends on
items 1 and 2.

### 4. Later

- **Rollback inside ActionPool batches.** Needs the old values from item 2.
- **Per-element validation** for list properties such as `markers:`. Do it
  after item 1.
- **Owner known at class creation.** Use `__set_name__` in place of the
  `getframe` scrape and source lookup (`core.py:227`). Verified that
  `__set_name__` runs under a QObject-composed metaclass on this PySide6. Cost:
  high, and it gains robustness only. Do it last, if at all.

## Verification

- **Item 1:** a `StateProperty` whose `validate` raises `StateError`. Load a
  state with that bad value and a good one. The bad property keeps its default,
  the good one is set, the log names the item and the reason, and the load does
  not abort. Pure Python, in `tests/statekit`.
- **Item 2:** a setter set twice to the same value fires `observe` once. It
  never fires during load. The old value arrives with the change.
- **Item 3:** replace a bound value and confirm the old source's subscriber
  count drops to zero. Then render a gauge with an expression marker
  (`docs/design-references/presets/`) and Read the PNG: the marker must look the
  same as before the port.
- **Whole change:** `tests/statekit` and the full suite pass. Known failures:
  `test_gauge_fill_sources`, `test_shared_expression_panels`,
  `test_sizegroups_integration`.

## Scope

- Do not import Qt or LevityDash from statekit.
- Do not change `link` semantics.
- Land each item as its own commit.

## Related

- [value-sources.md](value-sources.md): decision 5, and the acquire/release API
  that item 3 wraps

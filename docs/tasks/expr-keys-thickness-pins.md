# Expression keys for `thickness:` and `pins:`

**Audit 2026-10-10: done.** Merged into `dev` (`feat/expr-props`).

Goal: a Graph's `thickness:` and `pins:` accept an expression for their `key:`, not only a
plain key. Example: `thickness: {key: max(environment.wind.speed.speed, today), weight: [0.2, 1.2]}`,
`pins: {key: environment.condition.icon, size: 14, offset: -1.2}`.

Branch: `feat/expr-props`, based on `dev` (`5661eb4`).

## The pattern to copy — `Realtime.py` already does exactly this for a panel key

- `acquireValueSource(text)` (`lib/plugins/computed.py:512`): a plain key comes back as
  itself and registers nothing; an expression is registered (locally, or via the remote
  bridge in mode=remote) and its computed key comes back; malformed logs an error and
  returns None — it never raises, because one item's exception aborts the whole load.
  Every call that returns a computed key needs a matching `releaseValueSource` with the
  same text.
- `KeySource(text, key)` held on the item (`Realtime.py:208-216, 242-245`): carries the
  text for `encode` and releases on replace/delete.
- The unchanged-key guard (`Realtime.py:211-214`): if the new value equals the current
  one, release the newly acquired source and return — without it a reload double-counts.
- `encode` returns `source.text` (`Realtime.py:236-240`), so a save round-trips the
  expression, never the computed key.

## Where to wire it

- `Graph.py:1853-1862` — the `thickness` condition (same shape at `pins`, ~1877-1886):
  route `value['key']` through `acquireValueSource`; the stored dict keeps the computed
  key (that is what `sideSeries` resolves) and the `KeySource` keeps the text.
- `Graph.py:1910, 1916` — the consumers: `self.data.sideSeries(self._thickness['key'])`.
  A computed key is just another dispatcher key (the engine connects a `ComputedSource`),
  so `sideSeries` needs no change.
- `Graph.py:1849-1850` / `1877-1878` — the setters: release the previous property's
  `KeySource` before storing the new one. Release on item delete as well, so a removed
  graph does not hold the expression's refcount up.
- `encode` for both properties must write the expression text back, not the computed key.

## Verify

- Render a preset with an expression `thickness`/`pins`; its effect must match the
  plain-key form (render-diff harness: `src/LevityDash/devtools/render_diff.py`).
- Refcount: two items sharing one expression key, then delete one — the survivor keeps
  updating. (`computed.py`'s entry count is the refcount; confirm the accessor name.)
- Save round-trip keeps the expression text as `key`.
- Condition-icon fixture: a graph with `pins: {key: environment.condition.icon, ...}`
  renders glyphs — the docstring's own example at `Graph.py:1866-1868`.

## Harness notes (2026-10-06, from the merge check) - all fixed

- `polar-clock` rendered black in `render_diff.py capture`. The cause was not a missing
  key: `_boot.freeze_time` only re-pinned modules whose attribute was named `now`, and
  `polar/item.py` imports the clock `as localNow`, so the plot asked the wall clock for
  "today" while the Fixture had stamped its series in the frozen day. It now pins by
  identity under any name. `polar-rose` and `polar-trail` also drew empty: `stormy-day`
  gives the wind direction no series, so `polar-day` is now a `SERIES_SOURCES` entry.
- Masks re-measured at 1600x900 / 2560x1440. `graph-figure` is now `(0, 494, 1269, 893)`
  on `emissive`. `ev-caption` is gone: eight showcase captures are byte-identical
  (`FIXTURE_DELAY_MS=end` removed the unit race by construction), so there is nothing
  to mask.
- A second `render_widget.py` run hung after writing its PNG. Not the second run, the
  Mock plugin: the design seed enables it, it never finishes, and the interpreter
  joins its worker thread at exit. `render_widget.py` and `render_dashboard.py` now
  call `_boot.shutdown(dashboard)` once the image is saved.

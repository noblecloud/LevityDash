# Gauge Studio: the value sources never reach their consumers, and 17 cells do not load

Two defects in one job — they share a smell: the Studio stands in for the app's data
in ways that depend on *where* a name happens to live rather than on a mechanism.

## Part 1 — `installSources()` patches a name no consumer reads

`src/LevityDash/devtools/_studio_stage.py:40` imports the module it means to patch as

```python
from LevityDash.lib.ui.frontends.PySide.Modules.Displays import Gauge as _gaugeModule
```

and `installSources()` (`:290`) then does

```python
_gaugeModule.openValueSource = _openValueSource    # :292
```

`Displays/__init__.py` does `from .Gauge import *`, so the name `Gauge` in that package
is the **class**, not the submodule: the assignment lands on a class attribute nothing
reads. The consumers call the bare name in their own module globals — `Gauge.py` before
the meter split, `meter/elements.py` after it — so the studio's stand-in reaches no
consumer at all.

Measured consequence, identical on `a31af10` and on `refactor/meter`: a marker, fill or
caption that names a key falls through to the real `lib.valuesource` against an un-booted
dashboard, and the element stays hidden. A fill naming `environment.temperature.high`
builds but is not visible; patch `openValueSource` where the consumer actually reads it
and the same fill draws (render hash `fe4e9546fad5` -> `ee1beb3530cf`). The split did not
change the defect's behaviour — it moved the consumer, so there are now **two** modules
that have to be satisfied.

## Part 2 — 17 of the 30 showcase cells never load (same smell, fold in per the review)

`gs.showcaseCells()` returns 30 cells. 13 load; 17 fail, identically in both trees:

- 16 raise `TypeError: 'NoneType' object is not callable` — a numeric field
  (`GaugeRange.min`/`max` at `meter/meter.py:61`, or `Graduations.usr_interval`) is
  decoded against `gauge.valueClass` while it is still `None` (`meter/meter.py:151` and
  `:187` call the decode helper in `meter/scale.py` with `self._gauge.valueClass`). The
  cell's states apply before `StudioGauge.build` assigns the value class.
- 1, Rain rate, raises `NotImplementedError: Multi-Unit values are not supported yet`.

## The change expected

1. **One lookup, not a swapped global.** Resolve value sources through a single function
   (for example `lib/valuesource.resolve(...)`) that consults a studio-installed stand-in
   when one is registered, and make both consumer modules call it. `installSources()` then
   installs the stand-in instead of patching names — and survives the next refactor that
   moves a consumer.
2. **The cell-loading order.** Assign the value class before the cell's states apply, or
   let a numeric field decode against the class the build assigns — pick one and say why.
   The `Multi-Unit` cell is its own small decision: support it, or fail with a message the
   Studio can show rather than an exception that costs the whole cell.

## Verification

`src/LevityDash/devtools/render_diff_tools/studio_smoke2.py` in the meter worktree — offscreen, no app boot:
`QT_QPA_PLATFORM=offscreen .venv/bin/python src/LevityDash/devtools/render_diff_tools/studio_smoke2.py`.

- Before: the keyed fill builds but stays hidden; 13 of 30 cells load.
- After: the keyed fill is visible; all 30 cells load.
- Slider regression must hold: `studio.studio.value`, the value label and a hash of
  `studio.studio.render()` move together across the sweep (40/55/70/85/100, five distinct
  hashes). A pass that holds a `studio.studio.gauge` reference across `settle()` will
  report a false negative — `settle()` rebuilds the gauge.

Raw numbers for both trees: `docs/tasks/studio-slider-smoke.md`.

## Suggested branch

`fix/studio-value-sources`. This one is explicitly *after* the `refactor/meter` merge:
part 1 needs one lookup across both consumer modules, which only makes sense once the
split has landed.

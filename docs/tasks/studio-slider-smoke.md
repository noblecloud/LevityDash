# Gauge Studio offscreen smoke: the value slider, the sources, a fill that names a key

Question under review: *run the Studio offscreen and confirm that the preview still follows
its value slider. If it does not, the defect is no longer latent and it becomes part of this
branch.* A first pass in this worktree suggested it did not; the attribution was missing.

Harness: `.render-diff/tools/studio_smoke2.py`, copied to scratch and fixed (see "Harness"
below for the two bugs it had and one trap that made the first pass look negative).
This note is the only file written in this worktree. No commit.

## Trees and commands

| tree | HEAD | branch / state | venv |
| --- | --- | --- | --- |
| meter (this worktree) | `fa72444` | `refactor/meter` (one docs-only commit past the merge `5dea824`; `git diff 5dea824 fa72444` touches only `docs/tasks/*.md`) | `.venv/bin/python` (CPython 3.14.3) |
| upstream baseline | `a31af10` | detached HEAD in `.claude/worktrees/emissive-check` (worktree already existed with its own `poetry install`) | `.venv/bin/python` |

```sh
# measured against each tree's own venv and its own src/
QT_QPA_PLATFORM=offscreen <tree>/.venv/bin/python studio_smoke4.py <tree>   # Q1-Q3
QT_QPA_PLATFORM=offscreen <tree>/.venv/bin/python studio_smoke5.py <tree>   # Q4
```

`_studio_env.prepare()` sets `LEVITYDASH_CONFIG_DEBUG=1`, so every `LevityDash` directory is a
throwaway temp dir: the real config is not read or written. Offscreen; no window.

## Q1. Which showcase cells load

`gs.showcaseCells()` returns **30** cells. **13 load, 17 fail — identically in both trees**
(the cell-by-cell outcome lists compare equal as sets of `(index, label, ok, error)`).

Load (13): Temperature, Humidity, Cloud cover, EV charging, Battery, Dimmer, Volume,
Activity rings, Thermostat, System, Pressure, Solar, CPU temp.

Fail (17):
- 16 cells: `TypeError: 'NoneType' object is not callable`. The gauge's key has no
  WeatherUnits class in the studio, so a numeric field (`GaugeRange.min`/`.max`, or
  `Graduations.usr_interval`) is decoded against `gauge.valueClass = None` and
  `decode_measurement` calls `None(value)` (`meter/scale.py:121` ->
  `WeatherUnits/__init__.py:76`). Cells: Wind, Drive, Water, Washer, Air quality, UV index,
  Fuel, Energy, Timer, Heart rate, Coolant, Sun, Clock, Clock, Engine, Download.
- 1 cell: Rain rate — `NotImplementedError: Multi-Unit values are not supported yet`
  (`WeatherUnits/__init__.py:78`).

**Verdict:** 13/30 showcase cells load, with the same 17 failures in the meter tree and
upstream a31af10 — pre-existing, not a property of this branch.

## Q2. Does the value slider move the preview?

Cell 1 "Temperature", key `environment.temperature.temperature`, range `(0.0, 120.0)`. The gauge is
re-read from the stage every step, because `settle()` rebuilds it.

Meter tree (`fa72444`), identical to upstream (`a31af10`), same hashes:

| slider | `studio.studio.value` | `gauge.value` | value-label text | render() sha256[:12] |
| ---: | ---: | ---: | :---: | :--- |
| 0 | 40.00 | 40.00 | `40°` | `fe4e9546fad5` |
| 250 | 55.00 | 55.00 | `55°` | `ca26cd7e12cc` |
| 500 | 70.00 | 70.00 | `70°` | `9a3df4030d3e` |
| 750 | 85.00 | 85.00 | `85°` | `2b341308d378` |
| 1000 | 100.00 | 100.00 | `100°` | `620cfd9374b6` |

`studio.value`, `gauge.value` and the value label each take 5 distinct values, and the rendered
image takes 5 distinct hashes. The same holds after `settle()` (the rebuild path).

**Verdict:** the preview DOES follow the slider — value, label text and rendered pixels all
move together — in the meter tree and identically in upstream a31af10. (The first pass reported
"does not" only because its harness held a stale `studio.studio.gauge` reference across a
`settle()` that rebuilds the gauge; see "Harness". The defect is not real and is not in this
branch's diff.)

## Q3. `openValueSource`: which module each consumer actually sees

The object each name points at, compared by identity to
`_studio_stage._openValueSource` (the studio's stand-in). `installSources()` runs
`_gaugeModule.openValueSource = _openValueSource` where `_gaugeModule` is
`from ...Displays import Gauge` — and `Displays/__init__.py` does `from .Gauge import *`,
which binds the package name `Gauge` to the **class**, not the module.

| name | meter `fa72444` | upstream `a31af10` |
| --- | --- | --- |
| `_studio_stage._gaugeModule` is | the **class** `Displays.Gauge` | the **class** `Displays.Gauge` |
| `Displays.Gauge` (CLASS attr) — the patch target | the studio one | the studio one |
| `Displays` package attr | NOT the studio one | NOT the studio one |
| `Gauge.py` MODULE attr | NOT the studio one | NOT the studio one |
| `meter/elements.py` MODULE attr | NOT the studio one | (no meter module) |

The consumers call the bare name `openValueSource`, which resolves in **their own module's
globals** — `Gauge.py`'s in upstream, `meter/elements.py`'s after the split. Neither is the
class attribute the patch writes, so the studio's stand-in reaches **no consumer** in either
tree. The markers/fills/captions that name a key therefore ask the real
`LevityDash.lib.valuesource.openValueSource`, against a dashboard that was never booted.

**Verdict:** the patch writes `Displays.Gauge.openValueSource` (the class) but the consumers
read the `Gauge.py` module global (upstream) or the `meter/elements.py` module global (meter)
— so it reaches neither; identical in both trees, pre-existing, and the split did not change it.

## Q4. A fill that names a key

`docs/design-references/presets/sun-path.levity` has `fill: {to: astronomy.sun.hour}`. That
preset cannot load in the studio at all: its `range: {min: 7.52, max: 19.15}` is decoded
against `gauge.valueClass = None` before the studio assigns the value class
(`_studio_stage.StudioGauge.build` sets `valueClass` *after* `Gauge(...)` returns), so loading
raises `TypeError: 'NoneType' object is not callable` (`meter/meter.py:151` /
`Gauge.py` equivalent -> `scale.py:121` -> `WeatherUnits/__init__.py:76`). Removing
`minor.interval` does not help; the range decode fails. Same in both trees. So the sun-path
fill item itself is never reachable.

To observe the fill path directly, experiment C/D put a fill that names a key
(`{to: environment.temperature.high}`) on the Temperature cell (which loads):

| experiment | meter `fa72444` | upstream `a31af10` |
| --- | --- | --- |
| C: consumer sees the REAL `openValueSource` | gauge built, fill built, **fill visible = False**, px `fe4e9546fad5` | gauge built, fill built, **fill visible = False**, px `fe4e9546fad5` |
| D: same, but patch `openValueSource` where the consumer looks (`Gauge.py` module; `meter/elements.py` module in meter) | fill built, **fill visible = True**, px `ee1beb3530cf` | fill built, **fill visible = True**, px `ee1beb3530cf` |

A fill that names a key builds but stays hidden, because the real source returns nothing for
the un-booted dashboard; when the stand-in is placed where the consumer actually reads it, the
same fill becomes visible and the render changes. Identical in both trees.

**Verdict:** a fill that names a key does NOT become visible in the studio (the sun-path gauge
cannot even load, and on a gauge that does load the fill builds hidden) in the meter tree and
identically in upstream a31af10 — pre-existing, caused by Q3's patch-target mistake, not by
this branch.

## Harness

`.render-diff/tools/studio_smoke2.py` (the starting point) had two bugs and one trap:

1. preset path was `DEVTOOLS.parent.parent / 'docs/...'` (that is `src/`) — fixed to
   `DEVTOOLS.parents[2] / 'docs/design-references/presets/sun-path.levity'`;
2. it did not print which of "the setter did not run" vs "the gauge did not follow" was true —
   the fixed harness prints `studio.studio.value`, `studio.valueSlider.value()`, `gauge.value`
   and the value-label text at every step;
3. **trap:** it captured `gauge = studio.studio.gauge` once and read that reference across
   `settle()`, which *rebuilds* the gauge — so `gauge.value` stayed pinned at the value from
   the freeze point while `render()` (live scene) moved. That is the whole of the earlier
   "does not follow" signal. Re-reading the gauge from the stage each step shows it follows.

## Verdicts, one sentence each

- **Cells load:** 13/30, with the same 17 failures (unknown unit class; one multi-unit) in both
  trees — pre-existing.
- **Slider follows:** yes, value + value-label + rendered pixels all track the slider in the
  meter tree, identically in upstream a31af10 — the earlier negative was a stale-reference
  harness artifact, so no defect joins this branch.
- **Sources reach consumers:** no — `installSources()` writes the class attr
  `Displays.Gauge.openValueSource` but consumers read the `Gauge.py` (upstream) /
  `meter/elements.py` (meter) module globals, in both trees — pre-existing.
- **Fill builds:** a fill naming a key builds but stays hidden (and the sun-path gauge cannot
  load at all) in both trees; it becomes visible only when the stand-in is patched where the
  consumer reads it — pre-existing, the same patch-target mistake.

**One line, meter vs upstream:** the meter tree and upstream a31af10 are byte-for-byte
identical on every measurement here (same 13 cells, same five slider hashes
`fe4e9546fad5 / ca26cd7e12cc / 9a3df4030d3e / 2b341308d378 / 620cfd9374b6`, same source
table, same fill outcome) — so nothing here is attributable to the meter refactor or its merge.

Worktrees left in place: `blackfish-meter` (this one) and `emissive-check` (upstream a31af10,
pre-existing). No commit; no push; no tests edited; no user config touched.

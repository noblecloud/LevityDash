# Gauge tick labels: each unit's compact convention, defaults a dashboard can set

**Status:** open, actionable. Recorded 2026-10-04.
**Base:** `feat/value-sources`. Step one: `git checkout -B feat/tick-label-format feat/value-sources`.
**Model:** 1a's ranking is decided (below); its API spelling is the implementer's. 1a-1c and 3 suit `levity-worker` (Sonnet). Phase 2 involves design calls: use Opus, or bring the questions back to the maintainer.

## The problem

A pressure dial with ticks at 28, 29, 30, 31 and 32 inHg labels them `28.00 29.00 …`. The precision is the unit's (`[UnitProperties] inHg = precision=2`). That precision suits the *reading*, `29.97`, but not a dial face.

The question is **how each unit is conventionally shown, with as little information as possible without looking silly**. That convention is cultural, and it is per **unit**, not per measurement type:

| unit | reading | dial face / scale label |
|---|---|---|
| inHg | `29.92` | `28 29 30` (whole inches) |
| hPa, mbar | `1013` | `1000 1010 1020`; never decimals |
| °F, °C | `98°` | `60° 70°` |
| mph, km/h | `12` | `0 10 20` |
| rain, in | `0.25` | `0.25 0.50` (here the zeros are the convention) |

The maintainer's rules for the fix:

- **Not per measurement type.** inHg and hPa have opposite conventions, so "all pressures" is wrong.
- **Not in `config.ini`.** `[UnitProperties]` is user-facing configuration, not where a unit's own conventions belong.
- **Use WeatherUnits formatting.** Do not post-process strings with regexes. That was tried and rejected.
- **No bolt-ons.** No format table inside the gauge.

## Phase 1 — units carry a compact format; the tick spacing sets its floor

### 1a. WeatherUnits: a compact format per unit (sibling repo `../WeatherUnits`)

Where a unit's formatting comes from today, lowest to highest (`ChainMap(extras, specParams, params)` in `SmartFloat.__format__`, `base/_SmartFloat.py` ~828):

1. class attributes: `_precision`, `_digit_budget`. Base defaults are in `base/_Measurement.py` ~428. Most unit classes set none: `InchOfMercury` (`pressure/pressure.py` ~135) is bare, and `Millibar` sets only `_digit_budget`.
2. `[UnitProperties]` in the loaded config, which writes onto the class. `inHg = precision=2, digit_budget=4, trailing_zeros=precision` is in `config/us.ini:39` and in LevityDash's `resources/example-config/config.ini:87`.
3. the caller's format spec, as a string (`'precision=0'`) or keywords. **This outranks config.**

Add a **compact** profile: the format for a number that is a label, not a reading (a dial face, an axis).

**The ranking is decided:** compact is something the caller *asks for*, so it sits at level 3, beside any other explicit spec. It does not compete with `[UnitProperties]`, which keeps governing readings.

**Its default is derived, not declared:** the unit's reading format with padding zeros dropped (`trailing_zeros: off`), still capped by the configured precision.
- inHg compact gives `28` and `29.5`, never `28.00`.
- A unit whose convention *keeps* its zeros (rain in inches) declares that, as a class attribute.
- So most units need nothing, and nothing goes in `config.ini`.

The implementer chooses the spelling:
- a named profile `format(v, 'compact')`;
- or a `compact=True` spec flag that expands to the unit's `_compact_format` (class attribute, default `{'trailing_zeros': 'off'}`).

Prefer whichever fits how `__format__` already resolves `specParams`. Do not build a parallel mechanism.

Also in that repo:
- **The keyword-precision fix.** `v.__format__('', precision=0)` is ignored when the unit's config says `trailing_zeros=precision`.
  - The string form `format(v, 'precision=0')` works, which is why the bug hides.
  - The fix (`params.explicitPrecision` in `base/_SmartFloat.py`) is uncommitted in the maintainer's checkout. Re-apply it from [the diff below](#the-keyword-precision-fix) and add the regression test.
  - Hand back a commit; the maintainer pushes WeatherUnits.

⚠️ **To reproduce it, load the US config.** WeatherUnits picks `us.ini` or `si.ini` from the **locale**, and a container without `en_US` silently gets `si.ini`. That config has no `inHg` line, so precision is 1 and the bug cannot show.
- The tell: plain `format(InchOfMercury(29.92), '')` gives `'29.9 inHg'`. With `us.ini` loaded it gives `'29.92 inHg'`.
- Set `WU_CONFIG_PATH=<abs path>/src/WeatherUnits/config/us.ini`. That is the variable; `WU_CONFIG` does nothing.

Verified 2026-10-04 with `us.ini` loaded:

| call | without the fix | with it |
|---|---|---|
| `format(H(28.0), 'precision=0')` | `28 inHg` | `28 inHg` |
| `H(28.0).__format__('', precision=0)` | **`28.00 inHg`** | `28 inHg` |
| `H(29.92).__format__('', precision=0)` | **`30.00 inHg`** | `30 inHg` |

#### The keyword-precision fix

In `SmartFloat.__format__`, right after `params.specParams = specParams`:

```python
		# The caller's own precision, from either spelling - `format(v,
		# 'precision=0')` or `v.__format__('', precision=0)`. Captured now:
		# `extras` is the first map, so every `params['precision'] = ...`
		# below writes into it and the asked-for value is gone by the time
		# trailing_zeros needs it.
		params.explicitPrecision = extras.get('precision', specParams.get('precision'))
```

and in the `trailing_zeros` branch, `configured = params.specParams.get('precision')` becomes `configured = params.explicitPrecision`.

### 1b. LevityDash: tick labels ask for the compact format

In `GaugeTickTextGroup` (`src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Gauge.py` ~3051):

- Replace the `_tick_format` class attribute with an `@format_spec.item_default`, the same pattern as `enabled.item_default` (~3247).
- It asks for the unit's compact format plus `show_unit: False`. The word unit is said once, by the unit label. Symbols like `°` and `%` follow the unit's convention.
- The user's `format:` still **merges over** the default rather than replacing it, so `format: {precision: 0}` must not bring the word unit back onto every tick. Keep that comment.

### 1c. The tick spacing is a floor, not the rule

Adjacent labels must stay distinct. A zoomed barograph at 29.90–30.10 with 0.05 ticks cannot drop to the compact `30 30 30`. So:

```
precision = max(compact precision, the smallest d for which every tick value rounds exactly to d places)
```

This rarely triggers. When it does, the labels show exactly the digits the scale needs (`29.90 29.95 30.00`): trailing zeros come back only where the spacing forces them.

### 1d. Optional: label only round ticks

Real instrument faces label whole units and leave the half-ticks bare. That avoids `28.5` beside `29` *and* `28.5` beside `29.0`.

- This is about **which** ticks get labels, which is the `Graduations` label interval (`usr_interval` / `required_interval_factors` near the top of `Gauge.py`).
- It is not part of the formatting. Do it only if 1a–1c still leave mixed-precision faces, and show the maintainer before/after renders.

### Verify

- **Tests:**
  - WeatherUnits:
    - `format(InchOfMercury(28.0), <compact>)` gives `28` and `29.5` stays `29.5`, **with `us.ini` loaded** (see the ⚠️ above);
    - `Hectopascal(1013.2)` compact gives `1013`;
    - the keyword `precision=0` gives `28`.
  - LevityDash: a new `tests/ui/test_gauge_tick_format.py` builds gauges (see the `_gauge` helper in `tests/ui/test_gauge_fill_sources.py`) and asserts the label strings for each of these:
    - inHg 28–32 by 1;
    - inHg 29.9–30.1 by 0.05;
    - hPa;
    - °F.
- **Render:**
  ```bash
  QT_QPA_PLATFORM=offscreen .venv/bin/python src/LevityDash/devtools/render_widget.py \
    --levity docs/design-references/presets/analog-dial.levity \
    --scenario hot-clear-day --name gauge --out /tmp/analog.png
  ```
  Expect `28 29 30 31 32` around the dial and `29.97` (the reading, unchanged) with `inHg` under it.

## Phase 2 — dashboard-level defaults (design, then build)

Unit conventions cover the common case. Overrides are for taste ("I want `°` off the ticks on every temperature dial in this dashboard"). The maintainer prefers per-dashboard defaults, with global defaults as an acceptable fallback.

The cascade, lowest to highest:

1. **The unit's compact format, floored by the tick spacing** (phase 1): the gauge class's `@item_default`.
2. **Global defaults**: a bundled file in `resources/` (not `config.ini`), with the same schema as layer 3.
3. **Dashboard `defaults:`**: a top-level block in the `.levity` file.
4. **`shared:` / `preset:`**: the existing inheritance; see `Stateful.shared` (`src/statekit/core.py` ~1967) and `setItemState` (~2115). The named-preset registry is planned in [gauge-presets.md](gauge-presets.md).
5. **The gauge's own `display:`**.

### The matcher: what a defaults entry is selected by

A defaults entry must say which gauges it applies to. There are two candidates, and `GaugeRange.ranges` (`Gauge.py` ~3435) already uses both: unit strings like `'inhg'` and `CategoryItem('*.humidity.*')` patterns.

- **Data key** (`environment.pressure.pressure`, or a pattern): selects by what is measured. The dashboard looks the same whichever unit the user picked. But a pattern is broad. `'*.pressure.*'` is exactly the over-reach the maintainer warned about.
- **Display unit** (`inHg`): selects by what is shown. The decimals then follow the unit actually on screen, since hPa and inHg want different decimals.

Recommendation, which the maintainer has not decided yet:

- accept both, as `ranges` does;
- prefer exact keys in anything bundled;
- make the more specific match win: exact key, then pattern, then unit.

Present the shape to the maintainer before building past a spike. A sketch:

```yaml
defaults:
  environment.temperature.temperature:
    gauge: {major: {labels: {format: {unit_symbol: false}}}}
  unit=inHg:
    gauge: {value-label: {format: {precision: 2}}}
```

The key syntax is open: `*` is not a valid bare YAML key, which is why [data-model-spec.md](data-model-spec.md) uses `default:`.

**Where it plugs in:** the same spot as presets. See the "Where it plugs in" section of [gauge-presets.md](gauge-presets.md) (`Realtime._init_args_`, `Realtime.py` ~127). Defaults are presets that a gauge receives by matching rather than by naming. Build them on the same merge so there is one cascade rather than two.

**Persistence:** the defaults must never get baked into each gauge's saved `display:`. A save after load must round-trip byte-identical. Test that explicitly.

## Phase 3 — the value label and the annotation labels

`GaugeValueLabel.__defaults__['format']` and `AnnotationLabels.format_spec` (`Displays/Annotations.py` ~260) are the other two per-label format specs. Once phase 2 exists, check that both read through the same cascade. Do not change their defaults; just make them overridable from `defaults:`.

## Out of scope

- Optical centering and curved labels. See [gauge-text-treatments.md](gauge-text-treatments.md) and [curved-gauge-labels.md](curved-gauge-labels.md).

## Report

Commits, test output, before/after PNG paths. Say "not verified" for anything you didn't look at.

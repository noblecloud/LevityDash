# Gauge tick labels: precision from the scale, defaults a dashboard can set

**Status:** open, actionable. Recorded 2026-10-04.
**Base:** `feat/value-sources`. Step one: `git checkout -B feat/tick-label-format feat/value-sources`.
**Model:** phases 1 and 3 suit `levity-worker` (Sonnet). Phase 2 involves design calls: use Opus, or bring the questions back to the maintainer.

## The problem

A pressure dial with ticks at 28, 29, 30, 31 and 32 inHg labels them `28.00 29.00 …`. The precision is the unit's (`[UnitProperties] inHg = precision=2`). That precision suits the *value*, `29.97`, but not a scale that steps in whole inches.

The maintainer's rules for the fix:

- **Not per measurement type.** Some pressure dials *do* need the zeros. A barograph zoomed to 29.90–30.10 with 0.05 ticks must read `29.90 29.95 30.00`. So no `Pressure → {trailing_zeros: false}` table, and no broad `'*.pressure.*'` default either.
- **Not in `config.ini`.** `[UnitProperties]` is for the unit's own formatting, which the value label also uses.
- **Use WeatherUnits formatting.** Every `Measurement` takes a format spec (`value.__format__('', **spec)`). Do not post-process strings with regexes. That was tried and rejected.
- **No bolt-ons.** Use the gauge's existing mechanisms: `StateProperty`, `@item_default`, `__defaults__`.

## Phase 1 — precision derived from the tick interval (the real fix)

The labels should show as many decimals as the **tick spacing** needs, and no more:

| interval | labels |
|---|---|
| 1 inHg | `28 29 30` |
| 0.5 | `28.0 28.5 29.0` |
| 0.05 | `29.90 29.95 30.00` |
| 10 °F | `60° 70° 80°` |

So `decimals = max(0, -floor(log10(interval)))`, corrected for intervals like 0.25 that need one more digit. A robust approach: the smallest `d` for which every tick value rounds exactly to `d` places.

**Where:** `GaugeTickTextGroup` (`Displays/Gauge.py` ~3051). Today it has:

- a `_tick_format = {'show_unit': False}` class attribute;
- a `format_spec` StateProperty (key `format`, default `None`);
- `format_value`, which merges the two.

Replace `_tick_format` with an `@format_spec.item_default`, the same pattern as `enabled.item_default` a few lines above it (~3247). That method returns `{'show_unit': False, 'precision': <derived>}`. The intervals are on `self._ticks` / `self.source` (the `Graduations`; see `tick_values`, `usr_interval`).

**Required:** `trailing_zeros` must still behave as configured. The precision is the derived one, so `29.90` keeps its zero.

**The user's `format:` merges over the default and does not replace it.** This preserves the current behaviour: `format: {precision: 0}` must not bring the word unit back onto every tick. Keep the comment explaining that.

**WeatherUnits dependency:** passing `precision` as a keyword (`v.__format__('', precision=0)`) was silently ignored until a fix in the sibling repo:

- the fix is in `../WeatherUnits/src/WeatherUnits/base/_SmartFloat.py`, `params.explicitPrecision`;
- it is uncommitted there and needs a regression test plus a commit;
- the maintainer pushes WeatherUnits.

Check `format(Pressure(28.0, 'inHg'), '')` vs `.__format__('', precision=0)` first. If the keyword form still prints `28.00`, the WU fix has not landed, and the stale result is not this phase's bug.

**Verify:**

- **Unit test.** In a new `tests/ui/test_gauge_tick_format.py`, build gauges (see the `_gauge` helper in `tests/ui/test_gauge_fill_sources.py`) with:
  - range 28–32, interval 1;
  - range 29.9–30.1, interval 0.05;
  - a temperature range.

  Then assert the label strings (`[l.text for l in group]`, or whatever `GaugeTickText` exposes).
- **Render:**
  ```bash
  QT_QPA_PLATFORM=offscreen .venv/bin/python src/LevityDash/devtools/render_widget.py \
    --levity docs/design-references/presets/analog-dial.levity \
    --scenario hot-clear-day --name gauge --out /tmp/analog.png
  ```
  Expect `28 29 30 31 32` around the dial and `29.97` (the value, unchanged) with `inHg` under it.

## Phase 2 — dashboard-level defaults (design, then build)

Derived precision covers the common case. Overrides are for taste ("I want `°` off the ticks on every temperature dial in this dashboard"). The maintainer prefers per-dashboard defaults, with global defaults as an acceptable fallback.

The cascade, lowest to highest:

1. **Derived** (phase 1): the gauge class's `@item_default`.
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

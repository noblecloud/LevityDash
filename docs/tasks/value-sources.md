# Value sources: keys, numbers and expressions wherever a value goes

**Status:** design agreed, not scheduled. Recorded 2026-07-26 as two briefs
(computed values, and values that drive display properties); merged and
extended 2026-10-04.

## What

Every slot in a `.levity` file that takes a key today should take a **value
source** instead. A value source is one of three things:

| Form       | Example                                           |
|------------|---------------------------------------------------|
| Key        | `environment.temperature.temperature`             |
| Number     | `0`                                               |
| Expression | `max(environment.temperature.temperature, today)` |

The slots this covers:

- the main value of a panel (`Realtime.key`, and so a gauge's needle)
- extra gauge indicators (`markers:`, new; see below)
- gauge range `min`/`max`
- fill spans (`from`/`to`) once gauges have separate track and fill layers
- display properties: colour, visibility, and later opacity or rotation

An expression can be maths over keys, a window function over a key's
timeseries, or a condition that picks between values or styles. One
evaluator serves all of them.

## Example

A gauge is the display of a `realtime.gauge` panel (see
[gauge-display.md](gauge-display.md)), so its main value is the panel's
`key` and the rest sits under `display:`:

```yaml
- type: realtime.gauge
  key: environment.temperature.temperature
  display:
    markers:
      - value: min(environment.temperature.temperature, today)
      - value: max(environment.temperature.temperature, today)
    range:
      min: min(environment.temperature.temperature, 7d) - 5
      max: max(environment.temperature.temperature, 7d) + 5
    needle:
      color: red if value > 90 else default
```

A pressure "set hand" is the same idea with a different function:

```yaml
- type: realtime.gauge
  key: environment.pressure.pressure
  display:
    markers:
      - value: at(environment.pressure.pressure, -3h)
```

A condition that picks a value:

```yaml
key: environment.wind.speed.gust if environment.wind.speed.gust > environment.wind.speed.speed * 1.5 else environment.wind.speed.speed
```

Nothing above is specific to weather. The same slots take CPU load, disk
use, service latency, or any key a plugin publishes.

## Design decisions

1. **Evaluate on the backend.** Each expression becomes a *computed key*
   that the frontend receives like any other key. The backend owns the
   timeseries and the dispatcher, so windows and aggregates belong there.
   The frontend never does maths, so every future frontend gets expressions
   without re-implementing them.

   The likely shape is a built-in `Computed` plugin. It holds the
   registered expressions, subscribes to their input keys, and publishes
   results through the normal plugin path (`accumulator.publish`). Over the
   wire, `RemoteBackend.attach()` then carries computed keys with no new
   update path, and `mode=live` works the same way because plugins run in
   the frontend there.

   The new part is registration. The frontend loads the `.levity` file, so
   it must tell the backend which expressions it needs. That wants a
   request message like the existing `ts_request` and `plugin_command`
   (`lib/wire/backend.py`).

2. **The same expression text is the same computed key.** Normalise the
   parsed expression, so whitespace and formatting do not matter, and
   intern it. Two panels that ask for today's maximum share one
   computation and one subscription. A name for an expression (so other
   expressions can refer to it) can come later; interning does not need
   one.

3. **Parse with Python's `ast`, check against an allowlist, never `eval`.**
   `ast.parse(text, mode='eval')` gives infix maths, comparisons, `and`/`or`
   and `x if cond else y` without a hand-written parser. Walk the tree and
   reject any node type, name or function not on the list. Keys are dotted
   names, which `ast` reads as attribute chains; resolve them back to
   `CategoryItem`s. Keys carrying a `source:` or `#identity` affix are not
   valid Python, so the tokeniser must protect them first (for example,
   substitute placeholders before parsing).

4. **Conditions come in two kinds, on one evaluator.**
   - *Choose a value:* `gust if gust > speed * 1.5 else speed`, in any
     value slot.
   - *Choose a style:* colour or visibility by threshold, in a display
     property slot. Inside a display property, `value` means the value the
     item is displaying.

5. **A missing input gives a missing result.** At startup, half the inputs
   are absent as a rule. The result is "no value yet", not an exception and
   not `0`. A marker with no value hides; a range bound with no value falls
   back to the static range resolution in `GaugeRange`. A condition
   short-circuits, so the branch not taken may be missing. **An expression
   must never raise during dashboard load**: one item's exception aborts
   the whole board (see the gotcha in `CLAUDE.md`). Reject a malformed
   expression at load with a logged error naming the item, and treat it as
   missing.

6. **Units go through WeatherUnits.** A sum or difference keeps the unit.
   A ratio gives a derived unit (WeatherUnits already models
   numerator/denominator pairs, for example `DistanceOverTime`). A
   comparison converts both sides to one unit first. A bare number takes
   the unit of the other operand, so `temp - 5` subtracts 5 degrees in the
   display unit. Decide whether that is the display unit or the source unit
   before building, and write the answer down here.

7. **Window functions** cover the first uses:

   | Function             | Meaning                                       |
   |----------------------|-----------------------------------------------|
   | `min(key, window)`   | lowest value in the window                    |
   | `max(key, window)`   | highest value in the window                   |
   | `avg(key, window)`   | mean over the window                          |
   | `at(key, offset)`    | the value at a time offset from now           |

   Windows are `today`, or a duration such as `24h` or `7d`. `today` covers
   observed and forecast points for the local day. That is better than a
   plugin's own daily high/low (`environment.temperature.high`, OpenMeteo's
   `temperature_2m_max`), which exists only in the daily series
   (`timeseriesOnly`) and only for sources that publish it. A window over
   the hourly series works for any key, including a local sensor or a
   system metric.

8. **When it recomputes.** On an update to any input key, coalesced the way
   the remote timeseries refetch is (`RemoteContainer._refetchTimeseries`:
   one request in flight, one more if inputs changed meanwhile). `today`
   also needs a recompute at local midnight even with no new data. A range
   bound changes the graduations, which costs a re-layout, so range bounds
   want to settle: round outward to the range's `round-to` and change only
   when the rounded value changes.

## Display properties (from the second original brief)

Colour driven by a value is the motivating case. **The gradient machinery
already exists and already does this**, only not from config:

- `Gauge.py`: `GaugeLabel(NonInteractiveLabel, ColorGradientMixin, ...)`
- `Graph.py`: plots take `gradient: RipeMalinkaGradient` from the dashboard
  file (see the `environment.wind.speed.speed` plot in `default.levity`)
- `Gauge.convert_gradient` maps a gradient onto a value range, using the
  gauge's `rounded_min`/`rounded_max` and `valueClass`

A gradient needs a range to map onto. The graph gets one from its axis and
the gauge from `GaugeRange`. A plain `realtime.text` panel has none, so lift
`GaugeRange.ranges` (keyed by unit string *and* by `CategoryItem` pattern)
out of `Gauge` and share it.

Size and weight risk fighting the size-group fitter, which computes one
scale across a group. A value-driven font size would have to feed *into*
that fitter, not override it afterwards. Colour should be a repaint, never a
refit.

## Range bounds from data (from the first original brief)

The first consumer recorded in July. Today the range comes from
`GaugeRange.ranges`, a fixed table keyed by unit string
(`'mph': MinMax(0, 15)`) and by `CategoryItem` pattern, falling back to the
unit's `typedLimits` and finally `MinMax(0, 100)`. A US config gives wind
0–24 mph, which is an m/s preset converted, not anything about the weather.
Wind is the clearest case: any fixed ceiling is a guess.

Options worth offering for a bound: today's high or low, a rolling window,
a percentile so one gust does not flatten the dial, and a padded round-up so
the needle does not sit at the very end.

**Gradients are mapped against absolute values.** `RipeMalinkaGradient`
spans 0–100 mph, so a gauge covering 0–24 shows only one slice of it. Once
the range moves with the data, gradients probably want to map onto the
*gauge's* range instead, or colours change meaning as the range moves.
Decide this alongside range bounds.

## Gauge markers

A gauge has one `needle:` today, and every indicator follows `gauge.value`
(`Needle.refresh`, `Gauge.py`, `setRotation(gauge.value_to_angle(gauge.value))`).
`GaugeRange.default_range` also reaches up to `self._gauge.parent.key`, so
the one-key assumption sits in the range layer as well as the panel.

Add `markers:`, a list of indicators. Each has a `value:` (a value source),
a type (reuse `Needle.Type`: `marker`, `circle`, `triangle`, …) and a
colour. Each marker gets its value from its own computed or plain key,
independent of the parent `Realtime`. This is the "multiple keys" gap
recorded in [gauge-display.md](gauge-display.md).

## Prior art in the repo

- `CategoryItem` already models structured keys, and `MultiSourceContainer`
  already reconciles several sources per key. A computed key sits in the
  same namespace, with `Computed` as its source.
- Plugin schemas already declare derived values with `sourceKey` tuples and
  `@period` placeholders, so a value whose definition is data rather than
  code already exists.
- The wire already carries whole timeseries in columns
  (`encode_timeseries_values`), and `MultiSourceContainer` already has
  `getDaily` and `nowFromTimeseries`.

## Open questions

1. Does the expression unit default to the display unit or the source
   unit (decision 6)?
2. Should expressions be nameable so that other expressions and panels can
   refer to them? If yes, the config defines keys as well as consuming
   them.
3. Should computed keys be visible to other plugins (dispatcher-level), or
   only to dashboards? The `Computed` plugin shape allows either; choose
   before exposing it.

## Suggested first slice

The high/low dial, end to end through every layer:

1. Backend: the `Computed` plugin, registration message, `ast` parser with
   allowlist, and the `min`/`max`/`at` window functions. No infix maths
   yet, so the evaluator has no unit questions to answer.
2. Frontend: gauge `markers:` with `value:` taking a key or an expression.
3. Tests: a missing input hides the marker; a malformed expression logs and
   does not abort the load; two panels with the same expression share one
   computed key; `today` rolls over at local midnight.

Infix maths and conditions follow on the same evaluator. Then range bounds,
then display properties (colour from a value, on `realtime.text` first).

## Suggested branch

`feat/value-sources`

## Related

- [gauge-display.md](gauge-display.md): the one-key gauge, and where
  multi-key was left
- `docs/tasks/timeseries-viewport-and-control-plane.md`: the plugin control
  plane, where expression registration may belong
- `docs/tasks/value-annotations-and-digit-budget.md`: also about what a
  displayed value *is* beyond its number

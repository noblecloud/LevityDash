# Values driving display properties

**Status:** idea, not scheduled. Recorded 2026-07-26.

## What

Let a value determine *how* it is displayed, not just what text appears —
colour from temperature being the motivating case:

```yaml
- type: realtime.text
  key: environment.temperature.temperature
  display:
    color:
      from: value
      gradient: TemperatureGradient
```

Beyond colour, the same mechanism plausibly drives opacity, weight, size,
rotation (a wind-direction arrow), or an icon choice.

## Why it is mostly plumbing, not invention

**The gradient machinery already exists and already does this**, just not
from config. `ColorGradientMixin` is real and in use:

- `Gauge.py` — `GaugeLabel(NonInteractiveLabel, ColorGradientMixin, ...)`
- `Graph.py` — plots take `gradient: RipeMalinkaGradient` from the dashboard
  file today (see `default.levity`'s `environment.wind.speed.speed` plot)
- `Gauge.convert_gradient` maps a gradient onto a value range, using the
  gauge's `rounded_min`/`rounded_max` and `valueClass`

So gradients are already: declarable in YAML, resolvable by name, and
mappable onto a measurement range. What's missing is applying one to a
*text/label* display driven by its own value.

## The design questions

1. **What is the input domain?** A gradient needs a range to map onto. The
   graph gets one from its axis; the gauge from `GaugeRange` (with a table
   of sensible per-unit defaults — `'f': MinMax(0, 120)` etc.). A plain
   realtime text panel has no range, so it needs one from somewhere:
   reuse `GaugeRange.ranges`, read the unit's `typedLimits`, or require it
   in config. **`GaugeRange.ranges` is the obvious thing to lift out of
   `Gauge` and share** — it is already keyed by unit string *and* by
   `CategoryItem` pattern.
2. **Which properties are drivable?** Colour is clearly useful. Size and
   weight risk fighting the size-group text-fitting engine, which computes
   a shared scale across a cluster — a value-driven font size would have to
   feed *into* that, not override it after.
3. **What drives it — the value, or another key?** "Colour this text by
   *that* other value" is strictly more useful and barely harder, since the
   subscription machinery is per-key already. Same shape as the multi-key
   problem in [gauge-display.md](gauge-display.md).
4. **When does it recompute?** On value change is obvious. Worth confirming
   it does not force a full re-layout — colour should be a repaint, not a
   refit.

## Suggested first slice

`color` on a `realtime.text` display, driven by its own value, with the
range resolved from the shared unit-range table. It reuses
`ColorGradientMixin` and the existing named-gradient resolution, and it
answers question 1 without touching the text-fitting engine.

## Related

- [gauge-display.md](gauge-display.md) — same underlying need for a display
  fed by more than its one parent key
- [computed-values-in-dashboard-config.md](computed-values-in-dashboard-config.md)
  — if a value can be computed, it can also drive a property
- `docs/tasks/value-annotations-and-digit-budget.md` — shelved, but the same
  question of "what a displayed value is beyond its number"

## Suggested branch

`feat/value-driven-properties`

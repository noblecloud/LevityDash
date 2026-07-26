# Computed values in the dashboard configuration

**Status:** idea, not scheduled. Recorded 2026-07-26.

## What

Let a `.levity` file define a value by *expression* rather than only by key,
so a panel can show something the plugins don't publish directly:

```yaml
- type: realtime.text
  key: average(environment.temperature.temperature, 24hr)
```

Arithmetic and aggregation over existing keys — averages over a quantity or
a timeframe, differences, sums, min/max, and ordinary maths between keys
(`environment.temperature.temperature - environment.temperature.dewpoint`).

## Why this is bigger than a formatting feature

Everything the dashboard currently displays is a value some plugin
publishes. This makes the dashboard able to *derive*, which changes what
counts as a data source. It is closer to a small expression language than to
a display option, and the interesting design questions are all about where
the seams go:

- **Where does it evaluate?** Backend or frontend. The backend owns the
  timeseries and the dispatcher, so aggregation belongs there; but the wire
  currently carries values for *known keys*, and a computed key is not one
  of those. It probably needs to become a first-class subscribable key so
  the frontend can ask for it like any other.
- **When does it recompute?** On every source update, on a timer, or lazily
  on paint. An `average(..., 24hr)` over a live series is not free.
- **What is the result's unit?** `average` keeps it, a difference keeps it,
  a ratio does not. WeatherUnits' derived units already model
  numerator/denominator pairs, so a division could legitimately produce a
  `DistanceOverTime` — worth leaning on rather than reinventing.
- **What happens when an input is missing?** Half the inputs present is the
  normal case at startup. Needs a defined answer that isn't a crash or a
  silently wrong number.

## Prior art in the repo

Not starting from nothing:

- `CategoryItem` already models structured keys, and the dispatcher already
  reconciles multiple sources per key via `MultiSourceContainer` — a
  computed key wants to sit in that same namespace.
- Plugin schemas already declare derived-ish values with `sourceKey` tuples
  and `@period` placeholders, so there is an existing idea of a value whose
  definition is data rather than code.
- The wire protocol already carries whole timeseries columnar
  (`encode_timeseries_values`), which is what an aggregate needs.

## Design questions to settle before building

1. **Expression syntax.** A function-call form (`average(key, 24hr)`) reads
   well and parses easily. Infix arithmetic (`a - b`) is friendlier but
   needs a real parser. Possibly both, with the function form first.
2. **Is a computed value addressable?** i.e. can another expression, or
   another panel, refer to one? If yes it needs a name, which means config
   defines keys as well as consuming them.
3. **Does it belong to the dashboard or to the plugin layer?** Defining it
   in the `.levity` file makes it presentation; putting it in the dispatcher
   makes it available to everything, including other plugins. The second is
   more useful and more work.

## First consumer: gauge min/max

Recorded 2026-07-26. A gauge's range should be able to come from the data
rather than a static table — **wind especially**, where any fixed ceiling is
a guess.

Today the range comes from `GaugeRange.ranges`, a hardcoded table keyed by
unit string (`'mph': MinMax(0, 15)`) and by `CategoryItem` pattern, falling
back to the unit's `typedLimits` and finally `MinMax(0, 100)`. A US config
currently gives wind 0–24 mph, which is arbitrary: it is a m/s preset
converted, not anything about the actual weather.

What is wanted instead is a range *expressed*, with a choice of how:

```yaml
display:
  range:
    min: 0
    max: max(environment.wind.speed.gust, today)
```

and eventually a set of options for the calculation — today's high/low, a
rolling window, a percentile to keep gusts from flattening the dial, a
padded round-up so the needle does not sit at the very end.

This is the same evaluation problem as the rest of this document, with two
extra wrinkles:

- **It feeds layout, not just text.** A changing range changes the
  graduations, so recomputing it is more expensive than recomputing a
  displayed number, and it wants to settle rather than jitter minute to
  minute.
- **Gradients are mapped against absolute values.** `RipeMalinkaGradient`
  spans 0–100 mph, so a gauge covering 0–24 only ever shows one slice of it.
  Once the range moves with the data, gradients almost certainly want to
  map onto the *gauge's* range rather than absolute values — otherwise the
  colours shift meaning as the range does. Worth deciding alongside.

See [gauge-display.md](gauge-display.md) for the current range resolution.

## Suggested first slice

`average(key, <timeframe>)` only, evaluated backend-side, exposed as a
subscribable key. It exercises every seam — parsing, evaluation, unit
preservation, wire transport, missing inputs — without committing to a
general expression language.

## Suggested branch

`feat/computed-values`

## Related

- `docs/tasks/timeseries-viewport-and-control-plane.md` — the plugin control
  plane, which is where a computed key would have to be declared
- `docs/tasks/value-annotations-and-digit-budget.md` — also about what a
  displayed value *is* beyond its raw number

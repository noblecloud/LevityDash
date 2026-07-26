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

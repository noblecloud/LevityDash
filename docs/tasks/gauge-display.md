# Gauge display: what actually works, and what doesn't

**Status:** investigated 2026-07-26, not fixed. This replaces the guess that
it was "mostly functional, just not wired to live values" — it *is* wired,
and it does construct, but it does not render.

Everything below was measured in a booted, headless dashboard
(`QT_QPA_PLATFORM=offscreen`, OpenGL forced off) using a two-gauge test
dashboard, not read off the source.

## It is wired — via `realtime.gauge`, not `gauge`

The dispatch is `Realtime` → `DisplayType` → display class, so a gauge is
the *display* of a keyed `Realtime` panel rather than a top-level item:

```yaml
- type: realtime.gauge
  key: environment.temperature.temperature
```

`Realtime._init_args_` maps `type` through `DisplayType[...]`, and
`Realtime.display.decode` builds a `Gauge` for `DisplayType.Gauge`. Live
values reach it in two places — `Realtime` sets `display.valueClass` and
`display.value` on both the container-change path and `updateSlot`.

⚠️ A bare `type: gauge` does **not** work: `itemLoader` has no `gauge` case,
so it falls through to `case str(panel)` and silently loads a plain `Panel`.
Worth either adding the case or rejecting the type loudly, since the failure
is currently invisible.

## What actually happens

With two gauges declared (temperature and wind speed):

| observation | value |
|---|---|
| `Realtime` panels created | 2 ✅ |
| `Gauge` displays created | **1** ❌ |
| the one that built | `visible=False`, `value=0` |
| its range | `0–120 °F` ✅ correct, from the `'f'` preset |

So one gauge silently fails to build a display at all, and the one that does
never becomes visible.

### 1. The second panel's display is the unset sentinel

`realtime.display` comes back as the class `Stateful` rather than a `Gauge`
instance — i.e. the decode never produced a display and the property fell
back to its default. Reading `.displayType` on it raises:

```
AttributeError: type object 'Stateful' has no attribute 'displayType'
```

The two panels differ only in key, and the failing one is
`environment.wind.speed.speed`. `GaugeRange.ranges` holds `CategoryItem`
entries for `environment.wind.speed` and `environment.wind.speed.gust`, and
`default_range`'s first branch does a `CategoryItem` comparison
(`self._gauge.parent.key < i`) — the wind keys are the only ones that
exercise that branch. Prime suspect, unconfirmed.

### 2. An infinite range during construction

```
File "Gauge.py", line 477, in usr_interval
  value_range = self.gauge.range.rounded_range
File "Gauge.py", line 2968, in rounded_max
  if is_prime(scaled_range):
File "shared.py", line 2330, in is_prime
  return n > 1 and all(n % i for i in range(2, int(n ** 0.5) + 1))
OverflowError: cannot convert float infinity to integer
```

A `Graduations` interval default is evaluated *before* the gauge's range is
known, so it reads an infinite range. By the time the dashboard has settled
the range is correct (`0–120 °F`), so this is an ordering problem, not a
wrong-value problem — construction recovers, but something is left in a bad
state along the way.

`is_prime` is also worth hardening regardless: it should reject a non-finite
argument rather than raise `OverflowError` from inside `range()`.

### 3. `_majorDivisions` AttributeError noise

```
AttributeError: 'Gauge' object has no attribute '_majorDivisions'
```

This one is *handled* — `StateProperty.__get__` catches `AttributeError` and
falls back to the registered `.factory`. It is noise, not a fault, but it
makes the real errors hard to find in a log.

## Already fixed while investigating

Every one of Gauge's `StateProperty` ordering declarations was spelled
`dependancies=` — including `major` depends-on `range`, which is exactly the
ordering issue in §2. `StateProperty` stores unknown options and never reads
them, so all of them were inert. Fixed across the repo (21 occurrences), and
unknown options now raise. See commit "fix(Stateful): reject unknown
StateProperty options".

That did **not** on its own fix §2, so there is more to the ordering than the
typo.

## The author's remembered blocker: multiple keys

Recalled as "I needed a way to connect multiple keys and never got far
enough into it." That is a real gap and it is *architectural*, not a missing
wire: a `Gauge` is the display of **one** `Realtime`, which owns exactly one
`key`. A gauge wanting a value plus a gust marker, or a min/max band, needs
either

- a `Realtime` that can hold several keys, or
- a gauge that can subscribe to keys itself, independent of its parent

Note `GaugeRange.default_range` already reaches *upward* for
`self._gauge.parent.key`, so the one-key assumption is baked in at the
range layer too, not only at the panel.

This overlaps with
[computed-values-in-dashboard-config.md](computed-values-in-dashboard-config.md)
— both want a display fed by something other than exactly one plugin key.

## Suggested order

1. Harden `is_prime` against non-finite input (trivial, removes a crash).
2. Find why the wind gauge's display decode returns the sentinel — the
   `CategoryItem` branch in `default_range` is the prime suspect.
3. Get one gauge *visible* with a live value. Until that works, multi-key is
   premature.
4. Only then design multi-key, alongside the computed-values work.

## Reproduction

`docs/tasks/` has no fixtures, so the harness used is worth recreating: seed
a config from `tests/resources/config-seed`, replace its
`saves/dashboards/default.levity` with two `realtime.gauge` panels, boot via
`LevityDashboard.init()` / `app.init_app()` (as `tests/conftest.py` does),
pump ~4s, then inspect `scene.items()` for `Gauge` instances. Force
`[QtOptions] openGL = False` or `view.grab()` returns blank white.

## Suggested branch

`fix/gauge-display`

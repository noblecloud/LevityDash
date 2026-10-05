# Gauge presets: one named preset per gauge-ui template

**Status:** open, not scheduled. Recorded 2026-10-04.

## What

Give LevityDash a named preset for each gauge template on gauge-ui.dev, so a
dashboard author writes `preset: speedometer` instead of 40 lines of `display:`.

Source: the gauge-ui repo, MIT licence, commit `cfe5341`. It is a React/SVG
library. Read its layouts as design references and re-express them in
LevityDash's own terms. Do not port its code. The templates are in
`lib/gauge-templates.ts` (27 templates; the site says 29 because the weather
dashboard adds a barometer and a humidity comfort band, see the table). If a
preset copies numbers closely, say so in `docs/` and credit the repo.

Every preset needs a use that is not weather. LevityDash shows any metric
(see [value-sources.md](value-sources.md)), so each row below names one of each.

## Why

- A gauge is 30-60 lines of `display:` today. Copying it per panel drifts.
- The roadmap already wants named, reusable `preset:` over anonymous `shared:`.
- The templates give a vetted set of data shapes (fill, zoned, signed, angular,
  nested). Mapping them shows exactly which primitives `Gauge` lacks.

## Blocker first

[gauge-display.md](gauge-display.md) records, as of 2026-07-26, that a
`realtime.gauge` can fail to build (the wind key) and that the one that builds
stays invisible. Gauge fixes have landed since (`2fa3a56`, `808363c`), so that
record may be stale. Render a gauge first and confirm it shows; if it does not,
do that brief's "Suggested order" steps 1-3 first. A preset that cannot render
is not a preset.

## 1. How a gauge preset works

### The file

A preset is a mapping of `display:` settings. A gauge opts in with `preset:`
and overrides any key beside it. The user's keys win.

```yaml
- type: realtime.gauge
  key: environment.wind.speed.speed
  preset: speedometer
  display:
    range:
      max: 60
    needle:
      type: triangle
```

`preset:` also takes an inline mapping, the same two forms `Stack.preset`
already accepts (a name, or a dict).

A preset sets the *shape* of the scale: angles, arc weight, graduations,
needle, label placement. It does not set units. Where the scale is part of
the instrument (compass 0-360, percent 0-100, AQI 0-500, UV 0-11) the preset
sets `range`. Elsewhere the dashboard sets it, or `GaugeRange` picks it per
unit as today. Use theme colours and named gradients in presets, never hex.

### Where files live

- Bundled: `src/LevityDash/resources/presets/gauge/<name>.yaml`.
- User: `<config dir>/presets/gauge/<name>.yaml`. A user file with a bundled
  name shadows it.
- Names are lowercase-with-hyphens, the gauge-ui template ids
  (`power-meter`, `air-quality`).

Keep the registry generic: `registry.get(kind, name)` with `kind` = `gauge`.
Stack presets can move onto it later.

### What exists

Checked in the code on 2026-10-04.

| Piece | Where | State |
|---|---|---|
| `Stack.preset` property (name or dict) | `Modules/Containers/Stacks.py:898` | exists |
| Name lookup for `Stack.preset` | `Stacks.py:917`, `case str(value) if value in self.presets` | **cannot match.** `presets` is keyed by `Direction`, so no string name is ever found. No `.levity` in the repo uses `preset:`. |
| Stack presets apply to children | `combined_preset` (`Stacks.py:910`), `itemSetter` (`Stacks.py:773`) | exists; per-direction dicts, in code only |
| `shared:` | `Stateful.shared`, `statekit/core.py:1967` | exists; anonymous, inherits down the parent chain |
| Merge rule, user wins | `setItemState`, `statekit/core.py:2115-2139`: `DeepChainMap(value, sharedValue)` | exists; reuse it |
| Values from shared are tagged `SourceType.Shared` | `core.py:2118`; `_revertOmittedKeys` skips them | exists; a preset must be tagged the same way, or `Ctrl+R` reverts it |
| `shared: display:` reaches a gauge | works by the rule above | exists, but anonymous and applies to every child |
| Named preset registry | none | **missing** |
| Preset files on disk (bundled and user) | none | **missing** |
| `preset:` on a `realtime.gauge` | none | **missing** |
| Preset for any display other than stacks | none | **missing** |

### Where it plugs in

1. Add `preset` resolution in `Realtime._init_args_` (`Displays/Realtime.py:127`).
   That method already pops `display` and rewrites it before `super()`. Pop
   `preset` there, look it up, and set `display = DeepChainMap(display, bundle).to_dict()`.
   Missing name: log an error naming the panel and use the empty bundle. A bad
   name must never raise during load (one item's exception aborts the board).
2. Tag the merged values `SourceType.Shared` so hot reload behaves as it
   does for `shared:`.
3. Put the lookup in a small registry module so `Stack.preset` can call it.
   Fix the `Stack.preset` name lookup to use the registry. That closes the
   roadmap item "migrate `shared:` to named `preset:`" for the first case.
4. A `preset:` and a `shared:` can both apply. Order, weakest to strongest:
   `shared:` from parents, then the preset, then the gauge's own `display:`.

Do not build `extends:` or list-layering in v1. Add them when two presets
want to share a base.

## 2. The templates

Primitives. Names are for this brief.

- **N1** Fill arc with `from`/`to`: a value-driven fill, anchored at `from`
  (so a signed gauge fills out from zero) and optionally capped at `to`
  (so a band such as "comfortable 30-60 %" is a fill with fixed ends).
  Today `GaugeArc` is a static track: `start-angle`, `end-angle`, `weight`,
  `cap`, `gradient`. Its colour does not follow the value.
- **N2** Zones: hard-edged bands with cutoffs and a mark at each cutoff.
  Today a `gradient:` ramps colour smoothly between stops.
- **N3** Markers bound to their own value: the `markers:` list in
  [value-sources.md](value-sources.md). Today every indicator follows
  `gauge.value`.
- **N4** Scale types: wrapping (0-360 bearing, shortest path across 0), time
  of day (hour 6-18), 12-hour turns (hour hand and minute hand), log.
  Today `value_to_angle` is linear and clamps to the arc.
- **N5** Animated display value: the shown value eases to the data value.
- **N6** Insets: more gauges inside one frame, each with its own key and
  `placement` (position, scale). Today one gauge is the display of one `Realtime`.
- **N7** Per-label formatters: tick labels that print text (`N`, `NE`,
  `Rain`, `E`, `+5`). Today `GaugeTickTextGroup` prints the numeric value;
  only `GaugeValueLabel` has `format`.

"Today" column: **yes** = a recognisable copy with one `Gauge` and no new
primitive; **partly** = same layout, with the loss named; **no** = the
template's point is missing. "Today" means one gradient arc, graduations
with numeric labels, one needle (`needle`, `circle`, `triangle`, `diamond`,
`marker`), a value label, a unit label and `range`.

Angles: gauge-ui puts 0 at the bottom and the speedometer's gap there. LevityDash
puts 0 at the top (`arcMoveTo(rect, -angle + 90)`; default arc is -120 to 120).
Convert with `angle - 180`: gauge-ui 40-320 becomes -140 to 140.
A full ring (360 sweep) is untested in `Gauge`. Test it first.

| Preset | Data shape | Non-weather use | Weather use | Needs | Today |
|---|---|---|---|---|---|
| simple | one bounded number, no arc | any metric | current temperature | none | n/a: `realtime.text` already does this. No gauge preset. |
| speedometer | range, graduated, hard redline zone | link rate, requests/s | wind speed | N2 | partly: gradient ramp replaces the zone |
| internet-speed | wide fill range | download Mbps | rain rate (log scale) | N1, N4 (log, optional) | no |
| saas-metric | bounded % on a half dial | conversion rate, cache hit | humidity, cloud cover | N1 | no |
| sun-path | position in a time window, half dial | work hours elapsed | daylight, sunrise to sunset | N1, N4 (time of day) | no |
| temperature | zoned range, fill, two extremes | CPU or room temperature | air temperature, day low and high | N1, N2, N3 | partly: gradient arc and circle needle; no zones, no extremes |
| thermostat | setpoint range, segmented fill, handle | any target level | indoor temperature against setpoint | N1, N3 (live setpoint, optional) | no |
| progress-ring | bounded % on a full ring | disk use, job progress | cloud cover, rain chance | N1 | no |
| dimmer | bounded % fill, broad band | light or fan level | humidity | N1 | no |
| volume | bounded % fill, thin scale | audio level, battery | none. Drop the knob control, see section 4. | N1 | no |
| analog-dial | range, numeric graduations | pressure (psi), voltage | barometric pressure, UV | none | **yes** |
| compass | angular, cyclical, letter labels | heading, phase angle | wind direction | N4 (wrap), N7 | partly: numeric degree labels, no wrap easing |
| wind (direction) | angular, cyclical, second value in centre | bearing of any source | wind from, speed in the centre | N4, N7, a second key in a label (value-sources) | partly: needle only, no centre speed |
| clock | cyclical time, two hands | any time source | time of day, sunrise | N4 (12 h turns), N7 | no |
| activity-ring | bounded fill, full ring | daily goal | rain today against forecast | N1 | no |
| fuel | bounded, E to F, low zone | tank, battery, queue depth | rain barrel, snow depth | N2, N7 (E, F) | partly: numeric labels, soft low zone |
| battery | bounded fill, full ring, limit notch | UPS, Govee sensor battery | none | N1, N2 (notch as a zone mark), N3 (live limit, optional) | no |
| tachometer | range, redline | RPM, throughput | gust against limit | N2 | partly: soft redline |
| power-meter | signed, centred on zero, half dial | grid import/export, net traffic | temperature anomaly against normal | N1 (`from: 0`), N7 (signed labels) | partly: no "in" / "out" captions |
| air-quality | zoned 0-500, half dial | indoor CO2, noise level | AQI, UV band | N2 | partly: soft bands |
| heart-rate | zoned range, zone-coloured fill | pulse, CPU load | heat index, wind chill | N1, N2 | partly: gradient arc and needle |
| timer | bounded fill, seconds, full ring | countdown, cooldown | minutes to rain | N1 | no |
| chronograph | cyclical 60, plus a register inset | stopwatch | none worth building | N4, N6 | no |
| speed-fuel | two dials in one ring | speed and tank | wind and gust | N2, N6 | no: the pair is the point |
| nested-rings | three concentric fills | three goals | temperature, humidity, cloud as % of range | N1, N6 | no |
| system | three half dials in one frame | CPU, memory, disk | humidity, cloud, rain chance | N1, N6 | no |
| orrery | N cyclical positions on rings | phase of any cycle | tide, moon, season | N1, N4, N6 | no. Decorative, so it comes after the rest, but it is in scope. |
| barometer *(weather-dashboard)* | range with words, set hand, fall arc | any value with a "was" mark | pressure with 3 h set hand | N1 (`from: set`), N3 (`at(key, -3h)`), N7 (words) | partly: needle and numeric labels, no set hand |
| humidity comfort band *(weather-dashboard)* | bounded % with a highlighted band and dot | CPU temperature in the safe band | humidity, comfortable 30-60 % | N1 (`from`/`to` band) or N2 | partly: gradient with band stops and a circle needle |

Totals: 29 rows. One preset is **yes** today (analog-dial). Eleven are
**partly** (speedometer, temperature, compass, wind, fuel, tachometer,
power-meter, air-quality, heart-rate, barometer, humidity band). `simple` needs
no gauge. The other sixteen are **no**.

The weather dashboard also has a UV index gauge (11 steps), cloud oktas (8
steps) and a rain ring. These are N1 fills cut into steps by ticks drawn in
the background colour, so they add no row and no primitive.

N1 is in the "Needs" column of 18 rows, more than any other primitive (N2: 9,
N4: 7, N7: 6, N6: 5, N3: 4). Some of those entries are optional, as marked. N1 alone turns eight presets from **no** to
**yes**.

## 3. Build order

Do the registry before any preset.

| Step | Lands | Presets that become possible |
|---|---|---|
| 0 | Registry, `preset:` on `realtime.gauge`, name lookup fixed for stacks | `analog-dial` (yes). Ship the eleven **partly** presets too, marked in a comment with the missing primitive; each gets better as the steps below land. |
| 1 | **N3** markers (already the first slice of [value-sources.md](value-sources.md)) | Adds day low/high marks to `temperature` and the set hand to `barometer`. No new full preset yet: both still need N1. |
| 2 | **N1** fill with `from`/`to` | `progress-ring`, `activity-ring`, `dimmer`, `saas-metric`, `internet-speed`, `thermostat`, `timer`, `volume`. Humidity band becomes complete. Needs the full-ring test first. |
| 3 | **N2** zones with marks | `speedometer`, `tachometer`, `air-quality`, `heart-rate` and `temperature` become complete; `battery` (with N1); `fuel` loses its soft low zone. |
| 4 | **N7** label formatters | `compass`, `wind` (still needs the second key), `fuel` E/F, `power-meter`, `barometer` words. Cheapest of the set. Do it with or just after step 2. |
| 5 | **N6** insets | `system`, `nested-rings`, `speed-fuel`. Interim: layer overlapping `realtime.gauge` panels in one group, each with its own preset. Untested; check that panel backgrounds stay clear. |
| 6 | **N4** scale types | `sun-path`, `clock`, `chronograph`, `orrery`; also shortest-path needle across 0 for `compass` and `wind`. |
| 7 | **N5** animated value | Nothing new. Polish for every preset. See section 4 for the one rule. |

Steps 2-4 are independent of each other. Step 2 first, because it unlocks the
most. Step 1 comes first only because the value-sources work already has it.

## 4. Do not copy

- **Low-contrast opacity tiers.** Tracks at 0.10-0.19, ticks at 0.4-0.5, and
  1.5-3 unit hairlines are drawn for a laptop screen. They disappear at room
  distance on a wall display. Give every mark that carries information a floor
  for contrast against the background, and every track a visible width. Check
  each preset at small render size with the render service
  (`GET /render/<name>?scale=0.25`) before it merges. Name the floor in the
  review, not by eye.
- **Absolute SVG units.** gauge-ui positions text and sets widths in units of
  one SVG box (arc `width: 26`, font `84`, `offset: -54`). Express LevityDash
  widths and offsets as a fraction of the radius (`Size.Height(relative=True)`,
  as `Gauge.radius` does) or in mm. Send font sizes through the size-group
  fitter, not fixed numbers.
- **Spring overshoot on data.** The weather example's wind vane uses
  `bounce: 0.25` and the health example `0.15`. The studio default is `0.1`.
  Overshoot makes a reading look as if it passed the true value. The shipped
  templates use `bounce: 0` or none. If N5 is built, use an ease with no
  overshoot, and never let the shown value pass the real one.
- **Drag controls.** `volume` sets `control: "knob"` so a viewer can turn it.
  A dashboard here is read-only. Drop the control. A later write path (the
  bidirectional HUD node idea) is a separate design.
- **Fake live data.** The weather example gusts the wind with a timer to look
  alive. A preset shows the key's value and nothing else.
- **Hard-coded text.** Several templates print fixed words and numbers ("307
  km", "Cabin", "5 m/s"). Take titles and units from the key, or leave the
  slot free for the dashboard.

## Verification

- A test in `tests/ui/` loads every bundled preset onto a `realtime.gauge`
  with a synthetic key and checks the display builds and no exception reaches
  the loader. The load-abort gotcha in `CLAUDE.md` is the failure to guard.
- A test for the lookup: a known name merges, an unknown name logs and loads,
  a user key beats the preset, a `shared:` value loses to the preset.
- A test that `Stack.preset: <name>` now finds a name.
- Render each preset: `render_widget.py --list`, then
  `GET /render/<name>` from `render_service.py`. Use a fixed value. Compare
  against the gauge-ui preview as a layout check only.
- Run the real app with `STATEFUL_DEBUG=1` on a dashboard that uses three
  presets. An offscreen render does not prove the dashboard loads.
- Under `mode=remote`, check a preset gauge on the frontend with the backend
  running as a separate process.

## Not in scope

- A preset editor or gallery UI.
- Presets for displays other than gauges and stacks.
- Data shape inference (choosing a preset from the key's unit). Possible later.
- Computed values. They are [value-sources.md](value-sources.md).

## Suggested branch

`feat/gauge-presets`. Branch from `dev` after `feat/value-sources` lands,
since step 1 and the `markers:` rows depend on it. Steps 0 and 2 do not.

## Related

- [value-sources.md](value-sources.md): N3 markers, range bounds from data
- [gauge-display.md](gauge-display.md): the build and visibility bugs to fix first
- [curved-gauge-labels.md](curved-gauge-labels.md): glyphs bent along the arc; touches N7
- `docs/roadmap.md`: "Migrate `shared:` to named `preset:`"
- `docs/design-references/`: example fragments for `design_mode.py`

Cockpit instruments (attitude indicator, altimeter, heading indicator, airspeed, vertical speed) are in scope for later, for a future overhead-flights tracker. They need a rotating dial card, an artificial horizon and a multi-hand scale, none of which exist yet.

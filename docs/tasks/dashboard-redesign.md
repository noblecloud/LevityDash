# Dashboard redesign — state of play

**Status:** in progress, 2026-07-26. The layout below is **installed and
running**; the font work is set up but not applied. Written as a handoff
mid-task, so it records what was learned as much as what is left.

Target display is **15 inch**. The previous layout was proportioned for
something closer to 8 inch — chunky dials, two-across grids. The correction
is *more readings, not bigger ones*: a physically larger screen is read from
further back but resolves more items.

## What is installed

`~/Library/Application Support/LevityDash/saves/dashboards/default.levity`
(previous version preserved beside it as `default.levity.backup-20260726-131139`).

Bottom band, four panels, sizes `20 / 15 / 31 / 31`:

| panel | contents |
|---|---|
| Condition | icon, sun times with icons, high/low, description |
| Wind | the one real dial + Gust / Dir |
| Atmosphere | Pressure, Humidity◯, Cloud◯ / Dew Pt, Feels, Rain |
| Sky | UV◯, High, Low / Sunrise, Sunset, Gust |

◯ = **mini gauge**: `major`/`minor`/`micro` all `enabled: false`, so it is an
arc plus a needle and no graduations — a badge beside the number rather than
a dial competing with it.

Only **wind** keeps a full dial. Angular position genuinely encodes speed
there; everywhere else a ring is decoration and a number is the reading.

### Generator, not hand-edited YAML

The dashboard is emitted by `mk3.py` in the session scratchpad
(`head.yaml` = base lines 1–262, plus `condition.yaml` = the condition
panel). It is not in the repo. If it is gone, the installed `.levity` is the
source of truth — read it rather than rebuilding the generator.

## Done since this was written (2026-07-27)

Fonts applied and the sun-time cells resolved — see *Type* and *Panels* below.
What remains open is the mini-gauge centring (§3) and the High/Low
duplication noted at the end.

### Type

Values are `Roboto Mono`, cell titles are `Roboto`, hero temperatures and
prose (`clear sky`) stay Nunito. Set per-item via the existing `font`
`StateProperty` — no code needed.

Two places deliberately keep the proportional face: the **wind dial's value**
(mono is wider, and the value grew into the floating `mph` beneath it) and
the big top-left temperatures.

### Panels

Sun times are gone from the stat grid; `Sky` became `Today`. Sizes are now
`20 / 17 / 44 / 16`. Atmosphere carries all three rings — Humidity, Cloud, UV
— which makes the ring a consistent idiom rather than a one-off.

**A lone glyph in a tall cell balloons.** UV rendering as `0` next to `71°`
came out enormous: it fits far larger in its box, and the size group did not
equalise it across that distance (the spatial-cluster `reach` behaviour in
`Groups.py`). Moving it beside the other rings fixed it, but the underlying
sizing-group gap is real and will bite again for any single-character value.

## Left to do

### 1. ~~Fonts~~ — done, see above. Original note kept for the config trap:

`[Fonts] monospace` in the user config was **`Nunito`** — not a fixed-width
face at all. That is why asking for monospace appeared to do nothing. It is
now `Roboto Mono` (present on the system, pairs with the bundled Roboto used
for titles).

Nothing in the dashboard references it yet, so that change is currently
inert. **No code is needed** — `font` is already a `StateProperty` on `Label`
(`Displays/Label.py:194`) and takes a family name string:

- `display: {font: Roboto Mono}` on the stat-grid values
- `title: {font: Roboto}` on the small cell titles, to separate the label
  layer from the value layer
- big hero temperatures stay Nunito

The real argument for fixed-width here is **not** density — mono is wider per
glyph. It is that **digits stop jittering horizontally as values update**:
`29.85 → 29.9` currently reflows the whole cell, and a column of ragged-width
numbers cannot line up.

### 2. The sun-time cells are out of place

Sunrise/Sunset in the Sky panel read wrong: they are *timestamps sitting among
measurements*, and the Condition panel already shows both with icons. Plan was
to drop them and make Sky a single tall row — High, Low, UV◯ — with sizes
going `20 / 15 / 34 / 28`.

### 3. Mini-gauge value labels are not centred

`value-label: {position: center}` puts the number *beside* the ring, not
inside it. This is the known `_center_transform` TODO in `Gauge.py`. The rings
were sized to read deliberately that way rather than paper over it, but it is
a placement bug, not a design choice — see
[gauge-display.md](gauge-display.md).

## Gotchas found the hard way

Each of these cost a full render cycle.

- **The condition panel's size is `28%`, not 25%.** Several attempts did a
  string substitution on `size: 25%`, which silently matched nothing — so the
  panel stayed 28% and every layout overflowed off the right edge. The
  failure looks like "the stack is broken", not "a replace missed".
- **Panel sizes must sum to ~97%, not 100%.** The stack's `spacing: 10px`
  between five panels costs ~2% of 1920px on top of the declared sizes.
- **`[Fonts] monospace = Nunito`** — see above. Check the *value* of a config
  key before concluding the feature that reads it is broken.
- **Dead keys pad density without adding information.** These have no source
  in the current plugin set and render as `•••`:
  `light.irradiance`, `light.illuminance`, `precipitation.precipitation`,
  `precipitation.daily`, `precipitation.type`, `pressure.trend`,
  `indoor.temperature.feelsLike`. An Indoor panel was cut for this reason.
- **Time values need an explicit format** or they render `10:05:41`. Use
  `display: {format: '%-I:%M%p'}`, as the condition panel already does.
- **A floating unit label clips at the panel edge.** Stat rows need to stop
  short of 100% height (94% works) or the unit under the bottom row is cut.

## Code changed for this

`GaugeLabel.visible` — a new `StateProperty` in
`Displays/Gauge.py` (~line 1838). There was previously **no way to hide a
value or unit label from config**: the label wrapper's own visibility is
meaningless because the textBox is reparented to the gauge (see the comment
in the `valueLabel` factory). The setter also drops the cached
`full_gauge_path`, which counts only visible labels.

This is what makes both the mini gauges and the floating `mph` possible —
`unit-label: {visible: true, position: below}` puts the unit under the value
instead of trailing it.

## Verification

Renders were produced offscreen at 1920×1080 (`render.py` in the scratchpad:
seeds a config copy, forces `[QtOptions] openGL = False`, pumps ~6s,
`view.grab().save()`). ⚠️ **Renders are not a substitute for the real screen** —
without live plugin data every value is a `•••` placeholder and the layout
reads completely differently. Several judgements made on placeholder renders
turned out wrong once real values appeared.

`poetry run pytest` — 196 passed, 1 skipped, at the point this was written.

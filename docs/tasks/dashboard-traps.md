# Dashboard authoring traps

A consolidated list of `.levity` layout mistakes that cost a full render cycle to
discover. Each was hit in practice (see `dashboard-redesign.md` for the original
war stories). This is the human-readable reference and the why behind each rule —
meant to inform hand-authored `.levity` files and the design skill directly,
not a programmatic generator (one was tried and scrapped; it could only emit a
narrow subset of the item types real dashboards use).

These are about the *layout YAML*, not the schema/source-key layer (that's
`docs/tasks/loud-failure-dev-mode.md` and the `LEVITYDASH_SCHEMA_DEBUG` work).

## Layout sizing

- **Panel sizes must sum to ~97%, not 100%.** The stack inserts `~2–3%` of
  spacing between bands (at 1920px, `spacing: 20px` between five panels). A
  declared `100%` silently overflows off the right edge — the failure looks like
  "the stack is broken", not "a size sum is wrong". The generator warns when the
  sum is outside `97% ± 2%`.
- **A `size: 25%` panel that is actually `28%` will not be fixed by a string
  replace.** Several attempts did `str.replace('size: 25%', 'size: 20%')` which
  matched nothing because the real value was `28%`. Read the actual value before
  editing. The generator emits sizes from the spec, so there is no literal to
  mistype.
- **Floating unit labels clip at the panel edge.** A realtime value cell at
  `height: 100%` / `width: 100%` pushes its unit label under the bottom edge.
  Stop short: `94%` works for both `height` and `width` on stacked value cells.

## Config key traps

- **`[Fonts] monospace` was `Nunito`, not a fixed-width face.** Asking for
  monospace appeared to do nothing because the *value* of that config key was a
  proportional font. Config reads from `lib/config.py`; check the key's value
  before concluding the feature that reads it is broken. (Now `Roboto Mono`,
  which pairs with the bundled `Roboto` used for titles.)
- **Mono is wider per glyph — its real win is digit stability, not density.**
  `29.85 → 29.9` reflows a proportional cell; a column of mono numbers lines up.
  Use `font: Roboto Mono` on stat-grid values, `font: Roboto` on titles.

## Dead keys

A *dead key* is a `key:` reference with no matching source in any loaded plugin
schema — it renders as `•••`, adding density but no information. There is exactly
**one** dead key in the default plugin set:

```
indoor.temperature.feelsLike
```

`indoor.*` is only used by the Govee plugin, whose indoor block defines
`temperature` / `dewpoint` / `heatIndex` but **not** `feelsLike`. Every other
commonly-suspected key — `light.irradiance`, `precipitation.precipitation`,
`precipitation.daily`, `pressure.trend`, `environment.temperature.feelsLike`,
`indoor.temperature.heatIndex` — *is* defined (OpenMeteo / WeatherFlow /
PirateWeather / OpenWeatherMap / Govee). An earlier draft listed seven "dead"
keys; that list was wrong (carried over from an older task note before those
plugins were wired up).

**How to verify a key before using it:** grep the schemas for the dotted path —
`grep -rn "indoor.temperature.feelsLike" src/LevityDash/lib/plugins/builtin/`
→ no match means dead. Don't trust a cached dead-key list; verify against the
schemas in the repo you're actually working in.

## Time formatting

- **Time values need an explicit format or they render `10:05:41`.** Use
  `display: {format: '%-I:%M%p'}` (the canonical short clock). The generator
  applies this to every `*.light.sunrise` / `*.sunset` item by default.
- **Sun times are timestamps among measurements.** Placing `Sunrise`/`Sunset` in
  a stat grid reads wrong — the Condition panel already shows both with icons.
  Keep them as their own row, not mixed into the measurement grid.

## Rendering caveats

- **Offscreen renders are not the real screen.** Without live plugin data every
  value is a `•••` placeholder and the layout reads completely differently. Several
  judgements made on placeholder renders turned out wrong once real values
  appeared. Render command pattern (from `dashboard-redesign.md`): seed a config
  copy, force `[QtOptions] openGL = False`, pump ~6s, `view.grab().save()`.
- **A lone glyph in a tall cell balloons.** A single-character value (e.g. `UV`
  rendering as `0`) fills its box and looks enormous next to multi-char numbers,
  because the size-group `reach` behaviour in `Groups.py` doesn't equalise across
  that distance. Move it beside other rings, or scope it to a sized group.

## On generating `.levity` programmatically

A repo-side generator (`scripts/dashboard_generator.py`) was built and scrapped
(2026-08-04). It could only emit `realtime.text` items in flat panels — no
gauges, clock, moon, or value-stacks, i.e. most of what a real dashboard uses —
so despite passing its own tests it never approached parity with a hand-tuned
layout, and there was no real workflow planning to consume its output.
Direction going forward is a design *skill* (judgment applied per-dashboard)
rather than a spec-driven generator; this file is what that skill and any
hand-authored `.levity` should draw on.

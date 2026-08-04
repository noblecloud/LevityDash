# Dashboard authoring traps

A consolidated list of `.levity` layout mistakes that cost a full render cycle to
discover. Each was hit in practice (see `dashboard-redesign.md` for the original
war stories). `scripts/dashboard_generator.py` bakes the checkable ones into
`--check` warnings; this file is the human-readable version and the why behind
each rule.

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

These keys have **no source in the default OpenMeteo / WeatherFlow plugin set**
and render as `•••`, padding density without adding information. The generator
refuses to emit them (warns + skips):

```
light.irradiance, light.illuminance,
precipitation.precipitation, precipitation.daily, precipitation.type,
pressure.trend,
indoor.temperature.feelsLike
```

(An Indoor panel was cut specifically because of the last one.)

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

## Where the generator fits

`scripts/dashboard_generator.py` is the repo-side replacement for the old
out-of-repo `mk3.py`. It emits a `.levity` from a compact panel spec and applies
the trap-safe defaults above. It does **not** replace hand-tuned dashboards — the
emitted file is still plain YAML you can open and edit. Run `--check` to validate
a spec's sizes/dead-keys before writing.

# Bend gauge tick labels along the arc

**Status:** idea, not scheduled. Recorded 2026-07-26.

## What

Gauge graduation labels should **curve with the arc** — each glyph sitting on
the curve with its own rotation — rather than the whole label string being
rotated as one rigid block, which is what happens today.

The difference is most obvious on a wide dial: at the moment `100` on a
240° arc is a straight run of three characters tilted to roughly match the
tangent. Bent, each character would follow the curve, the way it reads on a
real instrument face.

## Why it is tractable

Text here is already **vector, not raster**. `Text._update_path`
(`Displays/Text.py`, look for `path.addText(text_pos, font, text)`) builds a
`QPainterPath` from the font outline. So this is a matter of placing glyphs
individually along a curve, not warping an image — no rasterisation, no
quality loss, and the result stays a path.

## Where the labels live

| | |
|---|---|
| `GaugeTickText` | `Displays/Gauge.py` ~2316, subclasses `AnnotationText` + `GaugeItem` |
| `GaugeTickTextGroup(AnnotationLabels[GaugeTickText])` | same file, ~2523 |
| arc geometry | `GaugeArc`, `startAngle` / `endAngle` / `fullAngle`, `gauge.radius`, `gauge.center` |
| `AnnotationText` base | `Displays/Annotations.py` |

## Suggested approach

Per label, instead of one `addText(pos, font, string)` plus a rotation:

1. Walk the characters, taking each glyph's advance from
   `QFontMetricsF.horizontalAdvance`.
2. Convert cumulative advance to an angle — `angle = arc_length / radius` —
   centred so the string stays centred on its tick.
3. For each glyph, build a `QTransform` that rotates by that angle about the
   gauge centre and translates out to the radius, then `addText` the single
   character through it into one combined path.

**Keep the result a single `QPainterPath` per label.** Hit-testing,
`shape()`, and the existing collision/fitting logic all read that path, and
they keep working unchanged if the output shape is the same kind of object.

## Gotchas, including two fixed today

- **Vertical placement must use ascent/descent, not `tightBoundingRect`.**
  Ink extents hug the glyphs, so a descender shifts the whole string — that
  was the graph hour-label bug fixed in *"align text by font metrics, not
  ink extents"*. Easy to reintroduce when rewriting glyph placement.
- **`Gauge.recenter()` measures `full_gauge_path` at identity**, and that
  path includes tick label shapes via `mapFromItem`. Bent labels change its
  bounds, so recentring needs re-verifying (see the comment in `recenter`
  about why measurement happens at identity).
- **Text on the lower half of a dial needs flipping** or it renders upside
  down. Check how the current rotation handles that before replacing it.
- **Leave the `_center_transform` TODO alone.** There is a known-unfinished
  "labels are not moved correctly" note there; scope here is glyph
  placement only.

## Verification — visual, not readable

This cannot be checked by reading code. Render offscreen and look at the PNG:

- seed a config dir from `tests/resources/config-seed` (or the real one at
  `~/Library/Application Support/LevityDash`)
- put `type: realtime.gauge` panels in `<seed>/saves/dashboards/default.levity`
- env: `QT_QPA_PLATFORM=offscreen`, `LEVITYDASH_CONFIG_DEBUG=1`,
  `LEVITYDASH_CONFIG_SEED=<seed>`
- boot via `LevityDashboard.init()` then `app.init_app()` (mirrors
  `tests/conftest.py`), pump events ~4s, then
  `LevityDashboard.view.grab().save(path)`
- ⚠️ force `[QtOptions] openGL = False` on `userConfig` before `init_app`,
  or the grab is blank white

Compare before/after crops of a dial at several radii and font sizes, on a
wide arc (240°, the default) and a narrow one. Then `poetry run pytest -q`.

## Config reminder

Gauge settings nest under `display:` — at the item level they silently go to
the `Realtime` panel instead and appear to do nothing:

```yaml
- type: realtime.gauge
  key: environment.humidity.humidity
  display:
    radius: 98%
    arc:
      gradient: RainbowPercentage
```

## Suggested branch

`feat/curved-gauge-labels`

## Related

- [gauge-display.md](gauge-display.md) — current state of the gauge

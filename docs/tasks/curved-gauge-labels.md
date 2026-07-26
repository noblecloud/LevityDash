# Bend gauge tick labels along the arc

**Status:** idea, not scheduled. Recorded 2026-07-26.

## What

Gauge graduation labels should **curve with the arc** — the glyph outlines
themselves deformed, so vertical stems fan out along radii and horizontal
strokes become arcs. Today the whole label string is rotated as one rigid
block.

At the moment `100` on a 240° arc is a straight run of three characters
tilted to roughly match the tangent. Properly bent, the characters would be
*shaped* by the curve, the way numerals sit on a real instrument face — not
merely arranged along it. That distinction is the whole task; see
[NOT per-glyph placement](#not-per-glyph-placement) below.

## Why it is tractable

Text here is already **vector, not raster**. `Text._update_path`
(`Displays/Text.py`, look for `path.addText(text_pos, font, text)`) builds a
`QPainterPath` from the font outline — so the glyph geometry is available as
points to be moved, which is exactly what this needs. No rasterisation, no
quality loss, and the result stays a path.

## Where the labels live

| | |
|---|---|
| `GaugeTickText` | `Displays/Gauge.py` ~2316, subclasses `AnnotationText` + `GaugeItem` |
| `GaugeTickTextGroup(AnnotationLabels[GaugeTickText])` | same file, ~2523 |
| arc geometry | `GaugeArc`, `startAngle` / `endAngle` / `fullAngle`, `gauge.radius`, `gauge.center` |
| `AnnotationText` base | `Displays/Annotations.py` |

## NOT per-glyph placement

⚠️ **Placing each character separately along the curve has been tried and it
looks bad.** Each glyph stays internally straight, so the string reads as a
faceted polygon approximating the arc — visible gaps opening at the outer
edge between characters, pinching at the inner edge, and the taller the text
or tighter the radius, the worse it gets. Do not re-attempt it.

## Suggested approach: warp the outlines

The glyph **outlines themselves** must be deformed — vertical stems fanning
out along radii, horizontal strokes becoming arcs. This is a **non-affine**
transformation, so `QTransform` cannot express it (it is affine only). The
points have to be remapped individually.

1. Build the whole string flat: baseline on `y = 0`, `x` running `0 → width`.
2. **Flatten the path to polygons** — `QPainterPath.toSubpathPolygons()`
   converts béziers to line segments. Necessary because a warp applied to
   bézier *control points* distorts the curve rather than following it.
3. Map every point from flat text space into polar space about the gauge
   centre:
   - `theta = start_angle + (x / radius)` — arc length over radius, so
     spacing is preserved along the curve
   - `r = radius - y` — text-space `y` is negative above the baseline, so
     ascenders move outward and descenders inward
   - `point = center + (r·cos(theta), r·sin(theta))`
4. Rebuild a single `QPainterPath` from the mapped polygons.

### The bit that decides whether it looks good

**Flattening resolution.** After mapping, every straight segment becomes a
straight *chord* across the arc. A long horizontal stroke — the crossbar of a
`4`, the top of a `5`, the middle of a `0` — will visibly cut across the
curve unless it was subdivided before mapping. `toSubpathPolygons` flattens
béziers but leaves genuinely straight edges as single segments, so those need
subdividing to a maximum segment length chosen from the radius (shorter
segments for tighter arcs).

Getting this wrong is the difference between "curved text" and "text that
looks slightly broken", and it will not show up on a large radius — test on a
small dial.

**Keep the result a single `QPainterPath` per label.** Hit-testing, `shape()`,
and the existing collision/fitting logic all read that path and keep working
unchanged if the output is the same kind of object.

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
  "labels are not moved correctly" note there; scope here is the shape of the
  glyphs, not where the label sits.

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
wide arc (240°, the default) and a narrow one. **Small radii are the real
test** — a large dial hides insufficient flattening, a small one exposes it
immediately. Digits with long horizontal strokes (`4`, `5`, `7`, `0`) are the
ones to look at. Then `poetry run pytest -q`.

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

# Bend gauge tick labels along the arc

**Audit 2026-10-10: done.** Merged into `feat/value-sources` on 2026-10-04 (`feat/curved-gauge-labels`); the header below predates the merge.

**Status:** idea, not scheduled. Recorded 2026-07-26. Rewritten as a step-by-step
brief 2026-10-04, with every file and line checked against `dev` at `689c067`.

Line numbers below are for that commit. Search for the names, not the numbers, if
the file has moved.

## What

Gauge graduation labels should **curve with the arc**. The glyph outlines
themselves bend: vertical stems fan out along radii and horizontal strokes
become arcs. Today the whole label string is rotated as one rigid block.

At the moment `100` on a 240° arc is a straight run of three characters tilted to
match the tangent. Properly bent, the characters are *shaped* by the curve, the
way numerals sit on a real instrument face. That difference is the whole task.
See [NOT per-glyph placement](#not-per-glyph-placement).

The result is an opt-in setting. The default stays today's rigid rotation.

## Why it is tractable

Text here is already **vector, not raster**. `Text._update_path`
(`Displays/Text.py:898`) builds a `QPainterPath` from the font outline with
`path.addText(text_pos, font, text)` (line 1010). The glyph geometry is therefore
available as points that can be moved. There is no rasterisation, no quality
loss, and the result stays a path.

## Where things live

All paths are under `src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/`.

| | |
|---|---|
| `GaugeTickText(GaugeItem, AnnotationText)` | `Gauge.py:2838` |
| `GaugeTickTextGroup(AnnotationLabels[GaugeTickText])` | `Gauge.py:3062` |
| `AnnotationText(Text)` | `Annotations.py:23` |
| `Text._update_path`, `Text._layoutSignature`, `Text._builtSignature` | `Text.py:898`, `:625`, `:623` |
| `Text.updateTransform` (sets the scale) | `Text.py:393` |
| `Tick.draw`, `Tick.angle` | `Gauge.py:1343`, `:1301` |
| `TickSurface.refresh` (sets the surface origin to the gauge centre) | `Gauge.py:1430` |
| `Gauge.recenter` | `Gauge.py:4045` |
| `Gauge.full_gauge_path` | `Gauge.py:4593` |
| label config property `rotate` | `GaugeTickTextGroup.rotation`, `Gauge.py:3269` |

## What the code does today

Read these first. Three of them change how this task is built.

**Angles and the surface origin.** `Tick.draw` puts a tick at
`(radius·cos θ, radius·sin θ)` with `θ = radians(tick.angle)`. `tick.angle` is
`startAngle + index·interval_degree`, where the ticks' `startAngle` is
`gauge.startAngle - 90` (`Graduations.startAngle`, `Gauge.py:766`). So `tick.angle`
is a Qt screen angle: y down, degrees clockwise from +x. `TickSurface.refresh`
calls `self.setPos(self.gauge.center)`, so **the gauge centre is `(0, 0)` in the
tick surface's coordinates**, which are also the coordinates of every
`GaugeTickText` position. The user-facing arc keys are `display.arc.start-angle`
and `display.arc.end-angle` (defaults -120 and 120, zero at 12 o'clock; 240° is
the default sweep).

**Rotation and the flip.** `GaugeTickText.refresh` (`Gauge.py:2986`) does:

```python
rotation = self.tick.angle + 90 if self.rotated else 0
if 105 < rotation % 360 < 255:
	rotation += 180
self.setRotation(rotation)
```

So the item is rotated, its origin sits at the label position, and its local +x
runs along the tangent. The flip happens exactly when `tick.angle` mod 360 is in
(15°, 165°), that is `sin θ0 > sin 15° ≈ 0.259`. This is **not** plain
`sin θ0 > 0`. A label within 15° of the horizontal axis stays unflipped on
purpose (the comment says "keeps near-vertical radial labels as they are"). The
bend must use the same test, or labels jump when you switch modes. Move the test
into one helper (for example `_labelRotation()` returning the final rotation and
the flipped flag) and call it from `refresh` and from the bend code, so the two
cannot drift apart. `rotated` is false for the two end labels by default
(`rotate-leading` and `rotate-trailing` default to `False`), and false for the
whole group when `rotate: false`. An unrotated label is never bent.

**Position.** `GaugeTickText.position` returns `tick.startPoint`, `endPoint` or
their midpoint, chosen by the label position setting. `setPos` (`Gauge.py:2934`)
then calls `super().setPos`, nudges the label along the radial direction by the
arc half-width, and finally loops `moveBy` along the radial direction while the
label's `shape()` collides with the arc or its own tick. The nudge reads
`shape()`, which comes from the current path. `moveBy` is a C++ call and does not
re-enter the Python `setPos` override; confirm this when you wire the bend in.

**Size is a scale transform, not a font size.** `Text.updateTransform`
(`Text.py:393`) resets the transform, calls `_update_path` (which builds the path
at the font's own size), then ends with
`transform.translate(x, y); transform.scale(scale, scale)` and `setTransform`.
For a tick label `getTextPosition` returns `(0, 0)` (`Annotations.py:66`), so the
translate is zero, and `scale` comes from `getTextScale` (`Gauge.py:3039`):
`limitRect` height divided by the flat `_textRect` height, capped by
`scaleSelection` when the string is wider than `allowedWidth`. The font size is
`suggestedFontPixelSize`, which is `height_limit`. So the scale is usually near 1
but is a real `QTransform`, and `GaugeTickText.setTransform` (`Gauge.py:2871`)
reads `matrix.m11()` to rebuild its `_shape`. **The warp therefore runs in local
units.** See [Coordinates](#coordinates-and-the-mapping), step 3.

**Tick labels are not in a `SizeGroup`.** `GaugeTickTextGroup.size_group` exists
(`Gauge.py:3131`) but the line that would add each label to it is commented out
(`Gauge.py:2862`). Nothing else calls `size_group` or `addItem` for tick labels,
so `_sized` is never set and each label computes its own scale. The fitting rule
in [Size fitting](#size-fitting) still holds, but the thing to protect is
`getTextScale` and `_textRect`, not a group.

**Shape plumbing.** `GaugeTickText.setPath` (`Gauge.py:2921`) stores
`_shape = outline_path(path, group.offset_px)` and `shape()` and `boundingRect()`
return it. `GaugeTickTextGroup.shape` (`Gauge.py:3076`) maps each `label.path()`
into the surface with `surface.mapFromItem`, which applies the label's full
transform (rotation, scale, position). `Gauge.recenter` and `full_gauge_path` read
that group shape. All of this works unchanged if a bent label is still one
`QPainterPath` in the label's local coordinates.

**The layout-signature skip.** Commit `222fe78` added
`Text._layoutSignature` and `_builtSignature`. `Text.refresh` (`Text.py:649`)
returns early when the signature equals the one stored at the last
`_update_path`. The signature covers text, font key, `limitRect`, alignment, scale
type, format hint and `height_px`. It does not cover anything about the curve.

## NOT per-glyph placement

⚠️ **Placing each character separately along the curve has been tried and it
looks bad.** Each glyph stays internally straight, so the string reads as a
faceted polygon approximating the arc. Gaps open at the outer edge between
characters and pinch at the inner edge, and the taller the text or tighter the
radius, the worse it gets. Do not make it the default.

The maintainer does want it as a *second, opt-in* mode (2026-10-04). It suits
loose, letter-spaced labels where the faceting does not show. Build the warp
first. Per-glyph placement is a small option on top
([step 8](#suggested-order-of-work)).

## Coordinates and the mapping

Qt screen space: y down, angles in degrees or radians clockwise from +x. Work in
radians in code.

### 1. Build the label flat, at final size

Build the label flat, with its baseline on `y = 0` and `x` running from `0` to
`w`.

- `fm = QFontMetricsF(font)`, with `font = self.font()` (the same call
  `_update_path` makes, so the group's font size rules apply).
- `w = fm.horizontalAdvance(text)`.
- `ascent = fm.ascent()`, `descent = fm.descent()`. The vertical band is
  `y ∈ [-ascent, +descent]`. **Use font metrics, not ink bounds.** Ink extents
  hug the glyphs, so a descender would shift the whole string. That was the graph
  hour-label bug (see [text-baseline-alignment.md](text-baseline-alignment.md)).
- Add the text with `path.addText(QPointF(0, 0), font, text)`.

Centre it on the tick angle by shifting x:

```
x' = x - w/2
y_m = (descent - ascent) / 2
```

`y_m` is the y of the band's middle, measured from the baseline (y down, so it
is positive when the descent is bigger than the ascent). `y - y_m` is the
distance below the band's middle.

### 2. The mapping

Let `θ0` be the tick angle in radians, `R_l` the radius of the label *centre*
from the gauge centre, and `s` the side: `+1` when the label is not flipped
(glyph tops point outward), `-1` when flipped (glyph tops point inward). In
gauge coordinates, centre `c`:

```
θ = θ0 + s · x' / R_l
r = R_l − s · (y − y_m)
point = c + r · (cos θ, sin θ)
```

Why these signs:

- Arc length is preserved at the text's middle. A point `x'` along the flat text
  moves `x'` along the circle of radius `R_l`, so the angle changes by `x'/R_l`.
  Letter spacing along the label's middle line is the same as in the flat text.
- Not flipped (`s = +1`, upper part of the dial): a glyph top has `y < y_m`, so
  `r > R_l`. Tops point outward. Increasing `x'` increases `θ`, which is
  clockwise on screen, which is left to right along the top of a dial.
- Flipped (`s = -1`, lower part): tops get `r < R_l`, so they point inward
  (toward the centre). Increasing `x'` *decreases* `θ`, which is left to right
  along the bottom of a dial. The label reads left to right and is not upside
  down.
- At `x' = 0`, `y = y_m` the point is `c + R_l·(cos θ0, sin θ0)`: the label centre
  lands on the tick angle, at radius `R_l`.

`s` comes from the existing flip test, not from the sign of `sin θ0` (see "What
the code does today"). `R_l` is `hypot(pos.x, pos.y)` of the label item after
`setPos` has finished nudging it, because the surface origin is the gauge centre.
`R_l` may be larger or smaller than the arc radius. Labels placed outside the
arc work with no special case, since the formula never refers to the arc radius.

### 3. Do the warp in the label's local units

The item is rotated by `ρ` (the final rotation, including the flip's 180°),
placed at `pos`, and scaled by `S = transform.m11()` after the path is set. The
path the item stores is in the item's local coordinates, before `S`, rotation and
translation. The gauge-space formula above is therefore not applied directly.
Two equivalent ways to apply it:

**A (recommended): warp in the local frame.** The local frame has its origin at
the label centre and x along the reading direction. The gauge centre sits at
`(0, +R_l)` when `s = +1` and at `(0, −R_l)` when `s = −1`. Define
`α = x'/R_l`, `r = R_l − s·(y − y_m)` as before. Then:

```
local_x = r · sin α
local_y = s · (R_l − r · cos α)
```

I checked numerically that this equals the gauge-space formula pushed through
`pos` and `ρ`, for `θ0` of 30°, 90°, 200° and 270°, flipped and not. Build the
flat path at final size first (multiply by `S`), warp, then divide the result by
`S`. Equivalently, work in local units throughout with `R_local = R_l / S` and the
flat path at font size; both give the same shape. In pixel terms, `R_l`, `ε`, and
the subdivision length `L` are scene units; divide by `S` if you work in local
units.

**B: warp in gauge coordinates.** Warp as in step 2, then map back with
`QTransform` built from `pos`, `ρ` and `S`, inverted. Only pick this if A proves
confusing. It is the same path.

`S` is read from `self.transform().m11()`, because `GaugeTickText.setTransform`
already does the same.

### 4. Flatten, then subdivide

The warp is not affine, so `QTransform` cannot do it and Bézier control points
cannot simply be moved: moving control points distorts a curve instead of
following it. Convert the outline to polylines first.

1. Build the flat path at final size, then call
   `path.toSubpathPolygons(QTransform().scale(S, S))`. Qt flattens after applying
   the matrix, so curves are subdivided finely for the real pixel size. (Without
   the matrix, flatten a path at font size and the chords are too coarse once
   scaled up.)
2. `toSubpathPolygons` flattens curves but leaves genuinely straight edges as
   single segments. Subdivide **every edge** of every polygon so no edge is
   longer than

   ```
   L = sqrt(8 · r · ε)
   ```

   The sagitta (gap between a chord and its arc) of a chord of length `L` on a
   circle of radius `r` is about `L² / (8r)`. Setting that to `ε` gives `L`. Use
   `ε ≈ 0.25` device pixels. Device pixels are `scene units × view scale`
   (`self.scene().viewScale`, as `AnnotationText.limitRect` reads it), so
   `ε_scene = 0.25 / viewScale`. Use the smallest `r` the label spans
   (`R_l − s·(y_min − y_m)` at the inner edge), or just `R_l − ascent − descent`,
   floored at a small positive number.
3. Map every point of every subdivided edge with the formula in step 3.
4. Rebuild **one `QPainterPath` per label**. For each mapped polygon call
   `addPolygon` then `closeSubpath`. Set the original fill rule
   (`Qt.WindingFill`, as `_update_path` does) so the counters of `0`, `4`, `6`,
   `8` and `9` stay open.
5. Divide by `S` if you worked at final size, then `setPath(bent)`.

This is what makes the result look curved. Without step 2 the crossbar of a `4`,
the top of a `5` and the top of a `7` stay chords across the arc, and the label
looks slightly broken. A large dial hides this. A small dial shows it.

Keep one path per label. `shape()`, hit-testing and the collision loop in
`setPos` then keep working.

## Placement

**Decision: keep the item where it is today.** The label item stays a child of the
tick surface, at `pos` (the tick anchor plus the radial nudge), with its current
rotation and scale. The bent path is built in the item's local coordinates, as
step 3A describes. The other option (put the item at the gauge centre with no
rotation and build the path in gauge coordinates) is rejected because:

- The nudge loop in `setPos` moves the *item*. An item at the centre would need
  a different collision scheme.
- `GaugeTickText.shape`/`boundingRect`, the group shape, and
  `Gauge.recenter`/`full_gauge_path` all assume a label is a small shape near its
  tick. A label shape spanning the whole dial makes every bounding-box test
  larger.
- Step 3A needs only the item's own `pos`, rotation and scale, all of which exist.

`Gauge.recenter` clears the transforms of the arc, needle, markers, fills and
three tick surfaces, measures `full_gauge_path`, then sets a translate on them
(`Gauge.py:4045`). That measure includes the label shapes through
`GaugeTickTextGroup.shape`. A bent label is a different size from a flat one, so
the bounds `recenter` sees change slightly. Re-verify centring after the change.
The comment about measuring at identity explains why a mid-update measure
snaps ticks back, so do not add a bend that reads the surface transform.

Leave the `_center_transform` TODO alone (`Gauge.py:4026` and the "labels are not
moved correctly" note in `recenter`). Scope here is the shape of the glyphs, not
where the label sits.

**Where to run the bend.** `updateTransform` is deferred through an action pool,
and `refresh` calls `setPos` after `super().refresh()`. So the rotation, scale
and final position are not all known at one point. Put the bend in one method,
`_bend()`, and call it from the end of `GaugeTickText.setPos` and from the end of
`GaugeTickText.setTransform` (skip when `matrix` is identity, which
`updateTransform` sets first). `_bend()` builds its own flat path from `text` and
`font()`, so it never reads `self.path()` and cannot bend an already bent path.
It computes a key `(mode, text, font key, round(S, 4), flipped, round(θ0, 4),
round(R_l, 2))` and returns if the key equals the last one. After a bend that
changed the label's size, rerun the collision nudge once, because the nudge ran
against the flat shape.

## Size fitting

Fit sizes on the **flat** path, never on the bent path's bounds. If the bent
bounds fed `getTextScale`, the scale would change with the label's angle, and
labels on one dial would wobble in size.

In practice: `_update_path` keeps building the flat path and the flat
`_textRect`/`_sizeHintRect` from it. `getTextScale` and `scaleSelection` keep
reading `_textRect`. Only the path passed to the item at the end is the bent one,
and that happens in `_bend()` after the scale is chosen. The arc length of the
text along the label's middle line is unchanged by the bend, so the width cap
(`allowedWidth`) stays correct.

`GaugeTickTextGroup._measure_step` (`Gauge.py:3164`) picks the label thinning step
from `label.path().boundingRect()` times `label.scale()`, plus the label's
rotation, to test whether neighbours overlap. A bent path's bounding box is
larger on the curved axis and the rotation term then double counts. Decide
whether to feed it the flat rect in curved mode (simplest: keep the flat bounding
rect on a `_flatRect` attribute, set where the flat path is built, and read that).
Check the overlap result visually on a dense dial.

## The layout signature

Commit `222fe78` made `Text.refresh` return early when `_layoutSignature()` equals
`_builtSignature`. A bent label must not be skipped when only the curve inputs
changed, for example when the gauge radius changes and the label moves outward.
Override `_layoutSignature` in `GaugeTickText`:

```python
def _layoutSignature(self) -> tuple:
	return super()._layoutSignature() + (self.group.curve, round(self.tick.angle, 3), round(hypot(*self.tick.startPoint.toTuple()), 2))
```

Use values read from the tick (`tick.angle`, anchor radius), not from the item's
`pos`, because `_layoutSignature` runs before `setPos` has moved the label. The
gauge centre is `(0, 0)` in surface coordinates, so it needs no entry; if the
code later moves the centre, add it. `_builtSignature` is stored inside
`_update_path`, so `_bend()` keeps its own key (above) for what it depends on
after the nudge.

## Configuration

An opt-in setting on the tick-label group, next to the existing `rotate`
property (`GaugeTickTextGroup.rotation`, key `rotate`, `Gauge.py:3269`). In a
`.levity` file the labels live at `display.major.labels` (and `minor`/`micro`).
Gauge settings nest under `display:`. At the item level they silently go to the
`Realtime` panel instead and appear to do nothing.

Suggested key: `curve`, values `none` (default: today's rigid rotation), `warp`,
`glyphs`.

```yaml
- type: realtime.gauge
  key: environment.humidity.humidity
  display:
    radius: 98%
    major:
      labels:
        curve: warp
```

Add it as a `StateProperty(key='curve', default=..., allowNone=False,
after=refresh)` on `GaugeTickTextGroup`, with an enum decode in the style of
`position_leading` (`Gauge.py:3280`), which decodes with `DisplayPosition[value]`.
Define a small `Enum` (`none`, `warp`, `glyphs`) next to the group. Check that
the property is written out to a saved dashboard only when the user set it, as
`position_leading` does with a `condition`.

`curve` has no effect on a label whose `rotated` is false. Placement of labels
outside the arc is set by the existing `position` key under the same `labels:`
group (`Outside`/`Inside`/`Above`/`Below` map to the tick ends in
`GaugeTickText.position`). Check the accepted spellings against `DisplayPosition`
before you write the fragment. Labels outside the arc are a real case, because
the maintainer may move labels outside, so `R_l` greater than the arc radius has
to work. It does, because nothing in the mapping reads the arc radius.

## Per-glyph mode (opt-in, second)

Same group property, value `glyphs`. Small, and written after `warp` works.

For each character `i` in `text`:

- `adv_i = fm.horizontalAdvance(text[:i])` (this includes kerning with the
  previous characters), `g_i = fm.horizontalAdvance(text[i])`.
- Centre of the glyph, along the flat label: `x'_i = adv_i + g_i/2 − w/2`.
  `α_i = x'_i / R_l`.
- Place the glyph's centre at local `(R_l · sin α_i, s · R_l · (1 − cos α_i))`,
  which is the step 3A formula with `r = R_l` and `y = y_m`.
- Rotate the glyph about its own centre by `s · α_i` (clockwise in screen space),
  so its stem lines up with the radius there.
- Build one path: `addText` for each glyph into a small path centred on the
  band's middle, apply `QTransform().translate(...).rotate(...)` per glyph, and
  `addPath` into the result. No flattening or subdivision is needed, since
  nothing is warped.

For text that must read as one run (`QTextLayout`), shaping and advances may be
used instead of `horizontalAdvance`. That matters only for scripts that need
shaping. Digits and `.`, `-`, `°`, `%` do not.

## Gotchas

- **Vertical placement must use ascent/descent, not `tightBoundingRect`.** Ink
  extents hug the glyphs, so a descender shifts the whole string. That was the
  graph hour-label bug, fixed in "align text by font metrics, not ink extents".
  It is easy to reintroduce when rewriting glyph placement.
- **`Gauge.recenter()` measures `full_gauge_path` at identity**, and that path
  includes tick label shapes via `mapFromItem`. Bent labels change its bounds,
  so recentring needs re-verifying (see the comment in `recenter` about why
  measurement happens at identity).
- **Text on the lower part of a dial needs flipping.** The existing rule is in
  `GaugeTickText.refresh`; reuse it, as described above.
- **The signature skip.** Without the `_layoutSignature` change, a bent label
  never rebuilds when only the curve inputs change.
- **Never put a `QGraphicsItem` change inside `_bend()` that triggers
  `updateTransform`.** `updateTransform` calls `setTransform`, which calls
  `_bend()`. Call `setPath` only.
- **One item's exception aborts the whole dashboard load.** A bug in `_bend()`
  raised from `refresh` costs the whole board, not one label. Run with
  `STATEFUL_DEBUG=1` (see `CLAUDE.md` gotchas) and grep
  `~/Library/Logs/LevityDash/LevityDash.log` for `Dashboard load aborted`.
- **Leave the `_center_transform` TODO alone.**

## Verification: visual, not readable

This cannot be checked by reading code. Render and look at the PNG. Offscreen
renders are not proof that the real app works (`CLAUDE.md`), so finish with a
windowed run.

1. **Write a fragment** `docs/design-references/presets/curved-labels.levity`
   (the folder holds `analog-dial.levity` and others as models; copy their
   shape). Put several named gauges in it, one per case, each with
   `display.major.labels.curve: warp`. Cases:
   - a small dial and a large dial (the same arc, radius `40%` and `98%`);
   - a 240° arc (the default), a 180° arc, and a 90° arc
     (`display.arc.start-angle` / `end-angle`);
   - labels inside the arc (default) and outside it (`position: outside`);
   - ranges whose labels include `4`, `5`, `7` and `0` (for the long strokes);
   - labels in the lower half of the dial, on a 240° arc, to check the flip.
   Also add one gauge with `curve: none` as the control, and one with `glyphs`
   once step 8 is done.
2. **Render one item:**

   ```bash
   QT_QPA_PLATFORM=offscreen PYTHONPATH=src /Users/noblecloud/Code/LevityDash/.venv/bin/python \
     src/LevityDash/devtools/render_widget.py --levity docs/design-references/presets/curved-labels.levity \
     --name gauge --scenario hot-clear-day --scale 3 --out <png>
   ```

   `--name` takes the item's `name:`; `--list` prints the names. `--scenario`
   turns on the Fixture plugin with fixed values (`hot-clear-day`,
   `stormy-day`, `busy-server`).
3. **For repeated looks, use `render_service.py`** (`--scenario hot-clear-day`),
   then `curl 127.0.0.1:8670/render/<name>?scale=3 -o out.png`, and `POST /reload`
   after editing the fragment. It renders in about 85 ms per call against about
   6 s for a cold boot.
4. **Read the PNGs.** A render that printed an error is not evidence. Look at:
   - crossbar of `4`, top of `5` and `7`: smooth arcs, no visible chords, on the
     small dial;
   - no gaps or pinch between characters at any angle;
   - lower-half labels read left to right, tops toward the centre;
   - no label jumps position or flips when you switch `curve: none` to `warp`
     (the end labels, with `rotate-leading`/`rotate-trailing` false, must stay
     as they are);
   - label sizes do not vary with angle;
   - the dial stays centred in its panel (`recenter`).
5. **A real windowed run.** Offscreen is not proof that the dashboard loads
   (`CLAUDE.md`). Run the real app (`poetry run LevityDash`, or
   `LevityDash-run`) with the fragment's gauge in a real dashboard and
   `STATEFUL_DEBUG=1`. Resize the window, change the radius, and watch the log.
   Press `Ctrl+R` to confirm the labels rebuild.
6. **Tests.** Add no new unit tests, except at most one tiny pure test of the
   mapping function (a function from `(θ0, s, R_l, x', y, y_m)` to a point, with
   no Qt). Then run `poetry run pytest -q`.

## Suggested order of work

Branch: `feat/curved-gauge-labels`, from `dev`.

1. **Config and enum.** Add the `curve` property and enum on
   `GaugeTickTextGroup`. Default `none`. Check it loads and saves.
2. **Flip helper.** Move the rotation and flip test out of `refresh` into one
   method that returns the final rotation and the flipped flag. Keep behaviour
   identical. Render before and after and compare.
3. **Pure mapping function** (`s`, `R_l`, `x'`, `y`, `y_m` to a local point), in
   a module with no Qt import, so it can be tested alone. A tiny test is optional.
4. **Flatten and subdivide helper.** Takes a `QPainterPath`, `S`, `r`, `ε` and
   returns polygons with no edge longer than `L`.
5. **`_bend()` for `warp`.** Build the flat path from text and font metrics, call
   the helpers, `setPath`. Wire it from `setPos` and `setTransform`. Add the
   `_layoutSignature` override and the `_bend` key.
6. **Keep fitting on the flat path.** Confirm `_textRect` stays flat. Handle
   `_measure_step` as noted.
7. **Fragment and visual checks.** Write the fragment, render every case, read
   the PNGs, fix, repeat. Small dial first. Check `recenter`. Run the windowed
   run last.
8. **`glyphs` mode.** Add it after `warp` passes review.

Commit format: `type(Scope): summary`, for example `feat(UI.Gauge): ...`.

## Related

- [gauge-display.md](gauge-display.md) - current state of the gauge
- [text-baseline-alignment.md](text-baseline-alignment.md) - why vertical
  placement uses font metrics
- [gauge-end-labels-handoff.md](gauge-end-labels-handoff.md) - end-label
  `rotate-leading` / `rotate-trailing` behaviour

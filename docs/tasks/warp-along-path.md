# Warp text along a free path, with a bend blend

**Status:** not started. Recorded 2026-10-05. Follow-up to the shared `warp:` option
(branch `feat/warped-text`), which bends text along a circle only.

## What

Let `warp:` take a free path instead of a circle, and add one control, `bend`, that
blends rigid glyphs with the full outline warp. Both extend `WarpSpec` in
`src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/curvetext.py`.

The user asked for this in two steps. Their words:

- "is bending along a path the same way possible?"
- "not placing glyphs on a path, I mean actual warping"
- "or I guess a combination of both"

So: warping the outlines is the main mode. Nothing falls back to placing rigid glyphs
on its own. Rigid glyphs are the `bend: 0%` end of the blend, chosen by the user.

## Spec

```yaml
warp:
  path: "M 0 80 C 30 0 70 0 100 80"   # SVG path data in the item's own box, 0-100 = the box
  align: 50%        # where along the path the middle of the text sits
  offset: 0         # moves the text along the normal
  flip: auto        # auto: flip when the path runs right to left
  bend: 100%        # 0% rigid glyphs, 100% full outline warp (default)
```

`mode: warp` and `mode: glyphs` stay as aliases for `bend: 100%` and `bend: 0%`, so
`curve: warp|glyphs` and `warp: {mode: ...}` keep parsing and looking the same.
Accept `px` as well as `%` in path coordinates if the existing size parser makes that cheap.

## Step 1: ellipse, before the free path

The user asked for this order: "if adding elipise support is simple, add that before
path". An ellipse needs the same arc-length core as a free path, but it is smooth and
closed, needs no SVG parser and has no sharp corners. So build the core below, prove it
on the ellipse, and ship that first. Then add the free path on the same core.

```yaml
warp:
  center: dial
  radius: {x: 45%, y: 30%}   # a single value still means a circle
  rotation: 0                # turns the ellipse, in degrees
  angle: 0                   # where the middle of the text sits; degrees clockwise from the top, measured from the centre
```

- Sample the ellipse into the same numpy arc-length table as a path. Map `angle` to
  arc length by finding the point on the ellipse in that direction from the centre.
- The inner side of a bend folds where the ellipse is tightest: at the ends of the
  long axis, where the radius of curvature is `b²/a`. Apply the same fold rule as the
  path edge cases: shrink the text or log a warning.
- Keep the circle's closed-form path when `x == y` and `rotation` is 0. Check that its
  output is unchanged, using the same pixel-identical check that `feat/warped-text` used
  on `curved-labels.levity`.
- Verification: render one preset that shows text on a wide ellipse, on a tall
  ellipse, on a rotated ellipse, and flipped along the bottom of an ellipse. Include a
  close-up crop where the bend is tightest.
- The `bend` blend can wait for step 2, or come in step 1 if it costs little. Report
  which you did.
- Later, the meter refactor (`docs/tasks/meter-and-bar.md`) can reuse this ellipse
  sampling for an elliptical gauge track.

## Core: a curve sampled by arc length

Give the helper one curve abstraction that returns a position `P(s)` and a unit normal
`N(s)` by arc length `s`. The circle becomes one implementation (closed form, and keep
it as the fast path), the path another.

- Every outline point `(x, y)` (x along the text, y off the baseline) maps to
  `P(s0 + x) + (y - y_mid) * N(s0 + x)`. `warp_point` in `curvetext.py` is this formula
  for a circle.
- For a path, parse the SVG data (M L H V C S Q T Z, absolute and relative; reject arcs
  with a clear error), flatten it once into an arc-length table (points and tangents) in
  numpy, and interpolate with `np.interp`. Never call `QPainterPath.percentAtLength`
  per point: it is far too slow. Cache the table per path string and box size.
- `N` is the tangent turned a quarter turn, `(-Ty, Tx)` in y-down coordinates.
- Subdivide outline edges with the existing `_subdivide`, using a max length taken from
  the path's tightest bend, so straight glyph edges come out as smooth curves.

## Blend: `bend`

```
rigid(p)  = P(s_c) + R(theta_c) . (p - c_glyph)      frame at the glyph's centre arc length s_c
warped(p) = P(s) + (y - y_mid) * N(s)
result(p) = lerp(rigid(p), warped(p), bend)
```

This needs each outline point grouped by glyph. `QPainterPath.addText` returns one
subpath per contour, not per glyph, so lay out glyph by glyph: add each character as its
own path at its advance offset (what `glyph_ring_text` already does), or use a
`QTextLayout` glyph run. Keep `c_glyph` (the glyph's box centre) and its advance to get `s_c`.
`bend: 0%` must match today's `mode: glyphs`; `bend: 100%` must match today's `mode: warp`.

## Edge cases to handle and report

- **Fold.** Where the bend is tighter than the text height, the inner side of the glyphs
  folds over itself. Clamp the offset on the inner side to about 0.9 of the local radius
  of curvature (squeezes the glyph bottoms instead of folding) and log a warning once.
- **Sharp corners.** Round them with a small fillet when sampling (a quadratic Bezier
  cut back by min(fillet, half of each adjacent segment)). Keep warping the outlines
  through the corner. Never switch to glyph placement there. A fillet of about half the
  text height is a good start.
- **Overflow.** Text longer than the path: shrink to fit by the same rule as the circle
  (`arcFit`: width at the final scale must not exceed the path length). Text that runs past
  an end because of `align` continues along the end tangent in a straight line.
- **Direction.** `flip: auto` reverses the curve when the tangent at `align` points left.

## Verification

Extend `docs/design-references/presets/warped-text.levity` and its PNG:

- the same word on the same curve at `bend` 0%, 50% and 100%, side by side;
- one wavy path and one S-curve, both with visibly bent letterforms (not rotated rigid letters);
- one close-up crop of a path example, saved next to the PNG, that shows the strokes
  stretch on the outer side of a bend and squeeze on the inner side.

Also: a before/after render of `gauge-showcase.levity` with no visible change; timing for
the circle fast path against the general path on a live-updating value label; Gauge Studio
export round trip; `pytest tests -q -p no:cacheprovider`.

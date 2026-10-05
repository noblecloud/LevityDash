# Meter survey: angle and radius dependence in `Gauge.py`

**Status: phase 1 of [`meter-and-bar.md`](meter-and-bar.md) — read-only. No source file was changed.**

- Branch: `refactor/meter`, cut from `feat/value-sources` at `099ce84`, then merged up to
  `fd873b5` (the studio-sliders merge) before this document was committed; the revision this
  survey describes is therefore `fd873b5`.
- Worktree: `.claude/worktrees/blackfish-meter` (the main checkout was not touched).
- Phase-2 gate status at the time of writing: `feat/warped-text` merged (`f706e33`) and
  `fix/studio-sliders-contrast` merged (`fd873b5`), so phase 2 is unblocked.
  `feat/studio-snapping` does not exist yet, so phase 4 is still gated.
- Test baseline at `fd873b5`: `env -u PYTHONPATH .venv/bin/python -m pytest tests -q
  -p no:cacheprovider` → **498 passed, 1 skipped** in 39s. The brief's 492 predates the
  `feat/warped-text` merge; that merge added `tests/ui/test_warp_spec.py`, which collects
  exactly 6 tests, so 492 + 6 = 498 is fully accounted for. Phase 2 should treat 498 + 1 as
  its gate, not 492 + 1.
- Scope of this document: `src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Gauge.py`,
  6,299 lines.

## How the numbers below were measured

Comments were stripped, then each line was matched against a pattern set. Counts are line
counts, not occurrence counts, and a line may match several patterns.

- `angle|radius|radii` (case-insensitive substring, so `startAngle`, `radius_px` and
  `fullAngle` all count): **304 lines**.
- `cos`, `sin`, `atan2`, `hypot`, `radians`, `pi`: 16 lines.
- `arc`: 101 lines. `sweep`: 2 lines.
- Union of all of the above: 391 lines.

The brief says "roughly 316 lines refer to angle or radius." 304 by this measurement
confirms that figure. `angle|radius` per class: `Gauge` 84, `Graduations` 52, `Needle` 38,
`GaugeArc` 29, `GaugeValueLabel` 16, `GaugeTickText` 15, `GaugeZones` 15, `GaugeFill` 14,
`Tick` 12, `Arrow` 10, `GaugeCaption` 7, `GaugeMarker` 5, `GaugeTickTextGroup` 2,
`SubTick` 2, module-level 1, `GaugeLabel` 1, `GaugeUnit` 1.

Two class-level facts shape everything below. First, every value-to-position conversion in
the file goes through one of **three** similarly named methods: `Gauge.value_to_angle`
(two definitions, see "Dead and shadowed code"), `Gauge.value_to_angle_degrees` and
`Gauge.angle_degrees_to_value`. Second, `gauge.radius` is the **universal relative base**
for sizes that have nothing to do with circles: tick length, tick width fallback, needle
length/width/offset/tail/head/hub, marker sizes, halo width, value-label glyph height,
caption text height and offsets, and the tick font's point size. That is the single largest
coupling in the file and the main risk (see Risks, item 1).

---

## 1. Every place that depends on angle or radius, by class

### Module level (1 line)

- `shortestDelta(current, target, span=360.0)` — L93-99. The signed turn the short way
  across the wrap join, in degrees.

### `GaugeItem` L102-140, `StatefulGaugeItem` L141-147

No angle or radius. Both do assume the owning item is a `Gauge`: `__extract_gauge`
(L110-118) searches the constructor arguments for a `Gauge` instance and raises
`ValueError(f'No gauge provided for {self.__class__.__name__}')` otherwise. This is the
only thing in the file that hard-codes "my owner is a Gauge" rather than "my owner is a
meter of some shape."

### `Graduations` L148-1061 (52 lines)

Tick *values* are already shape-free: `step_count` (L857-862), `value_at` (L864-866),
`tick_values` (L868-888) and `compatible_intervals` (L807-855) work in value units only.
The angle enters wherever a size in pixels has to become a size in value units, and
wherever the width of the sweep has to be divided up.

- L304-313, L356-371 `length_px` — major tick length is a share of `gauge.radius`
  (L360); minor and micro are shares of the parent tick's `length_px` (L362, L364).
- L406-421 `width_px` — major width is a share of `gauge.baseWidth` (L410), minor/micro of
  the parent's width.
- L563-593 `usr_interval_deg` — turns a user interval, percent or length into an `Angle`.
  Uses `gauge_angle_range = self.gauge.endAngle - self.gauge.startAngle` (L565) and divides
  by `self.gauge.radius` (L585, L589).
- L601-606 `interval_degree` — `interval / rounded_range * gauge_angle_range`.
- L623-652 `min_interval` — same degree conversion at L634, L644 and L648, each dividing by
  `self.gauge.radius`; the `max(...)` on L645, L649 and L651 floors the result at
  `self._min_interval`.
- L654-681 `max_interval` — the same again at L663, L673 and L677.
- L683-695 `_min_interval` — `min_spacing_deg` and `gauge_angle_range` decide the smallest
  interval that keeps two ticks a tick-width apart.
- L697-720 `min_spacing` — a `StateProperty` whose docstring says "the minimum arc length
  spacing between graduations"; floats and percentages are a fraction of the tick width.
- L722-740 `spacing_deg` — `radius = self.gauge.radius - self.length_px` (L734), then
  `value_to_angle_degrees(usr_spacing, radius_px=radius, relative_px=self.width_px)`
  (L736-740).
- L742-759 `min_spacing_deg` — computes `arc_length_px = radius * fullAngle / 180 * pi`
  (L755) and returns a fraction of `fullAngle` (L759).
- L761-763 `min_spacing_val` — returns `None`; a stub.
- L773-780 `angle_range` — `gauge.fullAngle` when there is no parent, otherwise the parent's
  `angle_range / count`. This is sweep arithmetic, not geometry.
- L782-791 `min_interval_deg` — returns `Unset`; the `getattr` calls have no `else`, so every
  branch falls through. A stub.
- L803-805 `startAngle` — `self.gauge.startAngle - 90`. The `- 90` is Tick's own correction
  for Qt's arc convention.
- L890-891 `interval_to_deg` — `gauge.value_to_angle_degrees(interval, gauge.radius)`.
- L893-925 `determine_interval` — minor and micro pass
  `gauge_max_angle_deg = parent.angle_range / parent.count` (L913, L922).
- L927-1048 `_determine_interval` — takes `gauge_max_angle_deg` and uses it at L980 to turn
  a configured spacing into an interval. L945 is the default for that parameter:
  `gauge_max_angle_deg = gauge.startAngle if gauge_max_angle_deg is None else
  gauge_max_angle_deg`. `startAngle` is an *endpoint* of the sweep, not its width, so this
  default looks wrong. It is only reachable for a major graduation with `spacing` configured
  (L979), i.e. rare, and it is not this task's job to fix — recorded so the refactor does not
  quietly preserve or quietly change it.

### `GaugeArc` L1098-1312 (29 lines)

This class is the arc. Nothing in it is reusable as-is for a straight track, but every
concept in it has a track equivalent.

- L1125-1127 `center` — `self.gauge.rect().center()`.
- L1133-1137 `centered_gauge_rect` — the gauge rectangle moved to (0, 0); the rect that
  `arcTo` and `arcMoveTo` are called with everywhere else in the file.
- L1139-1181 `makeShape` — the stroked outline. Builds the inner arc from
  `safe_radius` (L1141), the outer from `exterior_safe_radius` (L1142), closes the end with
  `radialPoint(QPointF(0, 0), width, self.endAngle - 90)` (L1160), then runs the outer arc
  backwards (L1164).
- L1183-1192 `draw` — `arcMoveTo(rect, -startAngle + 90)` and
  `arcTo(rect, -startAngle + 90, -fullAngle)` (L1187-1188), then publishes the path's centre
  back to the gauge with `update_center_offset` (L1190).
- L1200-1216 `updateAppearance` — pen width from `weight_px`, and the same `arcTo` shape.
- L1258-1260 `weight_px` — `size_px(self.weight, self.gauge.radius)`.
- L1262-1276 `start-angle` and `end-angle` `StateProperty` pairs; L1278-1300 the cap.
- L1302-1304 `fullAngle = endAngle - startAngle`; L1306-1309 `inverted`.

The sign dance is worth naming precisely: `GaugeArc` draws with `-angle + 90`, while
`Tick.draw` (L1434) places a tick at `radians(self.angle)` with the tick's own angle being
`gauge.startAngle - 90 + index * interval_degree` (L805, L1391). The two conventions
cancel, and both live inside geometry code that the refactor will move.

### `Tick` L1313-1486 (12 lines), `SubTick` L1487-1503 (2)

- L1389-1391 `Tick.angle` — `self.properties.startAngle + self._index *
  float(self.properties.interval_degree)`.
- L1424-1426 `Tick.radius` — `self.gauge.radius`.
- L1432-1471 `Tick.draw` — the whole tick is `radians(angle)` into `cos`/`sin` (L1434-1435),
  a point on the circle at `radius` (L1442-1443), and a two-point line whose second point
  steps along the same radial direction by `length_px` (L1445-1463). The three cases are
  `Below|Inside` (step inward), `Above|Outside` (step outward) and `Center` (split either
  side of the rim).
- L1497-1500 `SubTick.angle` — `superTick.angle + index * properties.spacing`.
- `TickSurface` L1504-1611 has no angle or radius of its own. Its `pen` (L1600-1605) takes
  width from `_properties.width_px`, and `spacing` (L1582-1584) reads the raw `_spacing`
  state value, which nothing on the item consumes.

### `Needle` L1612-2387 (38 lines), `Arrow` L2388-2512 (10)

Every needle style is drawn in local coordinates with "up" = -Y, then the *whole item* is
rotated by the value. The shape code and the placement code are already separate, which is
what makes this survivable.

- L2019-2024 `_radial` — a relative size in pixels, defaulting to a share of `gauge.radius`.
- L2026-2027 `_pivotY` — the pivot's local y, `offset_px`.
- Sizes, each falling back to a share of `gauge.radius`: `length_px` L1779, `width_px`
  L1762, `offset_px` L1822, `tail` L1851, `head` L1885, `hub` L1920.
- L2029-2042 `_hubPath` and L2044-2056 `_extras` — hub disc at `(0, _pivotY())`, halo ring
  at `(0, offset_px - gauge.radius)` (L2054).
- Shapes that sit **at the rim** and therefore encode both the radius and the outward
  direction: `_edge_circle` L2269-2292 (`pos = (0, offset_px - gauge.radius)`),
  `_edge_triangle` L2294-2320, `_edge_marker` L2322-2355, `_edge_diamond` L2357-2384,
  `_style_dot` L2160-2168, `_style_notch` L2170-2176.
- Shapes drawn **from the pivot**: `_default` L2233-2267, `_style_tapered` L2087-2103,
  `_style_line` L2105-2118. These are exactly the members of `_PIVOT_STYLES` (L1643).
- `_style_arrow` L2120-2161 — `rim = off - radius` (L2134), and the tail crosses to the far
  rim with `far = radius - off` (L2154).
- L2184-2226 `_applyAngle`, `_onAnimated`, `_stopAnimation` — the value becomes a
  `setRotation(target)` (L2195) or, with `animate:` set, a `QVariantAnimation` from the
  shown angle to the target (L2206-2214). A wrapping range turns the short way across the
  join using `shortestDelta(shown, target, gauge.fullAngle)` (L2202-2203).
- L1694-1708 `refresh` — `_applyAngle(gauge.value_to_angle(gauge.value))`, then
  `setPos(gauge.center)` and reapply `gauge._recenterTransform` (L1701-1706).
- `Arrow` L2388-2512 — a `Needle` subclass with its own `draw` that strokes a ring plus an
  arrowhead and a centre disc. Nothing instantiates it (see "Dead and shadowed code"). Its
  `paint` (L2390-2393) draws a red rectangle around its own bounding rect, left in.

### `GaugeMarker` L2513-2660 (5 lines)

- L2617-2640 `_markerAngle` — a clock hand's fraction is turned back into a value
  (L2623), then `gauge.value_to_angle(value)` (L2635). Failures warn once and return `None`.
- L2642-2658 `refresh` — `_applyAngle(angle)`, `setPos(gauge.center)`, recentre transform.

The clock machinery beside it is shape-free: `CLOCK_HANDS` L2481, `clockTurn` L2484-2498
(a pure fraction of one turn), `parseClockTime` L2501-2510, and the timer at L2596-2607.

### `GaugeZones` L2661-2809 (15 lines)

- L2719-2724 `_span` — a zone's `from`/`to` become dial angles; a missing end is
  `gauge.startAngle` or `gauge.endAngle`.
- L2726-2736 `colorAtAngle`, L2738-2743 `colorAt`, L2745-2752 `_angle` — all value or
  angle lookups funnel through `gauge.value_to_angle`.
- L2754-2798 `refresh` — `rect = gauge.arc.centered_gauge_rect` (L2764), `arcWeight =
  gauge.arc.weight_px` (L2765), one `arcMoveTo`/`arcTo` stroke per zone (L2774-2779), and
  for each `mark` cutoff a line across the arc built from
  `radialPoint(QPointF(0, 0), radius ± reach, angle)` (L2781-2790).

### `GaugeFill` L2821-3034 (14 lines)

- L2937-2954 `_angles` — both ends through `gauge.value_to_angle`, refusing non-finite
  results with a warning.
- L2956-3019 `refresh` — the fill's ends are sorted (L2965), and either one `arcTo` span
  (L2996-3004) or `segments` strokes with a `gap` between them (L2974-2995). The gap is
  converted from pixels to degrees at L2980-2981 (`gapPx / radius * 180 / pi`), and each
  segment is tested against the fill span by its *midpoint angle* (L2987).
- L3021-3024 `_valueAtAngle` — the inverse map, `angle -> value`. It has no callers.

### `GaugeCaption` L3035-3199 (7 lines)

- L3129-3152 `_placeWarped` — resolves a `WarpSpec` against the card rect, then
  `arcFit(...)` (L3137) and `warp_path(...)` (L3140) from `curvetext`, and rotates the text
  by `place.rotation` (L3144).
- L3176-3185 `refresh` — the *plain* path is already pivot-relative and shape-free: it
  takes `gauge._valueAnchor()` (L3176), offsets by `gap` and `self._offset` scaled by
  `gauge.radius * 2` (L3177, L3184-3185).

### `GaugeLabel` L3235-3289 (1 line), `GaugeValueLabel` L3290-3766 (16), `GaugeUnit` L3767-3970 (1)

- L3281-3287 `GaugeLabel.offsetPx` — `offset * gauge.radius * 2`.
- L3375-3389 `limitRect` — the `Left`/`Right` case uses `_sideValueRect`; every other case
  uses `gauge.arc.sceneBoundingRect()`.
- L3391-3426 `getTextPosition` — reads `arc.startAngle` and `arc.endAngle` into
  `min_angle`/`max_angle` (L3396), and `angle_spread` (L3398). `Inline` places the label at
  `arc_center - (arc_center - gauge_center) * (angle_spread / 360)` (L3410-3412). `Top` uses
  `gauge.safe_radius` (L3416). `Bottom` measures from `gauge.rect().bottom()` (L3424).
- L3440-3456 `getTextScale` side-strip branch — caps glyph height against
  `gauge.radius * 2` (L3455).
- L3490-3582 `getTextScale` main branch — `_unit_reserve`, a needle-hub floor built from
  `needle.offset_px`, `needle.width_px` and `gauge.radius` (L3513-3515), and a bisecting
  fit against `gauge._gauge_path()`; the `size` cap at L3580 is again a share of
  `gauge.radius * 2`.
- L3719-3759 `alignment_auto` — `min_angle`/`max_angle` again (L3741), `angle_spread`
  (L3743), and a midpoint angle `angle_mid = ((min + max) / 2 + 90) % 360` (L3747) used to
  pick Right/Left and Top/Bottom alignment from four angular bands (L3749-3757).
- L3761-3764 `position_auto` — `Inline` when the needle is a needle and
  `arc.fullAngle > 180`, else `Center`.
- `GaugeUnit` L3885-3886 `limitRect` and L3916 `height_relative_to`; its placement
  (L3812-3839) is relative to the value label's box, not to the dial.

### `GaugeTickText` L3971-4294 (15 lines)

The most arc-entangled label class, because tick labels rotate, bend and are nudged
radially.

- L4021-4031 `_labelRotation` — `rotation = self.tick.angle + 90 if self.rotated else 0`
  (L4025), flipped half a turn when it would read upside down (L4028-4030).
- L4033-4035 `_layoutSignature` — appends `round(self.tick.angle, 3)` and
  `round(hypot(*self.tick.startPoint.toTuple()), 2)`.
- L4037-4070 `_bend` — `radius = hypot(self.pos().x(), self.pos().y())` (L4049), then
  `warp_path(self.text, font, scale, radius, side, mode, ...)` (L4062).
- L4131-4184 `setPos` — the nudge direction is a `radialPoint` at the tick's angle
  (L4142-4152); the collision loop pushes the label outward one pixel at a time until it
  clears `self.gauge.arc` and `self.tick` (L4176-4184), bounded by the label's own diagonal
  (L4156).
- L4192-4200 `_placementKey` — the memo key contains `tick.angle`, `tick.startPoint`,
  `arc.path()`, `arc.pen().width()` and `arc.sceneTransform()`.
- L4240-4250 `allowedWidth` — `radius * fullAngle / 180 * pi` where `radius` is
  `safe_radius` or `exterior_safe_radius` depending on which side the group sits.

### `GaugeTickTextGroup` L4295-4830 (2 lines)

- L4323-4325 `text_size_relative_to` — `self.gauge.radius`.
- L4541-4590 `_measure_step` and its nested `extent` — label-overlap detection in the
  parent's coordinates. It uses each label's rotation (`atan2`, `radians`, `cos`, `sin`,
  L4569-4570) and its `_flatRect`, and it tests every *pair* of labels, not just
  neighbours, because pushed-in labels can meet across the dial (L4586-4588).

### `Gauge` L4831-6300 (84 lines)

`GaugeRange` (L4840-4993) is value and range arithmetic with no angle or radius at all, and
moves unchanged.

The rest, in source order:

- L5127-5141 `radius` StateProperty — a `Size.Height`, resolved against `radius_max`.
- L5143-5153 `arc`, L5155-5165 `needle`, L5167-5201 `fill`, L5212-5312 `caption`,
  `subLabel`, `_syncCaptions`, `zones`, `markers`, `majorDivisions`/`minorDivisions`/
  `microDivisions`, `valueLabel`, `unitLabel`.
- L5540-5546 `type` and `displayType` — both `DisplayType.Gauge`.
- L5552-5570 `startAngle`, `leading_angle`, `endAngle`, `trailing_angle` — delegations to
  the arc, plus the `% 360` normalisations.
- L5572-5588 `convert_gradient` / `map_gradient_to` — a **`QConicalGradient`** built with
  `start_angle=self.startAngle` and `stop_angle=self.endAngle` (L5578-5583).
- L5616-5702 `recenter` — resets the transform on needle, arc, zones, markers, fills and
  the three tick surfaces (L5629-5634), measures `full_gauge_path` at identity, and applies
  a translate `t` (L5644-5673). The comment at L5620-5628 documents a past bug where
  measuring with a previous centring still applied produced a near-zero offset and snapped
  the ticks back. `anchor` short-circuits the whole computation (L5668-5670).
- L5704-5733 `_syncUnitUnderValue` — hangs a `float-under` unit beneath the value's final
  glyphs.
- L5743-5768 `refresh`, L5770-5771 `_update_shape` (clears two `cached_property`s).
- L5805-5807 `value_to_angle` — **shadowed**, see below.
- L5809-5822 `valueClass`, L5824-5834 `updateSlot` / `animateValue`.
- L5864-5914 `_ANCHORS`, `anchor`, `inset`, `insetPx` — pins the pivot (the arc centre) to
  a corner of the box, and scales `radius` against the short side when it is set.
- L5916-5945 `center_offset` — the path centre the arc reported at L1190.
- L5947-5986 `_valueSide`, `_sideStripWidth`, `_dialRect`, `_sideValueRect` — the box
  machinery that carves the panel into a dial square and a value strip.
- L5988-6013 `center` — the corner case when `anchor` is set (L5991-5997), otherwise
  alignment multipliers over `boundingRect`, minus `_center_offset`, clamped to
  `marginRect`.
- L6019-6021 `baseWidth` — `sqrt(height² + width²) * INVERSE_GOLDEN_RATIO * 0.01`.
- L6023-6037 `radius_max` and two `radius` properties (one dead, see below).
- L6039-6043 `gaugeRect` — a `radius * 2` square centred in the panel.
- L6045-6047 `fullAngle`, L6053-6057 `tickFont` — point size `max(radius * .1, 18)`.
- L6081-6084 `arc_length`, L6086-6094 `value_to_angle` (the live one, with the `wrap`
  branch at L6090-6092 and the `sorted((s, angle, e))[1]` clamp at L6094).
- L6096-6129 `value_to_angle_degrees`, L6131-6155 `angle_degrees_to_value` — the size↔angle
  and angle↔value converters, all of them through `radius`, `fullAngle` and `pi`.
- L6157-6158 `interval_to_count_float`.
- L6160-6178 `safe_radius`, L6179-6196 `exterior_safe_radius`, L6198-6218
  `value_safe_radius` — how far the ticks and their labels eat into the dial, as a trim on
  `radius`.
- L6220-6222 `safe_area`, L6247-6286 `_gauge_path`, L6288-6296 `full_gauge_path`,
  L6298-6299 `full_gauge_rect`.

---

## 2. What each place becomes under `Scale` and `Track`

The mapping below is the whole argument for the split. `Scale` replaces every
value↔fraction conversion; `Track` replaces every fraction↔point/angle/px conversion.
Nothing else in the file needs an angle or a radius.

| Present code | Under `Scale` / `Track` |
| --- | --- |
| `Gauge.value_to_angle` L6086, L5805; `GaugeMarker._markerAngle` L2635; `GaugeZones._angle` L2752; `GaugeFill._angles` L2944; `Needle.refresh` L1701 | `Scale.toT(value) -> t` in 0..1. The `sorted((s, angle, e))[1]` clamp becomes a clamp on `t`; the `wrap` branch becomes `t % 1` (the `wrap` case at L6090-6092 is already exactly that arithmetic, expressed in degrees). |
| `Gauge.value_to_angle_degrees` L6096, `angle_degrees_to_value` L6131 | `Scale.tOfPx(px)` / `Scale.pxOfT(t)`, with the reference length supplied by the track rather than by `radius` and `fullAngle`. |
| `shortestDelta` L93 | `Scale.shortestDelta(t_from, t_to)` — span is always 1 (`wrap` only). Used by `Needle._applyAngle` L2202-2203. |
| `Graduations.usr_interval_deg` L563, `interval_degree` L601, `min_interval` L623, `max_interval` L654, `_min_interval` L683, `min_spacing_deg` L742, `spacing_deg` L722, `interval_to_deg` L890 | All become `Scale.spanOf(size_or_interval)` and `Scale.intervalOf(span)`. The arc-length step `radius * fullAngle / 180 * pi` (L755, L6104, L6140) becomes `Track.lengthPx`. |
| `Graduations.angle_range` L773, `startAngle` L803 | `Scale.spanOfTick(index)`; `Track.pointAt(t)` replaces `startAngle + index * interval_degree`, and the `- 90` disappears into `ArcTrack`'s Qt convention. |
| `Graduations.length_px` L356 and `width_px` L406 | First rung (L360, L410) resolves against `track.thickness` rather than `gauge.radius`/`gauge.baseWidth`; second rung (L362, L364, L412, L414) is already relative to the parent tick and is unchanged. |
| `Tick.angle` L1389, `SubTick.angle` L1497, `Tick.radius` L1424, `Tick.draw` L1432-1471 | `t = scale.toT(value)`; `p0 = track.pointAt(t)`, `n = track.normalAt(t)`, `p1 = p0 + n * ±length_px`, draw the segment. The three `position` cases (inward / outward / centred) survive verbatim; the trig does not. |
| `GaugeArc` entirely: `makeShape` L1139-1181, `draw` L1183-1192, `weight_px` L1258-1260 | The *track* becomes `ArcTrack(center, radius, start_angle, end_angle)` with `pointAt`, `tangentAt`, `normalAt`, `subPath(t0, t1)` and `lengthPx`. `GaugeArc` remains the scene item that strokes `ArcTrack.subPath(0, 1)`. The `-angle + 90` sign convention and the `inverted` property (L1306-1309) move inside `ArcTrack`. `weight_px` becomes the track's thickness. |
| `Needle` sizes L1779, L1762, L1822, L1851, L1885, L1920, L2019-2024 | Relative sizes resolve against `track.thickness` (cross-axis) and `track.lengthPx` (along-axis), not against a radius. This is the meaning change flagged in Risks item 1. |
| `Needle` rim-anchored shapes L2269-2384, `_style_dot` L2160-2168, `_style_notch` L2170-2176, `_style_arrow` L2120-2161 | Local-coordinate shapes are unchanged. Placement becomes `track.pointAt(t) + track.normalAt(t) * offset_px`, and orientation becomes `track.angleAt(t)`. |
| `Needle._applyAngle` L2184-2199, animation L2200-2226 | Keep the animation object; interpolate `t` instead of degrees. Rotation is `track.angleAt(t)` for an arc and a pure translation along the track for a line — the same code path, a different placement function. |
| `GaugeZones._span` L2719-2724, `colorAtAngle` L2726, `refresh` L2754-2798 | Zones become `track.subPath(t0, t1)` strokes; a `mark` cutoff becomes a segment across the track at `pointAt(t) ± normal * reach` instead of a `radialPoint` line. Colour lookup becomes `colorAt(t)`. |
| `GaugeFill._angles` L2937, `refresh` L2956-3019 | `track.subPath(t0, t1)`; `segments`/`gap` move into `t` space (`gapPx / track.lengthPx` instead of `gapPx / radius * 180 / pi`, L2980-2981); the per-segment midpoint test (L2987) stays. |
| `GaugeTickText._labelRotation` L4021, `_bend` L4037, `setPos` L4131, `_placementKey` L4192, `allowedWidth` L4240 | Placement becomes `pointAt(t) + normalAt(t) * offset_px`; rotation and `_bend` stay in the arc subclass. `allowedWidth` uses the local spacing between adjacent `t`s times `track.lengthPx`. |
| `GaugeTickTextGroup._measure_step` L4541 | Unchanged. It is a rotated-box overlap test; with a straight track every rotation is 0 and it degenerates to axis-aligned boxes. |
| `GaugeValueLabel.getTextPosition` L3391, `alignment_auto` L3719, `position_auto` L3761 | The fitting machinery (`getTextScale`) is unchanged. The *positions* gain track-relative meanings: `Inline` is "inside the fill", `Top`/`Bottom` become the track's normal sides, and `position_auto`'s `fullAngle > 180` test becomes a per-track default. |
| `Gauge.convert_gradient` L5572-5588 | A fork, not a rename. A `QConicalGradient` swept from `startAngle` to `endAngle` is arc geometry; a bar needs a `QLinearGradient` along the track. `Meter` should own "map a `Gradient` to a brush for this shape", with the arc and line implementations differing. |
| `Gauge.safe_radius` L6160, `exterior_safe_radius` L6179, `value_safe_radius` L6198 | The same three margins expressed against `track.thickness` (how far ticks and labels eat across the track) rather than against a radius. |
| `Gauge.gaugeRect` L6039, `radius_max` L6023, `radius` L6035, `baseWidth` L6019 | `Meter.trackRect()` (the box the track lives in) plus `Meter.crossSize` (the track's cross-axis extent, `radius` for a gauge). `radius` stays as a gauge-only alias so `radius:` YAML keeps working. |
| `Gauge._dialRect` L5964, `_sideStripWidth` L5955, `_sideValueRect` L5977 | Unchanged in spirit: these partition the panel, and the partition is a meter-level concern already. |

---

## 3. Code that only makes sense on an arc, and stays in `Gauge`

- **The Qt arc convention.** `GaugeArc.makeShape` L1139-1181 and `draw` L1183-1192, plus
  `Tick.angle`'s `- 90` (L805) and every `radialPoint` call. Under the split this is
  `ArcTrack`'s private business; no other class should carry it.
- **Clock hands** as *drawn*. `clockTurn` L2484-2498 and `parseClockTime` L2501-2510 are
  pure fractions and move to the shape-free side (they are tested directly by
  `tests/ui/test_gauge_helpers.py`). The *hand* — a needle rotated about the pivot by
  `clockTurn(...) * fullAngle` — is arc presentation. Expose the fraction from `Meter`;
  keep the rotation in `Gauge`.
- **Corner placement**: `_ANCHORS` L5864-5868, `anchor` L5872-5891, `inset` L5893-5908,
  `insetPx` L5910-5914, the `center` corner branch L5991-5997, and the `anchor` short
  circuit in `recenter` L5668-5670. On a bar, `anchor`/`inset` would place the track's
  rectangle; there is no pivot to pin.
- **Warped text**: `GaugeTickText._bend` L4037-4070, `GaugeCaption._placeWarped`
  L3129-3152, and the shared helpers in `Displays/curvetext.py` (`WarpSpec`, `WarpPlacement`,
  `warp_point`, `bend_text`, `glyph_ring_text`, `warp_path`, `arcFit` — this file is where
  the merged `feat/warped-text` work now lives).
- **Conical gradients**: `Gauge.convert_gradient` / `map_gradient_to` L5572-5588.
- **`Inline` value placement** L3410-3412 and `position_auto`'s `fullAngle > 180` test
  L3761-3764.
- **`Arrow`** L2388-2512 — a gauge-only decorative needle, and unused (see below).

---

## 4. Risks

1. **`radius` is overloaded as the universal size base.** 84 lines in `Gauge` and 38 in
   `Needle` resolve a user's relative size against it, for quantities that are not
   radial — tick *width*, label glyph height, marker width, caption offsets. On a bar the
   natural base is the track's cross-axis size. If `Meter` keeps exposing `radius` and
   `LineTrack` invents a fake one, every `size_px(x, meter.radius)` call silently changes
   meaning. Proposal: `Meter.crossSize`, with `Gauge.crossSize == self.radius` (bit-identical
   today) and `Bar.crossSize == track thickness`. This is the most likely source of
   pixel diffs and the first thing to pin down in phase 2.
2. **`value_to_angle` is two functions with different clamping.** L5805 (dead) clamps with
   `sorted(...)` only; L6086 (live) adds the `wrap` branch. Consolidating onto `Scale` must
   preserve the live behaviour, including the clamp at L6094 for out-of-range values on a
   non-wrapping dial. Worth a preset that drives an out-of-range value; none of the current
   22 obviously does (see Risks item 7).
3. **`recenter` is order-dependent and self-referential.** L5616-5702 measures a path built
   from items whose transforms it has just reset, and its own comment (L5620-5628) records a
   past bug of exactly that kind. Moving `refresh`/`recenter` into `Meter` risks
   re-introducing the "correct for a split second, then jump" failure. Keep `recenter` in
   `Meter` but keep the reset-then-measure-then-apply order literal, and cover it with the
   pixel diff rather than with unit tests.
4. **`GaugeTickText.setPos` nudges one pixel at a time.** L4131-4184 loops until the label
   clears `self.gauge.arc` and `self.tick`, bounded by the label's own diagonal (L4156),
   reading `arc.path()`, `arc.pen().width()` and the tick's path. A track swap changes the
   loop's termination condition and can shift labels by a pixel. This is precisely what the
   diff harness exists to catch; do not "fix" a one-pixel diff by loosening the threshold.
5. **Animation interpolates degrees.** `_applyAngle` L2184-2199 and `_onAnimated` L2216-2221
   drive `setRotation`. A bar translates rather than rotates, so the placement function has to
   be part of the same abstraction while the interpolation variable becomes `t`. Choose this
   deliberately in phase 2, not by accident when the first bar animates.
6. **The diff harness must freeze the clock and settle the animation.** The brief's known
   starting point — 48k pixels different between two unchanged showcase renders — is
   consistent with the Mock plugin driving live values, but there is a second source:
   `docs/design-references/presets/wrap-compass.levity:20` sets `animate: 800ms`, and three
   presets use clock markers (`clock.levity`, `corner-gauges.levity`, `warped-text.levity`).
   `render_dashboard.py` already accepts `--levity`, `--seed`, `--scenario`, `--size` and
   `--settle`, so `render_diff.py` mainly needs to (a) always pass `--scenario` so the
   Fixture plugin supplies fixed values instead of Mock, and (b) apply the same four clock
   patches as `tests/conftest.py`'s `frozen_time` fixture — `shared.now`, `shared.strftime`,
   `datetime.now`, and the Moon module's `datetime.now(tz)`, which reads the module directly
   and is patched separately. Settle time alone will not freeze a clock.
7. **Preset count.** The brief says 21 preset files; `docs/design-references/presets/`
   holds **22** `.levity` files (plus a handful of `.png` renders that must not be counted).
   The harness should enumerate the directory, never a hard-coded 21.
8. **`DisplayType` is a closed enum and `Realtime` branches on it.** `DisplayType` lives at
   `lib/ui/frontends/PySide/utils.py:636` with `Gauge = 'gauge'`, and `Realtime.py` branches
   on `DisplayType.Gauge` at L312, L542 and L592, and registers
   `class RealtimeGauge(Realtime, tag='realtime.gauge')` at L751 with the display created in
   `display.decode` (L766). `Bar` needs a tag class, almost certainly a `DisplayType.Bar`,
   and a read of those three branches before the second display type exists.
9. **There is no `size_px` reference that survives both shapes unchanged.** `baseWidth`
   (L6019-6021) is a panel-diagonal share, `radius` is a panel-short-side share, and
   `radius * 2` is the dial's diameter. Three different bases are in use for "how big is a
   small thing". Phase 2 should name them (`crossSize`, `trackLength`, `boxDiagonal`) before
   moving any call site.
10. **Studio handles assume an arc.**
    `devtools/_studio_handles.py:60-100` hard-codes "the pivot is (0, 0), 0 degrees is up and
    angles run clockwise", and `toScene`/`polar`/`angleValue` convert a scene point to
    `(angle, radius)`. Phase 4 is correctly gated on `feat/studio-snapping`; until then, bars
    will be editable through the generated controls only — `devtools/_studio_schema.describe`
    (docstring at `_studio_schema.py:1-30`) walks `type(owner).statefulItems` on the gauge and
    on every part it holds, and makes one control per settable property, so a new display
    class needs no Studio edit to get controls. (`gauge_studio.py` itself only assembles the
    window; the introspection lives in `_studio_schema.py`.)

## Dead and shadowed code found while surveying

Not part of this task's scope — recorded so the refactor does not carry it forward by
accident, and so nobody "fixes" a shadowed definition by deleting the live one. Each was
checked by reading the definitions, not by name matching.

- `Gauge.value_to_angle` **L5805-5807 is shadowed** by the second definition at L6086-6094.
  Neither is decorated; the later plain method wins. The shadowed one has no `wrap` branch.
- `Gauge.radius` **L6030-6032 is shadowed** by the second `@property` at L6034-6037. The
  shadowed one clamps to `radius_max`; the live one clamps to `radius_max * 2`.
- `GaugeFill._valueAtAngle` (L3021-3024) has no callers anywhere in `src/` or `tests/`.
- `class Arrow(Needle)` L2388-2512 is never instantiated: nothing in `src/` or `tests/`
  constructs `Arrow`, and `Needle.draw` routes `Needle.Type.Arrow` to `_style_arrow`
  (L2120) instead. Its `paint` override (L2390-2393) draws a red rectangle around its own
  bounding rect, unconditionally.
- `Graduations.min_spacing_val` L761-763 returns `None`; `Graduations.min_interval_deg`
  L782-791 returns `Unset` on every path because each `elif` binds without an `else`.
- `Print` instrumentation: `TickSurface.rebuild` prints a line per rebuild (L1572), and
  `Tick.mouseMoveEvent` prints on every mouse move (L1355-1356).

The many repeated `def`s inside `Gauge` (e.g. `range` x4, `fill` x4, `caption` x4) are the
`StateProperty` getter/setter/decode/encode idiom and are **not** duplicates — checked by
reading the decorator above each definition.

---

## 5. Proposed file split

A `meter/` package beside `Gauge.py`, keeping `Gauge.py` importable as a shim. The brief
names `scale.py`, `track.py`, `elements.py`, `gauge.py` and `bar.py` as examples; a sixth
module is proposed for `Meter` itself so that `elements.py` does not have to import from the
subclasses that import it.

| File | Contents | Rough size |
| --- | --- | --- |
| `meter/scale.py` | `Scale` (min, max, `wrap`, `toT`, `fromT`, `spanOf`, `intervalOf`, `pxOfT`, `tOfPx`, `shortestDelta`); the pure helpers `filter_factors`, `_isWholeSteps`, `formatDuration`, `shortestDelta`, `decode_measurement`, `clockTurn`, `parseClockTime`. | ~150 lines now; ~250 with `Scale` |
| `meter/track.py` | `Track` — `pointAt(t)`, `tangentAt(t)`, `normalAt(t)`, `angleAt(t)`, `subPath(t0, t1)`, `lengthPx`, `thickness`, `bounds`, `distanceAt(t)`; `ArcTrack(center, radius, start_angle, end_angle)`; `LineTrack(start, end)`. Written so a later `PathTrack(QPainterPath)` fits the same interface. | ~300 |
| `meter/meter.py` | `Meter(Display)` — the value source, `GaugeRange`, `valueClass`, `alignment`, `recenter`, `refresh`, `rebuild`, `_update_shape`, `trackRect`, `crossSize`, `center`, `baseWidth`, `marginRect`, `anchor`/`inset`, `_ANCHORS`, `center_offset`, `_dialRect`/`_sideStripWidth`/`_sideValueRect`, `_valueSide`, `_syncUnitUnderValue`, `safe_area`, `_gauge_path`/`full_gauge_path`/`full_gauge_rect`. | ~900 |
| `meter/elements.py` | `MeterItem`, `MeterPathItem`, `Graduations`, `Tick`, `SubTick`, `TickSurface`, `Needle`, `GaugeMarker`, `GaugeZones`, `GaugeFill`, `GaugeCaption`, `GaugeText`, `GaugeLabel`, `GaugeValueLabel`, `GaugeUnit`, `MeterTickText`, `MeterTickTextGroup`. | ~4,600 |
| `meter/gauge.py` | `GaugeArc`, `GaugeTickText`, `GaugeTickTextGroup`, `Gauge(Meter)`, `Arrow`, the clock-hand placement, `convert_gradient`/`map_gradient_to`, the arc-specific `_bend` and `_labelRotation` overrides. | ~1,400 |
| `meter/bar.py` | `Bar(Meter)` and its `LineTrack` wiring, a pointer that reuses the `Needle` shapes, the bar's value-label positions. | new, ~500 |
| `Gauge.py` | Shim only: `from .meter.gauge import *` plus explicit re-exports of everything other modules import by name. | ~30 |

The shim has to carry four current import sites (checked by grep across `src/` and `tests/`):

- `lib/ui/frontends/PySide/Modules/Displays/__init__.py:49` — `from .Gauge import *`.
- `Displays/Realtime.py:313` and `:766` — `Gauge`.
- `devtools/_studio_stage.py:40-41` — imports the **module** `Gauge as _gaugeModule` *and* the
  class `Gauge` from it.
- `devtools/_studio_editors.py:937` — `Needle`.
- `tests/ui/test_gauge_helpers.py:4` — `clockTurn`, `formatDuration`, `parseClockTime`,
  `shortestDelta`.
- `tests/ui/test_gauge_tick_format.py:2`, `tests/ui/test_gauge_interval_steps.py:1` —
  `GaugeTickTextGroup`, `_isWholeSteps`.

New members on `DisplayPosition` for bar value positions (start, end, inside the fill,
and the existing above/below) belong in `lib/ui/Geometry/__init__.py` beside
`ValueDisplayPosition` (L726) and `UnitDisplayPosition` (L730), not in the meter package.

## Cross-links

- [`meter-and-bar.md`](meter-and-bar.md) — the brief this surveys for.
- [`gauge-presets.md`](gauge-presets.md), [`gauge-display.md`](gauge-display.md),
  [`gauge-text-treatments.md`](gauge-text-treatments.md) — existing gauge notes.
- `docs/reviews/schema-pipeline.md` — the other deep-dive in this repo; the schema engine
  is unrelated, but it is the shape this document follows.

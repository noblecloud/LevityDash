# Emissive colour, stroke glow and border beams

Suggested branch: `feat/emissive-color` off `feat/value-sources`. Phases 1 and 2 can
start now. The Oklab gradient step in phase 1 edits `colors/gradient.py`, so start that
step only after `feat/gradient-unit-stops` has merged. Phase 3 waits for the user's answer
on how to bring in `border-beam-qt` (see the end).

## What the user asked for

> I check out the ~/Code/color_sphere. I want to use the color system in that and try
> to replicate some of the glow. there's also border-beam-qt that might be interesting
> to use

## The two source projects

**`~/Code/color_sphere/demo.html`** is a 2D-canvas copy of the glowing trefoil knot on
jlongster.com, with a colour lab. Read its `AGENTS.md` first. To view it, serve the folder
over HTTP: `python3 -m http.server 8731 --directory ~/Code/color_sphere`. A `file://` URL
shows a blank canvas. The two parts to bring over are:

- **The colour system.**
  - It takes hues at a fixed Oklch lightness and chroma (L 0.70, C 0.20).
  - It lowers the chroma by binary search until the colour is inside sRGB.
  - It derives a palette from one base hue by a scheme: triadic, split-complement,
    analogous, complementary or golden (`SCHEMES` in the script).
  - It interpolates between palette colours in linear light.
  - It sends each colour through `displayColor`: a gain (emission × 3.2 × 2^0.25), an
    ACES-style tone map on luminance, a gamma of 2.2 and an optional saturation. Bright
    colours then roll off towards white the way light does, instead of clipping to flat
    primaries.
- **The glow.** Each knot segment draws several strokes of the same path:
  - stroke k has width `1 + glowSize·(1.6 + (k-1)·1.2)` times the core width and alpha
    `glow·0.12·2^(2-k)`, in the segment's exact colour, with normal (source-over)
    blending;
  - one extra stroke uses additive (`lighter`) blending, with alpha capped at 0.04;
  - the core stroke goes on top.
  `AGENTS.md` in that folder explains why the additive pass is capped: hue-ring colours
  added together go to white and wash the glow out. It uses no blur at all, so it is cheap
  and gives the same result cold or warm.

**`~/Code/border-beam-qt`** is the user's own PySide6 port of the React `border-beam`
component: a travelling or breathing glow around a card. Read its `AGENTS.md`, which lists
Qt quirks found in PySide6 6.11 (LevityDash's venv runs 6.11.1).

- `src/border_beam/oklch.py` is already a Python port of color_sphere's colour chain:
  `oklch_to_linear`, `oklch_color`, `display_color`, `ring_color`. It matches the demo
  byte for byte, and its docstring says not to "fix" the constants. Start from it.
- `src/border_beam/styles.py` is the painting engine. Its painters
  (`paint_ring_front`, `paint_line_front`, `paint_pulse_inner_front`,
  `paint_pulse_outside_behind`/`_front`) take a `QPainter` and a `PaintCtx`, not a
  widget. So they can draw inside a `QGraphicsItem.paint()`.
- `BorderBeam` itself is a `QWidget` wrapper with a `QGraphicsEffect`. LevityDash draws
  with `QGraphicsItem`s, so do not use the wrapper. Use the painters.
- `pulse_driver.py` is a shared ~30 fps clock with reference counting, and `set_time()`
  freezes it for tests and renders.
- The project has no commits yet.

## Where things are in LevityDash

- `src/LevityDash/lib/ui/colors/`: `color.py` (`Color`), `gradient.py` (`Gradient`,
  `Gradient.QtGradient`), `presets.py` (named gradients) and `cubehelix.py`.
- Gauge drawing: `Modules/Displays/Gauge.py` (`GaugeArc`, `GaugeFill`, `GaugeZones`,
  needles, markers). Graph lines: `Modules/Displays/Graph.py` (plots paint on a worker
  into a `QImage`; read the off-thread painting gotcha in `CLAUDE.md`).
- The moon (`Modules/Displays/Moon.py`) glows through a `QGraphicsEffect`. Cold renders
  composite that effect badly (see `CLAUDE.md`). Stroke glow avoids the problem.
- Panels: `Modules/Panel.py`. A border beam would be drawn by a panel decoration.

## Phase 1: the colour system

1. Add `colors/oklch.py`, ported from `border_beam/oklch.py`.
   - Keep it free of Qt: return float triples. `Color` converts them to `QColor`.
   - Keep the constants and the HSLuv code bit-identical to the source, as both
     `AGENTS.md` files require.
2. Colour values in YAML accept:
   - `oklch(L C h)`, for example `oklch(0.70 0.20 145)`, with chroma clamped into sRGB;
   - a bare hue on the palette ring, `hue: 145`, which uses the default L and C.
   Existing colour strings (`#rrggbb`, names) keep their meaning.
3. Palettes from one hue: `palette: {hue: 145, scheme: triadic}` gives a list of colours
   that a gradient, zones or markers can use. Use the scheme table from the demo, with the
   same names.
4. Emissive display: an opt-in `emission:` value on a colour or a gradient runs the colour
   through `display_color`. With no `emission:`, nothing changes.
5. Oklab interpolation for gradients: `gradient: {space: oklab, …}`, with `srgb` as the
   default so existing files render the same. Qt's `QLinearGradient` interpolates in sRGB,
   so build extra stops (for example 16 between each pair) sampled in Oklab. **Wait for
   `feat/gradient-unit-stops` to merge before this step.**

## Phase 2: stroke glow

1. Write one glow helper that takes a painter, a path, a pen colour, a core width and
   glow settings, and draws the stack described above. It must be pure painting, with no
   `QGraphicsEffect`, so it works on a worker `QImage` (graphs) and in a cold render.
2. Settings, shared by every user of the helper:

   ```yaml
   glow:
     strength: 1.0   # the demo's `glow`
     size: 0.6       # the demo's `glowSize`
     passes: 4       # the demo's `glowPass`, 1-4
     bloom: 0.04     # cap on the additive pass alpha; 0 turns it off
   ```

   `glow: true` means these defaults. Leaving `glow` out means no glow, so existing files
   render the same.
3. Use it on the gauge arc track, the fill, zones, needles and markers, and on graph plot
   lines. Extend each item's bounding rect by the widest glow stroke, or the glow will be
   clipped and leave smears when the item moves.
4. Add a preset, `docs/design-references/presets/emissive.levity`, that shows a few gauges
   and one graph with Oklch palettes, emission and glow. Tune it against the color_sphere
   demo side by side (see the memory note on defaults: do not ship untuned defaults).
5. Gauge Studio gets a Glow section through the usual `StateProperty` introspection.
   Every numeric control keeps a slider.

## Phase 3: border beams (after the user answers)

1. Draw the `border_beam` painters on a LevityDash panel through a small decoration item,
   with a `PaintCtx` built from the panel's rect and corner radius.
2. Settings: `beam: {size: md|sm|line|pulse-inner|pulse-outside, variant, duration,
   strength, active}`, with names taken from border-beam's public API.
3. Uses to show: a panel that pulses while an alert is active, and a beam that runs once
   when new data arrives. A beam that runs all the time on a room display is a
   distraction, so the default is off.
4. Cost: one 30 fps repaint per beam. Measure CPU on the live display with a beam on and
   off. `lambda` is an Intel Mac and is slower. Stop the driver when no beam is active.

## Rules

- Offscreen only (`QT_QPA_PLATFORM=offscreen`) for every render, test and Studio run.
  End scripts with `app.quit()`. Never use `kill -9`, `pkill`, `killall` or a bare
  `timeout`. Stop only processes you started, by PID.
- Do not touch the user's real config or the supervisor (ports 8667 and 8668). Work in a
  separate worktree.
- Prefer real renders to new unit tests. Small tests are fine for the colour maths (the
  Oklch round trip, gamut clamping, and `display_color` against values taken from the
  demo).
- `pytest tests -q -p no:cacheprovider` must pass (baseline 498 passed, 1 skipped; one
  known flaky test passes on a rerun).
- Commit early. Do not push.

## Verification

- A render of `gauge-showcase.levity` before and after shows no change, because every
  new option is opt-in.
- The emissive preset next to a screenshot of the demo at its default settings.
  Compare the colours and the glow falloff.
- One gradient drawn in `srgb` and in `oklab`, for example blue to yellow, which turns
  grey in the middle in sRGB.
- Render time for one glowing gauge, cold and warm, against the same gauge with no glow.

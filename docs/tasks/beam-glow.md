# Border-beam pieces take a `glow:` **Status: FIXED 2026-10-06.**

## Symptom / ask

The gauge elements (`Needle`, `GaugeArc`, the fill) take a `glow:` and draw a halo through
`paintGlow`, but the border-beam items do not. The beam (`Modules/beam/`) has no `glow`
property, so a `.levity` author cannot give the beam or its card an outer halo, and the
Studio's beam popover has no glow control.

## Cause

`PanelBeam` was `QGraphicsItem, Stateful` with no `GlowMixin`, and its `paint` /
`paintBehind` never called `paintGlow`. `boundingRect` returned `panelRect()` unchanged, so
any halo would be clipped, and there was no `glowChanged` hook for the mixin to call.

## Fix

`src/LevityDash/lib/ui/frontends/PySide/Modules/beam/item.py`:

- `PanelBeam` is now `GlowMixin, QGraphicsItem, Stateful`. It gains the shared `glow`
  `StateProperty`, a `glowChanged()` that re-measures and repaints, and bounds grown by
  `glow.pad(rect, glowWidth)`.
- Two pieces, each with the right `paintGlow` flag:
  - **the beam's outline** — stroked (`filled=False`), coloured with the beam's leading
    blob colour for the frame, so it keeps the beam's hue;
  - **the card fill** — filled (`filled=True`), coloured with the fill, drawn behind the
    panel by `_BehindLayer` (whose `boundingRect` also grows).
- `glowWidth()` is the band the beam paints (1px on the rounded rectangle, 2px on a custom
  path — the same band `styles.band_mask` uses). `reach` is a share of that band.
- `src/LevityDash/devtools/_studio_editors.py`: `BeamForm` gains a `glow` part with
  `GlowEdit()`, the same pattern `FillForm` already uses.
- `docs/design-references/presets/border-beam.levity`: each card sets
  `glow: {strength: 1.0, reach: 4.0, passes: 6}` so the halo shows in the preset render.

## Verification

- `tests/ui/test_border_beam.py`, section glow: `glow: true` puts non-transparent pixels
  outside the panel rect; absent and `glow: false` put none; the bounds grow; the card
  fill's halo paints and grows `_behind`; the value round-trips through state.
- `tests/devtools/test_studio_beam_editors.py`: `BeamForm` round-trips `glow`.
- `pytest tests -q` green (781 passed, 1 skipped; +8 new).
- Offscreen: `render_diff.py capture <dir> --only border-beam` differs from the no-glow
  capture by 12762 px (max Δ108) at reach 4.0 — a ~2px rim outside every card. With no
  `glow:` in the preset the new code is pixel-identical to before the change (max Δ0),
  so the option is fully opt-in.

## Cross-links

- [emissive-color-and-glow](emissive-color-and-glow.md) — phase 2 (the glow helper) and
  phase 3 (the beam itself).

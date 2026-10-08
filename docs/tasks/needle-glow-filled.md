# Needle glow rides the pen width, not the shape

**Status: FIXED 2026-10-06.** The needle's paint — on the shared
`StatefulGaugePathItem` base, not the needle's own body — now passes
`filled=True` and the shape's own thickness (`self.width_px`) instead of the pen's
width, so at `reach: 0` nothing shows outside the outline and a halo starts flush
at the blade's edge. On `dev` (`0d69fa5`, `14457d4`), pinned by
`tests/ui/test_glow_filled.py`.

At `reach: 0` the halo should be invisible (every pass flush), but the needle shows a
uniform gray band around its blade — a hard-edged outline roughly 40-50% of the blade's
width on each side. All passes stack at the same width, so it reads as one band rather
than a soft falloff.

Cause: `paintGlow` is handed `self.pen().widthF()` — the needle's stroke width — and for
a *filled* shape the halo is stroked along the outline, so a pen-width stroke puts half
of that width *outside* the shape. `reach` then scales the wrong base.

Two edits, in order:

1. **The needle never got `filled=True`.** The earlier patch at `meter/elements.py:3732/3738`
   landed on the *fill*'s paint (the class above it, the one with the `_segments` builder).
   The needle's paint is not in its own class body (`Needle` at line 2298; nothing in
   2298-2500) — it is on the shared base `StatefulGaugePathItem`. Find `paintGlow` there,
   pass `filled=True`, and do the same for its `glow.pad(...)` call.
2. **The base width for a filled shape must be the shape's drawn thickness, not the pen.**
   The caller knows it — the needle builds its own blade and dot — so pass it through
   instead of letting `paintGlow` infer it from the pen.

Acceptance: the same case as the attached screenshot — `reach: 0` on the `dot` needle —
shows **no band**; at `reach: 0.5` a soft halo starts at the blade's edge.

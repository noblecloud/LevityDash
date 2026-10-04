# Gauge text: optical centering

**Status:** open, not scheduled. Recorded 2026-10-04.
**Base:** `feat/value-sources`. Step one: `git checkout -B feat/optical-centering feat/value-sources`.
**Model:** the algorithm is a design call (Opus). The render check suits `levity-worker` (Sonnet).

## The problem

A gauge reading `98°` looks off-centre to the right, even though it is centred exactly. The `°` takes as much advance width as a heavy glyph but carries almost no ink. The eye centres on the **ink mass**, which is the digits, so the readout seems to lean right. The same happens with `%`, a trailing `.`, and a leading `1` (narrow ink in a full-width tabular slot).

## Expected change

Centre labels on what the eye sees, not on their bounding box. The candidates, in increasing ambition:

1. **Hang light trailing symbols.** Centre the string as if the symbol (`°`, `%`, `'`, `"`) were not there, so it hangs outside the centred block. Typographers call this hanging punctuation. It is cheap and covers the screenshot that started this brief.
2. **Ink-weighted centre.** Rasterise the label path to a small mask (or approximate it: sample the `QPainterPath` with `contains()` on a grid). Take the horizontal centroid of the ink, then shift the label so that centroid sits on the target x. Damp the result (e.g. 50–70 % of the full shift), because pure centroid centring over-corrects on strings like `100`.
3. **Per-glyph weights.** A small table of each glyph's visual weight for the bundled fonts (Nunito, Roboto, Roboto Mono). It is more stable than measuring ink every frame.

Start with option 1, measure, and reach for option 2 only if 1 isn't enough.

### Where

- **The value:** `GaugeValueLabel.TextBox.getTextPosition`, and `Gauge.recenter` / `_syncUnitUnderValue` in `Displays/Gauge.py`. The horizontal centre used there is `gauge.center.x()`.
- **Generally:**
  - `Text._update_path` / `Text.updateTransform` in `Displays/Text.py`. Alignment decides where the path sits relative to the origin.
  - The cleanest home is an alignment option on `Text`, e.g. `alignment: {horizontal: center, optical: true}`, so Realtime text displays and size groups (`lib/ui/Groups.py`) get it too.
  - Make it opt-in, or default it on only for gauges. Size-group fitting assumes the path's bounds.
- **Don't break fitting.** `getTextScale` and the collision checks read the path and its bounds. An optical *offset* to the position leaves them valid. Changing the *path* does not.

## Verify

Render the same gauge with values `98°`, `100°`, `71%`, `29.97` (with and without the shift), and crop the readouts side by side:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python src/LevityDash/devtools/render_widget.py \
  --levity <fragment> --scenario hot-clear-day --name gauge --out /tmp/x.png
```

`render_service.py` is faster if you'll iterate. Judge by eye and say so; there is no numeric pass/fail here. Then run `pytest tests/ui -q`.

## Related: curved labels

Bending the label glyphs along the arc is its own brief: [curved-gauge-labels.md](curved-gauge-labels.md).

The maintainer wants both modes, outline-warp *and* per-glyph placement. The per-glyph mode is cheaper and suits loose letter-spaced labels. That brief's warning stands for normal tracking, so it should be an option, not the default.

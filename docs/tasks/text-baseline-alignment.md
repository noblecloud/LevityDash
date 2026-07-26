# Graph hour labels aren't vertically aligned (descenders shift them)

> ✅ **FIXED 2026-07-26.** `_update_path` derived the `addText` baseline
> origin from `tightBoundingRect` (ink extents), so a descender moved both
> the origin and the height correction. Vertical placement now uses
> ascent/descent for Top and Bottom; `VerticalCenter` was already correct
> (centring cancels the height term) and was left alone. Measured in a
> booted dashboard: the hour labels went from two clusters 2.18px apart,
> split precisely by descender presence, to a shared baseline.
> Pinned by `tests/ui/test_label_baselines.py`.
>
> ⚠️ **One residual, unrelated:** two of the nineteen hour labels sit ~3px
> below the rest *as a pair* — `6a` at 263.235 and `12p` at 263.295 while
> the other seventeen are at 260.394. They are internally consistent with
> each other and the split does not follow descender presence, so it is a
> different cause (likely edge labels at a different scale, or mid
> transition). Not investigated.

**Status:** reported 2026-07-25, fixed 2026-07-26.

## Symptom

Along the bottom of the graph, the hour labels sit at inconsistent heights:
`12p` and `6p` render slightly higher than `6a` and `12a`.

The distinguishing factor is the **descender**. `p` drops below the
baseline; `a` does not. Any label containing a descender is displaced.

## Cause (per the author, who wrote the original implementation)

The fitting/positioning logic aligns using the **rendered extents** — the
lowest pixel/vector of the glyph outline — rather than a fixed reference
point from the font metrics.

A descender extends the glyph's bounding box downward, so bottom- or
centre-aligning by that box pushes the whole string up relative to a string
without one. The two label sets then disagree by roughly the descender
depth.

The original implementation reportedly used a **set point within the font
metadata** (i.e. the baseline, or an ascent/descent-derived reference) to
determine where the bottom of the text was, precisely so that strings of
differing glyph heights would still align. That behavior was lost somewhere
in the size-group / text-fitting rewrite.

## Expected fix

Align by a **font metric**, not by the path's bounding rect:

- `QFontMetricsF.ascent()` / `.descent()` give a per-font, per-size constant
  reference independent of which glyphs are present.
- The baseline is the natural anchor — it's what typography aligns on, and
  it's invariant across `6a` and `12p`.
- The relevant code is the text-fitting engine (`lib/ui/Groups.py`) and
  `Displays/Text.py`'s `updateTransform`/path building, which is where the
  rendered-extents measurement is taken.

Beware: some places legitimately want the tight bounding rect (for fitting
text *into* a box, the ink extents are what matter). The fix is to use the
metric-derived reference for **alignment/positioning** while keeping the
ink extents for **size fitting** — conflating the two is likely what
introduced this.

## Verification

Render a graph and compare label baselines across a mixed set —
`6a`, `12p`, `6p`, `12a` — which is exactly the sequence along the bottom
axis. All four baselines must be identical. Screenshot via the offscreen
`.grab()` harness (see CLAUDE.md) makes this checkable without eyeballing a
live window.

Worth also checking anywhere else short strings with mixed ascenders and
descenders are aligned as a row — the day labels (`Sat`/`Sun`/`Mon`) and
the bottom-row value/unit pairs are the obvious candidates.

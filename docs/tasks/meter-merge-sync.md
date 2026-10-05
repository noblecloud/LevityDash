# The sync merge: port `feat/value-sources` into the meter layout

`refactor/meter` was branched from `fd873b5`; `feat/value-sources` has since moved
34 commits, and six of them changed `Gauge.py` (+215/-59). This branch meanwhile
moved most of that file into `meter/`. Git reports that as one huge conflict. The
merge is *in progress in the working tree* with conflict markers in
`src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Gauge.py` — resolve it,
port each upstream change to where its code now lives, and commit.

## The port list is generated, not remembered

```
cd /Users/noblecloud/Code/LevityDash/.claude/worktrees/blackfish-meter
.venv/bin/python .render-diff/tools/port_list.py          # summary
.venv/bin/python .render-diff/tools/port_list.py --full   # the diffs to apply
```

It reads git objects only, so it works with the tree mid-merge. It reports, for
every member this branch moved or kept: whether upstream changed it, and the hunks
between upstream's text and this branch's. It also reports **class bases** and
**members upstream has that this branch has nowhere** — the three base changes
(`Gauge`, `GaugeArc`, `Needle` each gain `GlowMixin`) and the new glow/gradient
members are in that second list.

## How to resolve

1. `Gauge.py` keeps **this branch's structure** (it is the arc-side remainder):
   `git checkout --ours -- src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Gauge.py`
   then port the upstream changes that belong *in this file*: the base changes for
   `Gauge` (`class Gauge(Meter)` becomes `class Gauge(GlowMixin, Meter)`) and
   `GaugeArc`, the new members (`GaugeArc.boundingRect`/`glowChanged`/`paint`,
   `Gauge.glowChanged`, `Gauge.resolve_gradient`) and the modified ones
   (`convert_gradient`, `map_gradient_to`).
2. Everything else in the merge already arrived cleanly take-theirs (new files:
   `lib/ui/glow.py`, `lib/ui/colors/*`, `curvetext.py`, Studio presets, tests).
   Leave them as the merge staged them.
3. The members that moved go to the module that holds them now:
   - `meter/elements.py` — `GaugeFill` (`_glow`, `_glowToDraw`, `boundingRect`,
     `glowChanged`, `paint`, `configure`), `GaugeZones` (`configure`,
     `glowChanged`, `paint`, `refresh`), `Needle` (`_glowToDraw`, `boundingRect`,
     `glowChanged`, `paint`, and the `GlowMixin` base), `GaugeCaption._placeWarped`,
     the whole end-label set (`GaugeTickText.position`, `display_position`,
     `end_position_set`, `setPos`, `END_LABEL_POSITIONS` and the
     `_END_LABEL_ALIASES`/`_endLabelPosition` helpers it needs), and
     `GaugeTickTextGroup.fill_brush`/`position_leading`/`position_trailing`.
   - `meter/meter.py` — `Gauge.glowChanged` (it reads the items, which Meter owns
     now) and `Gauge.resolve_gradient` if it turns out to have no arc in it; if it
     does, it stays with `Gauge`. Check, don't assume.
4. **Apply the hunks, do not replace members wholesale.** Every member this branch
   also edited keeps its edit: the `_gaugeKeyName` → `gaugeKeyName` renames, the
   lazy `gauge_class()` swaps, the `Gauge = None`/`GaugeArc = None` sentinels, the
   annotation formatting. Where an upstream hunk and one of those collide, keep
   both - the rename wins on the name, upstream wins on the logic.
5. `GaugeMarker._tickClock`: both sides changed it, and the upstream commit is the
   same change this branch cherry-picked as `49c1623`. Take upstream's text
   verbatim (`shared.now()`), so the two branches are byte-identical there.
6. Remove every conflict marker. `grep -rn '<<<<<<<' src/` must be empty.

## Verification

- `.venv/bin/python -m pytest tests -q -p no:warnings` — the count rises above the
  old 552: upstream brought new test files (`test_gradient_unit_stops.py`,
  `test_oklch_color.py`). Report what you see; the requirement is no failures.
- `.venv/bin/ruff check --no-cache --select F821,F811` on `Gauge.py`, `meter/`,
  `curvetext.py`, `lib/ui/glow.py` and `lib/ui/colors/`. Expect the two
  pre-existing F811s in `Gauge.py` and nothing else.
- `.venv/bin/python .render-diff/tools/port_list.py` — the remaining hunks must all
  be ones this branch deliberately made. Read them; anything else is a missed port.
- **Pixels.** The old `.render-diff/baseline` predates the glow and the unit stops,
  so it cannot judge this merge - do not chase differences against it. Instead:
  add `docs/design-references/presets/emissive.levity` to the capture set in
  `src/LevityDash/devtools/render_diff.py` (the glow paths need pixel cover, and
  `emissive` is the preset upstream wrote for them), capture a **fresh baseline**
  from the merged tree, then run `render_diff.py selfcheck` and report the two
  captures' verdict. A stable baseline is the deliverable; a clean comparison to
  the pre-merge baseline is not expected.
- Commit the merge (`git commit`, no `--amend`, no `--no-verify`) on
  `refactor/meter`, message explaining the port in the style of the branch. Stage
  explicit paths, never `-A`. Do not push. Do not merge anything else.

## Report back

The merge commit SHA and its parents, the port list's remaining hunks with a
one-line reason each, the test and ruff results, and the two capture verdicts.
If a port turns out not to belong where this brief says, put it where it does
belong and say so - the brief was written from a generated list, not from reading
every hunk.

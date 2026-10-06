# The rest of M2, and the two side jobs

The meter split (`meter-and-bar.md`) has its item layer out of `Gauge.py` and the
first two batches of `Meter` in. This brief covers what is left of phase 2's
`Meter` extraction, plus two read-only jobs that can run beside it. The working
note `meter-harness-status.md` is the record of *why* each guard exists; read it
before touching anything, because every trap below cost somebody an afternoon.

## The state of the branch

Worktree: `.claude/worktrees/blackfish-meter` on `refactor/meter`, clean, unpushed.
`Gauge.py` is 1,292 lines; `meter/` holds `scale.py`, `track.py`, `elements.py`
(4,534) and `meter.py` (569, with `GaugeRange` and `Meter(Display)`).

The gate every step has passed so far, and must keep passing:

```
.venv/bin/python -m pytest tests -q -p no:warnings          # 552 passed, 1 skipped
.venv/bin/ruff check --no-cache --select F821,F811 <files>  # only the 2 known F811s
.venv/bin/python src/LevityDash/devtools/render_diff.py capture <dir> --jobs 4
.venv/bin/python src/LevityDash/devtools/render_diff.py compare .render-diff/baseline <dir>
                                                            # 23/23 clean, 0 px
```

(`ruff` is installed in this worktree's venv, machine-locally, not in pyproject.
The two F811s it reports are pre-existing shadowed `radius`/`value_to_angle` in
`Gauge.py` - leave them.)

## Job A - finish the `Meter` extraction (the only writer)

Move the remaining members of `Gauge` that have no shape in them onto `Meter`, in
two batches, each with its own commit and a full gate run.

**The principle, not a list.** Re-derive the cut with the classifier, which counts
what each member actually touches:

```
src/LevityDash/devtools/render_diff_tools/arc_cut.py src/.../Displays/Gauge.py Gauge
```

A member belongs on `Meter` if it does not reference the arc, the angles, or
`self.radius`. When in doubt, leave it in `Gauge`: a smaller `Meter` is fine, a
broken one is not. These stay in `Gauge` by decision, not by accident: `arc`,
`startAngle`, `endAngle`, `fullAngle`, `leading_angle`, `trailing_angle`,
`convert_gradient`, `map_gradient_to`, `radius`, `_radius`, `radius_max`,
`arc_length`, `gaugeRect`, `tickFont`, `sizeAcross`, `sizeAlong`,
`value_to_angle*`, `angle_degrees_to_value`, `safe_radius`,
`exterior_safe_radius`, `value_safe_radius`, `safe_area`, `recenter`,
`_center_transform`, `_recenterTransform`, `refresh`, `_gauge_path`,
`full_gauge_path`, `full_gauge_rect`, `_debug_paint`, `animateValue`, `duration`,
`easing`, `_needleAnimation`.

Batch 3 is the layout: alignment, anchor, inset, `center_offset`, the side rects,
`_dialRect`, `center`, `scene_center`, `baseWidth`, `setRect`, `pen`,
`defaultColor`, `displayType`, `type`, `parentResized`, `_update_shape`,
`rebuild`, `releaseSources`, and whatever else the classifier clears.

Batch 4 is the item holders: `needle`, `fill`, `zones`, `markers`,
`majorDivisions`, `minorDivisions`, `microDivisions` and their clear/item helpers.

**How to move them.** `src/LevityDash/devtools/render_diff_tools/move_members.py SOURCE.py Class
TARGET.py Class Name...` moves a member *group* - every definition sharing a name,
decorators included - because `@prop.factory` and `@prop.setter` are evaluated in
the class body and only work beside their base property. Always run it against
copies in a scratch directory first, check both files parse, then run it for real;
`check_move.py` and `diff_member.py` (same directory) prove the moved text is
byte-identical to the original, which every previous step has been.

**Traps, each of which has already bitten once:**

- A member moved to a class the child does not inherit from stops being a state
  item of the child. `Gauge` derives from `Meter` now; if you move something and
  its `AttributeError` points at a member that plainly exists, check the base
  class before you check the member.
- Anything a moved member's *annotations* name has to resolve in the target
  module's globals (`Text.surface` calls `get_type_hints` at layout time).
  `tests/ui/test_meter_annotations.py` walks the package and fails loudly; if it
  fires, the fix is an import or the hand-over at the foot of `Gauge.py`, never a
  changed annotation.
- Python mangles double-underscore class attributes: `self.__value` inside this
  class body is `_Gauge__value`, and moving the member without the attribute
  renames it silently. Check before each batch.
- The moved module gets its own logger (`log = UILogger.getChild('meter')`), and
  `_gaugeKeyName` is `gaugeKeyName` there. Rename at the call site; keep the log
  message text identical.
- If a log-able failure appears, look for a swallowed warning first - the fill
  and label paths log-and-continue on purpose, so a missing import can look like a
  rendering difference instead of an error.

**Rules.** No push. No merge into `dev`. Never touch the real config or the
supervisor. Do not edit the tests to make them pass - if a test fails, the code is
wrong, or the brief is. Leave the tree clean at the end of each batch (commit it),
because two readers are working against this branch while you work.

## Job B - audit the split so far (read-only, writes one doc)

Independently check the claim "moved, not changed" across every step on this
branch, from the committed states rather than from anyone's summary:

- For each move (the pure helpers, `Track`/`ArcTrack`, the element classes,
  `GaugeRange`, and the `Meter` batches), extract the member's text at the commit
  *before* it moved and compare it with its text now. Report each by name:
  identical, or identical-modulo-<documented change>. The documented changes are:
  the lazy `gauge_class()`/`label_group_class()` swaps in `meter/elements.py`, the
  `_gaugeKeyName` -> `gaugeKeyName` renames, the quoted `GaugeArc` annotation, and
  the `Gauge(Meter)` base class.
- Run the gate on the current HEAD and report the real numbers.
- Write `docs/tasks/meter-split-audit.md`: a table of step -> names -> verdict ->
  the command that shows it, a short list of what you could not verify, and any
  place the claim does not hold. No source edits.

Record the commit you read (`git rev-parse HEAD`); the writer is moving members in
the same tree while you work, so prefer `git show <commit>:<path>` over reading
the working file.

## Job C - the M3 recon (read-only, writes one doc)

Prepare the last step, from greps and the AST, not from memory:

- Every module-level name other files import from `Displays/Gauge.py`
  (`src/` and `tests/`), with file:line - this is the shim's export list.
- What `GaugeArc` needs to move to `meter/gauge.py` (run the inventory tool on its
  own members), and the arc-only members of `Gauge` that would move with it.
- The import-order constraint (`elements` <- `meter` <- `gauge`) and how the
  hand-over at the foot of `Gauge.py` has to look when `Gauge` itself has moved.
- Write `docs/tasks/meter-m3-recon.md`. No source edits.

## What comes back

Each job returns its commit SHAs or doc path, the gate numbers it actually saw,
and anything that resisted - in those words, not a summary of the diff.

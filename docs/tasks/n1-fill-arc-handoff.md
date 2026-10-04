# N1 gauge fill arc: handoff

## Goal
Add a value-driven fill arc to gauges: `display: fill:` (sibling of `arc:`) with keys
`from` (number or value-source string; default range min), `to` (optional; default the
gauge value), `weight`, `color`. With `to` omitted it fills from `from` to the current value.
With numeric `from` and `to` it is a fixed band. Draw it over the track and under the needle.
A missing value hides it. A bad spec logs a warning naming the gauge key (`_gaugeKeyName`)
and never raises. A colour change repaints and never relayouts. Spec: docs/tasks/gauge-presets.md, section N1.

## Done
Nothing in code. No implementation commits.

## Base branch problem (fix this first)
- This worktree started on `origin/main`, which is old. `git merge dev` conflicted in `Modules/Panel.py`.
  I aborted it and ran `git reset --hard dev`; nothing was lost because the old base was origin/main.
- `dev` does NOT contain `docs/tasks/gauge-presets.md`, `docs/design-references/presets/high-low-dial.levity`,
  the scenarios, or `render_widget.py --scenario`. They are on `feat/value-sources` (local and origin),
  and `--scenario` is also on `origin/design/gauge-fixtures` (commits 77d7fb5 brief, 3ee4cba fixture/--scenario).
  `acquireValueSource`/`releaseValueSource` (LevityDash.lib.plugins.computed) probably live there too.
- Next agent: branch from `feat/value-sources` (`git checkout -B <branch> feat/value-sources`), then confirm those files exist.

## Next steps
1. Read docs/tasks/gauge-presets.md (N1) and .claude/skills/levity-dashboard-design/SKILL.md.
2. In `src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Gauge.py`, add `GaugeFill(StatefulGaugePathItem)`
   modelled on `GaugeArc`. Build its path from `gauge.value_to_angle(from)` to `value_to_angle(to or gauge.value)`.
   Refresh it the way `Needle.refresh`/`GaugeMarker.refresh` do. Set its z between the arc and the needle.
3. Add a `fill` StateProperty on `Gauge` next to `arc` (dev: around line 3086). Have string `from`/`to` go through
   `acquireValueSource`, released on teardown. Number-only is acceptable for this phase.
4. Make fragments `docs/design-references/presets/fill-dial.levity` and `comfort-band.levity`
   (key `environment.humidity.humidity` if hot-clear-day has it; band 30 to 60 plus the needle), starting from `high-low-dial.levity`.
5. Render, read the PNGs, commit them next to the fragments.

## Commands (from the worktree)
    PYTHONPATH=$PWD/src QT_QPA_PLATFORM=offscreen /home/user/LevityDash/.venv/bin/python src/LevityDash/devtools/render_widget.py --levity <fragment> --scenario hot-clear-day --name gauge --out <png>
    PYTHONPATH=$PWD/src QT_QPA_PLATFORM=offscreen /home/user/LevityDash/.venv/bin/python -m pytest -q -p no:cacheprovider tests/ui

## Gotchas
- Worktree-isolated agents: keep git commands simple and inside the worktree. Loops, `cd` chains and `&&` chains get refused.
- The permission classifier blocked reads of the main checkout after the `reset --hard`. Stay inside the worktree.
- Not verified: everything. No render or test was run.

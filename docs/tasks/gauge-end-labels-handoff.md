# Handoff: gauge end-label leading/trailing options

**Goal:** check whether `GaugeTickText` (Gauge.py, `src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/`) applies `rotate-/align-/position-leading|trailing` to the wrong end tick, and fix it if so. Use a tabs-only, minimal fix. Commit format: `fix(UI.Gauge): …`.

## Code (on `dev`, approx. lines 2384-2520)
- `display_position`: `ticks[0]` uses `position_trailing` and `ticks[-1]` uses `position_leading`.
- `rotated`: `ticks[0]` uses `rotation_trailing` and `ticks[-1]` uses `rotation_leading`.
- `alignment`: both `ticks[0]` and `ticks[-1]` use `align_leading`, so `align_trailing` is never read.
- `Gauge.leading_angle` docstring: "Left side of the arc" is the larger angle. `trailing_angle` is the right side.

## Verdicts so far (not verified by render)
1. **Rotate swap:** inconclusive. Position and rotate are swapped the same way, so the swap may be deliberate if `ticks[0]` is the right end (max-to-min ordering). The answer depends on where `ticks[0]` sits. Check whether it is the 60 (min) label, and whether min is on the left.
2. **Alignment:** almost certainly a bug, because `align_trailing` is dead code. One end should use `align_trailing`, and it should be the same end that reads `rotation_trailing` (currently `ticks[0]`), since `_align_trailing_auto` depends on `rotation_trailing`.
3. **Position:** same mapping as rotate, so verdict 1 applies.

`git log -S rotation_trailing` only reaches e2a1513 / 401b3b5 (docs and serialization), so it gives no evidence of intent.

## Rendering caveats
- `devtools/render_widget.py`, the Fixture plugin and `docs/design-references/presets/` exist only as uncommitted work in the main checkout, not on `dev`. A worktree `src` cannot render. I used a scratch copy of the main checkout's `src` at `/tmp/claude-0/-home-user-LevityDash/7f7f9324-ce71-5a44-ab8b-aebb9d0db62b/scratchpad/ticks/src`.
- The before renders printed `RuntimeError: LEVITYDASH_FIXTURE is set but the Fixture plugin did not load`, but still wrote PNGs. Inspect them before trusting them:
  - `.../scratchpad/ticks/before-rotate-leading.png`
  - `.../scratchpad/ticks/before-rotate-trailing.png`
- There are no after renders yet.

Script: `.../scratchpad/ticks/run.sh <tag>`. It builds the fragments (preset plus `rotate: false` and `rotate-leading|trailing: true` under `display.major.labels`) and runs:

```
cd /home/user/LevityDash && PYTHONPATH=<src> QT_QPA_PLATFORM=offscreen /home/user/LevityDash/.venv/bin/python <src>/LevityDash/devtools/render_widget.py --levity <frag> --scenario hot-clear-day --name gauge --out <png>
```

Use `PYTHONPATH=<worktree>/src` once the devtools land on `dev`. Until then, patch the scratch copy, render, then port the patch.

## Left to do
1. Read the before PNGs and find which end label (60 = min, 110 = max) is rotated in each.
2. Fix `alignment` (and swap `rotated`/`display_position` if the renders show the swap is wrong). Render after, compare, and port the change to the worktree's Gauge.py.

# Session handoff, 2026-10-05

**Audit 2026-10-10: stale.** Superseded by [docs/roadmap.md](../roadmap.md). Kept as history; do not use it as the start point.

State of play for a fresh Claude Code project on LevityDash. Read `CLAUDE.md` first,
then this file. Every commit named here is on `feat/value-sources` and `origin/dev`
unless the text says otherwise.

## Where the code is

- **Working branch:** `feat/value-sources`. HEAD is `dd241a0`. `dev` points at the
  same commit, locally and on `origin`.
- **Push flow after each merge:**

  ```bash
  git push origin feat/value-sources
  git push origin feat/value-sources:dev
  git branch -f dev HEAD
  ```

- **Feature branches** merge into `feat/value-sources` with `git merge --no-ff`.
- **Tests:** `QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m pytest tests -q -p no:cacheprovider`.
  The current count is 560 passed, 1 skipped. `tests/wire/test_remote_connection_signal.py`
  is flaky and passes on a rerun. Grep the output for `FAILED|passed|failed`; a
  `&&` chain after pytest does not stop on a failure that the grep hides.
- **`lambda`:** do not push to it. The user said to hold off so as not to break it.

## Rules the user set

- Push to GitHub is allowed. Do not push to `lambda`.
- Delegate bounded work to subagents, Sonnet by preference (`levity-worker`), each in
  its own worktree. Keep review and merge in the main thread.
- Prefer real renders and end-to-end checks to unit tests. Small tests for pure maths
  are fine.
- Never write the user's real config (`~/Library/Application Support/LevityDash`)
  beyond what was asked. Never touch the supervisor (ports 8667 and 8668).
- Agents run Qt with `QT_QPA_PLATFORM=offscreen` and end scripts with `app.quit()`.
  Never use `kill -9`, `pkill`, `killall` or a bare `timeout`. Stop only processes
  you started, by PID.
- Set `LEVITYDASH_CONFIG_DEBUG=1` before any ad-hoc LevityDash import. Without it
  the import reads the real config and can connect to the live backend.
- Chat replies use the caveman style from the user's global `CLAUDE.md`. Commits,
  docs and briefs use plain prose.

## The live display

`LevityDash-run` (the supervisor) runs from a terminal on this machine. It restarts
when a `.py` file under `src/LevityDash` changes, so a merge on `feat/value-sources`
reaches the display within seconds. Check it with
`curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8668/health` (200 means up).
Child output is in `~/Library/Logs/LevityDash/<name>.out`.

## What landed today

- **Gauge Studio** (`devtools/gauge_studio.py` and `_studio_*.py`):
  - the wheel guard (a control takes the wheel only after the pointer rests on it);
  - larger, left-aligned section headings;
  - labelled "enabled" rows;
  - a Text section that holds every text part;
  - a breadcrumb over the control list;
  - preset gradients that keep their unit (`stopunits.unitText`).
- **Gradient stops pinned to units** (`colors/stopunits.py`, `Gradient.resolve`), with a
  colour band and draggable nodes in the Studio.
- **Emissive colour and stroke glow**, phases 1 and 2 of
  [emissive-color-and-glow](emissive-color-and-glow.md): `colors/oklch.py`, `oklch()`,
  `hue:`, `palette:`, `emission:`, `glow:`, and `space: oklab` on gradients.
- **Border beams**, phase 3 (`22eb0e0`): the `Modules/beam/` package and a `beam:` key on
  any panel. A beam is off by default. `active:` and `sweep:` take a key or an expression.
  One running beam costs 15–25% of a core on this machine; nobody has measured it on
  `lambda`.
- **Clock hands** read `shared.now()` (`a31af10`, cherry-picked from Blackfish's
  `49c1623`), so a frozen render freezes them.
- **Gauge fixes:**
  - `arc.extend` (default `auto`): with a flat cap, each end of the arc reaches the
    outer edge of the end tick.
  - `fill.cap`: round by default, but flat with `segments`; an explicit value wins.
    Round ends land on the value.
  - Concentric rings now have round ends.
  - The value label's `float-under` position lays out in a strip under the dial
    (`1b53014`). Before, it raised `NotImplementedError` and drew nothing.

## Work in flight

### Blackfish: `refactor/meter` (another session, not pushed)

- **Worktree:** `.claude/worktrees/blackfish-meter`, branch `refactor/meter`, HEAD
  `3633c5f`, based on `fd873b5`.
- **What it does:** it splits `Gauge.py` (6,299 lines) into `meter/scale.py`,
  `meter/track.py`, `meter/elements.py` and `meter/meter.py`, and `Gauge` now derives
  from `Meter`. Gate at its HEAD: 552 passed, 1 skipped, confirmed independently.
- **Review result:** sent to the user to relay. The main points:
  1. **Blocker.** The branch is behind `feat/value-sources`, and `git merge-tree`
     reports a conflict in `Gauge.py`. Blackfish must merge `feat/value-sources` and
     port these into the new files:
     - `bcfc1f7` glow;
     - `c1ddf34` unit stops;
     - `fb1a2e4` end-label positions;
     - `5f512b5` warp;
     - `a0c75ec` and `dd241a0` arc extend and fill caps;
     - `1b53014` float-under, which touches `_valueSide`, `_dialRect`,
       `_sideValueRect`, `center` and `radius_max`, all Meter-side now.

     Then re-take the `render_diff` baseline at the new tip, with
     `presets/emissive.levity` in the capture set.
  2. **The M3 shape is approved**, to start after that merge: `GaugeArc` moves into
     `meter/gauge.py`, and `Gauge.py` becomes a shim.
  3. **Dial geometry belongs on the Gauge side** before a second Meter exists:
     `center`, `scene_center`, `center_offset`, `_dialRect` and `_sideValueRect`.
     Fill, zones and the captions also declare `dependencies={'range', 'arc'}`.
     Record these in the M3 recon; do not move them yet.
  4. **Separate small bugs:**
     - `_studio_stage.py:40` binds the class `Gauge` where the code wants the module.
     - `get(kwargs, 'gauge' 'parent', …)` in the item base joins the two strings into
       the key `'gaugeparent'`.
- **Next step:** do not merge `refactor/meter` until the sync merge comes back and
  passes review.

## Decisions waiting on the user

- **Border beam:**
  - default colour space: `hsv` or `oklch` (recommended: `oklch`);
  - keep `phase:`, `fill` and `radius` as public keys (recommended: keep);
  - sweep length: one cycle for a rotating beam, two breaths for a pulse.
- **Emissive:**
  - glow alpha and size defaults;
  - tuning `presets/emissive.levity` (overlaps, smeared needle glow).
- **Gradient editing:** the distance a node is dragged off to delete it, decimals,
  whether folds persist, and what happens to a bare stop when a unit is added.
- **The tick-label fix:** a global `position: inside` fix for tick labels.

## Known bugs, not started

- **Border beam:** the `pulse-outside` halo is cut off in hard rectangles at its
  layer edge (see `presets/border-beam.png`). No beam has run in the windowed app or
  on live data yet, and nobody has checked that the Studio shows beam controls.
- **Render tools:** `render_dashboard.py` and the other render tools hang at exit
  under offscreen, in a thread-pool join, after the PNG is written. Stop them by PID
  once the PNG exists.
- **Colour:** colour names and `r/g/b` dicts decode wrongly. `Color.toQColor` is missing
  on the Graph path.
- **Gauge:**
  - a 50°C gradient stop node is drawn past the arc end (minor);
  - `float-under` is checked only on a 270° dial; check a full ring, a half dial, a
    corner-anchored gauge and one with a unit label. Its 22% strip height is not
    tuned.
- **Studio:**
  - the needle type row is missing;
  - needle length and width show `0.00`;
  - the Studio writes to the real `LevityDash.log`.
- **Showcase:** the Drive card labels collide (`Coolant191°`, `Battery69%`). The
  `power.energy.net` fill warns about an unknown key, `opacity`.
- **Other:** the `--scenario` render crash
  ([render-scenario-crash](render-scenario-crash.md), on `refactor/meter`), the
  caption-unit race, and rain showing `0.0` where it should show `0`.

## Later

- Snapping, guides and wireframe in the Studio ([studio-snapping-guides](studio-snapping-guides.md)).
- Warp along a path, ellipse first ([warp-along-path](warp-along-path.md)).
- A Dock tile for the backend.
- Linear meters and bars after the Meter split ([meter-and-bar](meter-and-bar.md)).

## Worktrees

`.claude/worktrees/` holds about 50 agent worktrees, most from finished work. Not all
of their branches were checked for merge. Leave `blackfish-meter` alone, and remove others only when the user asks.

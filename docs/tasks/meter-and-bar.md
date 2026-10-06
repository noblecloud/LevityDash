# Meter base class, and progress bars

Suggested branch: `refactor/meter` off `feat/value-sources`. Phase 1 is read-only and can
start at any time. **Do not start phase 2 until `fix/studio-sliders-contrast` and
`feat/warped-text` have merged into `feat/value-sources`.** Both edit `Gauge.py`, so
check `git log feat/value-sources` for them first.

Read `AGENTS.md` first. This brief assumes its conventions: tabs, commit style
`type(Scope): summary`, and the dependency direction `qolkit ← statekit ← LevityDash`.

## What the user asked for

> we need progress bars! Can we abstract the common stuff into a parent class?

A progress bar is the same idea as a gauge. Both map a value onto a track and draw
zones, a fill, markers, ticks, labels and a value readout along it. Only the shape of
the track differs: an arc for a gauge, a straight line for a bar.

## Where things are

- `src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Gauge.py`, about 6,300
  lines. Its classes include `GaugeItem`, `Graduations` (tick values and levels),
  `GaugeArc`, `Tick`/`SubTick`, `Needle`/`Arrow`/`GaugeMarker`, `GaugeZones`,
  `GaugeFill`, `GaugeCaption`, `GaugeLabel`/`GaugeValueLabel`/`GaugeUnit`,
  `GaugeTickText`/`GaugeTickTextGroup`, and `Gauge(Display)`. Roughly 316 lines refer to
  angle or radius. That is the code that has to go through a track.
- `Modules/Displays/curvetext.py` bends text outlines onto a circle. After
  `feat/warped-text` merges, it holds a shared warp helper.
- Gauge features in use today: zones; text tick labels (`text: {0: E}`, `compass`,
  `sign`); segmented fill; fill `from`/`to`; markers bound to keys or expressions
  (`"at(key, -3h)"`); ten needle types; clock markers (`time: hour|minute|second|day`);
  `range: {wrap: true}`; `caption` and `sub-label`; `value-label: {format: duration,
  position: left|right|above|below|inline, size, offset}`; `anchor` and `inset` for
  corner dials; and `arc: {color, weight, cap, start-angle, end-angle}`.
- Examples: `docs/design-references/presets/*.levity` (21 files) and
  `docs/design-references/gauge-showcase.levity` (30 cards). There is an identical copy at
  `src/LevityDash/resources/example-config/templates/dashboards/GaugeShowcase.levity`.
- Rendering: `src/LevityDash/devtools/render_dashboard.py OUT.png --levity FILE
  --scenario stormy-day --size WxH --settle 14` feeds fixed values from
  `docs/design-references/scenarios/`. `tests/conftest.py` has a `frozen_time` fixture
  that shows how to freeze the app clock (`shared.now`, `shared.Now.now`).
- Gauge Studio, `src/LevityDash/devtools/gauge_studio.py`, builds its controls from
  `StateProperty` introspection. A new display class gets controls with no Studio
  change. Its drag handles (`_studio_handles.py`) assume an arc today.

## Target design

- **`Scale`** maps a value to a position `t` in 0..1 and back. It handles min, max and
  wrap. Write it as a class so that log and square-root scales can be added later; do
  not add them now.
- **`Track`** maps `t` to a point, a unit tangent and a unit normal. It can also build
  the sub-path between `t0` and `t1` and measure arc length.
  - `ArcTrack(center, radius, start-angle, end-angle)` serves the gauge.
  - `LineTrack(start, end)` serves the bar, horizontal or vertical.
  - The interface must allow a later `PathTrack` built from a `QPainterPath`.
- **`Meter(Display)`** owns everything that does not depend on the shape: the value
  source, range, scale, zones, fill, markers, graduation values and levels, tick
  labels, value and unit labels, captions, format and colour gradients. Every element
  draws through `self.track`.
- **`Gauge(Meter)`** uses an `ArcTrack`. The YAML type stays `realtime.gauge`. Every
  existing `.levity` file must load and render the same as before.
- **`Bar(Meter)`** uses a `LineTrack`, with YAML type `realtime.bar`. It supports:
  - an orientation, horizontal or vertical;
  - a track weight and a cap, round or square;
  - ticks on either side;
  - a pointer in place of a needle, reusing the marker shapes (triangle, line, dot,
    notch);
  - a value label at the start, at the end, inside the fill, or above or below the
    bar.
- Prefer moving code into a `meter/` package beside `Gauge.py`, for example
  `scale.py`, `track.py`, `elements.py`, `gauge.py` and `bar.py`. Keep `Gauge.py`
  importable as a shim, so existing imports and the Studio keep working.

## Phases

1. **Survey (read-only).** Write `docs/tasks/meter-survey.md`. It must contain:
   - every place in `Gauge.py` that depends on angle or radius, grouped by class;
   - what each place becomes under `Scale` and `Track`;
   - code that only makes sense on an arc and stays in `Gauge`, such as clock hands,
     `anchor`/`inset` corner placement and warped tick labels;
   - the risks;
   - the proposed file split.
   Stop after this phase and report.
2. **Pixel-diff harness, then the refactor.**
   - First build `src/LevityDash/devtools/render_diff.py`. It renders every preset and
     the showcase with frozen time and fixed scenario data into a directory, then
     compares two directories pixel by pixel. It writes a diff image for each mismatch
     and exits non-zero on any difference beyond anti-aliasing noise. Run it twice on
     unchanged code and confirm that two runs match. Known starting point: on
     2026-10-05 two showcase renders of unchanged code differed by about 48k pixels
     (by more than 30 levels), because the Mock plugin drives live values. Use the
     Fixture scenario data, not Mock. If they do not, fix the cause:
     needle animation, clocks or a settle time that is too short.
   - Capture the baseline on the pre-refactor commit.
   - Move `Gauge` onto `Meter` plus `ArcTrack` in small commits. Run the diff after
     each commit. **Phase 2 is done only when the diff is clean.**
3. **Add `Bar`.** *(Done 2026-10-06: `meter/bar.py`, YAML `realtime.bar`; fragments and a showcase board in `docs/design-references/bars/`, values in `scenarios/bar-cards.yaml`, options in `docs/config/dashboard/bar.md`. `Bar` draws its parts in one canvas item through a `LineTrack` and shares `Meter` with `Gauge`; it does not reuse the arc-based tick, fill and needle items. Gauge renders are unchanged.)* Write presets: progress, battery, segmented, thermometer
   (vertical, with a bulb), and a range bar with markers for today's low and high. Add
   one showcase row of bars. Render it, and check readability at 2560x1440: labels
   at least about 14 px tall.
4. **Make the Studio handles follow the track,** so they work on bars too. Do this
   only after `feat/studio-snapping` merges, or coordinate with it.

## Rules

- Use only `QT_QPA_PLATFORM=offscreen`, for every render and every test. Never open a
  real window. When a real-window Python process is killed, it leaves a ghost icon in
  the user's Dock. End scripts with `app.quit()`. Do not end them with `kill -9` or a
  bare `timeout`. Stop only your own processes, by PID. Never use `pkill`.
- Do not touch the user's real config (`~/Library/Application Support/LevityDash`) or
  the running supervisor (`LevityDash-run`, ports 8667 and 8668). The supervisor
  restarts the live display whenever a `.py` file under the main checkout's
  `src/LevityDash` changes. Work in a separate worktree or clone, never in the main
  checkout.
- Prefer real renders to new unit tests. Small tests are fine for pure maths, such as
  `Scale` and `Track` round trips.
- `pytest tests -q -p no:cacheprovider` must pass: the baseline is 492 passed and 1
  skipped, and one known flaky test passes on a rerun.
- Do not push. In the report, give the branch, the commits, the diff-harness results
  and the PNG paths.

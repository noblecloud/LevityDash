# The graph divides by a zero-second time range

**Status: FIXED 2026-10-06.** `normalize()` guards the divide (`Graph.py:884`,
`if seconds > 0:`) and pins a zero-span series to the left edge, and
`pos_px_to_value` takes its single sample rather than indexing by a zero span.
Both are on `dev` (`d917135`, merged via `fix/graph-zero-time-range-test`),
pinned by `tests/ui/test_graph_zero_time_range.py`. A frozen clock no longer logs
a divide-by-zero — but it still destabilises a graph preset for a separate
reason, so the harness's `NO_FREEZE` exemption did **not** become droppable; see
the correction under Verification and
[emissive-upstream-check](emissive-upstream-check.md).

## What is wrong

`src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Graph.py:862` normalises every
series' x values with a division by the figure's time range:

```python
start = self.graph.timeframe.start
seconds = self.figure.figureTimeRangeMaxMin.total_seconds()
x = (x - start.timestamp()) / seconds
```

When that range is zero seconds, `seconds` is `0.0` and every x becomes `inf`/`NaN`.
The y normalisation two lines above already guards its own range (`np.ptp(y) or 1`); the
x axis does not. `figureTimeRangeMaxMin` is a property of the same class at
`Graph.py:4161`.

Measured on the devtools render harness, `docs/design-references/presets/emissive.levity`
(a graph preset) with the clock frozen:

- `RuntimeWarning: divide by zero encountered in divide` at `Graph.py:863`;
- a plot whose pixels differ between two captures of the same code — 2.8k to 4.0k px
  over tolerance, 90% of them in the plot band;
- in about half the runs, a shutdown crash:

  ```
  RuntimeError: libshiboken: Internal C++ object (LevitySceneView) already deleted
    raised from Annotations.limitRect -> app.viewScale
  ```

The freeze collapses the series' time range; with the clock live the range is never
zero and both trees render cleanly (exit 0, PNG). Reproduced run for run on `a31af10`
(upstream, pre-refactor) with this branch's harness held constant, and every crashing
module is byte-identical between the two trees — the crashing code is upstream's. The
full isolation table and the raw runs are in `docs/tasks/emissive-upstream-check.md`.

## Why it matters beyond the harness

The harness works around it — a `NO_FREEZE` exemption for `emissive` plus two named
masks over the plot band and the time axis (`meter-harness-status.md`) — but the
division itself is a live-board risk. Any dashboard whose figure ends up with a
zero-length time range (an empty or single-point series, a window that collapses as
data ages out) takes this path with the clock live. The NaN x-values are also the
plausible source of the post-teardown crash family: a path carrying non-finite geometry
can leave an update queued that runs after the scene view has been deleted.

## The change expected

Decide what a zero-length range should draw — a single point at the plot's start or
centre, or no path at all — and guard the range where the normalisation happens, the
way the y axis is already guarded, so that no non-finite coordinate is ever produced.
Do not merely silence the warning or catch the exception downstream: the point is that
the path never carries NaN coordinates.

## Verification

- Direct reproduction, no harness exemption in the way:

  ```sh
  python src/LevityDash/devtools/render_dashboard.py /tmp/em.png \
    --levity docs/design-references/presets/emissive.levity --scenario <staged> \
    --seed <staged> --size 1600x900 --freeze-time
  ```

  Before: the `divide by zero` warning, exit 139 (SIGSEGV), no PNG. The exact command
  lines that were run, with the staged scenario and seed paths, are in
  `docs/tasks/emissive-upstream-check.md`.
- After: exit 0 and a PNG, twice, byte-identical.
- ⚠️ **Correction (2026-10-06): the follow-up this was expected to unblock did not
  unblock.** Guarding the divide stops the `divide by zero` warning but not the
  crash: with the freeze on, `emissive` still exits `-11` (SIGSEGV) about half the
  time, and the runs that survive log `RuntimeError: libshiboken: Internal C++
  object (LevitySceneView) already deleted` from the graph's time-axis labels
  (`Annotations.resize -> TimestampLabel`). Measured on `dev` `b2499da`: frozen
  4/4 dirty (2 SIGSEGV, 2 with 7 and 12 tracebacks), live 4/4 clean. So
  `NO_FREEZE` stays and the masks stay; see
  [meter-harness-status](meter-harness-status.md).
- Regression: a live-clock capture of a graph preset still renders, and a normal
  (non-degenerate) range is unmoved by the guard.

## Suggested branch

`fix/graph-zero-time-range`.

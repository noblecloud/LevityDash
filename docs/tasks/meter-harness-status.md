# Meter harness — phase 2 working note

**Status: in progress, 2026-10-05.** This is not a brief; the brief is
[meter-and-bar.md](meter-and-bar.md) and phase 1's survey is
[meter-survey.md](meter-survey.md).

Branch `refactor/meter`, worktree `.claude/worktrees/blackfish-meter`.
Captures are local and gitignored: `.render-diff/`.

## Done

- `src/LevityDash/devtools/render_diff.py` — `capture | compare | selfcheck`
  over the 22 presets + the showcase, one PNG per target per capture plus a
  manifest of inputs, hashes and per-file ink; `compare` writes a diff image per
  mismatch and exits non-zero past anti-aliasing noise.
- `_boot.freeze_time()` (the `conftest` patches, plus every module that did
  `from shared import now`, found by identity) and `render_dashboard.py
  --freeze-time`.
- The scenario is generated: `stormy-day` + `gauge-cards` + every key of Mock's
  own table at its base value, read out of `Mock.py`. Each capture stages its
  own seed with Mock off.
- The showcase pins its clock hands with `at: '10:08:36'` (both copies), as
  `clock.levity` already did.
- `selfcheck` — two captures of unchanged code — has reached **23/23 files,
  0 differing pixels**. The 22 presets are bit-stable across every capture taken
  so far.

## Open

- The showcase's EV-card caption (`sub-label: {value: ev.charge.range}`) renders
  `313` or `313 km`, roughly 50/50, **in the full showcase only**.
  Ruled out: settle (14 s, 30 s, 60 s), publish delay (50 ms … 6 s, and
  injecting the values after the dashboard has settled), `PYTHONHASHSEED`.
  A minimal one-gauge fragment with the same caption is stable (5/5), so it
  needs two consumers of the same key — the showcase also shows
  `ev.charge.range` in a `realtime.text`. Suspect: two displays sharing one
  value source, where the first format converts the unit in place.
- Then: re-run `selfcheck`, re-capture `.render-diff/baseline/`, and start the
  refactor proper, diffing after each commit.

## Reproduce

```sh
cd .claude/worktrees/blackfish-meter
poetry run python src/LevityDash/devtools/render_diff.py selfcheck .render-diff/s1 --jobs 6
poetry run python src/LevityDash/devtools/render_diff.py compare A B --verbose
```

## Queued asks from Neal (not part of phase 2)

- **Fill cap options.** `fill:` should take the same `cap:` the arc has.
  `GaugeFill` hard-codes `FlatCap` (Gauge.py:3010); `GaugeZones` does the same
  at :2778 and :2788.
- **Track-end fine-tune.** The drawn END of an arc/fill/line needs a small
  adjustment so it can be made to line up with the ticks: a square cap may
  overlap the tick, but the author needs a nudge to make it sit right. It
  belongs to the track stroke, never to the ticks, and ticks must render
  identically under every cap type. Screenshots:
  `~/Library/Application Support/Hermes/composer-images/image_101e94.png` and
  `image_9fa70e.png`.

## Findings for the report to Opus/Neal

- `Gauge.py:4344` uses `Any` without importing it, so `import LevityDash.lib`
  raises `NameError` on Python 3.13. Invisible on 3.14 (PEP 649 defers
  annotation evaluation). `pyproject.toml` declares 3.13–3.14.
- `render_dashboard.py --scenario X` with no `--seed` hangs forever: the design
  seed enables Mock, and Mock's ticker thread keeps the process alive after the
  PNG is written.
- A value that reaches its display before the display has resolved the
  configured unit is formatted with the source unit and never re-formatted:
  `ev.charge.range` reads `313` (km) or `194` (mi, what `[Units] length = mi`
  asks for) in otherwise identical renders.

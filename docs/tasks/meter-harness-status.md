# Meter harness — phase 2 working note

**Status: in progress, 2026-10-05.** This is not a brief; the brief is
[meter-and-bar.md](meter-and-bar.md) and phase 1's survey is
[meter-survey.md](meter-survey.md).

Branch `refactor/meter`, worktree `.claude/worktrees/blackfish-meter`.
Captures are local and gitignored: `.render-diff/`.

## Done

### The refactor, step by step

Each step is its own commit on `refactor/meter`, and each one is diffed against
the baseline before it lands. "Clean" below means `render_diff compare` against
`.render-diff/baseline/` reports no pixel over the anti-aliasing level, except
where noted.

- `f21b6a2` **helpers** — `filter_factors`, `_isWholeSteps`, `formatDuration`,
  `shortestDelta`, `CLOCK_HANDS`, `clockTurn`, `parseClockTime`,
  `decode_measurement` move to `meter/scale.py`; `Gauge.py` imports them back, so
  every existing import site is unchanged. Bodies verified byte-identical to
  HEAD's. 23/23 clean.
- `5413d67` **tracks** — `meter/track.py`: `Track`, `ArcTrack`, `LineTrack`.
  `GaugeArc.draw` builds its path with `ArcTrack.subPath(0, 1)`;
  `tests/ui/test_meter_track.py` pins the new path against the old hand-built one
  element for element over six angle ranges. 22/23 clean, the one difference
  being the EV caption region named below.
- `fdfd15e` **scale** — `meter/scale.py`'s `Scale` (min + span, `toT`, `fromT`,
  `spanOf`, `wrap`), and `Gauge.value_to_angle` is now
  `startAngle + t * fullAngle`. `Gauge.value_scale` carries the range;
  `from_span` exists because the gauge holds `rounded_min`/`rounded_range`, and
  `min + span - min` is not always `span` in floats. Pinned against the old
  inline arithmetic bit for bit inside the range, 1e-12 past the ends, over nine
  range/angle/wrap combinations. 22/23 clean, same caption region.
- Next: the rest of the degrees arithmetic — `value_to_angle_degrees`,
  `angle_degrees_to_value`, `GaugeMarker._markerAngle`, `GaugeZones._angle`,
  `GaugeFill._angles`. Then ticks through `track.pointAt(t)`/`normalAt(t)`, then
  zones and fills through `track.subPath(t0, t1)`, then `Meter` itself, then
  `Gauge(Meter)`, then `Bar`.

### The harness itself

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
- `compare` prints each differing cluster's bounding box and writes a diff image
  per mismatch, so reviewing a diff is a glance rather than a hunt.
- **One mask, named and reported** (Opus, 2026-10-05: phase 2's bar is "clean
  everywhere except that one named region"): `MASKS` in `render_diff.py` holds
  `ev-caption` for `gauge-showcase`, the EV caption's unit word, with the render
  size it was measured at and the condition for removing it (when
  `fix/caption-unit-race` merges). Every comparison reports the pixels it
  masked -
  `gauge-showcase  0 px >30  (0.00%)  max Δ166  masked 409 px (ev-caption)` -
  and `--no-mask` turns the mask off to show the raw difference and the diff
  image. A mask whose recorded size no longer matches the capture is skipped
  with a warning rather than silently blocking a region.
- Three consecutive captures of unchanged code (`--jobs 6`) came back
  **bit-identical: 23/23 files, 0 differing pixels** — usually true, but the EV
  caption's unit word is a per-capture coin flip, so a comparison can also come
  back with one file and ~400 px, in that one named region. The pre-refactor
  baseline is `.render-diff/baseline/`; `baseline2` and `baseline3` are the same
  render again. Captures are local (gitignored).

## Open

- The EV caption's unit word is a **per-capture coin flip**, not a property of
  the code. Measured 2026-10-05 with the refactor's own steps: `s3-scale` and
  `s4-recheck` are the *same commit* and differ by 409 px in exactly this
  region (`s3` renders `313`, `s4` renders `313 km`). Across seven captures the
  region read `313 km` five times and `313` twice. An earlier three-in-a-row of
  identical captures was luck; this is the flip, and it is *not* caused by the
  refactor - which is why the rule is a guide. `s1-scale`, `baseline`,
  `baseline2` and `baseline3` all read `313 km`; `s2-track` and `s3-scale` read
  `313`.
- The mechanism, as far as it was pinned down: the caption prints the unit only
  when the value it is handed is a `Measurement`, and prints a bare number when
  it is a float; it never re-formats. Whatever decides which of those two it
  gets is not the settle time, the publish delay, the publish count, or the
  hash seed (all ruled out by measurement).
- Ruled out along the way, each by measurement: settle (14 s, 30 s, 60 s),
  publish delay (50 ms … 6 s), injecting the values after the dashboard has
  settled, `PYTHONHASHSEED`, and publishing twice. Minimal repros were stable
  too: a one-gauge fragment with the same bound caption (5/5), and a
  two-consumer fragment — gauge caption + `realtime.text` on one key (6/6) —
  so the flip needs the full showcase as well as a reused seed.
- **Where a diff is expected, if one appears**: the EV caption
  (`sub-label: {value: ev.charge.range}`, showcase, x172-238 y767-782) and thin
  needle marks in `needle-designs` (x11-24 y436-438). Both are ~450 px clumps.
  `compare` prints each cluster's bounding box, so they are recognisable at a
  glance, and every diff it writes gets looked at.
- Publishing twice does change those two marks versus a single publish — a
  second update re-settles an element that animates on change. It is kept: three
  captures are identical with it, and a live dashboard sees values arrive again.
- Neal's ruling on the rule itself (2026-10-05: "sounds like an extreme gate, I
  wouldn't sweat that too much", plus "a lot of automatic positioning … hard to
  pin down deterministically"): pixel-exactness is a *guide*. `compare` reports
  per-file counts and regions and writes diff images; a diff is reviewed, not
  treated as an automatic failure.
- Then: start the refactor proper, diffing after each commit.

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
- `render_dashboard.py --scenario` **segfaults on a full dashboard** (rc=-11, no
  PNG), while a single-preset dashboard renders fine under the same conditions.
  This was first recorded as "hangs forever"; the current symptom is a crash, and
  the trigger is the *dashboard*, not the scenario, the publish delay, the settle
  or Mock — all measured. It does not affect this harness, which renders presets
  and the showcase. Written up with the repro and the faulting stack in
  [render-scenario-crash.md](render-scenario-crash.md).
- A value that reaches its display before the display has resolved the
  configured unit is formatted with the source unit and never re-formatted:
  `ev.charge.range` reads `313` (km) or `194` (mi, what `[Units] length = mi`
  asks for) in otherwise identical renders.
- A caption bound with `value:` prints a bare number when the value it is handed
  is a float rather than a `Measurement`; the caption never re-formats, so the
  unit word appears or not. Observed as the showcase's EV caption flipping
  between `313` and `313 km`, and only in the full showcase.

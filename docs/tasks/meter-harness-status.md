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
- `204be55` **the size reference** — `Gauge.sizeAcross` / `sizeAlong` (Opus's
  wording: a call site names the meaning it wants). Thirteen sites resolve
  through `sizeAcross` now: tick length, the arc's weight, the needle's width,
  length, offset, hub, halo, tail dot, the zones' weights, the fill's weight and
  gap. Same function, same arguments, so the diff is empty. Left alone for their
  own steps: the caption/value-label sizes that use the dial's *diameter*
  (`radius * 2`) and the tick-*width* sizes that use the panel share
  (`baseWidth` - the same meaning on a bar).
- `d2580b5` **ticks through the track** — `Tick.draw` asks the track for a point
  and an outward direction (`pointAtAngle` / `normalAtAngle`) instead of doing
  its own cos/sin, in the angle convention `Tick.angle` already carries. 23/23
  clean.
  - Two findings: `QPainterPath` quantises arc angles to a 16th of a degree, so
    `arcMoveTo` is up to **0.199 px** off the marks' own arithmetic on a 400 px
    radius - placing marks through the Qt arc would have moved every tick, so
    `pointAtAngle` is the marks' arithmetic and `subPath` stays Qt's arc. They
    disagree by that 0.2 px; a test pins the gap, and making them agree is a
    **visible change for its own task**, not a refactor.
  - The harness earned its keep: the first version of this subtracted the 90°
    a tick's angle already carries, and **20 of 23 files / 2.0 M px** moved in
    one capture. Caught, fixed, re-measured clean.
- Next: `Meter` and `Gauge(Meter)` as one slice, handed over when it lands.

### The Meter slice, in steps

`Meter` cannot move before the items do: its state properties reference the item
classes, and `GaugeRange` is nested inside the `Gauge` class body today. So the
slice is a sequence, one family per commit, each moved verbatim and imported back
by `Gauge.py` (which keeps re-exporting every name the rest of the app imports):

- **M1a** (done) — `meter/elements.py`: `GaugeItem`, `StatefulGaugeItem`,
  `GaugePathItem`, `StatefulGaugePathItem`, plus `Numeric`/`GaugeValue` into
  `meter/scale.py`. `Gauge` is named through a lazy `gauge_class()` inside
  elements - a real import there would be a cycle, since a gauge imports this.
  Bodies verified verbatim except those two call sites, which a script checks.
- **M1b + M1c (done, folded into one step)** — `meter/elements.py`: `Graduations`,
  `Tick`, `SubTick`, `TickSurface`, then `GaugeTickText` and `GaugeTickTextGroup`.
  Folded because the state layer forced it: `StateProperty.returns` calls
  `typing.get_type_hints` on the getter at run time, and `Graduations.labels` is
  annotated `-> 'GaugeTickTextGroup'` - resolved against the module the method
  was *defined* in. With the group still in `Gauge.py`, that turned into a
  `NameError` the moment a gauge was built (the gauge would not build at all:
  9 test failures, 22 of 23 renders wrong). A lazy fetch at the call site, which
  is what the first attempt did, does not help: the name has to exist in the
  module. `tests/ui/test_meter_annotations.py` now walks every `StateProperty` in
  the package and touches `returns`, so the next step finds this in a second
  instead of an afternoon.
- `_gaugeKeyName` moved with the label code that logs with it, as
  `elements.gaugeKeyName`; `Gauge.py` imports it back under its old name so its
  own call sites are untouched.
- **M1f (done)** — `meter/elements.py`: `GaugeCaption`, `GaugeText`, `GaugeLabel`,
  `GaugeValueLabel`, `GaugeUnit`, plus the two offset helpers only they used
  (`_decodeOffset`, `_shiftByOffset`) and the `_UNIT_UNDER_VALUE` constant, which
  both modules read. Two traps this step surfaced, both about *names*, which is
  where this split keeps biting:
  - the moved code had a runtime `isinstance(self.gauge, Gauge)`; a moved class
    names the display class through `gauge_class()` now, like the item bases;
  - `Text.surface` calls `typing.get_type_hints(type(self))` at layout time, so
    every *class-level* annotation on a moved class must resolve in
    `meter/elements.py`'s globals. `GaugeUnit.surface: Gauge` failed there (a
    NameError mid-layout, which surfaced as a segfault in pytest's own failure
    reporting - see below). `meter.elements` now declares `Gauge = None` and
    `GaugeArc = None`, and `Gauge.py` hands the real classes over at its foot.
    `tests/ui/test_meter_annotations.py` grew a test that runs `get_type_hints`
    on every class in the package, mirroring the app's own call.
  - **Ruff is worth having.** No linter ships with the repo, so I installed one
    into this worktree's venv (`pip install ruff`, machine-local, not in
    pyproject): `ruff check --select F821,F811 <files>` catches an undefined name
    in one second. It found the `GaugeArc` annotation, and it would have found the
    two missing import-backs. What it cannot catch is a right name holding the
    wrong object - `from copy import copy` where the code wanted the module - and
    that was a 4-file pixel difference. The harness is still the real gate.
  - **A failing test can look like a crash.** The first attempt did not report a
    failure: it segfaulted, because pytest's failure repr called
    `Label.__rich_repr__` → `textBox` → `Text.__init__` → recursion until the C
    stack ran out. `--tb=native` printed the actual `NameError`. Worth knowing
    before chasing a phantom Qt bug: if a test run dies with a stack dump, re-run
    that file with `--tb=native --tb=no`.
- **M1d (done)** `Needle`, `Arrow`, `GaugeMarker`; **M1e (done)** `GaugeZones`,
  `GaugeFill` + `_FillEnd`. Each moved verbatim, each gated on the suite and a
  capture.
- **M2b, batch 1 (done)** — `Meter(Display)` exists in `meter/meter.py`, and the
  label/caption machinery moved into it: `_buildLabel`, `valueLabel`, `unitLabel`,
  `subLabel`, `caption` and their helpers and fields (15 member groups), moved
  verbatim apart from three `_gaugeKeyName` → `gaugeKeyName` renames in warning
  paths. **`Gauge` now derives from `Meter`** rather than `Display`, which is not
  cosmetic: a class's state items are a `ChainMap` seeded from its *parent's*
  `__state_items__` (statekit's metaclass, `core.py:1829`), so a member moved to a
  class the child does not inherit from stops being a state item of the child.
  Without the base change `refresh()` died on `AttributeError: 'Gauge' object has
  no attribute 'valueLabel'` - a member that is defined, has a factory, and is
  simply invisible to the machine that builds it.
- **M2b, batch 2 (done)** — the value side: `value`/`_value`/`valueChanged`,
  `valueClass`/`_valueClass`, `updateSlot`, `value_scale`, `range` (all four
  definitions). One check earned its place first: Python mangles
  double-underscore class attributes, so a moved member reading `self.__value`
  would silently look for `_Meter__value`. The only such attribute is `__value`,
  written but never read, by `_init_defaults_` - which stays in Gauge. Scripted
  it rather than reading 1,300 lines for `__` names.
  `animateValue`/`duration`/`easing`/`_needleAnimation` stay with the needle;
  they move when a pointer abstraction does (phase 3).
- Tooling: `move_members.py` moves a *member group* - every definition sharing a
  name, decorators included, since `@prop.factory`/`@prop.setter` are evaluated in
  the class body and only work beside their base property. Its first version
  inserted member by member and renumbered the lines under itself, mangling the
  target class *after* writing both files; it inserts one block now, and every
  move is validated on copies in scratch before the worktree sees it.
- **M3** `GaugeArc` and the arc-specific label overrides into `meter/gauge.py`;
  `Gauge.py` becomes the shim.
- The remaining batches, and two read-only jobs beside them (an audit of
  every move so far, and the M3 recon), are briefed in
  `docs/tasks/meter-m2b-remaining.md`.
- **M2b, batches 3 and 4 (done)** — `80fcfe2` the layout (alignment, anchor,
  inset, center_offset, the side rects, `_dialRect`, `center`, `scene_center`,
  `baseWidth`, `setRect`, `pen`, `defaultColor`, `displayType`, `type`,
  `parentResized`, `_update_shape`, `rebuild`, `releaseSources`: 28 member
  groups), `210b3d9` the item holders (`needle`, `fill`, `zones`, `markers`, the
  three divisions and their clear/item helpers, plus `_markerText` moved by hand
  since it is a module-level function, not a member). `Gauge.py` 1,292 -> 835
  lines. Byte-identity spot-checked against `fd873b5`: only the documented
  `gaugeKeyName` renames differ.
- **The audit** (`meter-split-audit.md`) re-derived every move independently. Two
  corrections to this note and the brief, both mine: `label_group_class()` does
  not exist anywhere (it was removed in M1c, not kept - the brief listed a swap
  that is gone), and the `GaugeArc` annotation is unquoted with a `None` sentinel
  rather than quoted. It also caught something the note should say plainly: **the
  working tree is genuinely broken between a member move and its import fix** - a
  capture run in that window failed 20 of 23 renders with `NameError: QPointF`.
  That is why every batch is committed only green, and why read-only work in a
  shared tree must read committed revisions (`git show <rev>:<path>`), not the
  working copy.
- **The M3 plan** is `meter-m3-recon.md`: the shim's export list by file:line
  (`Gauge` 4 sites, `Needle` 1, `GaugeTickTextGroup` 1, `_isWholeSteps` 1,
  `clockTurn`/`formatDuration`/`parseClockTime`/`shortestDelta` 1), 33 meter-package
  names the shim must keep or `Displays.<name>` disappears, and the traps - the
  elements `__all__` is too small for a star import to carry the classes, the
  hand-over belongs at the foot of `meter/gauge.py`, `meter/__init__.py` must stay
  docstring-only, and the two shadowed `radius`/`value_to_angle` definitions must
  move in order.

Every step ends with the suite and a capture against the baseline. Renames the
survey proposes (`GaugeItem` → `MeterItem` and friends) come after the package is
assembled, as one names-only commit, so the moves stay reviewable.

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
- The showcase's two clock cards follow the app clock (`shared.now()`), so
  `--freeze-time` pins their hands for a capture, and a live board still tells
  the time. `49c1623` fixed the cause - `Gauge._tickClock` read `datetime.now()`
  directly, so a frozen render drew a *live* hand, and the `at:` pins stood in
  for the freeze instead. The pins are gone (`clock.levity`'s own are its
  design, untouched). The pre-refactor baseline was **re-taken** after this,
  because the hands legitimately moved from the pinned `10:08:36` to the frozen
  time; the old one is kept as `.render-diff/baseline-pinned`.
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

## The sync merge (2026-10-05)

`feat/value-sources` moved 34 commits ahead while the refactor ran, six of them
touching `Gauge.py` (+215/-59). The merge (`5dea824`, parents `3633c5f` +
`a31af10`) was resolved by keeping this branch's structure and porting each
upstream change to the module that owns the member now — the glow set, the
`GlowMixin` bases, `resolve_gradient`, the end-label positions, `fill_brush`,
`GaugeCaption._placeWarped`. `.render-diff/tools/port_list.py` generates the work
list and judges the result (it reads git objects, so it works mid-merge, and it
takes `--rev` — judging against a *moving* upstream ref reported 17 members from
commits that were never part of the merge). Verified after: 578 tests pass (upstream
brought two new test files), ruff shows only the two pre-existing F811s in
`Gauge.py` plus three F821s in upstream's own `colors/` files (byte-identical to
a31af10, so not ours), and the port's four remaining hunks are this branch's own
documented edits: three `gaugeKeyName` renames and one `sizeAcross` call.

**emissive cannot be the glow cover as the harness stands.** It is the only preset
using `glow:`, and it does not render reliably: a shutdown segfault
(`libshiboken: Internal C++ object (LevitySceneView) already deleted`, raised from
`Annotations.limitRect` via `app.viewScale` — files this branch never touched),
sometimes no PNG at all, and 3239 px of difference between two captures of the
same code. A separate job is measuring whether that is pre-existing at upstream's
tip; until it is settled, the capture set carries emissive but the baseline cannot
be called stable.

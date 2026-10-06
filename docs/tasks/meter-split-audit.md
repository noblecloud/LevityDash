# Meter split audit — is every moved member byte-identical?

**Job B of [meter-m2b-remaining.md](meter-m2b-remaining.md). Read-only audit: this document is
the only file written; no source file was touched.**

Central claim under test: *every class and member this branch calls "moved" is byte-identical to
its original text, except where the branch documents a change.*

- **Revision audited:** `210b3d9` (`refactor(Meter): the item holders move to Meter`),
  `git rev-parse HEAD` = `210b3d9280267400c3494004e00b90e2eaf3d421`, read 2026-10-05.
  The audit began while HEAD was `1922538` and followed it as Job A committed batch 3
  (`80fcfe2`) and batch 4 (`210b3d9`) *during* the audit; every step was re-run against the
  final revision.
- **Method.** For every commit that moved members out of `Gauge.py`, each named definition's
  source text is extracted with `ast` from the file at that commit's **parent**
  (`git show <commit>^:.../Gauge.py`) and from the target module **at HEAD**, then compared
  line for line. Indentation is normalised, because one member (`GaugeRange`) moved out of the
  `Gauge` class body (nested, one tab) to module level. A member "group" means every definition
  sharing a name — the `@StateProperty` getter/setter/decode/encode idiom — compared in order.
- **Reproduce:** `python src/LevityDash/devtools/render_diff_tools/split_audit.py` (all steps) or
  `python src/LevityDash/devtools/render_diff_tools/split_audit.py <commit>` (one step). Read-only (`git show` only).
  The tool is new, lives in the gitignored `.render-diff/` beside `check_move.py`/`diff_member.py`,
  and is the "command that shows it" for every row below.
- **The tree was being written while this ran.** Job A committed batches 3 and 4 *during* the
  audit, so for stretches the working tree was mid-move. Every number in the gate section was
  therefore measured either from a pristine `git archive <commit>` copy or against the now-clean
  working tree at `210b3d9`; the transient failures that mid-move state produced are recorded
  under "Where the claim does not hold", because they happened and matter.

## Verdict table

| step | commit | names moved | verdict | command |
| --- | --- | --- | --- | --- |
| pure helpers → `meter/scale.py` | `f21b6a2` | `filter_factors`, `_isWholeSteps`, `formatDuration`, `shortestDelta`, `CLOCK_HANDS`, `clockTurn`, `parseClockTime`, `decode_measurement` | **8/8 identical** | `split_audit.py f21b6a2` |
| `Numeric`, `GaugeValue` → `meter/scale.py` | `26a79e3` | `Numeric`, `GaugeValue` | **2/2 identical** | `split_audit.py 26a79e3` |
| item bases → `meter/elements.py` | `26a79e3` | `GaugeItem`, `StatefulGaugeItem`, `GaugePathItem`, `StatefulGaugePathItem` | **2 identical; 2 identical-modulo `gauge_class()`** (`GaugeItem`, `GaugePathItem`) | `split_audit.py 26a79e3` |
| ticks + tick labels → `meter/elements.py` | `2b7e68b` | `Graduations`, `Tick`, `SubTick`, `TickSurface`, `GaugeTickText`, `GaugeTickTextGroup` | **5 identical; `GaugeTickTextGroup` identical-modulo `_gaugeKeyName`→`gaugeKeyName`** (applied in a later commit) | `split_audit.py 2b7e68b` |
| needle/arrow/markers → `meter/elements.py` | `1291bc6` | `Needle`, `Arrow`, `GaugeMarker` | **2 identical; `GaugeMarker` identical-modulo rename** | `split_audit.py 1291bc6` |
| zones + fill → `meter/elements.py` | `fae5d57` | `GaugeZones`, `GaugeFill`, `_FillEnd` | **`_FillEnd` identical; `GaugeZones`, `GaugeFill` identical-modulo rename** | `split_audit.py fae5d57` |
| label family → `meter/elements.py` | `c34db29` | `GaugeCaption`, `GaugeText`, `GaugeLabel`, `GaugeValueLabel`, `GaugeUnit`, `_decodeOffset`, `_shiftByOffset`, `_UNIT_UNDER_VALUE` | **5 identical; `GaugeCaption`/`GaugeValueLabel` rename; `GaugeLabel` `gauge_class()`** | `split_audit.py c34db29` |
| `GaugeRange` → `meter/meter.py` | `14ac71f` | `GaugeRange` | **identical** (modulo the one-tab nesting indent) | `split_audit.py 14ac71f` |
| `Meter` label/caption batch | `b76cac9` | `_buildLabel`, `_captionItem`, `_captionItems`, `_clearCaption`, `_decodeCaption`, `_setCaption`, `_subItem`, `_syncCaptions`, `_syncUnitUnderValue`, `_unit`, `_valueAnchor`, `caption`, `subLabel`, `unitLabel`, `valueLabel` | **12 identical; `_setCaption`, `_syncUnitUnderValue`, `_valueAnchor` identical-modulo rename** | `split_audit.py b76cac9` |
| `Meter` value batch | `a3f1291` | `_value`, `_valueClass`, `range`, `updateSlot`, `value`, `valueChanged`, `valueClass`, `value_scale` | **8/8 identical** | `split_audit.py a3f1291` |
| `Meter` layout batch | `80fcfe2` | `_ANCHORS`, `_anchor`, `_captionSpec`, `_center_offset`, `_dialRect`, `_s_inset`, `_sideStripWidth`, `_sideValueRect`, `_subSpec`, `_update_shape`, `_valueSide`, `alignment`, `anchor`, `baseWidth`, `center`, `center_offset`, `defaultColor`, `displayType`, `inset`, `insetPx`, `parentResized`, `pen`, `rebuild`, `releaseSources`, `scene_center`, `setRect`, `type`, `update_center_offset` | **27 identical; `releaseSources` identical-modulo rename** | `split_audit.py 80fcfe2` |
| `Meter` item-holders batch | `210b3d9` | `_markerText` (module) + `_clearFill`, `_clearMarkers`, `_clearZones`, `_fillItems`, `_zoneItems`, `fill`, `majorDivisions`, `markers`, `microDivisions`, `minorDivisions`, `needle`, `zones` | **10 identical; `fill`, `markers`, `zones` identical-modulo rename** | `split_audit.py 210b3d9` |
| `_gaugeKeyName` → `gaugeKeyName` | `2b7e68b` | `gaugeKeyName` | **identical-modulo the rename — plus one extra, undocumented docstring re-quote (see below)** | `split_audit.py 2b7e68b`; `git show 2b7e68b^:.../Gauge.py` vs `:.../meter/elements.py` |
| `Gauge` base class | `b76cac9` | `class Gauge` | **`class Gauge(Display)` → `class Gauge(Meter)`, exactly as documented** | `git show b76cac9^:.../Gauge.py \| grep '^class Gauge'` |

Steps whose members are checked but that are **not moves** (reported so they are not mistaken for
one):

| step | commit | names | verdict | command |
| --- | --- | --- | --- | --- |
| `Scale` | `fdfd15e` | `Scale` (`meter/scale.py`) | **new class, not a move** — `class Scale` is absent at `fdfd15e^`; behaviour pinned by `tests/ui/test_meter_scale.py` (old inline degrees vs new `startAngle + t*fullAngle`, bit-for-bit in range, 1e-12 past the ends, 9 range/angle/wrap cases) | `git show fdfd15e^:.../Gauge.py \| grep -c 'class Scale'` → 0 |
| `Track`/`ArcTrack`/`LineTrack` | `5413d67` | `meter/track.py` | **new module, not a move** — no `meter/track.py` at `5413d67^`; `ArcTrack.subPath` pinned against the hand-built path by `tests/ui/test_meter_track.py` over 6 angle ranges | `git cat-file -e 5413d67^:.../meter/track.py` → absent |
| size reference | `204be55` | `sizeAcross`/`sizeAlong` | in-place edit; no member changed package | `git show 204be55 --stat` |
| ticks through the track | `d2580b5` | `Tick.draw`, `ArcTrack` | in-place edit; no member changed package | `git show d2580b5 --stat` |

**Totals:** 99 moved member-name checks over 11 steps — **83 byte-identical**, **16 changed**, and
all 16 change by exactly one documented mechanism (`gauge_class()` swap, or the
`_gaugeKeyName`→`gaugeKeyName` rename), checked hunk by hunk.

### The documented changes, as the diffs actually show them

- **`gauge_class()` lazy swap** — 5 call sites in 3 member groups: `GaugeItem` (3),
  `GaugePathItem` (1), `GaugeLabel` (1). The original text named `Gauge` directly; the moved item
  cannot import it (a cycle), so it resolves the class lazily. Every other line of those members
  is unchanged.
- **`_gaugeKeyName` → `gaugeKeyName`** — the helper's name only, across the label, marker, zone,
  fill, caption and value-label members, `releaseSources`, and the `_setCaption` /
  `_syncUnitUnderValue` / `_valueAnchor` / `fill` / `markers` / `zones` holders. Log message text
  is unchanged.
- **`GaugeRange`** — identical once the one-tab nesting indent is normalised away.
- **`Gauge(Meter)`** — the base class, changed in `b76cac9`, exactly as documented (a class's
  state items are seeded from its parent's `__state_items__`, so the base change is what keeps
  the moved members visible to `Gauge`'s state machine).

## Gate — the real numbers

- `pytest tests -q -p no:warnings` @ `210b3d9` (clean working tree): **552 passed, 1 skipped** in
  42.42s. From a pristine `git archive 80fcfe2` copy: **552 passed, 1 skipped** in 42.61s.
  (An earlier run against the live, half-moved tree collected **11 errors** — transient; see below.)
- `ruff check --no-cache --select F821,F811 .../meter/ .../Gauge.py` @ `210b3d9`: **2 errors**,
  both the pre-existing F811s — shadowed `radius` (`Gauge.py:559`, previous def `:555`) and
  shadowed `value_to_angle` (`Gauge.py:617`, previous def `:536`). **No F821, nothing new.**
  The brief says to expect "only the 2 known F811s"; that is what it is.
- `render_diff.py capture .render-diff/audit-210 --jobs 3` then
  `compare .render-diff/baseline .render-diff/audit-210` @ `210b3d9`:
  `23 files compared: 23 clean, 0 over tolerance, 0 with a size change` /
  `total differing pixels (>30 levels): 0`. Same result at `80fcfe2` from a pristine copy.
  The named `ev-caption` mask (~409 px) was **not exercised**: the caption coin-flip landed on
  the baseline's side in both captures, so there was nothing to mask. The mask guard is ready
  but this run did not need it.

## What I could not verify

- **`label_group_class()`** — the brief lists it as a documented lazy swap in `meter/elements.py`.
  No such name exists anywhere in `src/`, `tests/` or `docs/`; only the brief mentions it. The
  only lazy swap actually implemented is `gauge_class()`. If a `label_group_class()` swap is
  still intended, it is not in the tree at `210b3d9`.
- **The "quoted `GaugeArc` annotation"** — there is no quoted `'GaugeArc'` annotation anywhere.
  `GaugeArc` appears as an **unquoted** local annotation in `GaugeValueLabel.getTextPosition`
  (`arc: GaugeArc = gauge.arc`, `elements.py:3927`); ruff's F821 for it is resolved by the
  `GaugeArc = None` sentinel at `elements.py:77`, not by quoting. The quoted annotations that do
  exist are class-level (`surface: 'Gauge'`) and `Graduations.labels -> 'GaugeTickTextGroup'`;
  those rely on the `Gauge = None` sentinel plus the hand-over at the foot of `Gauge.py`, and are
  guarded by `tests/ui/test_meter_annotations.py`. So the *mechanism* the brief refers to exists
  and is guarded; its name in the brief does not match the tree.
- **The rendered images themselves.** I verified 23/23 clean and 0 differing pixels; I did not
  open every PNG. That is the harness's verdict, not my eyes.
- **`Scale`/`Track` "byte-identical"** is not testable by text comparison — they are new classes
  with no original. I verified they are new and that their behavioural tests exist and are inside
  the passing 552; I did not re-derive their internal arithmetic by hand.

## Where the claim does NOT hold

1. **`_gaugeKeyName` → `gaugeKeyName` is not a pure rename.** The docstring's inline-code quoting
   changed with it: `` ``gauge`` `` (Gauge.py at `2b7e68b^`) became `` `gauge` ``
   (`meter/elements.py:93` at HEAD). Behaviour is identical; the text is not byte-identical, and
   this is the only difference in a moved member that is not on the brief's documented list.
2. **"The gate passes at every HEAD" was false of the *working tree* for a time.** Run against
   the live tree while Job A's batch 3 was uncommitted, the capture failed **20 of 23 renders**
   with `NameError: name 'QPointF' is not defined` (the half-applied `_center_offset` move into
   `meter/meter.py`), and a `pytest` run collected **11 errors**. Both came from the *uncommitted*
   mid-move state, not from any committed revision — the committed `80fcfe2` and `210b3d9` both
   pass the full gate — but anyone re-running the gate while a batch is in flight will see them,
   and they are not a property of the branch.

Otherwise the central claim holds: **83 of 99 moved member-name checks are byte-identical** to
their original text, and the 16 that differ do so only by a documented `gauge_class()` swap or
`_gaugeKeyName`→`gaugeKeyName` rename.

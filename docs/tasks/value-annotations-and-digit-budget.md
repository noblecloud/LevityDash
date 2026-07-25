# Value annotations + making the digit budget real

Three interlocking pieces that together fix small-value display. They are
listed in dependency order — the third is unsafe to build without the first
two, and the first two are half-measures without the third.

## Context

A precipitation rate of `0.01 in/hr` overflows its panel and collides with
the neighbouring column. Two smaller values are indistinguishable from "no
reading at all": `0.004 in/hr` renders `'0.00'`, and true zero renders
`'0'`.

The author had previously encoded a semantic distinction in that difference
— `0` meaning *no reading*, `0.0` meaning *near zero but not quite*. That
scheme should be **retired**, for three reasons:

1. It is undiscoverable. The author, who devised it, was unsure of it.
2. It is load-bearing on display logic. The `0` vs `0.00` difference is a
   side effect of dynamic precision selection, driven by the digit budget —
   change `max` or `precision` in config and the "meaning" silently changes.
3. **Null already has a representation**: `⋯`, via `nullValue`
   (`Realtime.py`; `format()` returns `⋯` for `None`). It is visible on the
   live dashboard today for Today/Expected/Time/Lightning/Last Strike. So
   `0` is free to just mean zero.

Verified current behavior (US config, `precipitationRate = precision=2`
`us.ini:45`, `max = 3` `us.ini:17`):

```
Inch(0.0)     -> '0 in/hr'      precision 0
Inch(0.004)   -> '0.00 in/hr'   precision 2   <- indistinguishable from zero
Inch(0.01)    -> '0.01 in/hr'   precision 2
```

---

## 1. `max` is not enforced below 1 (WeatherUnits) — bug

`_SmartFloat.py:870` gates the entire `max` clamping block behind
`if float(value) > 1:`. Sub-1 values never have precision recomputed or
clamped, so **`max` is fiction for exactly the values that need it**:

```
Inch(0.004)  ->  '0.00'  at max=3, max=2, AND max=1   # 3 digits on a 1-digit budget
Inch(1.25)   ->  '1.2'   at max=1                     # correctly clamped
```

### ⚠️ Attempted 2026-07-25 and reverted — items 1 and 2 must land TOGETHER

The one-line fix is easy (`precision = max(min(p, max - intLength), 0)` in
the `else` branch) and the behavior matrix showed it doing exactly the right
thing. **It was reverted because it regresses the live dashboard.**

The shipped config (`resources/example-config/config.ini:97`, and the
author's live `config.ini:99`) says:

```ini
precipitationRate = precision=2, max=2
```

That is **internally contradictory**: `precision=2` asks for hundredths,
but `0.01` needs *three* digits (`0`,`0`,`1`) and `max=2` allows two. It
has only ever "worked" because `max` was inert here — precision won by
default and the value rendered one digit over its stated budget.

Enforce `max` on its own and precipitation goes `0.01` → **`0.0`**, i.e.
unreadable. Strictly worse than the bug.

This also sharpens the diagnosis of the panel overflow: the value is
rendering **wider than its own configured budget**, so any layout sized
from that budget will be overrun by exactly one digit. That is consistent
with the observed "overlaps a lil".

**Resolution — `leadingZero` is what makes the config coherent.** With the
leading zero dropped, `.01` is two digits: it satisfies `max=2` *and*
`precision=2` simultaneously, which is evidently what the config always
meant.

| | `max=2`, `precision=2` |
|---|---|
| today (max inert) | `0.01` — right value, 3 digits, over budget |
| item 1 alone | `0.0` — in budget, **information destroyed** |
| items 1 + 2 | `.01` — right value, 2 digits, in budget ✅ |

So the ordering in this brief is a **dependency, not a sequence**: ship 1
and 2 in one change, or neither.

**Also found:** `Length.Foot(5120)` currently renders `'0.970 mi'` — four
digits on Length's 3-digit budget, with a trailing zero carrying no
information. Item 1 correctly makes it `'0.97 mi'`. Harmless, but it means
`tests/test_formatting.py::test_values_are_rescaled_to_fit_the_max_digit_budget`
needs updating as part of the change, not working around.

**Care required:** this changes rendered output for every sub-1 value in the
app. Guard with the before/after behavior matrix (8 unit types × ~33 specs,
the harness used for the `:`-separator and `type=f` fixes) and a live
dashboard render diff. Note the LevityDash suite is the one that catches
config-dependent breakage — `tests/wire/test_codec.py`'s precipitation
assertion failed only under the app's config, not WeatherUnits' own.

## 2. `leadingZero` (WeatherUnits) — already written, commented out

`_SmartFloat.py:927` still carries the implementation:

```python
# if 0 < floatValue < 1 and not params['value'].startswith('0.0'):
# 	params['value'] = params['value'].lstrip('0')
```

`leadingZero` is declared and documented in `config/template.ini`
("Display zero before values less than 1") and consumed nowhere — see
`docs/formatting.md`.

**The guard is backwards for this use case.** `not ....startswith('0.0')`
strips `0.5` → `.5` but *skips* `0.01`, which is precisely where the space
is needed.

Dropping the leading zero **frees exactly one digit of budget**, which at
`max=3` buys a whole extra decimal place — enough that most real
precipitation values become visible rather than needing a marker at all:

| | with leading `0` | without |
|---|---|---|
| max=3 | `0.01` | `.001` |
| max=2 | `0.0` (reads as zero) | `.01` |

Keep it an **option**, not a default: the leading zero carries no
information for a sub-1 value, but it is a legibility convention, and
whether to drop it depends on viewing distance — a wall display and a dense
panel want different answers. That is a taste call the engine cannot make.

## 3. Value annotations (LevityDash, and partly WeatherUnits) — new

A channel for "display this alongside the value to make it clearer, **if you
can**" — presentational metadata the renderer may surface or drop depending
on available space.

This fixes a **layering** problem. Baking `≲` into the formatted string
forces the formatting layer to know how much room it has; it doesn't and
can't. Instead the value states a fact ("nonzero but below display
resolution") and the layout layer decides whether to show it.

**Not speculative — the pattern already exists twice, ad hoc:**

| case | current mechanism |
|---|---|
| no reading | `nullValue` → `⋯` |
| stale reading | `TimeOffsetLabel` → the "31 s ago" on the live dashboard |
| below resolution | *nothing* |

### Derived vs assigned

- **Derived** — computed from what is already present, by anyone holding the
  value. *Trace*: `value != 0 and round(value, precision) == 0`. *Stale*:
  from the timestamp. Needs no wire, no plugin, no schema changes, and
  **cannot desync from the value it describes**, because it is recomputed
  from that value.
- **Assigned** — must be told, because the number doesn't reveal it:
  *estimated vs measured*, *sensor fault*, *clamped*. Requires a plugin API,
  schema support, codec work, and a version-compat rule (an older backend
  sends none — absence must mean *unknown*, not *false*).

### Staged plan

**v1: derived only.** Covers trace and staleness — both things wanted today
— at near-zero cost. Defer assigned annotations.

This is safe to stage because **the consumer side is identical for both
kinds**. A renderer asks what annotations a value carries; it never cares
whether the answer was computed or delivered:

```python
def annotations(value):
	yield from _derived(value)                       # v1
	yield from getattr(value, '_annotations', ())    # v2, additive
```

The v1 renderer keeps working untouched when v2 lands.

### Shape

Each annotation carries:

- **short form** — the glyph (`≲`, `~`) or icon
- **priority** — what to sacrifice first when several compete for one corner
  (stale + trace simultaneously is a real pairing). Without this, "if you
  can" has no way to choose.
- **kind/id** — so styling can target it, making "dim the value" available as
  an alternative to drawing a symbol

**Guardrail:** an annotation must change *how you read the number*. Trace,
stale, estimated qualify. It must not become a general notes field, or the
priority ordering stops meaning anything.

### Symbol choice

`≲` (U+2272 LESS-THAN OR EQUIVALENT TO) or `⪅` (U+2A85 LESS-THAN OR
APPROXIMATE — semantically exact but from a rarely-covered block). Both
confirmed present in Nunito via `QFontMetrics.inFont`. Prefer `≲` for
coverage odds. Verify a fallback glyph doesn't look stylistically off beside
Nunito's digits.

Rejected alternatives, with reasons worth not re-litigating:

- **`T` (meteorological "trace", NWS convention)** — domain-correct and
  zero-width, but the author didn't recognize it, which is strong evidence
  it is too cryptic for a glanceable display.
- **Combining overline/dot above (`0̄`, `0̇`)** — both already mean *repeating
  decimal*, so `0.0̄` reads as exactly zero: the opposite of the intent.
  Also depends on font GPOS mark positioning that a display face is unlikely
  to have tuned for digits.
- **Hardcoded `<0.01`** — the threshold is the smallest representable
  increment, so it must be *derived* (`10⁻ᵖ`) and shifts with the budget: at
  `max=2` it becomes `<0.1`. Always costs the full budget plus a symbol,
  i.e. widest exactly when there is least room.

### How the pieces compose

Dropping the leading zero **pays for** the marker — same width, more
meaning:

```
0.01    4 cells, 3 digits
≲.01    4 cells, 2 digits + marker
```

Giving a degradation ladder — information first, typography second,
exactness-honesty paid out of the typography budget:

| space | render | sacrificed |
|---|---|---|
| room | `0.01` | nothing |
| tight | `.01` | leading-zero convention |
| below resolution | `≲.01` | leading zero, to buy the marker |

## Verification

- Before/after behavior matrix around items 1 and 2 (both change rendered
  output library-wide).
- `pytest ../WeatherUnits/tests` and `poetry run pytest` in LevityDash —
  LevityDash renders every dashboard value through WeatherUnits, so it is
  the real integration check.
- Live render diff of the dashboard (offscreen `.grab()` harness, see
  CLAUDE.md) — confirm the precipitation panel stops overlapping and that
  no other panel's width shifts unexpectedly.
- Extend `WeatherUnits/tests/test_formatting.py`, which already pins the
  `30.0 -> '30'` gap and the precision/max table this work changes.

## Related

- `WeatherUnits/docs/formatting.md` — the parse pipeline, parameter table,
  and the four declared-but-unimplemented display options (`trailingZero`,
  `leadingZero`, `forcePrecision`, `sizeHint`). `sizeHint` ("override
  generated size hint string... when you know the expected max string
  length") is the intended lever for reserving layout width, and is the
  natural companion to item 3.
- `trailingZero`/`forcePrecision` are the intended fix for the separate
  `30.0 -> '30'` width-drift issue, also unimplemented.

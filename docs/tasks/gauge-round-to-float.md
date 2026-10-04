# `round_to` returns 1e-323 for any gauge narrower than 1 unit

**Status:** open, actionable. Recorded 2026-10-04.
**Base:** `feat/value-sources`. Step one: `git checkout -B fix/gauge-round-to-float feat/value-sources`.
**Model:** suits `levity-worker`. The fix direction is decided below; no design call is outstanding.

## Symptom

A gauge whose range is narrower than one unit cannot be constructed. The
failure surfaces as an unrelated-looking error, because the gauge dies partway
through `__init__`:

```
AttributeError: 'Gauge' object has no attribute '_needle'. Did you mean: 'needle'?
  src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Gauge.py:3795  needle getter
  ...:3799   @needle.factory
  ...:1544   Needle.__init__
  ...:1572   Needle.refresh
  ...:4446   value_to_angle

OverflowError: cannot convert float infinity to integer
  src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Gauge.py:3585  rounded_min
```

Reproducing fragment:

```yaml
- type: realtime.gauge
  name: g
  key: environment.pressure.pressure
  display:
    range: {min: 29.9, max: 30.1}
    major: {interval: 0.05}
```

The `_needle` AttributeError is a **symptom, not the cause**. Construction dies
before `needle` is set, so the getter finds nothing. Do not start there.

## Cause

`GaugeRange.round_to.item_default` (`Gauge.py:3533-3550`) picks the step the
range snaps to, by walking powers of ten down until one *exactly* divides the
span:

```python
_value_range = abs(float(self.max - self.min))
if 99 < _value_range <= 350:
    return 10
if log10(_value_range).is_integer():
    return _value_range / 10
_power = int(log10(_value_range)) + 1
while _value_range % 10 ** _power > 0:
    _power -= 1
return 10 ** round(_power)
```

For a span below 1, `int(log10(span))` is 0 or negative, so `_power` starts at
≤ 1 and walks into **negative** powers. Float `%` never returns exactly `0.0`,
so the walk keeps going until `10 ** _power` is small enough that the remainder
underflows to zero — at **`_power = -323`**, about 324 iterations.
`round_to` becomes `1e-323`.

Then `rounded_min` (`:3585`) computes `floor(float(29.9) / 1e-323)` =
`29900000000000`, which overflows when coerced into the unit, and `__init__`
never finishes.

Measured, current behaviour:

| range | span | `round_to` | note |
|---|---|---|---|
| 29.9–30.1 | 0.20000000000000284 | **1e-323** | 324 iterations, `_power` ends at −323 |
| 0–0.5 | 0.5 | **1e-323** | same path |
| 0–0.05 | 0.05 | **1e-323** | same path |
| 0–1 | 1.0 | 0.1 | decade branch, correct |
| 28–32 | 4.0 | 1 | correct |
| 950–1050 | 100.0 | 10 | correct |

The loop **is bounded** — it terminates at `_power = -323` — so this is a
precision question, not a hang. It was previously reported as an unbounded
loop; that was wrong, and the distinction matters: the cost is a garbage
`round_to`, not a hang.

**Blast radius is wider than sub-1 ranges.** Any span that is not an exact
multiple of a power of ten within float precision walks down. A span of 0.3
would stop at whatever power first divides it cleanly. Only spans that land on
a power of ten, or in the `99 < span <= 350` band, are safe today.

## Fix direction (decided)

Do not test exact float divisibility. `span % 10 ** p == 0` is the wrong
question — it is false for almost every real span, which is what produced the
walk into negative powers in the first place.

Pick the power from `floor(log10(span))` and ask whether the divisor divides
the span **within tolerance**:

```python
power = math.floor(math.log10(span))
divisor = 10 ** power
quotient = span / divisor
if math.isclose(quotient, round(quotient), rel_tol=1e-9):
    return divisor
```

`span / divisor` is then compared to its own rounding, which absorbs the
representation error that made the exact test fail.

Reusing the tick-rounding logic added for
[gauge-tick-label-format.md](gauge-tick-label-format.md) (the smallest `d` for
which values still round distinctly) is a reasonable alternative — the two
questions are cousins — but they are **not** the same question, so do not merge
them without checking that:

- `round_to` is the *step the range snaps to*, and it sets `rounded_min` and
  `rounded_max` (`:3581`, `:3623`), which in turn position **every tick**
  (`:832`, `:2850`, `:4446`).
- The 1c floor is the smallest number of decimals a *label* needs.

So for 29.9–30.1 with 0.05 ticks, `round_to` must divide 0.05, not 0.2.
Returning `0.1` — which divides 0.2 exactly — would snap the range to
29.9 / 30.0 / 30.1 and **drop the 29.95 and 30.05 half-steps**. That is
arithmetic-correct for the span and wrong for the dial. The fix must respect
the graduations, not just the span.

## Verify

- **Tests:** a new `tests/ui/test_gauge_round_to.py` asserting `round_to` for
  every range in the table above, plus the invariant that it never returns a
  value below `1e-12`, and that `floor(min / round_to)` stays finite. Cover at
  minimum: **29.9–30.1, 0–0.5, 0–1, 950–1050, 28–32**.
- **A 29.9–30.1 gauge builds** and renders. That is the regression that
  matters: today it raises before it draws.
- **A render** of a fine-scale dial, to confirm the half-steps survive:

  ```bash
  QT_QPA_PLATFORM=offscreen .venv/bin/python src/LevityDash/devtools/render_widget.py \
    --levity <a preset with a sub-1 range> --scenario hot-clear-day \
    --name gauge --out /tmp/round-to.png --scale 3
  ```

  (No preset currently has a sub-1 range; one may need writing. `render_widget.py`'s
  `--help` prints the *app's* CLI, not its own — the real usage is in its
  module docstring.)

- **No change** for 0–1, 950–1050, 28–32. Those already work; the fix must not
  move them.

## Also broken on a fine-scale range, NOT fixed here

With `round_to` repaired the 29.9-30.1 gauge **constructs and renders** - the
crash is gone. But it draws **no graduations at all**, because a second,
independent bug lives in `rounded_max` (`Gauge.py:3639-3660`):

```
round_to      = 0.05
rounded_min   = InchOfMercury(29.85 inHg)
rounded_max   = np.float64(0.4)          <-- should be ~30.15
rounded_range = 29.45                    <-- |0.4 - 29.85|
tick_values   = [0.4]                    <-- every tick outside the range
```

`rounded_max` scales a fractional `rounded_range` up to a whole number of
ticks, then maps back by **dividing by** `scaled_amount` instead of
**multiplying by its reciprocal**. On a range of 0.30000000000000426 that
yields 0.4, which lands *below* `rounded_min`, so `rounded_range` comes out as
29.45 and every graduation falls outside the dial.

Not fixed here, deliberately:

- It is a different defect in a different property, with its own blast radius
  (any fractional range: 0-0.9 and 0.4 both mis-round today).
- The fix is not obvious from the code's intent. Scaling up to count ticks and
  back again has several defensible formulations, and picking one is a design
  call, not a mechanical repair. An attempted reciprocal rewrite was checked
  against four ranges and was wrong on three of them, so it was reverted
  rather than shipped.

**A fine-scale gauge therefore still does not label correctly.** The crash is
fixed; the graduations are not. Tracked here so it is not lost.

## Scope

- Only `round_to.item_default`. The `99 < span <= 350` and decade branches are
  correct and stay.
- Do **not** touch tick-label formatting — that is
  [gauge-tick-label-format.md](gauge-tick-label-format.md), already on
  `feat/tick-label-format`.
- Do **not** fix the `AttributeError: '_needle'` message. It is honest about
  what the caller sees and disappears once construction completes.

## Related

- [gauge-tick-label-format.md](gauge-tick-label-format.md): the 1c spacing floor,
  and the fine-scale dials this bug blocks
- [gauge-display.md](gauge-display.md)
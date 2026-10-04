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

`round_to` follows the span only. An earlier attempt let a finer major
interval (0.05 on a 29.9-30.1 dial) override it so that the 29.95 and 30.05
half-steps would survive. That was dropped: those half-steps would be labelled,
and a dial labelled every 0.05 inHg is not something anyone asked for. Fine
unlabelled ticks between coarse labels are a labelling question, not a
`round_to` one.

## Verify

- **Tests:** a new `tests/ui/test_gauge_round_to.py` asserting `round_to` for
  every range in the table above, plus the invariant that it never returns a
  value below `1e-12`, and that `floor(min / round_to)` stays finite. Cover at
  minimum: **0–0.5, 0.1–0.3, 0–1, 950–1050, 28–32**.
- **A sub-1 gauge builds** and renders. That is the regression that
  matters: today it raises before it draws.
- **A render** of a sub-1 dial (`docs/design-references/presets/rain-rate.levity`):

  ```bash
  QT_QPA_PLATFORM=offscreen .venv/bin/python src/LevityDash/devtools/render_widget.py \
    --levity <a preset with a sub-1 range> --scenario hot-clear-day \
    --name gauge --out /tmp/round-to.png --scale 3
  ```

  (`render_widget.py`'s `--help` prints the *app's* CLI, not its own — the real
  usage is in its module docstring.)

- **No change** for 0–1, 950–1050, 28–32. Those already work; the fix must not
  move them.

## Also fixed: `rounded_min` / `rounded_max`

With `round_to` repaired, a sub-1 gauge built but drew no graduations:

- `rounded_max` scaled a fractional range up to a whole number and back down
  again, and returned a range *width*, not a bound. It came out as 0.4 on a
  29.9-30.1 dial. It now counts whole `round_to` steps and adds them to
  `rounded_min`.
- `rounded_min` and `rounded_max` floored and ceiled a raw float quotient.
  `29.9 / 0.1` is `298.99999999999994`, which floors to 29.8, so a round bound
  moved out by one step. Both now round the quotient to 9 places first.
- The prime-count bump (a prime number of steps gets one more) now applies only
  to whole-number ranges. On a fractional range it only padded the dial.

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
# Two size-group tests fail on `lambda`, pass on the ARM Mac

**Status:** open, low priority. Found 2026-07-28 while converting `lambda` from
rsync to a real git checkout — the first time the suite had ever run there.

## Symptom

On `lambda` at `f6cdd3f`:

```
2 failed, 277 passed, 1 skipped in 175.40s
FAILED tests/ui/test_sizegroups_integration.py::test_no_blank_text_on_load
FAILED tests/ui/test_sizegroups_integration.py::test_metrics_survive_resize
```

Same commit on the ARM Mac: `279 passed, 1 skipped in 27.7s`.

```
assert _blank(dashboard.visible_texts()) == []
AssertionError: assert ['Sea Level', ...'Diffuse', ...] == []
  Left contains 42 more items, first extra item: 'Sea Level'
```

## Ruled out

- **Not config bleed.** `tests/conftest.py` seeds a throwaway config from
  `tests/resources/config-seed/`, and `Sea Level`/`Diffuse` are in *that* seed's
  `default.levity` (lines 573/584) — not in lambda's user config, which points
  at `OpenMeteo.levity`. Both machines load the same test dashboard.
- **Not the rsync→git conversion.** The trees are byte-identical after the
  switch (verified with a `rsync --checksum` dry-run returning nothing).
- **Not a font miss.** The captured warnings show `QFont(Nunito, …)` resolving.

## What differs — read this before assuming a code fault

**`lambda` is CPU-throttled to ~897 MHz.** Its swollen battery was removed, and
an Intel MacBook with no healthy battery gets clamped hard by the SMC because
the adapter alone cannot supply peak current. This is hardware state, not a
software condition, and it will persist until the battery is replaced.

That is almost certainly the whole story here:

- It explains the 6× slower suite (175s vs 28s) — originally, and wrongly,
  attributed to Intel vs ARM.
- **42 texts blank on load is what a size-group refit that has not finished
  settling looks like.** At roughly a quarter of normal clock, a fixed settle
  budget that is generous on healthy hardware stops being generous.

So treat this as **a timing failure on degraded hardware until proven
otherwise**, not a layout bug. Two things follow:

- Do not "fix" `Groups.py` against this box. Re-measure after the battery is
  replaced, or on any other machine, before changing refit logic.
- If it reproduces on *unthrottled* hardware, then it is real — and the fix is
  probably that the test (or the refit) waits on a settle condition rather than
  a fixed duration, which would make it robust on slow displays generally. A Pi
  or similar low-end head is a stated goal in the roadmap, so a refit that
  depends on wall-clock speed is a genuine portability concern.

`lambda` is also **x86_64, Darwin 24.6.0** vs ARM, Darwin 27.0.0 — a real
difference, but a distant second suspect behind the throttle.

The suite had never run on lambda before, so this is very likely pre-existing
rather than a regression — an assumption, not a measurement. Each run costs ~3
minutes there.

## Next step

Get the *list* of the 42 blank items (`pytest -v`) and check whether they are
one contiguous panel or scattered. Scattered points at timing; contiguous points
at a panel that ended up zero-sized.

## Related

- `src/LevityDash/lib/ui/Groups.py` — the refit engine
- `tests/ui/test_sizegroups_integration.py`
- `tests/conftest.py` — the seeded-config fixture

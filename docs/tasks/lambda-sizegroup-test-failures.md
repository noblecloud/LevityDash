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

## What differs

`lambda` is **x86_64, Darwin 24.6.0**; the other machine is ARM, Darwin 27.0.0.
The suite had never been run on lambda before, so this is very likely
pre-existing rather than a regression — but that is an assumption, not a
measurement. **Confirm by running the suite there at an older commit before
treating it as such.** Each run costs ~3 minutes on that box.

Note the run is ~6× slower on lambda (175s vs 28s), so a timing-sensitive
settle in the size-group refit is a reasonable first suspect: 42 texts blank
looks more like "fitting hadn't finished" than like a layout fault.

## Next step

Get the *list* of the 42 blank items (`pytest -v`) and check whether they are
one contiguous panel or scattered. Scattered points at timing; contiguous points
at a panel that ended up zero-sized.

## Related

- `src/LevityDash/lib/ui/Groups.py` — the refit engine
- `tests/ui/test_sizegroups_integration.py`
- `tests/conftest.py` — the seeded-config fixture

# Colour decode fix (PR #18), handoff

**Branch:** `claude/project-thread-ozs67u`. It is open as draft PR #18 into
`feat/value-sources`.

## Done

- `Color.decode` (`colors/color.py`) now reads web colour names, whole-string hex
  (`#`/`0x`/bare, and 3/4/6/8 digits; the short forms double each digit as CSS does),
  channel-number strings, int or float lists, and r/g/b dicts with short or long keys.
  `decode` no longer pops `name` out of the caller's dict.
- `Graph.py`: the plot colour and the time-indicator colour both go through
  `Color.decode`. This removes the dead `toQColor` call.
- `tests/ui/test_color_decode.py` is new. The suite gives 578 passed and 1 skipped. The 2
  failures in `test_entry_points.py` come from the container's missing `en_US` locale
  and fail without this change too.

## Left to do

1. Check the change in a real render: a Graph plot with `color: black` and
   `color: aliceblue`, and a time indicator.
2. Look for `.levity` files outside the repo (the user config, `lambda`) that use 3- or
   4-digit hex. Those colours will now render differently.
3. Merge into `feat/value-sources` with `--no-ff`, then follow the push flow in
   `session-handoff-2026-10-05.md`. Do not push to `lambda`.

## Next bug, not started: rain shows `0.0`

`0` and `0.0` are different on purpose. `0` means exactly zero, and `0.0` means a trace
amount (0 < value < 0.05). A configured or overridden format wins over both. The bug is a
true zero showing as trace. A fix must keep both states and honour explicit config.

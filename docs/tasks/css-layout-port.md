# CSS layout port

Port the CSS layout algorithms that `Stack` lacks into `src/LevityDash/lib/layout/`. Read `css-mapping.md` in the project folder for the full mapping of LevityDash options to CSS.

The package is a skeleton. Every function raises `NotImplementedError`. Nothing imports it yet, so no board changes. Run `python -m LevityDash.lib.layout` to list what is left.

## Rules

- One spec section per task. The `@implements(...)` line on a stub names the spec and section.
- Port from the spec text only. Never from Taffy, a browser, or any other implementation.
- Pure functions in pixels. No Qt, no `lib.ui`. Test with the examples in the spec text, in `tests/layout/`.
- Set `status='done'` on the decorator when a stub is finished.
- Do not wire anything into `Stack` in these tasks.

## Order

1. `flex.resolve_flexible_lengths` (§9.7). Everything else in flex rests on it.
2. `flex.flex_base_and_hypothetical_size` (§9.2), `align.distribute_content`, `align.align_offset`.
3. `flex.align_main_axis`, `flex.cross_sizes`, `flex.align_cross_axis`, `flex.resolve_auto_margins`.
4. `flex.collect_flex_lines`, then `flex.layout_flex`, then `legacy.stack_as_flex` and the parity test.
5. Grid: `parse_track_list`, `expand_repeat`, the five track-sizing steps, `place_items`, `layout_grid`.
6. `align.baseline_shifts` (also needed by [text-baseline-alignment](text-baseline-alignment.md)).

## Wiring (done)

`Stack.setGeometries` hands its layout to `lib/layout/flex.py` when the stack has a `flex:` container key (`justify`, `align-items`, `wrap`) or any item has `flex:`. `type: grid` (`GridStack`) always uses `lib/layout/grid.py`. A stack with none of those keeps the original sizing. User docs: `docs/config/dashboard/layout.md`. Example: `docs/design-references/css-layout.levity`.

Check that a change to stacks moves nothing: `devtools/dump_layout.py` writes every panel's rect to a text file; diff a dump from before and after. Pixel diffs are noisy on boards with graphs and gauges.

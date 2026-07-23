# Dead-code sweep

**Status:** partially done (see below) — the commented-out-code portion needs a human pass, not another automated one
**Scope:** low-risk deletions + a few TODO verifications, no logic changes
**Suggested workflow:** own branch/worktree (see below), not `dev` directly

Confirmed via the project review (`docs/reviews/project-review.md`) — each item below was verified to have zero import sites or zero remaining purpose before being listed here.

## Confirmed dead code to delete — done

- **`src/LevityDash/lib/exceptions/`** — a 4-line package (`LevityException`), zero import sites anywhere in the tree. Deleted.
- **`src/LevityDash/lib/utils/debug.py`** — imports the Qt shim, defines one function (`path_to_image`) that's never called anywhere. Deleted.

**Not in scope:** `src/LevityDash/lib/backend.py` — no longer a scaffold (this note is stale; the backend/frontend split shipped and this is now the real headless backend process, see `docs/roadmap.md` and `AGENTS.md`'s "Wire protocol" section) but still not part of this sweep regardless — it's live, actively-developed code, not dead code.

## Commented-out code to review and likely remove — STOP, do not repeat this automatically

**An earlier automated pass on this exact section deleted large commented-out blocks in `Grid.py`, believing them abandoned.** They weren't — they're the maintainer's own preserved WIP for a future snap-to-grid + auto-packing feature (items locking to a grid), intentionally parked mid-implementation, not abandoned. Caught and reverted before merging; the blocks are now back in place with explanatory comments (search `INTENTIONALLY PRESERVED` in `Grid.py`) so this doesn't happen a third time (the maintainer confirmed this wasn't the first agent to make this mistake either). See `feedback-dead-code-wip-features` in the maintainer's memory system for the full account.

**Given that, this section is not something to hand to another automated pass with the same instructions.** If a human wants to pursue it:

- `src/LevityDash/lib/ui/Geometry/Grid.py` — **skip entirely.** Already has WIP grid-packing work preserved in commented blocks (with explanatory comments now). Don't touch without asking the maintainer directly what's safe to remove, if anything.
- `src/LevityDash/lib/ui/frontends/PySide/Modules/AttributeEditor/__init__.py`
- `src/LevityDash/lib/ui/frontends/PySide/Modules/Drawer.py`
- `src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Graph.py` and `Gauge.py` (lighter touch here — these are large, actively-used, working files; only remove clearly-dead commented blocks, don't go hunting)

Not attempted in this pass (deliberately, after the Grid.py incident above). For whoever picks this up: check `git blame`/history on every candidate block before touching it, and when a block reads as a parked feature/algorithm rather than obviously-superseded scaffolding, ask the maintainer rather than judging from code shape alone — "looks broken" is not evidence of "abandoned."

## Small TODO verification (bonus, low effort) — done

Four TODOs in `src/LevityDash/lib/ui/colors/color.py` said "AI Generated - varify accuracy":

- **`hue`**: verified correct against the standard HSL/HSV hue formula. TODO removed.
- **`lightness`**: verified correct against the standard HSL lightness formula. TODO removed.
- **`saturation`**: was actually computing HSV saturation in a class that's otherwise HSL (per `lightness`'s presence) — a real inconsistency. Fixed to the correct HSL formula and cross-checked against Python's stdlib `colorsys.rgb_to_hls` across 2000 random colors (exact match). Zero existing callers anywhere in the tree, so zero behavioral regression risk from the fix.
- **`gamma`**: not actually a gamma-correction value at all (no exponent/curve applied) — it's an unweighted mean of the RGB channels, at best a crude brightness approximation. Zero callers anywhere. Left the computation as-is (inventing a "correct" gamma formula for an unused property would be guessing new intent, not verifying existing intent) but corrected the misleading comment.

## Verification

- `poetry run pytest` — full suite green (94 passed, 1 skipped baseline as of the OpenWeatherMap plugin commit `970dd0c`; may differ if other tasks landed first — just confirm no regressions vs whatever the baseline is when you start).
- Live boot (`poetry run python -m LevityDash`) — confirm nothing that referenced the deleted commented-out code was actually load-bearing (it shouldn't be, since it's commented out, but a quick smoke test costs nothing).

## Suggested git workflow

```bash
cd ~/Code/LevityDash
git worktree add ../LevityDash-cleanup -b chore/dead-code-sweep
```

Work in `~/Code/LevityDash-cleanup`. When done:

```bash
cd ~/Code/LevityDash
git merge chore/dead-code-sweep    # after reviewing the diff
git worktree remove ../LevityDash-cleanup
```

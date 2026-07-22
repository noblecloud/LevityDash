# Dead-code sweep

**Status:** open, not started
**Scope:** low-risk deletions + a few TODO verifications, no logic changes
**Suggested workflow:** own branch/worktree (see below), not `dev` directly

Confirmed via the project review (`docs/reviews/project-review.md`) — each item below was verified to have zero import sites or zero remaining purpose before being listed here.

## Confirmed dead code to delete

- **`src/LevityDash/lib/exceptions/`** — a 4-line package (`LevityException`), zero import sites anywhere in the tree. Delete the whole package.
- **`src/LevityDash/lib/utils/debug.py`** — imports the Qt shim, defines one function (`path_to_image`) that's never called anywhere. Delete the file.

Before deleting either, re-grep to confirm nothing new imports them since the review (`grep -rn "lib.exceptions\|utils.debug" src --include="*.py"` from the repo root) — this doc is a point-in-time snapshot, not a guarantee.

**Not in scope:** `src/LevityDash/lib/backend.py` (403 lines, also flagged dead in the review) — this is deliberately NOT part of this sweep. It's the known Phase 4.2 scaffold (see `docs/roadmap.md`) and will be reworked, not deleted, as part of that phase. Leave it alone.

## Commented-out code to review and likely remove

These files have large blocks of commented-out code (estimated by eye, see the review for the counts) that make the live code paths harder to follow. Read each file, confirm the commented blocks are genuinely abandoned (not a "temporarily disabled, will re-enable" marker — check git blame/history if unsure), and delete:

- `src/LevityDash/lib/ui/Geometry/Grid.py` — heaviest offender, much of the file
- `src/LevityDash/lib/ui/frontends/PySide/Modules/AttributeEditor/__init__.py`
- `src/LevityDash/lib/ui/frontends/PySide/Modules/Drawer.py`
- `src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Graph.py` and `Gauge.py` (lighter touch here — these are large, actively-used, working files; only remove clearly-dead commented blocks, don't go hunting)

Git history preserves everything, so there's no data-loss risk — this is purely a readability cleanup.

## Small TODO verification (bonus, low effort)

Four TODOs in `src/LevityDash/lib/ui/colors/color.py` (grep `AI Generated` in that file) say "AI Generated - varify accuracy" — spend a few minutes with a real color picker/reference confirming the color values are actually correct, then either remove the TODO comment (if correct) or fix the value (if wrong).

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

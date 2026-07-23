# Dependabot alert triage

**Status:** done — full triage at [`docs/reviews/dependabot-triage.md`](../reviews/dependabot-triage.md). 48 alerts cleared via safe transitive/optional bumps, 18 needed zero action (already resolved or no longer a dependency), 43 flagged for a deliberate follow-up decision rather than bumped (`aiohttp` — direct, non-trivial dependency; `certifi` — an unexplained direct pin that's also silently blocking a `requests` alert).
**Scope:** research/reporting first; only apply dependency bumps that are clearly safe and well-tested
**Suggested workflow:** own branch/worktree for any actual dependency changes; the triage/report step itself can happen anywhere with `gh` access

## Context

When the LevityDash repo's full history was first pushed to GitHub (see `docs/reviews`/project memory from the Python 3.14 migration work), GitHub flagged **109 Dependabot alerts** (2 critical, 30 high, 50 moderate, 27 low) — never triaged. Many likely predate the dependency-floor bumps done during the 3.14 migration (numpy, scipy, aiohttp and its C-extension transitives, PySide6, etc. were all raised significantly) and may already be resolved; some may be real.

## The task

1. **List and categorize the alerts:** `gh api repos/noblecloud/LevityDash/dependabot/alerts --paginate` (or the `gh` equivalent for browsing them — `gh repo view --web` and check the Security tab if the API route needs different scopes). For each alert, note: package, current vs. patched version, severity, and whether the current `pyproject.toml`/`poetry.lock` floor (check both) already satisfies the patched version or not.
2. **Produce a short report** (a markdown file is fine, e.g. `docs/reviews/dependabot-triage.md` following the existing `docs/reviews/` convention) grouping alerts into: already resolved by existing floors (no action), needs a version bump (list the specific bump), and no fix available / needs deeper investigation.
3. **Apply only the clearly-safe bumps** — a patch/minor version bump for a package already on a recent major version, where the changelog doesn't suggest breaking changes. For anything that looks like it could break (major version jump, a package LevityDash uses non-trivially like PySide6/numpy/aiohttp), just report it — don't bump it as part of this task. Flag it back for a deliberate decision instead (dependency bumps to core packages have caused real breakage before in this project — see the PySide6 6.11-vs-6.6 incident referenced in `docs/roadmap.md`'s "Dependency & platform health" section).

## What NOT to do

- Don't loosen any pin that was deliberately tightened (check git blame/commit messages before changing a version constraint — `pyside6`/`pyside6-essentials` in particular are pinned exact for a documented reason).
- Don't push anything to GitHub — this stays local until reviewed.
- Don't touch `multidict`/`yarl`/`frozenlist` floors without checking they still resolve correctly against the current aiohttp pin (these were bumped specifically for Python 3.14 wheel availability, not for Dependabot reasons).

## Verification

For any dependency version actually changed: `poetry lock` (or `poetry update <package>` for a targeted bump) regenerates the lock file cleanly, `poetry install` succeeds, `poetry run pytest` is green, and a live boot (`poetry run python -m LevityDash`) still works.

## Suggested git workflow

The report itself can just be written directly (docs-only change, low risk). If any dependency version gets bumped:

```bash
cd ~/Code/LevityDash
git worktree add ../LevityDash-deps -b chore/dependabot-triage
```

Work in `~/Code/LevityDash-deps`. When done:

```bash
cd ~/Code/LevityDash
git merge chore/dependabot-triage    # after reviewing the diff
git worktree remove ../LevityDash-deps
```

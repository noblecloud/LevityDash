# Reconcile the docs site with 3+ years of drift

**Status:** open, not started
**Scope:** investigation + a written reconciliation plan first; only apply file changes for the clear-cut cases, flag anything ambiguous back for review rather than guessing
**Suggested workflow:** own worktree, but based on the `docs` branch, not `dev` — see "Suggested git workflow" below, this task is the one exception to the usual "branch off dev" default
**Touches:** the live, public LevityDash website (`levitydash.app`) — read this whole brief before touching anything, the stakes here are different from a normal cleanup task

## Context

GitHub Pages is configured (confirmed via `gh api repos/noblecloud/LevityDash/pages`) to serve the live site directly from the `docs` branch's `/docs` folder, `build_type: legacy` (no build step — it's a docsify site, client-side JS renders the `.md` files directly at request time). Custom domain `levitydash.app`, HTTPS valid. Whatever is on the `docs` branch's `/docs` folder right now is exactly what's live.

The `docs` branch has real merge history (`Merge remote-tracking branch 'origin/main'`, several times) — the old workflow was: work happens on `main`, someone periodically merges `main` into `docs` to publish. That stopped. `docs` and `main`/`dev` share a common ancestor from **December 2022**; the last update to `docs` was **April 2023** ("docs: clean up typos"). Since then, `dev`'s `docs/` folder kept evolving — pages moved, renamed, deleted, added — while `docs` branch's `/docs` folder is frozen at its 2023 state. Neither side is simply "ahead" of the other; **this is not a fast-forward or a clean merge.**

## The two trees differ in both directions — read this before assuming either side should just overwrite the other

Compare them yourself first (`git ls-tree -r --name-only refs/heads/dev -- docs/` vs `git ls-tree -r --name-only refs/heads/docs -- docs/`), but as a starting point:

**Only on `docs` branch (the live site) — likely site infrastructure that must be preserved, not discarded:**
- `docs/_fonts/` — custom webfonts (Jellee, National Park) referenced by the live site's CSS
- `docs/_footer.md`, `docs/_scripts/simple-footer.js` — footer content/script
- A chunk of `_images/` files `dev` doesn't have

**Only on `dev`'s `docs/` folder — either newer public content, or internal-only material that should NOT ship to the public site:**
- `docs/roadmap.md`, `docs/dashboard.md`, `docs/modules.md`, `docs/plugin_config.md` — look like genuine newer public content (verify by reading them)
- `docs/tasks/*.md` — **internal agent task briefs, this file included. Do not publish these to the site.**
- `docs/reviews/*.md` — **internal investigation notes (bug traces referencing specific commits). Do not publish these.**
- `docs/source/` — a vestigial Sphinx skeleton (see `CLAUDE.md`), nothing imports/builds it — almost certainly should be dropped entirely, not ported
- `docs/README.md`, `docs/_navbar.md`, `docs/_planned-features.md`, `docs/_scripts/stylesheet.css` — unclear, check whether these are referenced by `dev`'s `docs/index.html`/`_sidebar.md` before deciding

**Renamed/moved on `dev` relative to `docs` branch** (same content, different path — don't treat these as "new" and "deleted" separately):
- `docs/about/plugins.md` → `docs/plugins.md`
- `docs/config/plugins/WeatherFlow.md` → `docs/plugins/WeatherFlow.md`
- `docs/development/issues.md` → `docs/issues.md`
- likely others — check with `git diff --stat refs/heads/docs refs/heads/dev -- docs/` for the full rename-detected list

**Deleted on `dev` relative to `docs` branch** (old content that may have been deliberately retired — don't assume, but don't assume it must come back either):
- `docs/installing.md`, `docs/configuring.md`, `docs/requirements.md`, `docs/running.md`, `docs/quick-start.md`, `docs/development/changelogs/`, `docs/social-posts/`

`docs/index.html` and `docs/style.css` differ substantially between the two (299 and 367 changed lines respectively) — these likely contain docsify config (plugins, sidebar/navbar toggles, theme) and probably reference the `_fonts/`/`_footer.md` infrastructure that only exists on the `docs` branch. Don't blindly take either version wholesale.

## The task

**Phase 1 — inventory and plan (do this first, in full, before changing anything):**

Produce a report (a markdown file is fine, e.g. `docs/reviews/docs-site-reconciliation.md` on `dev`, following the existing `docs/reviews/` convention) that goes through every differing file and states one of: keep from `docs` branch (site infra), take from `dev` (newer content), merge both (e.g. `index.html`/`style.css` likely need pieces of each), drop entirely (e.g. `docs/source/`), or **flag for the maintainer** (anything you're not confident about — content you can't tell is stale vs. intentionally retired, or whether something like `docs/roadmap.md` is meant to be public-facing at all).

**Phase 2 — apply it:**

Only for the parts of the plan you're confident about. Build the new `/docs` folder state on your `docs`-based branch (see git workflow below) reflecting the plan. Leave anything flagged in Phase 1 untouched and clearly noted in your final summary — don't guess past the point of confidence just to finish the task.

## What NOT to do

- **Never push anything from this task to GitHub, under any circumstances** — this goes beyond the usual rule (see `AGENTS.md`, this clone's `origin` is already local-only). This branch, if mishandled, could end up live on a real public website. Stop at "pushed to the local main repo" and nowhere further, full stop — no exceptions, even if you're confident the result is correct.
- Don't touch `docs/CNAME`, HTTPS/domain config, or the GitHub Pages settings themselves — none of that is a docs-content problem.
- Don't attempt a redesign or a docsify version bump — this is a content/structure reconciliation, not a facelift. If `style.css`/`index.html` need changes, make the minimal change needed to keep both the preserved infra and the current content working, nothing more.
- Don't publish `docs/tasks/` or `docs/reviews/` content to the site — these are internal, not user-facing.
- Don't delete anything from the `dev` branch's `docs/` folder as part of this task — this task only produces a new state for the `docs` branch. `dev`'s `docs/` folder is a separate, unrelated concern.

## Verification

- Serve the reconciled `/docs` folder locally and click through it — docsify needs an actual HTTP server (it fetches `.md` files via JS, `file://` won't work): `npx docsify-cli serve docs` or `python3 -m http.server --directory docs`.
- Check the sidebar/navbar (`docs/_sidebar.md`, `docs/_navbar.md` if present) — every link should resolve to a real file, nothing 404s.
- Confirm fonts and footer still render (this is the main risk of a careless reconciliation — losing the `_fonts/`/`_footer.md` infra that only exists on the `docs` branch today).
- Confirm nothing from `docs/tasks/` or `docs/reviews/` ended up in the published tree.

## Suggested git workflow

This task's base is the **`docs` branch**, not `dev` — the usual "sync your branch with `dev` first" instruction in `AGENTS.md` doesn't apply here.

```bash
cd ~/Code/LevityDash
git fetch origin docs
git worktree add ../LevityDash-docs-site -b chore/reconcile-docs-site origin/docs
```

Work in `~/Code/LevityDash-docs-site`. You'll need to reference `dev`'s `docs/` folder content too — `git show dev:docs/<path>` works for individual files without checking anything else out (the worktree already has full repo history, no extra clone needed). Commit your work directly to `chore/reconcile-docs-site` as you go.

When done, just stop — the branch already exists in the local repo (that's what `worktree add -b` did), so there's nothing further to push or land. **Do not merge this into `docs` or `dev` yourself, and do not push it anywhere.** The maintainer reviews `git diff origin/docs chore/reconcile-docs-site -- docs/` personally before any of this goes near the real `docs` branch — the live-site blast radius is the whole reason this task has a different process than the others.

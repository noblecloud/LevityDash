# Smooth + randomize the cover screenshot's hover animation

**Status:** open, not started
**Scope:** small, self-contained CSS/JS tweak to one element on the docs site cover
**Suggested workflow:** own branch/worktree (see below), based on the `docs` branch — this is a docs-site task, not `dev`
**Touches:** the live public site (`levitydash.app`) — same elevated caution as other `docs`-branch work: local-only, never push, see `docs/tasks/reconcile-docs-site.md` for why

## Context

The docs site cover page (`docs/coverpage.html`) has the app screenshot doing a slow tvOS-icon-style 3D hover — it tilts on X and Y out of phase (pivoting around a point behind the panel, not on its own face) with a gentle vertical bob layered in. Implemented as a single CSS `@keyframes` animation (`levityHover`, `.screenshotAlpha` class, ~12s cycle).

The maintainer's reaction (verbatim): the motion "isn't very smooth between keyframes. The ease [in] and out to each point makes it look weird." They also want it **actually random** rather than a fixed repeating loop. Approved for later, not blocking the initial ship (already live).

## The task

1. **Fix the easing.** A plain CSS `@keyframes` with the default `ease-in-out` times every keyframe, so the motion has visible "landing" pauses at 0%/25%/50%/75%/100% (`animation-timing-function` per this session's read: too abrupt/mechanical). Try a custom `cubic-bezier` easing, or — better — a continuous sinusoidal-style curve with more intermediate keyframes so there's no perceptible deceleration/acceleration snap at each point.
2. **Make it random**, not a fixed repeating loop. A single CSS `@keyframes` animation is inherently deterministic/looping. To get real randomness, this likely needs a small inline `<script>` in `coverpage.html` that either:
   - periodically sets new random target `rotateX`/`rotateY`/`translateY` values via `element.animate()` (Web Animations API) with a randomized duration/easing each cycle, or
   - randomizes CSS custom properties (`--tilt-x`, `--tilt-y`, etc.) on an interval and lets a CSS `transition` ease between them.
   Keep the amplitude in the same restrained range as today (~±3.4° tilt, ~11px bob) — the ask was to fix the motion quality and add randomness, not make it more dramatic.
3. Preserve the existing `prefers-reduced-motion` handling (`.screenshotAlpha { animation: none; transform: none; }` under that media query) — whatever mechanism replaces the current animation must still fully disable itself for reduced-motion users.
4. Preserve the perspective setup: `.cover picture { perspective: 1600px; }` on the parent, `transform-origin: 50% 50% -340px` on `.screenshotAlpha` (pivot point behind the panel, not on it) — this is what makes it read as an orbit rather than a flat wobble. Don't reintroduce the earlier mistake from this session: putting `perspective()` inside the `transform` itself (rather than on the parent) makes the element balloon in size — keep `perspective` on the parent only.

## What NOT to do

- Don't change the amplitude/character of the motion beyond what's needed for smoothness — this is a polish pass on an already-approved effect, not a redesign.
- Don't touch anything else on the cover (gradient, wordmark, layout) — out of scope.
- Don't push to GitHub — same rule as every other `docs`-branch task, land the branch locally only.

## Verification

- Watch it run for a couple of minutes in a real browser (not just a screenshot) — confirm no visible "snap" or pause at any point in the cycle, and confirm it doesn't repeat the exact same path every ~12s.
- Toggle OS-level reduced-motion and confirm the screenshot goes fully static.
- Confirm the panel's rendered size stays correct (no ballooning) — this was a real bug hit during initial implementation; sanity-check `getBoundingClientRect()` width before/after if unsure.
- Check both light and dark cover modes (`prefers-color-scheme`) — the animation is shared between them, only the background/shadow differ.

## Suggested git workflow

```bash
cd ~/Code/LevityDash
git fetch origin docs
git worktree add ../LevityDash-docs-hover -b polish/cover-hover-animation origin/docs
```

Work in `~/Code/LevityDash-docs-hover`. When done, stop — the branch exists locally, nothing to push. The maintainer reviews and merges into `docs` (and pushes to GitHub) themselves.

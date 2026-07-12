# Loud-failure dev mode for silent schema fallbacks

**Status:** open, not started
**Scope:** small, additive — a new opt-in mode, no change to default (production) behavior
**Suggested workflow:** own branch/worktree (see below), not `dev` directly
**Touches:** the schema/observation engine directly — read `docs/reviews/schema-pipeline.md` first for full context on why these fallbacks exist and why they're lenient by design

## Context

The schema/observation pipeline (`src/LevityDash/lib/plugins/schema/__init__.py`, `categories.py`, `observation.py`) is deliberately lenient in production: a schema mistake degrades to a cosmetic oddity (wrong-looking value, fuzzy-matched to the wrong key) rather than crashing the app. That's the right default for an app someone is using to check the weather. But it also means schema bugs are hard to find during plugin development — see `docs/reviews/schema-pipeline.md`'s "Is there a better way?" section, recommendation #4.

One instance of this was already fixed today (commit `23cd7e5`): `ObservationValue.value` (`src/LevityDash/lib/plugins/observation.py`, around line 230) now logs a warning when `convertFunc` fails and it falls back to the raw value, instead of silently swallowing the exception. That's the pattern to extend.

## What's still silent

1. **`Schema.getUnitMetaData`'s fuzzy-match fallback** (`src/LevityDash/lib/plugins/schema/__init__.py`, the `getUnitMetaData` method) — when a key isn't found, it fuzzy-matches to the closest known key (`cutoff=0.5`) and silently substitutes it, only logging a warning (not distinguishing "this is probably fine" from "this masked a real typo"). A misspelled `sourceKey` in a plugin schema can silently bind to the wrong unit metadata with no clear signal something's wrong.
2. **`Schema.getExact`** (same file) — similar fuzzy/wildcard fallback behavior for key lookups.
3. **`LevityDatagram.findTimeKey`** — fuzzy-matches "timestamp" if the exact key isn't found.

## The task

Add an opt-in strict/dev mode — likely an env var (matching the existing `LEVITYDASH_CONFIG_DEBUG`/`LEVITYDASH_BACKEND_MODE` convention, see `src/LevityDash/__init__.py` and `src/LevityDash/lib/plugins/dispatcher.py` for examples of that pattern) or a config flag — that, when enabled:

- Makes the fuzzy-match fallbacks in `getUnitMetaData`/`getExact`/`findTimeKey` log at a more visible level (or even raise, if that's cleaner — your call, but raising might be too aggressive for a first pass; a loud, hard-to-miss WARNING/ERROR log with the exact key and its fuzzy-matched substitute is probably the right first step) instead of silently substituting.
- Optionally: a one-time-per-session summary of every fuzzy-match/unmapped-key event, rather than spamming per-occurrence (the existing per-occurrence warnings can be noisy during startup when many values arrive at once).

**Production/default behavior must not change** — this is purely additive. The lenient fallback stays the default; the loud mode is opt-in for plugin development.

## What NOT to do

Don't change the actual fallback *logic* (what gets picked when a key isn't found) — only add visibility into when it fires. Don't touch `ObservationDict.calculateMissing`'s dewpoint/heatIndex guard inconsistency — that's tracked separately (see `docs/tasks/` for other open items, or `docs/reviews/schema-pipeline.md`'s bug list if no task exists for it yet).

## Verification

- With the new mode off (default): behavior is byte-identical to before this change. Run the full test suite (`poetry run pytest`) to confirm.
- With the new mode on: intentionally misconfigure a plugin schema (e.g., typo a `sourceKey`) and confirm the loud warning appears clearly, then revert the typo.
- Live boot in both modes (`poetry run python -m LevityDash`, with and without the flag) — confirm no crash, no behavior change with the flag off.

## Suggested git workflow

```bash
cd ~/Code/LevityDash
git worktree add ../LevityDash-loud-failures -b feat/loud-failure-dev-mode
```

Work in `~/Code/LevityDash-loud-failures`. When done:

```bash
cd ~/Code/LevityDash
git merge feat/loud-failure-dev-mode    # after reviewing the diff
git worktree remove ../LevityDash-loud-failures
```

# Fix ScheduledEvent.instances race condition

**Status:** open, not started
**Scope:** small, mechanical, one-line fix + verification
**Suggested workflow:** own branch/worktree (see below), not `dev` directly

## The bug

`src/LevityDash/lib/plugins/utils.py`, class `ScheduledEvent.__init__` (around line 463), has an unprotected class-level dict mutation that's a classic check-then-set race:

```python
self.__owner = func.__self__
if self.__owner in self.instances:
    self.instances[self.__owner].append(self)
else:
    self.instances[self.__owner] = [self]
```

`ScheduledEvent.instances` is declared `ClassVar[dict['Plugin', list['ScheduledEvent']]] = {}` — a single dict shared across every plugin. Each plugin runs on its own `PluginThread` (a real `threading.Thread` subclass, see `PluginThread` in `src/LevityDash/lib/utils/shared.py`), and multiple plugins construct `ScheduledEvent`s concurrently at app startup. The check-then-set above isn't atomic, so two threads can race on it.

## The fix

Replace with the atomic `dict.setdefault`:

```python
self.__owner = func.__self__
self.instances.setdefault(self.__owner, []).append(self)
```

## Why this matters (context)

Found while chasing an intermittent crash in the OpenWeatherMap plugin (a real reproducer — `calculateMissing` in `src/LevityDash/lib/plugins/observation.py` reads a temperature value as `None` moments after it should have been set, but **only** when plugins are started via the real `plugin.thread.start()` path, never when calling `plugin.start()` directly — confirming it's a threading issue, not a logic bug in the plugin).

This `ScheduledEvent` race is the **leading suspect**, not a confirmed root cause — the code shape is a textbook race worth fixing regardless of whether it's the exact cause of the OpenWeatherMap crash.

## Verification

After applying the one-line fix:

1. Boot the app normally (`poetry run python -m LevityDash`) or headless (`QT_QPA_PLATFORM=offscreen poetry run python -m LevityDash`) several times in a row with OpenMeteo, OpenWeatherMap, and PirateWeather enabled. (Govee can stay enabled or disabled — it's unrelated; a known, separate, pre-existing macOS Bluetooth/TCC permission issue causes non-interactive terminal launches to abort if Govee tries to connect. Not what we're testing here.)
2. Watch for `TypeError: float() argument must be a string or a real number, not 'NoneType'` originating from `ObservationDict.calculateMissing` in the logs. If it stops appearing across several repeated runs, that's good evidence the fix worked. If it still happens, the race is elsewhere — this fix, while still correct to keep, didn't fully solve it. Report that back rather than assuming success.
3. Run the full test suite (`poetry run pytest`) to confirm no regressions — baseline is 94 passed, 1 skipped as of the OpenWeatherMap plugin commit (`970dd0c`).

This is accepted as good-enough-for-now, not a deep redesign — Phase 4 (the backend/frontend process split, see `docs/roadmap.md`) is expected to eliminate the one-thread-per-plugin model this race lives in.

## Suggested git workflow

```bash
cd ~/Code/LevityDash
git worktree add ../LevityDash-fix-scheduledevent -b fix/scheduled-event-race
```

Work in `~/Code/LevityDash-fix-scheduledevent`. When done:

```bash
cd ~/Code/LevityDash
git merge fix/scheduled-event-race    # after reviewing the diff
git worktree remove ../LevityDash-fix-scheduledevent
```

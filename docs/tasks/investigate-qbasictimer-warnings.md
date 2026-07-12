# Investigate "QBasicTimer::start: Timers cannot be started from another thread"

**Status:** open, not started
**Scope:** investigation first, fix second — root cause is not confirmed yet
**Suggested workflow:** own branch/worktree (see below), not `dev` directly

## The symptom

The console gets flooded with repeated lines like:

```
QBasicTimer::start: Timers cannot be started from another thread
```

This is a warning Qt's C++ internals print directly to stderr (not through Python's logging), so it has no traceback and no object context — that's *why* it hasn't been root-caused yet, not because it's untraceable. The app keeps working despite it ("it's clearly working" per the user), so this is a real bug but not currently a crash — could be silently dropping something, or could be truly harmless. Worth understanding definitively either way.

**Confirmed not the cause:** the Govee BLE plugin — the warnings happen with Govee disabled too.

## What the warning actually means

Qt requires a `QTimer` (which uses `QBasicTimer` internally) to be started from the same thread that owns it — its "thread affinity." Calling `.start()` from any other thread prints exactly this warning and the timer doesn't actually start.

**This is a known problem class in this codebase** — it already has a fix pattern: `startTimerSafe`/`stopTimerSafe` in `src/LevityDash/lib/utils/shared.py:1752-1777`. Both check `QThread.currentThread() is timer.thread()` and, if not, marshal the start/stop onto the timer's own thread via `QMetaObject.invokeMethod(..., Qt.ConnectionType.QueuedConnection)` instead of calling `.start()`/`.stop()` directly.

That wrapper is currently used in exactly two files:

```
src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Graph.py   (render_delay, timer, syncTimer)
src/LevityDash/lib/utils/data.py                                    (__delayTimer)
```

Every other `QTimer(...)` in the codebase still calls `.start()`/`.stop()` directly. Any of those that can be triggered from a plugin's background thread (not the GUI thread) is a candidate source of this warning.

## Leads (unconfirmed — starting points, not a diagnosis)

**Strongest lead:** `src/LevityDash/lib/plugins/utils.py`, `ScheduledEvent.__run()`, around line 598-605:

```python
if (loop := self.loop) is None:
    log.warning(f'{self.__owner} - No event loop found for {self.__func!r}')
    if self.fireImmediately:
        self.__fire()
        return
    self.timer = QTimer(singleShot=True)
    self.timer.timeout.connect(self.__fire)
    self.timer.start(when * 1000)
```

`ScheduledEvent` instances are constructed and run from each plugin's own `PluginThread` (a real `threading.Thread`, see `src/LevityDash/lib/utils/shared.py`). If `self.loop` is ever `None` when this fires, this `QTimer` gets created *and* started on that plugin thread — which has no Qt event loop (`exec_()`) running to service it. Worth checking: does `self.loop` actually go `None` in practice, and if so when/why? If this path is live, it's both the direct source of the warning *and* a timer that silently never fires.

**Other unmigrated `QTimer` sites worth checking** (not yet evaluated for whether they're ever touched off the GUI thread):

```
src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Realtime.py:104   (contentStaleTimer — this one is data-update-adjacent, see adjustContentStaleTimer, worth checking first)
src/LevityDash/lib/ui/frontends/PySide/Modules/Displays/Moon.py:201
src/LevityDash/lib/ui/frontends/PySide/Modules/Handles/Resize.py:168
src/LevityDash/lib/ui/frontends/PySide/Modules/Handles/Various.py:30,185
src/LevityDash/lib/ui/frontends/PySide/Modules/Panel.py:443
src/LevityDash/lib/ui/frontends/PySide/Modules/Drawer.py:206
src/LevityDash/lib/ui/frontends/PySide/app.py:247,312,1161,1166,1169,1176
```

Most of `app.py`'s timers are probably fine (constructed and only ever touched from the GUI thread), but `Realtime.py`'s `contentStaleTimer` is directly in the plugin-data-update path (`adjustContentStaleTimer`, called from `updateSlot`, which fires off a `container.channel.connectSlot(...)` connection — the same kind of cross-thread signal path that caused the Graph.py timers to need `startTimerSafe` in the first place) and is worth checking early.

## How to actually find it definitively

Grepping can find *candidates* but not prove which one is firing. To nail it down:

- Reproduce with `QT_FATAL_WARNINGS=1` set — this turns Qt warnings into aborts, which will drop you into a debugger/crash at the exact `.start()` call site (a real stack trace, not just a printed line).
- Or attach a debugger (lldb/gdb) and set a breakpoint on `QBasicTimer::start` in the Qt library itself, then run normally and inspect the backtrace when it hits.
- Or bisect by temporarily wrapping suspect `QTimer.start()` calls with a `print(threading.current_thread(), timer.thread())` right before the call, one at a time, until the offending one is found.

## The fix, once found

Almost certainly: wrap the offending `.start()`/`.stop()` call with the existing `startTimerSafe`/`stopTimerSafe` helpers (same pattern as Graph.py/data.py), or ensure the `QTimer` gets constructed on the GUI thread in the first place rather than lazily on whatever thread first needs it.

If it turns out to be genuinely harmless (timer never actually needed off-thread, or a fallback path that's dead in practice), it's still worth silencing properly (fix the actual cause) rather than suppressing the warning — per the project's own conventions, don't paper over a real threading bug.

## Verification

- The warning should stop appearing across several real app boots (`poetry run python -m LevityDash`), with the same plugins enabled as usual.
- Whatever the timer was *for* should still work — check it doesn't silently break a feature (e.g. if it's `contentStaleTimer`, confirm realtime displays still properly show a "stale" state after their update interval).
- Run the full test suite (`poetry run pytest`) to confirm no regressions.

## Suggested git workflow

```bash
cd ~/Code/LevityDash
git worktree add ../LevityDash-qbasictimer -b fix/qbasictimer-warning
```

Work in `~/Code/LevityDash-qbasictimer`. When done:

```bash
cd ~/Code/LevityDash
git merge fix/qbasictimer-warning    # after reviewing the diff
git worktree remove ../LevityDash-qbasictimer
```

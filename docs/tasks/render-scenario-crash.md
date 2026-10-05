# `render_dashboard.py --scenario` segfaults on a full dashboard

**Status: open, needs a fix or a finer bisect.** Suggested branch: `fix/scenario-render-segv`.

## What happens

Rendering a *real* dashboard (the seeded user config, all panels) with `--scenario`
dies with `SIGSEGV` in a Qt thread-pool runnable, before the PNG is written. The
Fixture plugin publishes, then the process crashes:

```sh
cd .claude/worktrees/blackfish-meter
LEVITYDASH_FIXTURE_DELAY_MS=end poetry run python src/LevityDash/devtools/render_dashboard.py \
    /tmp/out.png --scenario docs/design-references/scenarios/stormy-day.yaml \
    --seed .render-diff/probe-values/_seed --settle 8 --freeze-time
# rc=-11, no /tmp/out.png
```

## What is measured, not guessed

| Case | Result |
| --- | --- |
| full default dashboard + `--scenario` | **rc=-11, no PNG** — twice, back to back |
| single preset (`--levity docs/design-references/presets/clock.levity`) + `--scenario` | rc=0, PNG written — twice |
| the harness's 22 presets + showcase + `--scenario` + staged seed | rc=0, 23 PNGs — every capture so far, 161+ renders |
| same crash with Mock enabled *or* disabled (`--seed` staged with Mock off) | still crashes |
| same crash with `LEVITYDASH_FIXTURE_DELAY_MS` at its 50 ms default *and* at `end` | still crashes |
| same crash at `--settle 6` and `--settle 14` | still crashes |
| named scenario (`stormy-day`) *and* a generated scenario YAML | still crashes |

So the trigger is **the dashboard being rendered**, not the scenario source, the
publish timing, the settle, or Mock. A light dashboard is fine; the full one is
not. It is not yet bisected to a panel.

## The fault, as far as it shows

`PYTHONFAULTHANDLER=1` puts the crash in a worker thread:

```
QRunnableWrapper::run            (PySide6/QtCore.abi3.so)
QThread::qt_metacall
QTimerInfoList::activateTimers   (QtCore)
_PyEval_EvalFrameDefault         (Python)
PyObject_Str / PyObject_Repr
partial_repr / method_repr       (Python)
unicode_from_format              (Python)
slot_tp_repr                     (Python)
```

A timer-driven runnable is formatting a string that reprs a `functools.partial`
(or a bound method) and touching an object whose C++ side is gone. That is the
class of bug this repo already documents: live Qt objects crash on concurrent
`repr`, which is why traceback locals are off by default.

Also seen on stderr at shutdown: `resource_tracker: There appear to be 21 leaked
semaphore objects` — the plugin thread pools use `multiprocessing`, and their
machinery is up while the interpreter is going down.

## Impact

- **The meter phase 2 gate is not blocked**: it renders presets and the showcase,
  which is the case that works.
- Any *human* trying `render_dashboard.py --scenario` against their own dashboard
  gets a crash and no render, which is worse than the "hangs forever" it used to
  be recorded as (same fragility, different symptom — corrected in
  `meter-harness-status.md`).
- A CI-style check that renders a full board would be flaky at best.

## Suggested directions

1. Bisect by panel: render the seeded default dashboard minus one panel at a
   time (or build up from a preset) until the crash appears, then look at that
   panel's timers/thread use.
2. Find the log/repr site: the faulting string is built by
   `unicode_from_format` around `partial_repr`/`method_repr` — likely a log line
   formatting a callback. Guard it (the repo's rule: never repr live Qt objects
   from another thread) or drop the locals.
3. Check the plugin thread pools' shutdown ordering — `LifecyclePlugin.stop()`
   releases the loop thread, but the multiprocessing pools and Qt timers may
   outlive it. A one-shot render should shut plugins down and drain the pools
   before the process exits.

## Verification

The fix is verified by the same command exiting 0 with a PNG at both ends of the
range: the full default dashboard, and the full pre-refactor baseline capture
(`render_diff.py capture`, 23/23 files, 0 differing pixels).

# SystemError in LevitySceneView.eventFilter (parked — awaiting a recurrence)

**Status:** parked, not fixed. Observed once, non-fatal, could not be
reproduced. Written up so a second sighting starts with context instead of a
cold re-derivation.

## What was seen

Once, during a normal `poetry run python -m LevityDash` startup in
`mode=remote` (2026-07-24, at `1089960`), printed to stderr right after the
dashboard finished loading:

```
Error calling Python override of QGraphicsView::eventFilter(): Traceback (most recent call last):
  File "src/statekit/core.py", line 368, in __get__
    raise AttributeError("unreadable attribute")
AttributeError: unreadable attribute

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "src/LevityDash/lib/ui/frontends/PySide/app.py", line 320, in eventFilter
    if event.type() in ACTIVITY_EVENTS:
       ~~~~~~~~~~^^
SystemError: <function EnumType.__call__ at 0x...> returned a result with an exception set
```

The app was unaffected — PySide catches exceptions raised out of Python
overrides, prints this, and continues. The dashboard rendered and ran fine.

## Mechanism (confirmed, don't re-derive)

**`app.py:320` is the victim, not the culprit.** That `SystemError` is
raised by CPython's own function-result check (`_Py_CheckFunctionResult`):
the enum conversion inside `event.type()` completed *successfully*, but
CPython found an exception **already pending** on the error indicator when
it returned, so it raised `SystemError` and attached the stale exception as
`__cause__`. That's why the traceback reads "the direct cause" rather than
showing normal nesting, and why the `AttributeError` has only a single frame
(the stack was already unwound when it got re-attached).

So the real order of events is:

1. Somewhere earlier, `StateProperty.__get__`
   (`src/statekit/core.py:367-368`) hit
   `if self.fget is None: raise AttributeError("unreadable attribute")` — a
   state property declared without a getter.
2. That exception was swallowed at the Python level but left set at the C
   level.
3. The next C→Python boundary tripped over it. `LevitySceneView.eventFilter`
   runs on *every* event, so it is overwhelmingly the most likely place for
   any leaked exception in this app to surface — it will keep being the
   reported location regardless of the actual source.

**Corollary for next time:** do not start debugging at `app.py:320`. Start by
finding what left an exception pending.

## Ruled out

- **Not a regression from the 2026-07-24 work.** Nothing that day touched
  `statekit` or `LevitySceneView.eventFilter`. The `app.py` changes that day
  added `BackendConnectionIndicator` (a `QLabel` with its own event filter on
  the main window) which never touches statekit.
- **Not `noActivityTimer`** (`app.py:321`, the line immediately after the
  reported one) — it is a plain `QTimer` instance attribute, not a
  `StateProperty`.

## Reproduction attempts that FAILED (don't repeat these)

Both instrumented `StateProperty.__get__` directly and got **zero** hits on
the `fget is None` raise site, and zero pending exceptions on `eventFilter`
entry:

1. Headless boot (`QT_QPA_PLATFORM=offscreen`), full dashboard load, plus a
   forced window resize to drive the settled-resize `_refitAllText` path.
2. A real windowed run (`app.start()`), ~14s, full dashboard load.

So the trigger is interaction- or timing-dependent and does not fire on a
plain boot-and-idle.

## Leading suspect (unconfirmed)

`LevitySceneView._refitAllText`, `app.py:299-303`:

```python
try:
    if item.displayProperties.unitPosition is DisplayPosition.FloatUnder:
        item._syncFloatUnderPair(item.valueTextBox.textBox)
except AttributeError:
    pass
```

A bare attribute access that can raise out of a descriptor, wrapped in a
blanket `except AttributeError: pass` — exactly the swallow-an-AttributeError
shape the mechanism above needs, and it runs on the startup refit path the
original log shows executing. **This was not confirmed** — the instrumentation
never caught it raising. Treat as a starting point, not a diagnosis.

Note `DisplayLabel` sets `self.displayProperties = self` in `__init__`
(`Displays/Realtime.py:1379`), so this access only fails on a partially
constructed or non-`DisplayLabel` item.

## If it recurs

1. **Catch it live** — the app runs continuously on this machine, so a
   temporary patch on `StateProperty.__get__` that logs a full
   `traceback.format_stack()` whenever it raises `AttributeError` will
   identify the property and the caller within a session or two. This is the
   only step that actually answers the question; everything else is guessing.
2. Only then decide on a fix. Likely candidates: give the offending
   `StateProperty` a getter, or narrow the blanket `except AttributeError`
   at the swallow site to an explicit `getattr(..., None)` check.
3. Worth checking whether it correlates with a specific interaction
   (resize, dashboard reload via the `r` key / Dashboard menu, panel drag) —
   the one sighting was at startup, which the `_refitAllText` suspect fits.

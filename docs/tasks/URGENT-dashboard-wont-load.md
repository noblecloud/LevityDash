# 🔴 Dashboard fails to load — gauge value-label is a dict

**Status:** open, blocking. Found 2026-07-27 while trying to run the dashboard
on a room display. **Start here next session.**

## Symptom

`loadDefault` aborts partway through, leaving a broken board:

```
Gauge.py:3431 in refresh
    self.valueLabel.textBox.refresh()
AttributeError: 'dict' object has no attribute 'textBox'
```

## What's actually happening

`self.valueLabel` holds the **raw config dict from the `.levity`**, not a
`GaugeValueLabel`. So the `value-label:` block was assigned into the attribute
instead of being applied onto a constructed label.

Path: `Panel._init_args_` → `self.state = kwargs` → statekit finishes →
`_afterSetState()` → `Gauge._afterSetState` → `refresh()` → `refresh` assumes
`valueLabel` is live. It isn't yet. **An ordering problem**: the gauge refreshes
before its value-label has been decoded into an object.

Everything after this in the log is fallout, not separate bugs:

```
Realtime.py:608  self.display.displayType
AttributeError: type object 'Stateful' has no attribute 'displayType'
```

The `Gauge` constructor raised, so `Realtime.display` was never assigned and is
still the `Stateful` *class* — statekit's unset sentinel. Every mouse-press and
focus event on that panel then raises. This is the same symptom already written
up in [gauge-display.md](gauge-display.md); it is downstream, so don't chase it.

## Prime suspect

**Today's ring composition.** Commit `a6be510` added a `visible` StateProperty
to `GaugeLabel`, and the current dashboard uses the new shape:

```yaml
value-label: {visible: false}
unit-label: {visible: false}
```

Gauges before today used `value-label: {position: …, format: …}` and loaded
fine. Unproven — inferred from the traceback plus what changed. Verify before
acting on it.

**Cheapest bisect:** render a dashboard with the `visible:` keys removed from
the gauge blocks. If it loads, the suspicion is right and the fix belongs in
`Gauge`'s `value-label`/`unit-label` StateProperty — note neither has a
`.decode`, so a dict from YAML may land in the setter verbatim, while a nested
`Stateful` child would normally be built by `.factory` and then have the dict
applied to it.

## Unblocking the room display meanwhile

Timestamped backups sit next to the installed file:

```
~/Library/Application Support/LevityDash/saves/dashboards/default.levity.backup-*
```

A pre-2026-07-27 one should load.

## Second, probably unrelated bug

**The app opens fullscreen despite fullscreen being disabled in `config.ini`.**
Reported same session, not investigated at all. Could be the same saved-geometry
path that clobbers window size in `devtools/_boot.py` (the resize there has to
happen *after* `load_dashboard` for exactly that reason) — worth looking at
whether a saved window state is overriding the config on startup.

## Context

The goal behind all this: get LevityDash running on a display in the author's
room. That is the actual objective, not the dashboard redesign.

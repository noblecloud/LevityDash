# Dashboard fails to load — gauge value-label is a dict

**Status:** open, no longer blocking. Found 2026-07-27; the room display is
running on the gauge-free OpenMeteo template in the meantime.

## ⚠️ The prime suspect below is WRONG — cleared 2026-07-27

Rendered the *installed* `default.levity` (real config copied to a seed) under
`STATEFUL_DEBUG=1`, so statekit's silently-swallowed factory exceptions would
surface:

```
poetry run python src/LevityDash/devtools/render_dashboard.py OUT.png --seed <config-copy>
→ rendered OUT.png (1800x1015 @1x)
```

No `AttributeError`, nothing swallowed. Every gauge using
`value-label: {visible: false}` — wind, humidity, cloud, UV, terrarium — built
correctly and drew as a bare ring. **`a6be510` is not the cause and the ordering
theory does not reproduce on this path.**

Two things that narrow it instead:

- **The traceback never reached a log file.** Zero matches for
  `attribute 'textBox'` or `no attribute 'displayType'` across
  `~/Library/Logs/LevityDash/LevityDash.log{,.1,.2,.3}`. It was terminal-only,
  so the failing run wasn't logging the way a normal `poetry run LevityDash`
  does — that difference is a lead.
- **The difference is the environment, not the `.levity`.** The offscreen render
  has no window, no started plugins and no remote backend; the failing run had
  all three. Author's own hunch: *"there's like a partial sync going on"* — i.e.
  the dashboard file being read while something else is writing it. That fits a
  half-decoded `value-label` far better than a code ordering bug does.

**Next step is capture, not theory:** get the *first* exception of the cascade
from a real failing run (the pasted traceback started mid-cascade). Until then
everything below is history.

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

# condition-pins draws no curve — bisect results

A graph in `condition-pins.levity` renders its chrome (grid, labels, now-marker) but no
data curve. All of the following were ruled out with single-target captures
(`capture --only <stem> --no-freeze-time`; scenario `diff-stable` for every target):

- `thickness:`/`pins:` inside `plot:` vs beside it — both blank
- plain keys vs expressions in both — both blank
- root item vs a group child — both blank
- `emissive`'s graph block copied verbatim — blank
- header naming `hot-clear-day` (emissive's scenario) vs `condition-day` — blank

`emissive` draws its traces in the same capture, so the data path, the scenario and the
harness are fine; the difference is in the preset file itself. Next suspects: the item
`name` (the harness reads `item.name` while settling animations), `animate:` settling,
or the 100%-height geometry.

`ink` cannot answer this question: a 1px curve moves it about 0.001 against a 0.016
grid floor. Look at the PNG.

## Resolved

The preset set no `gradient:` or `color:` on the plot, so the line drew in no visible
colour. Every variant above shared that. Adding `gradient: TemperatureGradient` brings the
curve back. Two smaller faults hid behind it: the unquoted `max(a, b)` thickness key was
split at its comma by the YAML flow mapping (quote any key with a comma), and the scenario
never declared `environment.condition.icon`, so no glyph key existed to pin. A computed
key holds one value, so `thickness:` needs a key with a series; the preset now follows the
temperature itself.

# Bars

A bar shows one value on a straight track. It is the same idea as a gauge: a value, a range, zones, a fill, markers, ticks and labels. The track is a line instead of an arc.

Use `type: realtime.bar`. It takes the key, the title and the geometry that every `realtime` module takes. Everything below goes under `display:`.

```yaml
- type: realtime.bar
  key: system.battery.charge
  title: false
  display:
    range: {min: 0, max: 100}
    caption: Charge
    fill: {color: zone}
    zones:
      - {to: 20, color: $bad, opacity: 0}
      - {from: 20, to: 50, color: $warn, opacity: 0}
      - {from: 50, color: $good, opacity: 0}
    value-label: {position: end, format: {precision: 0}}
```

Sizes are in pixels (`12px`) or a share of the bar's cross size (`20%`). The cross size is the height of a bar that lies down and the width of a bar that stands. Colors can be tokens (`$accent`, `$rule`) or raw values. A raw value wins.

## The four styles

| Style | How to get it | Look in |
|---|---|---|
| Progress | The default. | `docs/design-references/bars/bar-progress.levity` |
| Battery | `style: battery` | `bar-battery.levity` |
| Segmented | `fill: {segments: 10}` | `bar-segmented.levity` |
| Thermometer | `style: thermometer` | `bar-thermometer.levity` |

`bar-day-range.levity` shows a range bar: the fill runs from today's low to today's high, with a pointer on the current value. `bar-showcase.levity` puts all of them on one board.

## Options

### `orientation: horizontal | vertical`

A horizontal bar has its minimum at the left. A vertical bar has its minimum at the bottom. A thermometer always stands.

### `style: bar | battery | thermometer`

`battery` draws an outlined cell with a terminal at the maximum end. `thermometer` draws a tube that stands on a bulb. The scale starts where the tube meets the bulb.

### `range: {min, max}`

The same as on a gauge. The bar rounds the range the way a gauge does, so the ticks fall on round numbers.

### `track: {color, weight, cap, segments, gap}`

The track under the data. `weight` is a size (default 28% of the cross size). `cap` is `round` (default), `square` or `flat`. `color` defaults to `$rule`.

`segments` and `gap` cut the track into cells. A fill that has `segments` cuts the track the same way, unless the track says `segments: false`.

### `fill: {from, to, color, gradient, weight, cap, segments, gap, opacity, glow}`

The part of the track from `from` to `to`.

- `from` and `to` are numbers, keys or expressions. `from` defaults to the range minimum. `to` defaults to the value of the bar.
- `color: zone` uses the color of the zone where the fill ends. With `segments`, each cell uses the color of the zone at its middle.
- `gradient` is a gradient or a token such as `$temperature`. The gradient is laid along the whole track, so a fill shows only as much of it as it reaches.
- `cap` defaults to `round`. It is `flat` when there are `segments`, and in a battery or a thermometer.

A fill whose `from` or `to` comes from a key stays hidden until the key has a value.

### `zones: [{from, to, color, weight, opacity}]`

Colored bands on the track. A missing end is the end of the range. A zone with `opacity: 0` draws nothing but still gives its color to `fill: {color: zone}`.

### `markers: [{value, type, color, size, side}]`

Extra indicators, each at its own value. `value` is a number, a key or an expression such as `min(key, today)`. `type` is `line` (across the track), `notch`, `triangle` or `dot`. `side` is `before` (above a lying bar, left of a standing one) or `after`. A marker with no value yet is hidden.

### `pointer: {type, color, size, side}`

A marker that follows the value of the bar, as a needle does on a gauge. It takes the same types as a marker.

### `major` and `minor`

Ticks. There are none unless you set them.

- `major: {interval, count, length, width, side, color, labels, format, size, every}`. `interval` is in the unit of the data. If you leave it out, the bar picks a round step that gives about five. `count` splits the range instead. `side` is `before`, `after` or `both`. With `labels: true` each tick has a number. The bar leaves out labels that would touch, unless you set `every`.
- `minor: {count, length, width, side, color}`. `count` is the number of steps in each major step (default 5).

### `value-label: {visible, position, align, size, color, format}`

The value as text. `position` is `end` (default), `start`, `above`, `below`, `left`, `right` or `inside`. On a standing bar, `end` is the top and `start` is the bottom. In a thermometer, `inside` is the bulb. `size` is the height of the text as a share of the cross size. `format` is the format of the unit, as on a gauge. Text on the track or in the bulb changes to dark or light so it stays readable.

### `unit-label: {visible, text, size, color}`

The unit word (`mph`) beside the value. It is off unless you set `visible: true`.

### `caption` and `sub-label`

Small text above and below the bar, at its start. Give a string, or `{text, value, format, size, color}`.

### `font`

A font family or a theme font token (`$mono`).

### `glow`

The same as on a gauge. The fill, the zones and the markers inherit it.

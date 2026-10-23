# Switch

A switch shows one of several items. The switch keeps its place in the layout. The space that one item does not need goes to the item that replaces it. It does not go blank.

Use a switch to show UV while it is dry and rain detail while it rains. Use a switch to turn through a few gauges, one at a time, in the same place.

## Choose with a condition

Each child of `items:` fills the switch. Give a child a `when:` to say when it is shown. The switch shows the first child whose `when:` is true.

A child with no `when:` is always true. It is the default. Put it last.

<!-- panels:start -->

<!-- div:left-panel -->

In the example, the switch shows the rain item while it rains. At other times, it shows the UV gauge. The gauge to the left of the switch always shows the temperature.

<!-- div:right-panel -->

```yaml
- type: group
  name: main
  items:
    - type: realtime.gauge
      name: temperature
      key: environment.temperature.temperature
      title: false
      geometry: {x: 1%, y: 4%, width: 29%, height: 92%}
      display:
        radius: 90%
        arc: {gradient: TemperatureGradient, weight: 10%}
        range: {min: 30, max: 110}
        value-label: {position: below}

    - type: switch
      name: sky-switch
      hold: 0.2s
      fade: 0
      geometry: {x: 32%, y: 4%, width: 36%, height: 92%}
      items:
        - type: group
          name: rain
          when: environment.precipitation.precipitation > 0
          items:
            - type: realtime.gauge
              name: rain-rate
              key: environment.precipitation.precipitation
              title: Rain
              geometry: {x: 0%, y: 0%, width: 100%, height: 72%}
              display:
                radius: 90%
                arc: {weight: 8%, gradient: {0: '#4aa3ff', 1: '#b06cff'}}
                range: {min: 0, max: 1}
                value-label: {position: below}
            - type: realtime.text
              name: rain-today
              key: environment.precipitation.daily
              title: Today
              alignment: Center
              geometry: {x: 10%, y: 74%, width: 80%, height: 24%}
        - type: realtime.gauge
          name: uv
          key: environment.light.uvi
          title: UV Index
          display:
            radius: 88%
            arc: {weight: 8%}
            range: {min: 0, max: 12}
            value-label: {position: below}

    - type: realtime.gauge
      name: humidity
      key: environment.humidity.humidity
      title: false
      geometry: {x: 70%, y: 4%, width: 29%, height: 92%}
      display:
        radius: 90%
        arc: {weight: 10%}
        range: {min: 0, max: 100}
        value-label: {position: below}
```

<!-- panels:end -->

A child of a switch does not need a `geometry:`. It fills the switch.

### <div class=mono>when: key | expression | bool</div>

`when:` takes a [value source](/config/dashboard/expressions.md). It is true when the value is true or not zero.

- An expression: `when: environment.precipitation.precipitation > 0`
- An expression with a unit: `when: environment.temperature.temperature > 90°F`
- A key. It is true when the value is not zero: `when: environment.precipitation.precipitation`
- A bool: `when: true`

- If the value is missing, the condition is false.
- If the expression is wrong, LevityDash logs the error once. The condition is then false.
- If no child is true, the switch shows nothing.

### Size conditions

A mapping under `when:` tests the size of the window, or of the item's parent, in the frontend. It is a media query for a dashboard.

```yaml
when: {min-width: 1200px}
when: {max-width: 800px, orientation: portrait}
when: {of: parent, min-aspect: 16:9}
when: {min-width: 1200px, and: environment.precipitation.precipitation > 0}
```

- `min-width`, `max-width`, `min-height`, `max-height`: pixels. `900` and `900px` are the same; other units are an error.
- `min-aspect`, `max-aspect`: width over height, as a number or a ratio (`16:9`).
- `orientation`: `landscape` (also a square) or `portrait`.
- `of`: `window` (the default) or `parent`.
- `and`: a [value source](/config/dashboard/expressions.md) that must also hold. Size and data combine here.

Everything written must hold. A bad condition logs once and counts as false. Size is a fact of this display, so it never goes through the plugins or a backend, and in `remote` mode the frontend reads its own window. In a `switch`, the first child whose size fits is shown, so a narrow layout can follow a wide one. The Studio's `when` popover has a *window or parent size* mode.

`when:` also works on an item that is not in a switch. The item is shown only while the condition is true.

```yaml
- type: text
  text: Freeze warning
  when: environment.temperature.temperature < 32°F
```

## An item in a stack

An item in a `stack` (or a `grid` stack) can use `when:` too. While the condition is false the item is hidden and takes no room, so the items after it move up and the others grow to fill the space. When the condition holds again the item comes back.

```yaml
- type: stack
  direction: Horizontal
  items:
    - {type: realtime.text, key: environment.temperature.temperature}
    - {type: realtime.text, key: environment.precipitation.precipitation, when: environment.precipitation.precipitation > 0}
    - {type: realtime.text, key: environment.wind.speed.speed}
```

## Stop a flicker

A value near a limit can cross the limit again and again. A switch that follows it would flip all the time. `hold:` prevents this.

### <div class=mono>hold: duration</div>

How long a change must last before the switch changes. The default is `30s`. The first choice, when the dashboard loads, is shown at once. `0` makes the switch change at once, always.

A duration is a number of seconds (`30`) or a number with a unit: `500ms`, `30s`, `2m`, `1h`.

## Turn through the children

### <div class=mono>cycle: duration</div>

How long each matching child stays up before the next one takes its place. The default is `0`. With `0`, a switch does not turn. The first match stays.

With `cycle:` set and more than one child that matches, the children take turns in the order of the file. A child with no `when:` always matches, so it is always in the turn.

Add a `when:` to each child to turn through only the children that apply now.

```yaml
- type: switch
  name: rotator
  cycle: 6s
  fade: 0.4s
  geometry: {x: 25%, y: 4%, width: 50%, height: 92%}
  items:
    - type: realtime.gauge
      name: temperature
      key: environment.temperature.temperature
      title: false
      display: {radius: 90%, arc: {gradient: TemperatureGradient, weight: 10%}, range: {min: 30, max: 110}, value-label: {position: below}}
    - type: realtime.gauge
      name: humidity
      key: environment.humidity.humidity
      title: false
      display: {radius: 90%, arc: {weight: 10%}, range: {min: 0, max: 100}, value-label: {position: below}}
    - type: realtime.gauge
      name: uv
      key: environment.light.uvi
      title: false
      display: {radius: 90%, arc: {weight: 8%}, range: {min: 0, max: 12}, value-label: {position: below}}
```

Each switch has its own `cycle:`. Two switches on one dashboard turn at their own rates.

## Fade

### <div class=mono>fade: duration</div>

How long the old child fades out while the new one fades in. The default is `0.3s`. `0` changes at once.

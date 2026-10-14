# Presets

A preset is a module that you write once and use many times. A preset has its own properties. A property has a default. When you use the preset, you write only the properties and fields that are different.

Use a preset for a panel that you repeat with different keys, such as an Indoor box and an Outdoor box. Use it for a gauge style that you want on many gauges.

## Write a preset

A preset is a file in a `presets` folder, named `<name>.yaml`. LevityDash looks in the `presets` folder of your configuration folder first, then in the presets that come with the app.

The file has three parts.

<!-- panels:start -->

<!-- div:left-panel -->

- `props:` The properties. A property is a name with a default. To add a type, a range, or a note, write the name with `default:`, `type:`, `min:`, `max:`, and `doc:`. The types are `number`, `size`, `text`, `key`, `color`, and `bool`. A default can use a property that is defined before it.
- `template:` The module. Write `$name` where a property goes, in the module or in any module inside it.
- `doc:` One line about the preset. This part is optional.

<!-- div:right-panel -->

```yaml
# presets/zone-dial.yaml
doc: Zoned 270-degree dial with the reading in the centre
props:
  key: {default: environment.temperature.temperature, type: key}
  min: {default: 0, type: number}
  max: {default: 100, type: number}
  interval: {default: 20, type: number, min: 0}
  zones: {default: []}
  track: {default: $rule, type: color}
template:
  type: realtime.gauge
  key: $key
  title: false
  display:
    arc: {start-angle: -135, end-angle: 135, weight: 6%, color: $track}
    range: {min: $min, max: $max}
    zones: $zones
    major: {interval: $interval, labels: {position: inside, height: 8%}}
    value-label: {position: center, size: 14%}
```

<!-- panels:end -->

## Use a preset

In the dashboard, write `preset:` with the name of the file. Put the properties that you change under `props:`. Any other field is merged over the template: a mapping is merged key by key, and a list or a value replaces the one in the template.

```yaml
- preset: zone-dial
  name: uv
  geometry: {x: 68%, y: 0%, width: 30%, height: 100%}
  props:
    key: environment.light.uvi
    max: 12
    interval: 2
    zones:
      - {from: 0, to: 3, color: $good}
      - {from: 3, to: 8, color: $warn}
      - {from: 8, to: 12, color: $bad}
  display:
    needle: {type: circle}      # not a property: merged into the template's `display:`
```

## Where a name comes from

`$name` is looked up in this order. The first match is used.

1. The `props:` of the use.
2. The defaults of the preset.
3. The `vars:` of the [dashboard](/config/dashboard/variables.md).
4. The [theme](/config/dashboard/themes.md).

A value that is exactly `$name` keeps its type. `max: $max` is the number `12`, not the text `12`.

## Rules

- A preset can use another preset. A preset cannot use itself, directly or through another preset.
- `preset:` on a stack that is not the name of a preset file keeps its old meaning: the defaults for the items of that stack.
- If a use is wrong, that module becomes a red error tile and the rest of the board loads. A use is wrong when it names a property that the preset does not have, when a value has the wrong type or is out of range, or when the preset file is wrong. The tile tells you why.
- A value that starts with `$` is not type-checked. It is only known after the file is resolved.
- A preset applies when the dashboard loads. Press `Ctrl+R` to see a change to a preset file.

## What a save writes

When you edit a dashboard in the app and save it, a use of a preset stays short.

- `preset:` and `props:` are saved as you wrote them.
- A field is saved only if it is different from what the preset gives. A field that you wrote and did not change is saved as you wrote it, with its `$name` text.
- A list that has any change is saved whole.
- If the app cannot work out a short form, it saves the full module. The result is the same board.

The preset-board example in `docs/design-references/preset-board.levity` saves as 846 bytes. The same board without presets saves as 12,703 bytes.

A saved gauge is written as `type: realtime.gauge`, and a saved bar as `type: realtime.bar`. Both load back as the same display. A gauge no longer saves its derived centre, so the file does not carry it.

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

## Presets that come with the app

These are in the app's `presets` folder. Copy one into your own `presets` folder to change it; yours is found first.

| Preset | What it makes | Properties you will change |
|---|---|---|
| `stat-row` | A row of small readings that share one title size and one value size | `items`, `group`, `font` |
| `reading-list` | A stack of small readings with muted titles | `items`, `direction`, `spacing`, `display` |
| `list-panel` | A titled panel that holds a `reading-list` | `title`, `items`, `spacing` |
| `callout` | One headline reading with a list of supporting readings beside it | `key`, `title`, `color`, `precision`, `items`, `hero_box`, `list_box` |
| `headline-panel` | A headline word, one big reading and a list: the panel of a conditional slot | `headline`, `headline_color`, `key`, `title`, `items`, three boxes |
| `meter-card` | A big reading, a zoned bar and a row of context | `key`, `title`, `color`, `min`, `max`, `zones`, `markers`, `items` |
| `room-card` | One room: temperature hero, a day graph, a row of readings | `title`, `key`, `extra`, `graph`, `items` |
| `compass` | A wind compass with the speed in the middle | `key`, `speed`, `label`, `arc_weight` |
| `ring` | A thin filled ring with no text, to nest | `key`, `radius`, `color`, `weight` |
| `sparkline` | A small graph with no labels, one or two series | `key`, `plot`, `key2`, `plot2`, `hours`, `min`, `max` |
| `day-column` | One day of a week table: high, low, rain, gust, heading | `label`, `offset` |
| `zone-dial`, `readout-bar`, `hero-readings` | A zoned dial, a captioned bar, a titled panel of four readings | See the files |

Every property has a `doc:` line in its file. The boards in `docs/design-references/boards` use them: `station`, `storm`, `sky` and `week`.

The module's own fields (`name`, `geometry`, `size`, `when`) are applied before its `items`, wherever you write them, so the children lay out against the final size.

## Leave a property out

A property whose default is `null` is not written at all when you do not set it. Where a preset has `font: $font` and you do not give `font`, the module has no `font` key, so it takes the font of the panel around it. The same holds for a mapping key (`$key2: {...}` is left out when `key2` is `null`), for a list item that is only `$prop`, and for a mapping that this leaves empty. You can also write `null` in `props:` to remove something that the default sets.

A property can also be the name of a key in the template. In `sparkline`, `$key: {plot: $plot}` writes the series under the key that you gave.

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

Known limit: a saved board with a gauge does not load back as the same board until [the gauge save fix](https://github.com/noblecloud/LevityDash/pull/66) is merged. This was true before presets.

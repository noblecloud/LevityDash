# Presets

A preset is an item that you write once and use many times. A preset has its own properties. A property has a default. Each use of a preset in a dashboard is an instance. An instance holds only the properties and fields that are different.

Use a preset for an item that you repeat with different keys, such as an Indoor box and an Outdoor box. Use it for a gauge style that you want on many gauges.

## Write a preset

A preset is a file in a `presets` folder, named `<name>.yaml`. LevityDash looks in the `presets` folder of your configuration folder first, then in the presets that come with the app.

The file has three parts.

<!-- panels:start -->

<!-- div:left-panel -->

- `props:` The properties. A property is a name with a default. To add a type, a range, or a note, write the name with `default:`, `type:`, `min:`, `max:`, and `doc:`. The types are `number`, `size`, `text`, `key`, `color`, and `bool`. A default can use a property that is defined before it.
- `template:` The item. Write `$name` where a property goes, in the item or in any item inside it.
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

## Make an instance

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
| `stat-row` | A row of small readings that share one title size and one value size | `items`, `titleGroup`, `valueGroup`, `font` |
| `reading-list` | A stack of small readings with muted titles | `items`, `direction`, `spacing`, `font`, `precision`, `titleGroup`, `valueGroup` |
| `list-panel` | A titled panel that holds a `reading-list` | `title`, `items`, `spacing`, `font` |
| `callout` | One headline reading with a list of supporting readings beside it | `key`, `title`, `color`, `precision`, `items`, `hero_box`, `list_box` |
| `headline-panel` | A headline word, one big reading and a list: the panel of a conditional slot | `headline`, `headline_color`, `key`, `title`, `items`, three boxes |
| `meter-card` | A big reading, a zoned bar and a row of context | `key`, `title`, `color`, `min`, `max`, `zones`, `markers`, `items` |
| `room-card` | One room: temperature hero, a day graph, a row of readings | `title`, `key`, `extra`, `graph`, `items` |
| `compass` | A wind compass with the speed in the middle | `key`, `speed`, `label`, `arc_weight` |
| `ring` | A thin filled ring with no text, to nest | `key`, `radius`, `color`, `weight` |
| `sparkline` | A small graph with no labels, one or two series | `key`, `plot`, `key2`, `plot2`, `hours`, `min`, `max` |
| `day-column` | One day of a week table: high, low, rain, gust, heading | `label`, `offset`, `headGroup` |
| `metric-tile` | A reading as the hero over its own day graph, with a row of context readings | `key`, `title`, `color`, `hint`, `hours`, `line`, `items`, three boxes |
| `ring-reading` | A ring with the number inside and a caption under it | `key`, `title`, `color`, `min`, `max`, `hint`, `start_angle`, `end_angle` |
| `range-bar` | A bar from today's low to its high with a marker for now, and a Low, Now, High row | `key`, `low`, `high`, `min`, `max`, `interval`, `gradient` |
| `hour-column` | One hour of an hourly table: temperature, feels, rain chance, rate, gust | `label`, `offset`, `headGroup` |
| `bar-stack` | A vertical stack of bars, for readout-bars that share a scale | `items`, `spacing` |
| `polar-card` | A titled polar plot: rose, trail or clock | `title`, `plot`, `direction`, `speed`, `key`, `window` |
| `alert-strip` | A wide, short panel: a word, the reading behind it and context readings | `headline`, `color`, `key`, `items` |
| `climate-card` | One room or chamber: temperature over its day, a humidity ring, dew point, gap, range | `title`, `id`, `temp_min`, `temp_max`, `humid_min`, `humid_max` |
| `zone-dial`, `readout-bar`, `hero-readings` | A zoned dial, a captioned bar, a titled panel of four readings | See the files |

Every property has a `doc:` line in its file. The dashboards in `docs/design-references/dashboards` use them: `station`, `storm`, `sky`, `week`, `garden`, `wind`, `rain`, `house`, `homelab`, `glance` and `gallery`.

An item's own fields (`name`, `geometry`, `size`, `when`) are applied before its `items`, wherever you write them, so the children lay out against the final size.

## Size groups

The presets that hold text (`stat-row`, `reading-list`, `day-column`, `hour-column`) put it in dashboard-wide size groups: titles in `global.title`, values in `global.value` and the day names in `global.head`, all `matchAll`. Every such preset on the dashboard then reads at one size per role. A tier still keeps a hero and its satellites apart. The group names are properties (`titleGroup`, `valueGroup`, `headGroup`); change one only for a part of the dashboard that should differ on purpose. A `global.` group needs no scope name, so a preset carries it without a property for the panel's name.

## Leave a property out

A property whose default is `null` is not written at all when you do not set it. Where a preset has `font: $font` and you do not give `font`, the item has no `font` key, so it takes the font of the panel around it. The same holds for a mapping key (`$key2: {...}` is left out when `key2` is `null`), for a list item that is only `$prop`, and for a mapping that this leaves empty. You can also write `null` in `props:` to remove something that the default sets.

A property can also be the name of a key in the template. In `sparkline`, `$key: {plot: $plot}` writes the series under the key that you gave.

## Where a name comes from

`$name` is looked up in this order. The first match is used.

1. The `props:` of the instance.
2. The defaults of the preset.
3. The `vars:` of the [dashboard](/config/dashboard/variables.md).
4. The [theme](/config/dashboard/themes.md).

A value that is exactly `$name` keeps its type. `max: $max` is the number `12`, not the text `12`.

## Rules

- A preset can contain an instance of another preset. A preset cannot contain an instance of itself, directly or through another preset.
- `preset:` on a stack that is not the name of a preset file keeps its old meaning: the defaults for the items of that stack.
- If an instance is wrong, that item becomes a red error tile and the rest of the dashboard loads. An instance is wrong when it names a property that the preset does not have, when a value has the wrong type or is out of range, or when the preset file is wrong. The tile tells you why.
- A value that starts with `$` is not type-checked. It is only known after the file is resolved.
- A preset applies when the dashboard loads. Press `Ctrl+R` to see a change to a preset file.

## What a save writes

When you edit a dashboard in the app and save it, an instance of a preset stays short.

- `preset:` and `props:` are saved as you wrote them.
- A field is saved only if it is different from what the preset gives. A field that you wrote and did not change is saved as you wrote it, with its `$name` text.
- A list that has any change is saved whole.
- If the app cannot work out a short form, it saves the full item. The result is the same dashboard.

The preset-dashboard example in `docs/design-references/preset-dashboard.levity` saves as 846 bytes. The same dashboard without presets saves as 12,703 bytes.

A saved gauge is written as `type: realtime.gauge`, and a saved bar as `type: realtime.bar`. Both load back as the same display. A gauge no longer saves its derived centre, so the file does not carry it.

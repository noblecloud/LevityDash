# Size groups

Text fits its box. Two labels with boxes of different shapes come out at different sizes. A size group makes labels agree, so a row of values or a column of titles reads as one table.

## Join a group

Write `matchingGroup:` on a label. A label is a `text` item, the `title` of a reading, the `valueLabel` of a reading, or a label of a gauge or bar.

```yaml
- type: stack
  name: wind
  shared:
    title: {matchingGroup: {group: rowTitle@wind, matchAll: true}}
    display:
      valueLabel: {matchingGroup: {group: rowValue@wind, matchAll: true}}
  items:
    - {type: realtime.text, key: environment.wind.speed.speed, title: {text: Wind}}
    - {type: realtime.text, key: environment.wind.speed.gust, title: {text: Gust}}
```

- `group:` is `key@name`. The name is the `name:` of a panel around the label. The key is yours. All labels with the same key and the same panel name are one group.
- Put the group in `shared:` on the panel. Every reading inside then joins it.
- Give titles and values different keys. A title and a value are never the same size.
- A plain string, `matchingGroup: rowTitle@wind`, makes a proximity group. Only labels whose boxes touch (within 10 px) share a size. Use `matchAll: true` when the labels are far apart or their boxes differ.
- `value-stack` already puts its titles in one group and its values in another.

The other places a group can live are `local.key`, `parent.key`, `global.key`, `group.key`, and `<type>.key` (the nearest panel of that type).

## What a group does

- **Tiers.** Labels with boxes of about the same height share a size. A box more than about 10 px taller or shorter is a different tier, so a large hero and a small caption in one group do not shrink to match.
- **Size.** The label with the tightest box sets the size for the tier.
- **Baseline.** In a plain group, labels with the same vertical alignment also share a baseline. A `matchAll` group keeps each label where it is.
- **Number shape.** A value is sized against the widest text it can show, so 7, 13 and 101 come out the same. A value with no digits, such as a compass point, has no such shape. Give it `format-hint`, for example `format-hint: WNW`.

## Mistakes

- A name that no panel has. LevityDash does not report it. Each label gets a group of its own, and the sizes will not match. Check the spelling of the `name:`.
- A fixed font size on a label in the group. The group does not resize it.
- A grid, a flex stack or a stack of `realtime.text` items that has no group. Layout does not match text sizes. Add one.
- `matchAll: true` on one label and not on another with the same key. The first one that loads decides.
- Two uses of one preset with the same group name. Give the preset a property for the name, as the `stat-row` preset does.

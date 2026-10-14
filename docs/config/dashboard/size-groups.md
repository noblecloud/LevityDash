# Size groups

A size group keeps text the same size across a dashboard. Each label fits its own box, so two labels in boxes of different shape come out at different sizes. When every title, value and caption of one kind belongs to one group, the whole dashboard reads as one design, however many panels it has.

Pick a role for each kind of text (`title`, `value`, `cap`, ...) and give every label of that role the same group. The example boards in `docs/design-references/boards/` do this with `global.title` and `global.value`. Where a role needs its own size, such as the Week day headings, give it its own key (`global.head`).

## Join a group

Write `matchingGroup:` on a label. A label is a `text` item, the `title` of a reading, the `valueLabel` of a reading, or a label of a gauge or bar.

```yaml
- type: stack
  shared:
    title: {matchingGroup: {group: global.title, matchAll: true}}
    display:
      valueLabel: {matchingGroup: {group: global.value, matchAll: true}}
  items:
    - {type: realtime.text, key: environment.wind.speed.speed, title: {text: Wind}}
    - {type: realtime.text, key: environment.wind.speed.gust, title: {text: Gust}}
```

`shared:` on a panel gives its setting to every reading inside, so write the group once per panel.

## Where a group lives

The text before the dot, or after the `@`, says which panel owns the group. The key after the dot is yours. Labels with the same owner and the same key are one group.

| Written as | Owner | Use it for |
| --- | --- | --- |
| `global.key` | the whole dashboard | one look everywhere |
| `type.key` | the nearest panel of that type, for example `group.key`, `stack.key`, `realtime.key` | one look per section of that type |
| `key@name` | the nearest panel above with that `name:` | one look per named panel, such as `value@weather` |
| `parent.key` | the panel one level above the label's own | one look per row or column |
| `local.key` | the label's own panel | labels in one panel |

Use `global` for text that should match on the whole dashboard. Use a name or a type to match inside one part of it, so a dense panel can keep smaller text than a sparse one.

A group is made the first time a label asks for it, so the first `matchAll` setting on a key decides for all labels that use it.

## What a group does

- **Size.** The label with the tightest box sets the size, so every member shows its widest text without clipping.
- **Tiers.** Labels with boxes of about the same height (within about 10 px) share one size. A box that is much taller or shorter is another tier, with its own size. Because of this a hero value and a small caption can share a group without the hero shrinking to match. To make two heights agree, give them the same box height.
- **`matchAll`.** The whole tier is one set and each label stays where it is. A plain string, `matchingGroup: title@wind`, is a proximity group: only labels whose boxes are within 10 px of each other share a size. Use `matchAll: true` for labels that are far apart.
- **Number shape.** A value is sized against the widest text it can show, so 7, 13 and 101 come out the same. A value with no digits, such as a compass point or a clock, has no such shape. Give it `format-hint`, for example `format-hint: WNW` or `000k`.
- `value-stack` already puts its titles in one group and its values in another for each stack.

## Mistakes

- A name that no panel has. LevityDash does not report it. Each label gets a group of its own, and the sizes do not match. Check the spelling of the `name:`.
- A fixed font size on a label in the group. The group does not resize it.
- A grid, a flex stack or a stack of `realtime.text` items that has no group. A layout does not match text sizes. Add a group.
- A title and a value in one group. They have boxes of different height, so they land in different tiers and never match. Give each role its own key.
- `matchAll: true` on one label and not on another with the same key.
- Two uses of one preset that share a group name. Give the preset a property for the name, as the `stat-row` preset does.

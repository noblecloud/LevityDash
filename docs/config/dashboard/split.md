# Split

A split puts two items on either side of a divider. Each item fills its side. Drag the divider to change how much space each side has.

Use a split when two parts of a dashboard should share a space in a fixed proportion, and you want to move that proportion by hand. For automatic layout of more items, use a [stack](/about/items.md) or [flex and grid](/config/dashboard/layout.md).

```yaml
- type: split
  name: outer
  orientation: vertical
  ratio: 0.4
  items:
    - type: stack            # first item: the left side
      name: now
      direction: vertical
      items:
        - {type: realtime.text, key: environment.temperature.temperature, title: {text: Temperature}}
        - {type: realtime.text, key: environment.humidity.humidity, title: {text: Humidity}}
    - type: split            # second item: the right side, split again
      name: right
      items:
        - {type: stack, name: uv, items: [{type: realtime.text, key: environment.light.uvi, title: {text: UV}}]}
        - {type: stack, name: rain, items: [{type: realtime.text, key: environment.precipitation.probability, title: {text: Rain chance}}]}
```

A complete dashboard is in `docs/design-references/dashboards/split.levity`.

## Items

A split holds one or two items. The first is on the left (vertical divider) or at the top (horizontal divider). One item fills the whole split. More than two items is an error: the split is replaced by an error tile that names the problem.

An item of a split does not need a `geometry:`. The divider sets it. If you write one, it is ignored, and a save does not write it. An item of a split also does not save `locked:`, `movable:` or `resizable:`. A split can be an item of a split.

### <div class=mono>orientation: horizontal | vertical</div>

The direction of the divider line. The default is `horizontal`.

- `horizontal`: the divider runs left to right. The first item is above it.
- `vertical`: the divider runs top to bottom. The first item is to its left.

### <div class=mono>ratio: number</div>

The share of the split that the first item has, from `0` to `1`. The default is `0.5`. A percentage also works: `ratio: 40%`. At `0` or `1`, one item is hidden and the other fills the split.

## Move the divider

In the dashboard, drag the divider to change `ratio`. Double-click the divider to swap the two sides. A save writes the new `ratio` and the new order of the items.

A save writes `orientation` and `ratio` only when they are not the default. An item of a split is saved as it is anywhere else.

## Size groups

A split does not group text and does not cut a group in two. Items on both sides of a divider that name the same [size group](/config/dashboard/size-groups.md), for example `global.value`, keep one text size. This stays true when the divider moves. Each item fills its own box, so a group still sets the size from its tightest box.

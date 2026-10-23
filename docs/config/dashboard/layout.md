# Flex and grid layout

A `stack` puts its items in a line. By default, an item with a `size:` keeps that size, and the items without one share what is left equally. This does not change. Add `flex:` to a stack or to one of its items and the stack uses CSS flexbox rules instead. Use `type: grid` for rows and columns.

Layout follows the CSS specifications. If you know CSS, the words mean what you expect.

## Flex

Put `flex:` on the stack for the container options. Put `flex:` on an item for the item options.

```yaml
- type: stack
  direction: horizontal
  spacing: 10px
  flex: {justify: space-between}
  items:
    - {type: text, text: fixed, size: 20%}
    - {type: text, text: grows, flex: {grow: 1}}
    - {type: text, text: grows twice as much, flex: {grow: 2}}
```

### Container options (on the stack)

| Key | Values | CSS |
|---|---|---|
| `justify` | `flex-start` (default), `flex-end`, `center`, `space-between`, `space-around`, `space-evenly`. Add `safe` in front, as in `safe center`. | `justify-content` |
| `align-items` | `stretch` (default), `flex-start`, `flex-end`, `center`, `baseline` | `align-items` |
| `wrap` | `nowrap` (default), `wrap`, `wrap-reverse` | `flex-wrap` |

`direction: horizontal | vertical` is `flex-direction`. `spacing:` is the `gap`, between items and between lines.

### Item options (on an item)

| Key | Meaning | CSS |
|---|---|---|
| `grow` | The share of the free space this item takes. An item with no `size`, no `basis` and no `grow` has `grow: 1`. | `flex-grow` |
| `shrink` | The share of the shortfall this item gives up, weighted by its size. Default 1. | `flex-shrink` |
| `basis` | The size before growing and shrinking. `size:` does the same. `auto` sizes the item by its text (see *Content size* below). | `flex-basis` |
| `min`, `max` | The least and most size along the stack. | `min-width`, `max-width` |
| `cross` | The size across the stack. Default: the full width of the line. | `height` in a row |
| `align-self` | Overrides `align-items` for one item. | `align-self` |
| `order` | Items go in order of this number, then in file order. Default 0. | `order` |
| `margin` | Space around the item: one, two or four values (top, right, bottom, left), as a list or a string. A side can be `auto` or a `%` (of the stack's inner width, on every side). `auto` takes the free space on that side. `margin: [0, 0, 0, auto]` pushes the item and all after it to the end. | `margin` |

Sizes take `%`, `px`, `mm`, `cm` and `in`, as everywhere else. Anywhere a length goes in `flex:` or `grid:` (`basis`, `min`, `max`, `cross`, `margin`, `gap`, track sizes) you can write `calc()`, `min()`, `max()` or `clamp()`: `calc(100% - 2 * 12px)`. `+` and `-` need a space on both sides, and a length cannot be multiplied by a length. This is css-values-4 section 10.

An item with a `size:` and no `flex:` keys does not grow, and it can shrink. This is the CSS default. A stack that has only `flex: {justify: ...}` can therefore shrink items that do not fit, where a plain stack lets them overflow.

## Grid

```yaml
- type: grid
  spacing: 10px
  grid: {columns: [2fr, 1fr, 1fr], rows: [1fr, 1fr, 1fr]}
  items:
    - {type: realtime.text, key: environment.temperature.temperature, grid: {column: 1, row: 1, row-span: 3}}
    - {type: realtime.text, key: environment.humidity.humidity}
    - {type: realtime.text, key: environment.pressure.pressure}
    - {type: realtime.text, key: environment.wind.speed.speed, grid: {column: 2, column-span: 2}}
```

Named areas read like the board. `.` is an empty cell, and a name repeated over cells is one rectangle:

```yaml
- type: grid
  spacing: 0
  padding: 0
  grid:
    columns: [38fr, 2fr, 33fr]
    rows: [24fr, 12fr]
    areas:
      - clock . now
      - stats . now
  items:
    - {type: realtime.text, key: environment.temperature.temperature, grid: {area: now}}
    - {type: realtime.text, key: environment.humidity.humidity, grid: {area: clock}}
    - {type: realtime.text, key: environment.pressure.pressure, grid: {area: stats, margin: [0, 8px]}}
```

A `.` is a real track, so `spacing` (the gap) applies on both sides of it, and so does `padding`. Set both to 0 when the picture spells out its own gaps, as above.

### Grid options (on the `type: grid`)

| Key | Meaning | CSS |
|---|---|---|
| `columns`, `rows` | A list of track sizes: lengths, `fr`, `auto`, `min-content`, `max-content`, `minmax(a, b)`, `fit-content(x)`, `repeat(n, ...)`, `repeat(auto-fill, ...)` and `repeat(auto-fit, ...)`. A `%` is a share of the grid's inner size. A string such as `'repeat(3, 1fr)'` works too. `repeat(auto-fill, minmax(200px, 1fr))` makes as many 200px-or-wider columns as the grid's width holds, and the count changes when the window does. `auto-fit` does the same and then drops the empty columns. | `grid-template-columns`, `grid-template-rows` |
| `areas` | A picture of the grid: a list with one string per row and one word per cell, `.` for an empty cell. Each name must cover one rectangle. It makes the explicit grid at least as big as the picture; tracks `columns` and `rows` do not list are sized by `auto-columns` and `auto-rows`. An item picks its place with `grid: {area: name}`. | `grid-template-areas` |
| `auto-columns`, `auto-rows` | The size of a track that the items need and the list does not give. Default `1fr`. | `grid-auto-columns`, `grid-auto-rows` |
| `auto-flow` | `row` (default) or `column`. | `grid-auto-flow` |
| `dense` | `true` fills earlier holes. | `dense` |
| `gap` | One value, or `[row, column]`. Default: `spacing`. | `gap` |
| `justify-content`, `align-content` | Where the tracks sit when they do not fill the grid. Same words as `justify`. | same |
| `justify-items`, `align-items` | How items sit in their area. Default `stretch`. | same |

### Grid item options (on an item)

`grid: {column, row, column-span, row-span, area, justify-self, align-self, shrink, margin}`. `area: name` places the item on a named area of `areas` and cannot be combined with `column`, `row` or a span. Lines count from 1. `margin` is the same shorthand as in flex. The margin box counts toward track sizes, and an `auto` side turns stretching off and takes the free space in the area, so two `auto` sides centre the item. An item with no `column` or `row` goes in the next free cell.

Spans are how a layout gets a bento look: put `dense: true` on the grid, give the large items a `column-span` or `row-span`, and the small ones fill the holes in order.

`shrink: true` (not CSS) lets an auto-placed item give up columns when it does not fit. It tries its full span in every hole of the explicit rows, from the top-left, and then the next narrower span, so a wide card lands in a gap rather than dropping below the rest. Rows must be declared (`rows: [...]`) for it to have anything to shrink into; with no explicit rows an item keeps its span and opens a new row. An item with a fixed `column` or `row` is never shrunk.

## Content size

An item that shows a number reports its size from its **format hint**, the widest text it can show, set in its own font. It never uses the value on screen, so the layout does not move when the number changes. The hint gives a width-to-height shape; the size follows from the other axis, as it does for an image.

- `flex: {basis: auto}` starts the item at that width (row) or height (column) and then applies `grow` and `shrink`. Default `grow` with `basis: auto` is 0.
- In a grid, an `auto`, `min-content` or `max-content` track is as wide as its widest hinted item, taking the item's height as one even row of the grid.

## Dividers

`dividers: {enabled: true}` draws a line in the middle of the gap between neighbours, as in a plain stack: between columns in a row, between rows in a column, and both in a grid. `dividers.size` shortens the lines.

## Border radius

`border: {enabled: true, radius: 12px}` rounds the corners of a border on all edges. A number or `px` is pixels; `8%` is a share of the shorter side, so `50%` makes a pill (or a circle in a square). The radius never passes half the shorter side. A border on some edges only stays straight.

`fill: '#2a4a6a'` fills the inside of a border on all edges, following the radius and sitting behind the item's content; `weight: 0` leaves the fill with no line. Any colour form works, tokens and alpha included (`fill: {color: $surface, alpha: 0.6}`). A fill on some edges only is ignored. To keep the curves parallel in a nested box, give the inner border `offset: X` and the same `$gap` in `padding`, with the inner radius the outer radius less `X`.

## Rules

- A stack without any `flex:` key, and no item with one, is laid out exactly as before. A grid is always laid out by the grid engine.
- A mistake in `flex:` or `grid:` (an unknown key, a wrong word) is an error on that item. The rest of the dashboard loads.
- A cell sizes its own text. To make the values in a grid or flex stack the same size, add a `shared:` size group (see the example dashboard).
- Not yet supported: `subgrid`, named lines, math functions in `size:`, `geometry:` and `spacing:` (only `flex:` and `grid:` take them), and sizing by anything but the text of a value (a gauge, a graph or a container has no content size, so for them `auto` is 0).

Example dashboards: `docs/design-references/grid-areas.levity` (named areas), the glance and homelab dashboards in `docs/design-references/dashboards/` (areas replacing hand-placed boxes), `docs/design-references/layout-margins.levity` (margins), `docs/design-references/css-layout.levity` (render: `docs/design-references/css-layout.png`) and `docs/design-references/grid-bento.levity`, a dense bento board with spans, a `shrink` item and an `auto-fill` strip.

## In the Studio

`studio.py` (the Studio builder) edits these keys. A stack, a `grid`, and each of their items has a **Layout** section on the Item tab with a `flex` or `grid` popover. The popover shows the container options when the item is a stack or grid and the item options when its parent is one; an option left on its default is not written, and a stack with nothing set stays a plain stack. The popovers also edit `margin` (flex and grid items), `areas` (one row per line) and `area`. `area` is a picker over the names in the parent grid's `areas` (a name that is not there can still be typed). Select a grid, or an item in one, and the stage tags every cell with its area name. The [Studio page](/config/dashboard/studio.md) covers the rest of the editor.

## Aligning to a sibling

`align-to:` puts one point of an item on one point of a named sibling in the same `group`, instead of placing it by the parent's box. It is CSS anchor positioning (`anchor()`), with the sibling's `name:` as the anchor name. The item's size still comes from `geometry:`; the position comes from the sibling, so the item follows when the sibling moves or the dashboard is resized.

```yaml
- {name: temp, type: realtime.text, key: environment.temperature.temperature, geometry: {x: 8%, y: 15%, width: 40%, height: 45%}}
- type: text
  text: Outside
  geometry: {x: 0%, y: 0%, width: 40%, height: 10%}
  align-to: {to: temp, x: center, y: bottom, self-y: top, offset: {y: 1mm}}
```

| Setting | Meaning |
| --- | --- |
| `to` | The `name` of the sibling. `align-to: temp` alone centres the item on it both ways. |
| `x` | The point on the sibling: `left`, `center` or `right`. |
| `y` | The point on the sibling: `top`, `center` or `bottom`. |
| `self-x`, `self-y` | The point on this item. Default: the same word as `x` and `y`, so `x: right` lines the right edges up, and `x: right, self-x: left` puts the item beside the sibling. |
| `offset` | `{x, y}` lengths added last; positive is right and down. |

Name only `x` or only `y` to follow the sibling on one axis and keep the item's own position on the other. An item that is itself aligned settles first, so a chain works; a loop does not (the items stay where they are). A sibling that does not exist logs one warning. `align-to` is not `anchor:` because a gauge already has an `anchor`. Example: `docs/design-references/align-to.levity`; code: `lib/layout/anchor.py`.

## Overflow and scrolling

`overflow:` on a `stack` (flex or grid) says what happens to content that does not fit. It is CSS `overflow`.

| Value | Effect |
|---|---|
| `visible` | The default. Nothing is cut off; items shrink by `shrink` as before. |
| `hidden`, `clip` | Content past the stack's box is cut off. The user cannot move it. |
| `scroll` | Cut off, and the wheel or trackpad moves the content. A thin bar always shows. |
| `auto` | As `scroll`, but the bar shows only while the content is longer than the box. |

The scroll axis is the stack's main axis (`direction`). In a scrolling stack an item that has a size (`size:`) defaults to `shrink: 0`, so it keeps that size and overflows instead of being squeezed; give an item `shrink: 1` to let it give. The scroll stops at both ends. Wheel and trackpad only: there is no touch drag yet, and a wrapping stack does not scroll on its cross axis. Example: `docs/design-references/overflow.levity`; code: `lib/layout/overflow.py` (Qt-free math) and `Stack.cssScroll`.

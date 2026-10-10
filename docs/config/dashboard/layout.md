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
| `basis` | The size before growing and shrinking. `size:` does the same. | `flex-basis` |
| `min`, `max` | The least and most size along the stack. | `min-width`, `max-width` |
| `cross` | The size across the stack. Default: the full width of the line. | `height` in a row |
| `align-self` | Overrides `align-items` for one item. | `align-self` |
| `order` | Items go in order of this number, then in file order. Default 0. | `order` |

Sizes take `%`, `px`, `mm`, `cm` and `in`, as everywhere else.

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

### Grid options (on the `type: grid`)

| Key | Meaning | CSS |
|---|---|---|
| `columns`, `rows` | A list of track sizes: lengths, `fr`, `auto`, `min-content`, `max-content`, `minmax(a, b)`, `fit-content(x)`, `repeat(n, ...)`, `repeat(auto-fill, ...)` and `repeat(auto-fit, ...)`. A string such as `'repeat(3, 1fr)'` works too. | `grid-template-columns`, `grid-template-rows` |
| `auto-columns`, `auto-rows` | The size of a track that the items need and the list does not give. Default `1fr`. | `grid-auto-columns`, `grid-auto-rows` |
| `auto-flow` | `row` (default) or `column`. | `grid-auto-flow` |
| `dense` | `true` fills earlier holes. | `dense` |
| `gap` | One value, or `[row, column]`. Default: `spacing`. | `gap` |
| `justify-content`, `align-content` | Where the tracks sit when they do not fill the grid. Same words as `justify`. | same |
| `justify-items`, `align-items` | How items sit in their area. Default `stretch`. | same |

### Grid item options (on an item)

`grid: {column, row, column-span, row-span, justify-self, align-self}`. Lines count from 1. An item with no `column` or `row` goes in the next free cell.

## Rules

- A stack without any `flex:` key, and no item with one, is laid out exactly as before. A grid is always laid out by the grid engine.
- A mistake in `flex:` or `grid:` (an unknown key, a wrong word) is an error on that item. The rest of the board loads.
- Dividers are not drawn in a flex or grid stack.
- Not yet supported: `subgrid`, named areas, `calc()`, `%` inside a track list, margins on items, and sizing by the text inside an item. Items do not report a content size, so `auto` tracks and `basis: auto` have no content to measure.

Example board: `docs/design-references/css-layout.levity` (render: `docs/design-references/css-layout.png`).

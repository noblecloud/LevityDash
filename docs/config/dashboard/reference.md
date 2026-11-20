# Dashboard reference

One page that lists every customization a `.levity` dashboard supports: the item types, the keys each takes, the values those keys accept, and where to find a worked example. It is written to brief a designer (human or model) who has not seen the app. The detail pages linked from each section go deeper; this page is the map and the lookup table.

The tables under **Key tables** are generated from the code (`@StateProperty` on each class) by `docs/_scripts/gen_reference.py`. Do not edit them by hand; edit the docstring in the code and run the script. `--check` fails if they are stale.

## 1. The shape of a dashboard

A dashboard is one YAML file with the extension `.levity`. The root takes `theme`, `vars`, `background` and `items`. Everything on screen is an **item**: one entry under `items:` with a `type:`. Items nest.

```yaml
theme: {extends: default, colors: {accent: '#ff9124'}, fonts: {display: Nunito, mono: Roboto Mono}}
vars: {t: environment.temperature.temperature}
items:
- type: group
  name: board
  items:
  - type: realtime.text
    name: now
    key: $t
    geometry: {x: 2%, y: 2%, width: 40%, height: 30%}
```

Rules that trip people up:

- Quote hex colours (`'#ff9124'`); unquoted, YAML reads `#` as a comment.
- Every item has `geometry` (`x`, `y`, `width`, `height`), by default the whole parent. Percent is of the parent. Units: `%`, `px`, `mm`, `cm`, `in`. Siblings whose geometry overlaps stack in file order, last on top. That is how a value goes over a graph.
- Inside a `stack` or `grid` the container places the items and `geometry` is ignored; use `size`, `flex` or `grid` on the item instead.
- `type: disabled-<type>` or `hidden-<type>` skips an item at load.
- Item `name`s are what `align-to`, `time-axis` and `@name` size groups refer to. Name anything another item points at.
- `when:` shows an item only while a key, expression or bool is true.

Item types, at a glance:

| Kind | `type:` | Detail page |
|---|---|---|
| Container, free layout | `group`, `titled-group` | [dashboard.md](../dashboard.md) |
| Container, automatic layout | `stack` (row or column, flex), `value-stack`, `grid` | [layout.md](layout.md) |
| Container, conditional or interactive | `switch`, `band`, `split` | [switch.md](switch.md), [band.md](band.md), [split.md](split.md) |
| Table | `preset: table` with `props: {columns, rows}` | [table.md](table.md) |
| Text | `text` / `label` | [dashboard.md](../dashboard.md) |
| One live reading | `realtime.text`, `realtime.gauge`, `realtime.bar` (plain `realtime` is the text one) | [dashboard.md](../dashboard.md), [bar.md](bar.md) |
| Time series | `graph`, `mini-graph` | [dashboard.md](../dashboard.md) |
| Radial wind or time plots, radar of aircraft | `polar` (`plot: rose / trail / clock / radar`) | presets `polar-*` |
| Clock, moon | `clock`, `moon` | [dashboard.md](../dashboard.md) |
| Dividers, gaps | `divider`, `spacer` (inside a stack) | [layout.md](layout.md) |
| A reusable item | `preset: name` with `props:` | [presets.md](presets.md) |

## 2. What every item shares

All the keys of `type: group` (first table under **Key tables**) work on every item.

- **Box**: `geometry`, `margins`, `padding`, `opacity` (a number, or `{of, from, to}`), `border`, `align-to`, `time-axis`, `name`.
- **Behaviour**: `when`, `movable`, `resizable`, `locked`, `frozen` (the last four only matter in edit mode).
- **Type**: on any text and on a reading's `valueLabel`: `font`, `weight`, `italic`, `tracking` (letter spacing in em; open up capitals, tighten a big number), `decimal-scale` and `decimal-align` (the digits after the point at a smaller size, level with the baseline or the top), `outline` (hollow letters: a weight, or `{weight, color, fill}`), `filters`, `warp`. Worked examples: the five dashboards in `docs/design-references/showcase/`.
- **Effects**: `beam` (a travelling or breathing outline) and `glow` (a halo) work on any item that lists them.
- **Cascades**: `shared:` (style for every descendant), `preset:` on a stack (defaults for each child), `defaultType:` (children without a `type`), `matchingGroup:` (one text size across a region). Details: `cascading-options.md` in the project files and [size-groups.md](size-groups.md).

### Borders

```yaml
border: {enabled: true, edges: [top, bottom], weight: 1, color: $rule, radius: 8}
```

`edges` takes the sides to draw. With all edges, `radius` rounds the corners and `fill` fills the inside.

### Beams (`beam:`)

Values: `size` is `sm | md | line | pulse-inner | pulse-outside`; `variant` is `colorful | mono | ocean | sunset`; `theme` is `dark | light | auto`; `color-space` is `hsv | oklch`; `path` is `circle | diamond | triangle | arc | wave | heart` or SVG path data. `active` and `sweep` take a key or expression. Worked example: `docs/design-references/presets/border-beam.levity` and `.png`; shapes in `path-shapes.levity` (project folder `levitydash/beam/`).

### Glow (`glow:`)

`glow: true` or `{strength, reach, passes, bloom}` on plots, needles, gauge arcs, bars and the moon. Notes: `docs/tasks/beam-glow.md`, `emissive-color-and-glow.md`; examples `glow-passes-4.levity`, `glow-passes-8.levity`, `emissive.levity`.

## 3. Layout

- **Free**: `group` plus `geometry`.
- **Stack**: `type: stack`, `direction: row | column`, `spacing`, `dividers`, `item-size`, `overflow: visible | clip | hidden | scroll | auto`. CSS flex through `flex:` on the stack (`justify`, `align-items`, `wrap`) and on each item (`grow`, `shrink`, `basis`, `min`, `max`, `cross`, `align-self`, `order`, `margin`).
- **Grid**: `type: grid` with `columns`, `rows` (`fr`, `px`, `%`, `auto`, `minmax()`, `repeat()`, `auto-fit`), `areas` (a picture, one string per row), `gap`, `auto-flow`, `dense`, `justify-*`, `align-*`. Items choose a place with `grid: {column, row, column-span, row-span}` or `grid: {area: name}`.
- **Align to a sibling**: `align-to: {to, x, y, self-x, self-y, offset}`.
- **Time axis**: `time-axis: {graph: name, at: 3h}` centres an item on a time of a graph.
- **Split**: draggable divider, `orientation`, `ratio`.
- **Switch**: shows the first child whose condition holds; `hold`, `fade`, `cycle`.

Full tables with the CSS equivalent of every option: [layout.md](layout.md). Which CSS answer applies to which design problem: `css-mapping.md` in the project files. Examples: `grid-areas.levity`, `grid-bento.levity`, `layout-margins.levity`, `align-to.levity`, `overflow.levity`, `css-layout.levity`.

## 4. Text, fonts and numbers

- `font` (a family or a theme token such as `$mono`), `weight` (`Thin ExtraLight Light Regular Medium DemiBold Bold ExtraBold Black`, or a number), `color`, `alignment` (fuzzy words: `left`, `center`, `top right`...), `text-scale-type` (`fill | auto | font | string`), `condense`, `icon`, `filters`.
- `text:` may be a list, longest first; the longest that fits is used (`condense` sets how far a text may shrink before a shorter one is chosen).
- Numbers: `precision`, `unit-string`, `unitPosition`, `unitSize`, `shorten`, `format`, `format-hint` (size against the widest value so 7, 13, 101 match), `number-align: end | decimal`, `tabular`, `convertTo` (a unit).
- Positions (`DisplayPosition`): `auto inline newline above below hidden baseline inside outside floating floatunder floatabove center left right top bottom`.
- **Size groups**: `matchingGroup: name` (or `{group, matchAll: true}`, or `name@panel`) makes labels share one size per tier. See [size-groups.md](size-groups.md) and `design-standards.md` in the project files for the type-scale rules (hero, value, label, header; ratio 1.25 to 1.33; at most five sizes).

## 5. Data: keys, expressions, bindings, variables

- `key: environment.temperature.temperature` binds an item to a reading. `connection:` adds `source`, `where`, `period`, `using`.
- Any `key:` may be an **expression**: `max(environment.temperature.temperature, today)`, `a - b`, windows and offsets. See [expressions.md](expressions.md).
- **Bindings** make a setting follow a value: a colour `{scale: $temperature, of: key}`, a number `{of, from: [lo, hi], to: [a, b], clamp, fallback}`. See [bindings.md](bindings.md).
- **Variables**: `vars:` at the root, used as `$name`. See [variables.md](variables.md).
- **Themes**: colour tokens (`$background $surface $text $muted $faint $rule $accent $good $warn $bad $info $series-1..6`), font tokens (`$display $mono $body`), scales (`$load $temperature`). `theme: {extends: name, colors: {...}}`. See [themes.md](themes.md).
- **Presets**: `preset: name` plus `props:`; 30 ship with the app (`src/LevityDash/resources/presets`). See [presets.md](presets.md).

## 6. Gauges (`realtime.gauge`)

A dial is `display:` with `range`, `arc`, `needle`, ticks (`major`, `minor`, `micro`), `value-label`, `unit-label`, `caption`, `sub-label`, `fill`, `zones`, `markers`, `anchor`, `inset`, `glow`.

```yaml
- type: realtime.gauge
  key: environment.temperature.temperature
  title: false
  display:
    range: {min: 60, max: 110}
    arc: {weight: 5%, start-angle: -120, end-angle: 120}
    fill: {weight: 5%, color: '#ff8a3d'}
    needle: {type: tapered, hub: 0.1}
    major: {interval: 10, labels: true}
    value-label: {position: below}
```

- Needle `type`: `needle circle triangle diamond marker tapered arrow line dot notch`.
- Tick `labels`: `text` (words for numbers, or `compass`, `compass-16`), `curve: none | warp | glyphs`, `rotate`, `sign`, `every`.
- `zones`: list of `{from, to, color, mark}`; `markers`: list of `{value, type, color, size, side}`; `fill`: `{from, to, weight, color}`. `from`/`to`/`value` take keys or expressions.
- Examples: `gauge-showcase.levity`/`.png`, `meter-showcase.levity`, `presets/needle-designs`, `fill-dial`, `fill-ranges`, `high-low-markers`, `day-range-fill`, `corner-gauges`, `partial-dials`, `curved-labels`, `analog-dial`, `comfort-band`. Notes: `docs/tasks/gauge-display.md`, `gauge-presets.md`, `gauge-text-treatments.md`.

## 7. Bars (`realtime.bar`)

`display:` takes the same range, zones, fill, markers, ticks and labels as a dial, plus `orientation: horizontal | vertical`, `style: bar | battery | thermometer`, `track`, `pointer`. Pointer `type` values are the needle types above. A fill can take `color: zone` to use the colour of the zone it ends in. Detail: [bar.md](bar.md). Examples: `docs/design-references/bars/*.levity` (battery, day-range, progress, segmented, thermometer, showcase).

## 8. Graphs (`graph`, `mini-graph`)

A graph holds `figures`; a figure holds plots; each plot is bound to a `key`.

```yaml
- type: graph
  name: temperature
  timeframe: {days: 1, hours: 12}
  annotations:
    dayLabels: {enabled: false}
    hourLabels: {alignment: BottomCenter}
  figures:
  - figure: temperature
    margins: {bottom: 20%, top: 15%}
    environment.temperature.temperature:      # a data key is the item
      plot: {type: plot, gradient: TemperatureGradient, weight: 1.2, fill: {opacity: 0.35, base: 45}}
      resolution: 2
```

A figure's items are the data keys written as mapping keys. Worked examples: `docs/design-references/line-fill.levity`, `bar-plots.levity`, `area-plot.levity`, `band-plot.levity`, `strip-plot.levity`, `hourly-row.levity`.

- Plot `type`: `plot` (a line), `bar`, `strip` (a row of marks, one per sample), `area`, `band` (`to:` the second key), `violin` (`bucket`, `bandwidth`).
- Line extras: `thickness: {key, weight: [thin, thick], range}`, `pins:` (symbols at times: `key`, `steps`, `map`, `size`, `only: peaks | troughs | extremes`, `glyph`, `rotate`), `fill`, `dashPattern`, `cap`, `gradient`, `scale`.
- `y-axis`: `side, ticks, format, size, color, grid, inset`. Annotations: day lines, hour labels, day labels, current-time `indicator`. `interpolate`, `smooth`, `smoothingStrength`, `resolution` control the curve.
- Examples: `graph-styles.levity`, `forecast.levity`, `line-pins.levity`, `line-thickness.levity`, `pins-at-peaks.levity`, `y-axis.levity`; the graph presets `graph-*` in resources.

## 9. Clock, moon, polar

- `clock`: cells (`ClockComponent`) with `format` (strftime, e.g. `%-I:%M`) and `offset` (`3h`, `-90min`). Presets: `clock`, `presets/polar-clock`.
- `moon`: `glow`, `glowStrength`, `interval`, `rotate` (tilt as seen at your latitude), `alignment`.
- `polar`: `plot: rose | trail | clock | carousel`, `direction`, `speed`, `key`, `window`, `sectors`, `rings`, `compass`, `span`, `top`, `view`, `gradient`, `accent`, `smooth`, `stamps`, `legend`, `marks`. Examples: `presets/polar-*.levity` (rose, trail, clock, spread, carousel), `polar-dashboard.levity`.

## 10. Looking at the result

- Render a dashboard headless: `python src/LevityDash/devtools/render_dashboard.py OUT.png --levity FILE.levity --seed DIR --scenario hot-clear-day --size 2880x1800 --theme dusk`. Scenarios (fixed data) are in `docs/design-references/scenarios`. Render one item with `render_widget.py`.
- Studio (the in-app editor) edits all of this visually: [studio.md](studio.md).
- Whole example boards: `docs/design-references/dashboards/*.levity` (glance, storm, station, sky, week, wind, rain, house, homelab, garden, gallery, desk, kiosk, magazine, pocket, power, amounts, floors, outlook, forecast, units, split, bindings, graph-styles). Their renders are in the shared project folder under `levitydash/examples-2`, `-3`, `-4` and `levitydash/bento`.
- The data keys available depend on the plugins; see `docs/config/plugins` and `lambda-keys.tsv` in the project files for a real list.

## Key tables

Generated. Keys are exactly as written in a `.levity` file. A blank default means none; a description is the docstring in the code, and a blank one means the key is undocumented in code (open a gap).

### Items, borders, beams, glow

<!-- GENERATED:item -->
#### Every item (`type: group`)
Tag: `group`  ·  class `Panel`

| Key | Default | What it does |
|---|---|---|
| `geometry` | `Geometry(width=1, height=1, x=0, y=0)` |  |
| `align-to` | `None` | Put a point of this item on a point of a named sibling: `align-to: temp`, or `{to, x, y, self-x, self-y, offset}`. Overrides `geometry`'s position on the axes it names; the size is still the geometry's. See `lib/layout/anchor.py`. |
| `time-axis` | `None` | Centre this item on a time of a named graph: `time-axis: {graph: temps, at: 3h}`. `at` is the distance from now (`3h`, `-90min`, `0h`). The item keeps its size and follows the graph's x axis as the graph scrolls or resizes, so a column of readings stays under the graph's line at that time. Only x is set. |
| `margins` | `Margins.default()` |  |
| `padding` | `Padding.default()` | The padding around the panel. |
| `border` | `Stateful` |  |
| `opacity` | `1.0` | How opaque the item and everything in it is, 0 to 1. A mapping `{of, from, to}` makes it follow a value (see `ui/bound_number.py`). |
| `when` | `None` | Show this item only while the condition holds. A key, an expression, or a bool; a missing value counts as false. A `switch` picks among its children by this. |
| `beam` | `Stateful` | A travelling or breathing glow around the panel. Off unless the file has a `beam:` section that turns it on. |
| `name` | `None` |  |
| `items` | `DefaultGroup(None, [])` |  |
| `movable` | `True` |  |
| `resizable` | `True` |  |
| `locked` | `False` |  |
| `frozen` | `False` |  |

#### `border:`
Class `Border`

| Key | Default | What it does |
|---|---|---|
| `edges` | `LocationFlag.Edges` | The edges of the parent that the border is on. Returns ------- `PositionLiteral` \| `LevityDash.lib.ui.Geometry.LocationFlag` Decoding -------- `str` : `left`, `right`, `top`, `bottom` or a combination of them along with `all` and `edges` int : The int value of the LocationFlag associated with the edge Encoding -------- str : Comma separated list of the edges or `all` if all edges are selected Example Config -------------- ```yaml edges: top, left ... edges: all ... edges: top-left # same as 'top, left' but relies on fuzzy matching ``` |
| `radius` | `'0'` | How round the corners are when the border is on all edges. A number or `12px` is pixels; `8%` is a share of the shorter side, so `50%` makes a pill or a circle. It is held as written and read against the parent's size each time the path is built. Example Config -------------- radius: 12px radius: 50% |
| `offset` | `Dimension(0, absolute=True)` | The offset of the border from the parent. Returns ----- `LevityDash.lib.ui.Geometry.Dimension` \| `unitcorn.Length` Decoding -------- `str` : A string representation of a Dimension or Length > Example: '10px', '10%', '1mm', '0.1in' `int` \| `float`: The offset in pixels Encoding -------- str : A string representation of the offset Example Config -------------- offset: 10px offset: 10% offset: 1mm |
| `size` | `Size.Height(1, absolute=False)` | The size of the border. Value ----- Size.Height \| Size.Width Decoding -------- str : A string representation of a absolute pixel value or a relative percentage. Relative values are relative to the parent's height or width depending on the value of the 'edges' property. Examples: '10px', '10%' int : The size in pixels Encoding -------- str : A string representation of the size |
| `weight` | `1.0` |  |
| `color` | `DefaultGroup(Color('#ffffff'), colo...` |  |
| `fill` | `None` | A colour that fills the inside of a border on all edges, following its `radius`. With `weight: 0` there is no line, only the fill. Colours take the usual forms, `$tokens` and `alpha` included. Example Config -------------- ```yaml border: {enabled: true, radius: 16px, fill: '#ffffff22', weight: 0} ``` |
| `enabled` | `False` |  |
| `opacity` | `1.0` |  |

#### `beam:`
Class `PanelBeam`

| Key | Default | What it does |
|---|---|---|
| `size` | `Size.MEDIUM` | The shape: `sm` a compact ring, `md` a full border, `line` bottom only, `pulse-inner` a breathing inner edge, `pulse-outside` a halo. |
| `variant` | `ColorVariant.COLORFUL` | The palette: `colorful` (rainbow), `mono` (grey), `ocean` (blue and purple), `sunset` (orange and red). |
| `theme` | `Theme.AUTO` | `dark` for a dark card, `light` for a light one. The strengths and saturation differ. `auto` follows the dashboard theme's mode. |
| `color-space` | `ColorSpace.HSV` | `hsv` keeps the upstream colours. `oklch` takes them from LevityDash's palette ring. |
| `duration` | `None` | Seconds per cycle. Left out, the size decides: 1.96 for sm and md, 3.1 for line, 2.3 for the pulses. |
| `strength` | `1.0` | How bright the beam is, 0 to 1. |
| `radius` | `None` | Corner radius in px. Left out, the size decides (32 for sm, 16 for the rest). |
| `path` | `None` | The outline the beam follows: SVG path data (M, L, H, V, C, S, Q, T, A, Z), or one of `circle`, `diamond`, `triangle`, `arc`, `wave`, `heart`. It is scaled to fill the panel. Left out, the beam follows the panel's rounded rectangle. |
| `fill` | `None` | A card colour painted under the content and inside the beam. `pulse-outside` needs one, as its halo lies behind the card. |
| `active` | `False` | `true` runs the beam, `false` turns it off. A key or expression runs it while the value is true, for example `environment.wind.speed.speed > 25`. |
| `sweep` | `None` | A key or expression. The beam runs once each time a new value arrives. |
| `phase` | `None` | Hold the beam at this time in seconds, with no animation. For renders and previews. |

#### `glow:` (anything that glows)
Class `GlowMixin`

| Key | Default | What it does |
|---|---|---|
| `glow` | `None` | A halo of fainter, wider strokes around the item: ``true``, or ``{strength, reach, passes, bloom}``. Left out, or ``false``, there is no glow. ``strength: 0`` also draws nothing, which turns off a glow the item would otherwise inherit. |

#### Colour
Class `ColorMixin`

| Key | Default | What it does |
|---|---|---|
| `color` | `Color.default` | Color to use for the item's fill brush Valid values ------------ - Hexadecimal color codes (with or without the leading '#') - Comma-separated RGB[A] values - Web Color names (case-insensitive) Example Config -------------- - A mapping `{scale: ..., of: ...}`: the colour of a scale at a value, following it (see `lib/ui/colors/bound.py`) ```yaml color: '#ff0000' color: white color: 255, 0, 0 color: {scale: $temperature, of: environment.temperature.feelsLike} ``` Returns ------- Color |

#### Colour with a gradient
Class `ColorGradientMixin`

| Key | Default | What it does |
|---|---|---|
| `gradient` | `None` |  |

<!-- /GENERATED:item -->

### Containers

<!-- GENERATED:containers -->
#### The dashboard root
Tag: `dashboard`  ·  class `CentralPanel`

| Key | Default | What it does |
|---|---|---|
| `items` |  |  |
| `theme` | `None` | The colour theme: a name, or ``{extends: name, colors: {...}}``. Tokens such as ``$accent`` read from it. |
| `background` | `None` | The ground of the dashboard: a colour, a theme token (`$background`, or a scale such as `$sky` for a gradient), or a gradient written in place. `{gradient: $sky, angle: 160}` sets the direction. `lib/ui/colors/backdrop.py` |
| `vars` | `None` | Named values for the file: `vars: {hot: 90°F}`, used as `$hot`. Applied when the file loads (`lib/variables.py`); a save writes the `$name` uses back where the value is unchanged. |

#### `type: stack`
Tag: `stack`  ·  class `Stack`

| Key | Default | What it does |
|---|---|---|
| `defaultType` | `Panel` |  |
| `flex` | `None` | Turns this stack into a CSS flex container: `justify`, `align-items`, `wrap`. It may also carry the item options (`grow`, `shrink`, ...) for when this stack is an item of another. A stack with no `flex:` on itself or on any item keeps the original sizing, so existing dashboards do not move. See docs/config/dashboard/layout.md. |
| `overflow` | `'visible'` | What happens to content larger than the stack: `visible` (default), `clip`, `hidden`, `scroll` or `auto`. `scroll` and `auto` let the wheel move the content along the stack's main axis; `auto` only when it overflows. A scrolling stack gives items that have a size `shrink: 0`, so they keep it and overflow instead of squeezing. See docs/config/dashboard/layout.md. |
| `dividers` | `Stateful` |  |
| `items` |  |  |
| `preset` | `None` | Values to be applied to each item of the stack. Can be a string or a dict. If a string, it must be a key in the `presets` dict. |
| `item-size` | `None` | The size for each item in the list. |
| `item-size-min` | `None` | The minimum size for each item in the list. |
| `item-size-max` | `None` | The maximum size for each item in the list. |
| `spacing` | `Size.Height(5, absolute=True)` | The spacing between items in the list. |
| `direction` | `Direction.Vertical` | The orientation of the stack. |

#### On an item inside a stack
Class `StackedItem`

| Key | Default | What it does |
|---|---|---|
| `size` | `None` |  |
| `flex` | `None` | CSS flex item options: `grow`, `shrink`, `basis`, `min`, `max`, `cross`, `align-self`, `order`, `margin`. Any of them turns on the flex engine for the stack that holds this item. |
| `grid` | `None` | Where this item sits in a `grid` stack: `column`, `row`, `column-span`, `row-span`, `justify-self`, `align-self`. Lines count from 1. |
| `size-ratio` | `None` |  |
| `type` |  |  |

#### `dividers:`
Class `DividerProperties`

| Key | Default | What it does |
|---|---|---|
| `enabled` | `False` |  |
| `size` | `Size.Height(1, relative=True)` |  |
| `weight` | `Size.Width(1, relative=False)` |  |
| `color` | `Color.text` |  |
| `opacity` | `1.0` |  |

#### `type: value-stack`
Tag: `value-stack`  ·  class `ValueStack`

| Key | Default | What it does |
|---|---|---|
| `labelAlignment` |  | The alignment of the label. |
| `valueAlignment` |  | The alignment of the value. |
| `label-size` |  | The size of the label. |

#### `type: grid`
Tag: `grid`  ·  class `GridStack`

| Key | Default | What it does |
|---|---|---|
| `grid` | `None` | `columns`, `rows` (track lists such as `[1fr, 200px]` or `repeat(auto-fit, minmax(150px, 1fr))`), `auto-columns`, `auto-rows`, `auto-flow` (row \| column), `dense`, `gap`, `justify-content`, `align-content`, `justify-items`, `align-items`. |

#### `type: split`
Tag: `split`  ·  class `SplitPanel`

| Key | Default | What it does |
|---|---|---|
| `items` | `DefaultGroup(None, [])` |  |
| `orientation` | `'horizontal'` | Which way the divider runs: `horizontal` (first item above) or `vertical` (first item to the left). |
| `ratio` | `0.5` | The first item's share of the split, `0` to `1`. Dragging the divider changes it. |

#### `type: switch`
Tag: `switch`  ·  class `Switch`

| Key | Default | What it does |
|---|---|---|
| `items` | `DefaultGroup(None, [])` |  |
| `hold` | `30.0` | Seconds a change must last before the switch flips, so a value hovering at a threshold does not flap. The first pick is instant. |
| `fade` | `0.3` | Seconds the old child fades out and the new one fades in. `0` swaps at once. |
| `cycle` | `0.0` | Seconds each matching child stays up before the next takes over. `0` (the default) never rotates. |

#### `type: band`
Tag: `band`  ·  class `Band`

| Key | Default | What it does |
|---|---|---|
| `items` | `DefaultGroup(None, [])` |  |
| `mode` | `'step'` | `step` moves a page at a time and rests between moves (`dwell`, `transition`, `step`); `continuous` scrolls smoothly like a marquee (`speed`, `fps`). |
| `visible` | `3.0` | How many items are in view at once. A fraction (`3.5`) lets the next item peek in at the edge. |
| `direction` | `'left'` | Which way the content moves: `left` (new items come in from the right; the default), `right`, `up` or `down`. |
| `gap` | `0.0` | Space between items as a share of the band's length: `2%` or `0.02`. |
| `dwell` | `8.0` | Step mode: seconds each stop lasts. |
| `transition` | `0.6` | Step mode: seconds one move takes. `0` jumps. |
| `step` | `1.0` | Step mode: items per move. `page` moves a whole page (`visible` items). |
| `speed` | `0.25` | Continuous mode: items per second (`0.25` is four seconds an item). `0` stands still. |
| `fps` | `30.0` | Continuous mode: frames per second. Lower it on a slow machine. |
| `cache` | `True` | Continuous mode: draw each item once and move the picture. Turn it off for an item that changes every frame. |

#### `type: titled-group`
Tag: `titled-group`  ·  class `TitledPanel`

| Key | Default | What it does |
|---|---|---|
| `items` | `DefaultGroup(None, [])` |  |
| `title` | `Stateful` |  |

<!-- /GENERATED:containers -->

### Text and labels

<!-- GENERATED:text -->
#### `type: label` / `type: text`
Tag: `label`  ·  class `Label`

| Key | Default | What it does |
|---|---|---|
| `filters` | `[]` |  |
| `warp` | `None` | Pin the text's middle to a circle and bend it along it: ``warp: true``, or ``{center, radius, angle, mode, flip}`` (see `WarpSpec`). |
| `alignment` | `Alignment.default()` |  |
| `text` | `...` |  |
| `condense` | `0.85` | With `text:` a list (longest first), how much a text may shrink before a shorter one is used. `text: [Temperature, Temp, T]` shows `Temperature` while fitting its width asks for at least 0.85 of the size the box's height allows, then `Temp`, then `T`. Use a higher number to switch sooner and 0 to always show the first. It looks at the box and the font only, so a size group's shared size does not change which text shows. |
| `icon` | `None` |  |
| `font` | `defaultFont.family()` |  |
| `weight` | `FontWeight.Normal` |  |
| `text-scale-type` | `ScaleType.auto` |  |
| `modifiers` | `{}` |  |
| `format-hint` | `None` |  |
| `number-align` | `None` | Line numbers up on the number and not on the whole string: `end` right-aligns the digits, `decimal` puts the decimal point on one line (a value with no point acts as if it ended in one). The unit and any other text after the cut hang to its right. Members of one size group (and one tier) share the line. The text is not changed: nothing is padded. |
| `decimal-scale` | `None` | Draw the fractional digits (the `.7` of `67.7`, with their point) smaller than the integer part. A share of the text size (`0.6`, or `60%`) or an absolute size for the small digits (`12px`, `9pt`, `3mm`, `0.2cm`, `0.1in`: the em size they end up at on screen, so they keep it while the main number grows). The integer digits keep their size, so with `tabular` or `number-align` they still line up; a unit or degree sign after the fraction keeps the full size. Off (`null`, `1`) by default. Where the fraction sits is `decimal-align`. |
| `decimal-align` | `baseline` | Where the small decimals sit: `baseline` (on the line, as in a price; `bottom` is the same), `top` (their tops level with the integer digits' tops, as a superscript) or `center`. |
| `tabular` | `False` | `font-variant-numeric: tabular-nums`: digits of one width. On whenever `number-align` is set. |
| `italic` | `False` | The font's italic, or a slanted regular where the family has none. |
| `font-axes` | `None` | Variable-font axes that follow the value the label shows: `{range: [20°F, 95°F], wght: [500, 800], ROND: [0, 100]}` puts a hot number heavy and round and a cold one lean and sharp. `range` (units are converted to the value's) is the span mapped; each axis (`wght`, `ROND`, `opsz`, `wdth`, `slnt`, or `weight`, `round`, `optical-size`...) is `[at the low end, at the high end]`, a number to hold it, or `{from, to, range}` with a range of its own. `corner` (em, e.g. `[0, 0.05]`) is not a font axis but rounds every convex corner of the outlines with a round-join pen (the weight is lowered to match), so it works in any font and shows where a font's `ROND` barely moves (an 8 not at all); about 0.05 is the most a bold figure takes. `clamp: false` extrapolates; `fallback: {wght: 500}` is used while there is no number. Turns tabular figures on. Needs a variable font: the bundled `Allo Variable` (OFL) has `wght` 100-900, `ROND` 0-100 and `opsz` 9-32. Cascades through `shared:` like any label property. |
| `tracking` | `0.0` | Space added between letters, in em, as CSS `letter-spacing`: `tracking: 0.12` opens all caps up, a negative number tightens a big number. `12%` is the same as `0.12`. |
| `outline` | `None` | Draw the letters as a line round their shape: `outline: true`, a weight in pixels (`outline: 2`), or `{weight, color, fill}`. The inside is empty unless `fill: true`; the line takes the text's colour unless `color` names another. |
| `text-height` | `None` |  |
| `matchingGroup` | `None` | Group to match the height of the label to. Returns ------- |

#### A title label
Class `TitleLabel`

| Key | Default | What it does |
|---|---|---|
| `text` | `...` |  |
| `icon` | `None` |  |

#### A clock cell
Class `ClockComponent`

| Key | Default | What it does |
|---|---|---|
| `format` | `'%-I:%M'` |  |
| `offset` | `0.0` | Show the time this far from now: `3h`, `-90min`, or hours as a number. Used by a column that sits under a later time. |

<!-- /GENERATED:text -->

### Realtime readings

<!-- GENERATED:realtime -->
#### `type: realtime` (and `.text`, `.gauge`, `.bar`)
Tag: `realtime`  ·  class `Realtime`

| Key | Default | What it does |
|---|---|---|
| `type` |  | `realtime.text`, `realtime.gauge`, `realtime.bar`, so a save loads back as the same display. Plain `realtime` picks the display from the key's data, which is wrong for a text over a time or a duration. |
| `key` | `Stateful` |  |
| `connection` | `Stateful` |  |
| `forecast` | `False` |  |
| `display` | `Stateful` |  |
| `alignment` | `None` |  |
| `title` | `Stateful` |  |

#### `connection:`
Class `Connection`

| Key | Default | What it does |
|---|---|---|
| `key` |  |  |
| `where` | `None` |  |
| `period` | `None` |  |
| `using` | `None` |  |
| `source` | `AnySource` |  |

#### `display:` on a text reading
Class `MeasurementDisplayProperties`

| Key | Default | What it does |
|---|---|---|
| `unit-string` | `Unset` |  |
| `max-length` | `Unset` |  |
| `precision` | `Unset` |  |
| `splitDirection` | `LocationFlag.Horizontal` |  |
| `unitPosition` | `DisplayPosition.Auto` |  |
| `shorten` | `Unset` |  |
| `unitSize` | `__valueUnitRatio` |  |
| `floating-offset` | `_floatingOffset` |  |
| `format` | `None` |  |
| `format-hint` | `None` | `format-hint` as configured. The derived hint is not reported here, so a save does not write it back as if set. |
| `null` | `None` |  |
| `convertTo` | `None` |  |

#### `display:` value and unit labels
Class `DisplayLabel`

| Key | Default | What it does |
|---|---|---|
| `valueLabel` | `Stateful` |  |
| `unitLabel` | `Stateful` |  |
| `splitter` |  |  |

#### `title:` (the title and its splitter)
Class `TitleValueSplitter`

| Key | Default | What it does |
|---|---|---|
| `text` | `Stateful` |  |
| `rotate` | `False` |  |
| `size` | `0.2` |  |
| `height` | `None` |  |
| `position` | `DisplayPosition.Top` |  |
| `visible` | `True` |  |

<!-- /GENERATED:realtime -->

### Dials

<!-- GENERATED:gauge -->
#### `display:` of every dial and bar
Class `Meter`

| Key | Default | What it does |
|---|---|---|
| `value-label` |  |  |
| `unit-label` |  |  |
| `sub-label` | `None` | Small text below the centre value (and its unit): same forms as ``caption``. |
| `caption` | `None` | Small text above the centre value: a string, or ``{text, value, format, size, color}``. |
| `range` |  |  |
| `alignment` |  |  |
| `anchor` | `None` | Pin the pivot (the arc centre) to a corner of the box: ``top-left``, ``top-right``, ``bottom-left`` or ``bottom-right``. ``radius`` then counts from the box's short side, so 100% is the whole short side minus ``inset``. Use it for a quarter-circle dial that fills a card. Without it the dial is centred as before. |
| `inset` | `Size.Height(0.0, relative=True)` | Gap between an `anchor`ed pivot and the box's two edges at that corner. |
| `needle` |  |  |
| `fill` | `None` | A value-driven arc over the track: ``{from, to, weight, color}``. Kept as the plain mapping the user wrote; the scene item is ``self._fillItem``. |
| `zones` | `None` | Coloured bands on the track: a list of ``{from, to, color, mark}`` mappings. Kept as the plain mappings the user wrote; the scene item is ``self._zonesItem``. |
| `markers` | `None` | Extra indicators: a list of ``{value, type, color, ...}`` mappings. Kept as the plain mappings the user wrote, so saving writes them back unchanged. The scene items built from them are ``self._markerItems``. |
| `major` |  |  |
| `minor` |  |  |
| `micro` |  |  |

#### `display:` of `realtime.gauge`
Class `Gauge`

| Key | Default | What it does |
|---|---|---|
| `radius` | `Size.Height(1.0, relative=True)` |  |
| `arc` |  |  |
| `center_offset` |  |  |

#### `range:`
Class `GaugeRange`

| Key | Default | What it does |
|---|---|---|
| `wrap` | `False` | A cyclic scale: a value past the maximum comes round again from the minimum. A clock face (0-12 hours) or a bearing (0-360) turns instead of stopping at the end. |
| `round-to` |  |  |
| `min` |  |  |
| `max` |  |  |

#### `arc:`
Class `GaugeArc`

| Key | Default | What it does |
|---|---|---|
| `color` | `None` | Colour of the track. Defaults to the gauge colour; a dark grey gives the unfilled-track look. |
| `gradient` | `None` |  |
| `weight` | `Size.Width(0.05, relative=True)` | Width of the arc. A bound number is a share of the gauge's width (0.05 is 5 %). |
| `start-angle` | `-120` | Where the arc starts, in degrees from straight up. A mapping `{of, from, to}` follows a value. |
| `end-angle` | `120` | Where the arc ends, in degrees from straight up. A mapping `{of, from, to}` follows a value. |
| `cap` | `Qt.PenCapStyle.FlatCap` |  |
| `extend` | `'auto'` | How far each end of the track runs past its angle: `auto` (reach the outer edge of the end tick when the cap is flat), a number of degrees, a length such as `2px`, or `0` for none. |

#### `needle:`
Class `Needle`

| Key | Default | What it does |
|---|---|---|
| `visible` | `True` | ``false`` hides the needle itself, for a dial drawn with a ``fill`` and markers. |
| `type` | `Type.Needle` |  |
| `width` |  |  |
| `length` |  |  |
| `offset` | `Size.Height(0, relative=True)` |  |
| `color` | `None` | Colour of the needle. Default: the gauge's text colour. |
| `tail` | `None` | Length behind the pivot, as a share of the radius (``tapered``, ``arrow``, ``line``). |
| `tail-dot` | `None` | Diameter of the dot at the end of the tail (``arrow``, ``line``). |
| `head` | `None` | Length of the arrowhead (``arrow``). Default 12% of the radius. |
| `point` | `None` | Where the ``arrow`` head sits: ``out`` (at the rim, default) or ``in`` (at the inner end). |
| `hub` | `None` | Diameter of a disc at the pivot (``needle``, ``tapered``, ``line``), as a share of the radius. |
| `hub-color` | `None` | Colour of the hub. Default: the needle colour. |
| `hub-hole` | `None` | Share of the hub's diameter cut out of its middle: a ring instead of a disc. |
| `halo` | `None` | Width of a ring around a ``dot``, in the ``halo-color``. |
| `halo-color` | `None` |  |
| `animate` | `0` | Milliseconds the hand takes to move to a new value; 0 (default) jumps. With a wrapping range (``range: {wrap: true}``) it takes the shorter way round. |

#### `major:` `minor:` `micro:` (ticks)
Class `Graduations`

| Key | Default | What it does |
|---|---|---|
| `enabled` | `True` |  |
| `labels` |  | The labels for the graduations. Major ticks are labeled by default. |
| `count` | `None` | The number of graduations to show on the gauge (including the first and last graduations). |
| `min-count` | `None` | The minimum number of graduations to show on the gauge (including the first and last graduations). |
| `max-count` | `None` | The maximum number of graduations to show on the gauge (including the first and last graduations). |
| `position` | `DisplayPosition.Inside` | The position of ticks relative (inside or outside) to the arc path. Example Config -------------- ```yaml position: 'inside' \| outside \| "out" ``` |
| `length` |  | The length of the ticks. Values can be specified as a percentage, a physical length ('1in', '0.3mm`, etc.), or a number. Numerical values are treated as pixel lengths except for float values between 0.0 and 1.0, which are handled as percentages. For major ticks, percentages are relative to the gauge's radius. With minor and micro ticks it is relative to the pixel length of the major or minor ticks, respectively. Example Config -------------- ```yaml gauge: major-ticks: length: 0.1 # 10% of the gauge's radius minor-ticks: length: 70% # 70% the length of the major ticks micro-ticks: length: 2mm # Two millimeters ``` |
| `width` |  | The width of the ticks. Values can be specified as a percentage, a physical length (`0.3cm`, `2mm`, etc.), or a number. Numerical values are treated as pixel lengths except for float values between 0.0 and 1.0, which are handled as percentages. |
| `required-interval-factors` |  | The interval must be a multiple of all the specified factors. Default is `{1}` to allow for any integer interval. Note: This is currently experimental |
| `excluded-interval-factors` |  | The interval must not be a multiple of any of the specified factors. Default is `{}` to allow for any interval. |
| `included-interval-factors` |  | The interval must be a multiple of at least one of the specified factors. Default is `{}` to allow for any interval. |
| `interval` |  | The interval between graduations. If an interval is provided by the configuration and has the correct factors, it will be used. Otherwise, the nearest allowed interval will be used. |
| `min-interval` |  | The minimum interval between graduations. |
| `min-spacing` | `1.0` | The minimum arc length spacing between graduations. All floats and percentages are interpreted as a fraction of the tick-width. |
| `max-spacing` | `None` | The maximum arc length/degree spacing between graduations. All floats and percentages are interpreted as a fraction of the tick-width. |

#### Tick labels (`labels:` on a tick set)
Class `GaugeTickTextGroup`

| Key | Default | What it does |
|---|---|---|
| `format` | `None` |  |
| `text` | `None` | Words in place of numbers: ``{0: E, 100: F}``, ``compass`` or ``compass-16``. |
| `sign` | `False` | Put a plus in front of positive labels (``+5``). |
| `position` |  |  |
| `enabled` |  |  |
| `rotate` | `True` |  |
| `curve` | `CurveMode.none` |  |
| `position-leading` |  | Where the first label sits against the arc's start. The labels in between keep `position`. outside radially out from the arc, clear of the arc and its tick inside radially in, clear of the tick's inner end center on the arc's centre line, over the arc, with no clearing float-under straight down on screen from the end of the tick, clear of the arc and tick `above` and `below` are read as `outside` and `inside`. `left` and `right` are not accepted. |
| `position-trailing` |  | Where the last label sits against the arc's end. The labels in between keep `position`. The four values mean the same as for `position-leading`. |
| `rotate-leading` | `False` |  |
| `rotate-trailing` | `False` |  |
| `align-trailing` |  |  |
| `align-leading` |  |  |
| `every` | `1` |  |

#### `value-label:` on a dial
Class `GaugeValueLabel`

| Key | Default | What it does |
|---|---|---|
| `alignment` |  |  |
| `format` | `None` |  |
| `format-hint` | `None` | `format-hint` as configured. The range's own hint is not reported here, so a save does not write it back as if set. |
| `size` | `None` | Largest height of the value text, as a share of the dial's diameter. Without it the value grows until it touches the dial, so a short value such as 'N' or '0' comes out far larger than '7.4'. ```yaml value-label: {size: 26%} ``` |
| `value-padding` | `Size.Height(0.05, relative=True)` |  |
| `position` | `ValueDisplayPosition.Auto` |  |

#### `unit-label:` on a dial
Class `GaugeUnit`

| Key | Default | What it does |
|---|---|---|
| `text` | `...` |  |
| `height` | `Length.Millimeter(5)` |  |
| `value-padding` | `Size.Height(0.05, relative=True)` |  |
| `position` | `UnitDisplayPosition.Auto` |  |

<!-- /GENERATED:gauge -->

### Bars

<!-- GENERATED:bar -->
#### `display:` of `realtime.bar` (also takes the Meter keys above)
Class `Bar`

| Key | Default | What it does |
|---|---|---|
| `orientation` | `'horizontal'` | ``horizontal`` (the minimum at the left) or ``vertical`` (the minimum at the bottom). |
| `style` | `'bar'` | ``bar`` (a plain track), ``battery`` (an outlined cell with a terminal) or ``thermometer`` (a tube with a bulb at the minimum; stands up whatever ``orientation`` says). |
| `track` | `None` | The track under the data: ``{color, weight, cap, segments, gap}``. ``weight`` is a size (default 28% of the cross extent); ``cap`` is ``round`` (default), ``square`` or ``flat``; ``segments`` and ``gap`` cut it into cells (a segmented ``fill`` cuts it the same way unless this says ``segments: false``). |
| `pointer` | `None` | A marker shape riding the value, as a needle does on a dial: ``{type: triangle\|line\|dot\|notch, color, size, side}``. Left out, there is none. |
| `font` | `None` | The text's font family, or a theme font token such as ``$mono``. |
| `value-label` | `None` | The value as text: ``{visible, position, align, size, color, format}``. ``position`` is ``end`` (default; the top of a standing bar), ``start``, ``above``, ``below``, ``left``, ``right`` or ``inside`` (on the track; in a thermometer, in the bulb). ``size`` is the text height as a share of the cross extent; ``format`` is the unit's format mapping, as a gauge's value label takes. |
| `unit-label` | `None` | The unit's word (``mph``) beside the value, smaller and fainter: ``{visible, text, size, color}``. Off unless ``visible: true``; the value label's own ``format`` decides whether the *symbol* (% or °) shows. |
| `caption` | `None` | Small text above the bar, at its start: a string, or ``{text, value, format, size, color}``. |
| `sub-label` | `None` | Small text below the bar, at its start: same forms as ``caption``. |
| `major` | `None` | Major ticks: ``{interval, count, length, width, side, color, labels, format, size}``. ``interval`` is in the data's unit (default: a round step that gives about five); ``count`` splits the range instead. ``side`` is ``before`` (above a lying bar, left of a standing one), ``after`` or ``both``. ``labels: true`` numbers them. There are no ticks unless this is set. |
| `minor` | `None` | Minor ticks, between the major ones: ``{count, length, width, side, color}`` (``count`` is the number of steps each major step is cut into; default 5). |
| `zones` | `None` | Coloured bands on the track: a list of ``{from, to, color, weight, opacity}``. A missing end is the range's end. ``opacity: 0`` draws nothing but still colours a ``fill: {color: zone}``. |
| `fill` | `None` | The part of the track up to a value: ``{from, to, color, gradient, weight, cap, segments, gap, opacity, glow}``. ``from`` and ``to`` are numbers, keys or expressions (default: the range minimum, and the bar's own value). ``color: zone`` takes the colour of the zone the end sits in. |
| `markers` | `None` | Extra indicators, each at its own value: ``{value, type, color, size, side}`` with ``type`` one of ``line`` (across the track), ``triangle``, ``dot`` or ``notch``. ``value`` is a number, a key or an expression such as ``at(key, -3h)``; with no value yet the marker is hidden. |

<!-- /GENERATED:bar -->

### Graphs

<!-- GENERATED:graph -->
#### `type: graph`
Tag: `graph`  ·  class `GraphPanel`

| Key | Default | What it does |
|---|---|---|
| `annotations` | `Stateful` |  |
| `scrollable` | `True` |  |
| `indicator` | `Stateful` |  |
| `figures` | `[]` |  |
| `timeframe` | `TimeFrameWindow()` |  |

#### `type: mini-graph`
Tag: `mini-graph`  ·  class `MiniGraph`

| Key | Default | What it does |
|---|---|---|
| `annotations` | `__defaults__['annotations']` |  |

#### A figure
Class `Figure`

| Key | Default | What it does |
|---|---|---|
| `opacity` | `1.0` |  |
| `items` |  |  |
| `figure` |  |  |
| `y-axis` | `None` | Round values down one edge of the figure, at the height each stands at on the plot. `{side: left, ticks: 4, format: '{:.0f}°', size: 12, color: '#888', grid: true, inset: 4}`. `side` is `left` or `right`. `ticks` is about how many marks to show (the step is a round one, so 0 to 100 asked for 4 gives 0, 50, 100), or a list of the values to mark. `format` is a format spec (`'{:.0f}°'`, `.1f`); with none the digits follow the step. `size` is pixels, `color` any colour (default the text colour, dimmed), `grid` draws a faint line across at each mark, `inset` is the gap to the edge in pixels. `y-axis: true` takes every default. |
| `max` | `inf` |  |
| `min` | `-inf` |  |
| `margins` |  |  |

#### A graph item
Class `GraphItemData`

| Key | Default | What it does |
|---|---|---|
| `z` |  |  |
| `plot` |  |  |
| `labels` | `Stateful` |  |
| `interpolate` | `True` |  |
| `smooth` | `True` |  |
| `smoothingStrength` | `1.0` |  |
| `smooth-ype` | `'savgol'` |  |
| `interpolation-type` | `'cubic'` |  |
| `key` |  |  |
| `source` | `AnySource` |  |
| `resolution` | `5` | The number of points per pixel to use when drawing the graph. |

#### Every plot
Class `Plot`

| Key | Default | What it does |
|---|---|---|
| `gradient` | `None` |  |
| `weight` | `1.0` |  |
| `color` | `None` |  |
| `opacity` | `1.0` |  |
| `type` |  |  |
| `dashPattern` | `DefaultGroup(Qt.SolidLine, 'solid',...` |  |
| `cap` | `DefaultGroup(Qt.RoundCap, 'round')` |  |

#### `type: line`
Class `LinePlot`

| Key | Default | What it does |
|---|---|---|
| `thickness` | `None` | Line width that follows another key: `{key: environment.wind.speed.speed, weight: [0.2, 1.2]}`. `key` may be an expression (`max(environment.wind.speed.speed, today)`), published as a computed key. `weight` is the thin and thick end in the units `weight` uses; `range: [lo, hi]` pins the values they stand for (default: the lowest and highest in view). Clamped outside it. |
| `pins` | `None` | Marks from another key riding the line, each at its own time and height: condition glyphs, say. `{key: environment.condition.icon, size: 14, offset: -1.2, spacing: 1.6, color: '#ffd400'}`. `key` may be an expression, published as a computed key. `size` is pixels (or `5mm`); `offset` is in sizes, negative above the line; `spacing` is the least gap between marks in sizes. An icon value draws as its glyph. Other values need `steps` (`[[0, wi:day-sunny], [0.05, wi:showers], [0.3, wi:rain]]`: a number takes the last row it reaches) or `map` (`{0: 'wi:day-sunny'}`: exact values); with neither, the value prints as text. `at` (0 bottom to 1 top of the figure) sets every mark at that height instead of on the line, which makes a row of glyphs: a condition timeline. A `strip` plot draws only that row. `only: peaks \| troughs \| extremes` puts pins only where the line turns (a turn must stand out by `prominence`, a share of the line's range, default 0.15), each taking the pin value nearest that time: with the line's own key and no steps, that prints the day's highs and lows; with a condition key, an icon at each. Troughs take the offset's opposite side. `glyph` draws one glyph for every value (`wi:direction-up`) and `rotate` turns it by the value read as degrees clockwise, plus the number of degrees `rotate` gives (`rotate: 180` makes wind direction, which names where the wind comes from, point the way it blows). `rotate: true` adds nothing. |
| `fill` | `None` | The space under the line filled with the line's own colour or gradient: `{opacity: 0.25, base: 50}`. `opacity` is how strong the fill is (default 0.25); `fade: true` fades it out toward the baseline. `base` is the value it reaches, in the unit of the data and held inside the axis range; without it the fill reaches the bottom of the figure. `true` is the defaults and a number is the opacity. A line and a fill of one key is `fill` on the line; an `area` plot is the fill alone. |

#### Filled plots
Class `FilledPlot`

| Key | Default | What it does |
|---|---|---|
| `width` | `0.8` |  |

#### Plots with a base
Class `BasedPlot`

| Key | Default | What it does |
|---|---|---|
| `base` | `0.0` |  |

#### `type: bar`
Class `BarPlot`

| Key | Default | What it does |
|---|---|---|
| `radius` | `0.2` |  |
| `align` | `'center'` |  |

#### `type: band`
Class `BandPlot`

| Key | Default | What it does |
|---|---|---|
| `to` | `None` |  |

#### `type: violin`
Class `ViolinPlot`

| Key | Default | What it does |
|---|---|---|
| `bucket` | `3600.0` |  |
| `bandwidth` | `1.0` |  |

#### `annotations:`
Class `DayAnnotations`

| Key | Default | What it does |
|---|---|---|
| `enabled` | `True` |  |
| `lines` | `Stateful` |  |
| `hourLabels` | `Stateful` |  |
| `dayLabels` | `Stateful` |  |

#### `lines:`
Class `TimeMarkers`

| Key | Default | What it does |
|---|---|---|
| `enabled` | `True` |  |
| `weight` | `1.0` |  |
| `color` | `Color.text` |  |
| `spacing` | `_spacing` |  |

#### `hourLabels:`
Class `HourLabels`

| Key | Default | What it does |
|---|---|---|
| `spacingIntervals` | `markerIntervals` |  |
| `relative-times` | `False` |  |

#### Plot labels
Class `PlotLabels`

| Key | Default | What it does |
|---|---|---|
| `alignment` | `Alignment.default()` |  |

#### `indicator:`
Class `CurrentTimeIndicator`

| Key | Default | What it does |
|---|---|---|
| `enabled` | `True` |  |
| `color` | `Color.role('series-1')` |  |
| `opacity` | `1.0` |  |
| `weight` | `Size.Width(1, absolute=True)` |  |

#### Any annotation labels
Class `AnnotationLabels`

| Key | Default | What it does |
|---|---|---|
| `enabled` | `True` |  |
| `matchingGroup` | `None` | Size group every label here joins, so their text matches the group's other members. |
| `format` | `None` |  |
| `opacity` | `DefaultGroup('100%', 1.0)` |  |
| `position` | `DisplayPosition.Auto` |  |
| `height` | `Centimeter(0.5)` |  |
| `offset` | `Size.Height(5, absolute=True)` |  |
| `alignment` | `None` |  |

<!-- /GENERATED:graph -->

### Moon and polar

<!-- GENERATED:other -->
#### `type: moon`
Tag: `moon`  ·  class `Moon`

| Key | Default | What it does |
|---|---|---|
| `glow` | `True` |  |
| `glowStrength` | `0.2` |  |
| `interval` | `timedelta(minutes=5)` |  |
| `alignment` | `None` |  |
| `rotate` | `True` |  |

#### `type: polar`
Tag: `polar`  ·  class `Polar`

| Key | Default | What it does |
|---|---|---|
| `plot` | `'rose'` |  |
| `key` | `None` |  |
| `direction` | `None` |  |
| `speed` | `None` |  |
| `prefix` | `'aircraft'` |  |
| `slots` | `20` |  |
| `labels` | `6` |  |
| `ceiling` | `40000.0` |  |
| `sweep` | `False` |  |
| `glyphs` | `True` |  |
| `altitudes` | `True` |  |
| `window` | `'today'` |  |
| `sectors` | `16` |  |
| `rings` | `4` |  |
| `max` | `None` |  |
| `min` | `None` |  |
| `gradient` | `None` |  |
| `accent` | `None` |  |
| `compass` | `8` |  |
| `span` | `24` |  |
| `top` | `'noon'` |  |
| `view` | `120.0` |  |
| `smooth` | `True` |  |
| `stamps` | `6` |  |
| `legend` | `True` |  |
| `marks` | `True` |  |

<!-- /GENERATED:other -->


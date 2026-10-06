# Modules

There are several modules already available for use. However, you can also build your own.

## Realtime  <!-- {docsify-ignore} -->

Single line text with support for showing units and titles and mapping glyphs/emojis to values. The display can also be a gauge (`displayType: gauge`).

## Gauge  <!-- {docsify-ignore} -->

A radial gauge display for realtime values with customizable arcs, tick marks, needles, and value-mapped gradient coloring. Markers and fills can follow an [expression](/config/dashboard/expressions.md), such as the high of today.

## Graph  <!-- {docsify-ignore} -->

### Figures  <!-- {docsify-ignore} -->

A figure is a collection of plots. Figures can be resized within the graph and contain multiple plot types. Generally figure is limited to categorically similar values such as temperature, dewpoint, and apparent temperature.

### Plots  <!-- {docsify-ignore} -->

#### Line  <!-- {docsify-ignore} -->

Any scalar value can be plotted as a line. The line can be colored by a scalar value or by a categorical value. Coloring can also be a value mapped gradient.

#### Bar  <!-- {docsify-ignore} -->

One bar for each sample, for amounts such as rain in each hour. A bar plot takes a gradient that follows the value.

#### Violin  <!-- {docsify-ignore} -->

One violin for each stretch of time. It shows how the values in the stretch are spread.

A line can also change its thickness with the value of another key, and carry pins: marks, such as weather symbols, each at its own time. See the [dashboard options](/config/dashboard.md#graph).

## Mini Graph  <!-- {docsify-ignore} -->

A compact graph (`type: mini-graph`) for embedding a small timeseries plot inside other layouts.

## Clock  <!-- {docsify-ignore} -->

A customizable clock that can have whatever formatting you want and values can be placed wherever you want.

## Moon Phase  <!-- {docsify-ignore} -->

Displays the current moon phase. The moon tilts as it looks in the sky at your location.

## Groups & Stacks  <!-- {docsify-ignore} -->

Containers for organizing display modules:

- **group** — free-form container; children use their own geometry
- **titled-group** — a group with a built-in title bar
- **stack** — lays children out automatically in a vertical or horizontal stack, with optional dividers and spacers
- **value-stack** — a stack purpose-built for lists of labeled realtime values
- **switch** — a slot that shows one of several modules, chosen by a condition or in turn. See [Switch](/config/dashboard/switch.md)

## Planned Modules  <!-- {docsify-ignore} -->

- Weather Radar
- Multiline Text
- RSS Feeds
- Calendar
- More plot types

See the [roadmap](/roadmap.md) for the full picture.

## Other Features  <!-- {docsify-ignore} -->

- Drag and drop dashboard design (This can be a little funky at times)
- YAML based dashboard specifications with support for both absolute and relative size/positioning
- Module grouping with shared/preset styling
- Size-matching groups that keep related text consistently sized across panels
- Editable Margins for text modules
- Resizable graph figures
- Custom, value mapped, gradients for figure items
- [Themes](/config/dashboard/themes.md): named colors, fonts, and gradients that restyle a whole board
- [Variables](/config/dashboard/variables.md): name a value once and use it in many places
- [Expressions](/config/dashboard/expressions.md): a value from a calculation on keys, with units such as `> 90°F`
- A module that is shown only while a condition is true (`when:`)
- A dashboard that loads when one item fails. The item shows an error tile.
- Icon packs: Font Awesome (`fa:`), Material Design Icons (`mdi:`), Weather Icons (`wi:`)
- Text filters (lower, upper, title, capitalize, ordinal, add-ordinal)

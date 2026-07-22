# Modules

There are several modules already available for use. However, you can also build your own.

## Realtime  <!-- {docsify-ignore} -->

Single line text with support for showing units and titles and mapping glyphs/emojis to values. The display can also be a gauge (`displayType: gauge`).

## Gauge  <!-- {docsify-ignore} -->

A radial gauge display for realtime values with customizable arcs, tick marks, needles, and value-mapped gradient coloring.

## Graph  <!-- {docsify-ignore} -->

### Figures  <!-- {docsify-ignore} -->

A figure is a collection of plots. Figures can be resized within the graph and contain multiple plot types. Generally figure is limited to categorically similar values such as temperature, dewpoint, and apparent temperature.

### Plots  <!-- {docsify-ignore} -->

#### Line  <!-- {docsify-ignore} -->

Any scalar value can be plotted as a line. The line can be colored by a scalar value or by a categorical value. Coloring can also be a value mapped gradient.

#### Bar  <!-- {docsify-ignore} -->

Not fully implemented

## Mini Graph  <!-- {docsify-ignore} -->

A compact graph (`type: mini-graph`) for embedding a small timeseries plot inside other layouts.

## Clock  <!-- {docsify-ignore} -->

A customizable clock that can have whatever formatting you want and values can be placed wherever you want.

## Moon Phase  <!-- {docsify-ignore} -->

Displays the current moon phase and its rotation.

## Groups & Stacks  <!-- {docsify-ignore} -->

Containers for organizing display modules:

- **group** — free-form container; children use their own geometry
- **titled-group** — a group with a built-in title bar
- **stack** — lays children out automatically in a vertical or horizontal stack, with optional dividers and spacers
- **value-stack** — a stack purpose-built for lists of labeled realtime values

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
- Icon packs: Font Awesome (`fa:`), Material Design Icons (`mdi:`), Weather Icons (`wi:`)
- Text filters (lower, upper, title, capitalize, ordinal, add-ordinal)

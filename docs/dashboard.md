<style>
#h41 {
  font-size: 1.7em;
  font-family: monospace;
}
#h42 {
  font-size: 1.7em;
  font-family: monospace;
}
#h43 {
  font-size: 1.7em;
  font-family: monospace;
}
h4 .mono-header {
  font-size: 1.3em;
  font-family: monospace;
}
h5 .mono-header {
  padding-left: 1em;
  font-size: 1.5em;
  font-family: monospace;
}
description {
  padding-left: 1em;
}
</style>

# Dashboards

All dashboard configurations in the YAML format. You can get a general understanding of how these work by looking at
the [default dashboard](https://github.com/noblecloud/LevityDash/blob/main/src/LevityDash/example-config/saves/dashboards/default.levity).

## Shared options

### type:

The type of module. This is used to determine which module is used to display the data. Subtypes are specified with a dot. For example: `realtime.text`.

The current options are:

- realtime[text]
- group
- graph
- text
- clock
- moon

### key:

```yaml
key: environment.temperature.temperature
```

The key is the key used to access the data. This is the key used to access the data in the source. All sources use the same key, so it will be the same regardless of the source. Keys use a hierarchical format. For example, the key
for the temperature in the 'environment.temperature.temperature'. Note the double 'temperature' in the key since category 'temperature' contains many measurements.

### geometry:

All modules have a geometry option, this defines the location and size. There are four sub-options: x, y, width and height. They can be proved with percentages or absolute pixel values. All relative values are to the immediate parent.

```yaml
geometry:
  height: 40%
  width: 50%
  x: 0%
  y: 20%
```

### margins:

The margins are used to define the space between the module and the edge of the screen. Like Geometry, it can be provided with percentages or absolute pixel values. For simplification, margins can be
provided with a single comma separated value in the order lef, top, right, bottom. However, sub-options can also be provided individually.

```yaml
margins: 0%, 0%, 0%, 0%
```

or...

```yaml
margins:
  top: 0%
  right: 10px
  bottom: 0%
  left: 10px
```

### Other less used options...

Every module has the following options:

- resizeable: boolean
- movable: boolean
- frozen: boolean
- locked: boolean
	*Note: The difference between `frozen` and `locked` is that `frozen` only freezes the contents of the module, while `locked` locks the module and prevents it from being moved or resized.*

## Text Module

```yaml
- type: text
    geometry:
      height: 32px
      width: 100%
      x: 0%
      y: 0%
    margins: 0%, 0%, 0%, 0%
    text: Atmosphere
    alignment: center
```

This module is for displaying static text. It has all the shared options along with `text` and `alignment`. The alignment option is fairly flexable since fuzzy matching is used.

Alignment has horizontal and vertical sub-options, but a single string of can be provided to set both.
For example: `topLeft` or `bottom_center` will both work. However, on save, it will be changed to a proper value.

## Realtime Module

Realtime currently only supports displaying text but other display types will be added in the future. For now, the type must be set to `realtime` or `realtime.text`.

The Realtime module essentially a grouping that contains a title and a display submodule.

```yaml
- type: realtime.numeric
    title: false
    display:
      ...
    geometry:
      ...
```

### Title

The title is just a text module and has the same options along with `visible` and `ratio`. Ratio is simply the size ratio between the display submodule and the title. To hide the title, you can either give the title a `ratio` of `0`,
or set `visible` to `false` or set the entire title option to `false` like in the example above.

Title also has an optional position option, it can either be `Above`/`Top` or `Below`/`Bottom`. If not provided, it will default to `Above`.

```yaml
- type: realtime.numeric
    ...
    title:
      text: Outdoor
      visible: true
      position: Below
    ...
```

### Displays

The display section is used to determine how the data is displayed. The display section is optional, if it is not present, it will use the default.

------------------------------------------

#### .text :id=h41

Like its parent module, the `text` display type is a grouping containing a **value** and a **unit** text submodule. Both sections are optional if you just want to leave it to the defaults.

Since they are both text modules, the display options are similar to the parent module where there is a ratio, position, and visibility options.
To avoid confusion, the position option is `unitPosition` and the ratio is `valueUnitRatio`.

In addition to `Above` and `Below`, the position option can also be `Inline`, `Auto`, `Hidden` or `Floating`. The `auto` option will place the unit inline if there is enough space, otherwise it will place it below, this is also the
default.

Note: The `Floating` option is not fully implemented yet.

```yaml
- type: realtime.numeric
    ...
    display:
      unitPosition: below
      valueUnitRatio: 0.9
      value:
        alignment: center
        margins: 0%, 0%, 0%, 0%
      unit:
        alignment: top
        margins:
          top: 0%
          right: 10px
          bottom: 0%
          left: 0%
```

#### .gauge :id=h42

This display type is nearly complete, but was shelved for the initial release.

#### .mini-graph :id=h43

Not implemented yet

## Graph Module

```yaml
- type: graph
  timeframe:
    days: 2
    hours: 12
    lookback:
      hours: 6
  geometry:
    height: 480px
    width: 620px
    x: 500px
    y: 0px
  figures:
  - ...
  - ...
```

Like the previous Realtime, the Graph Module also a collection of submodules. It only has two of the shared options, `geometry` and `type` along with two additional options, `figures` and `timeframe`.

### Figures

Going with the theme, a figure is a collection of graph items that share a unit of measure and range, although it is not strictly required. For readability, each figure has a `figure` option to provide a hint of the contents of the figure.
It is completely optional, but will be added upon save.

The `margin` option defines spread of the figure across the graph

```yaml
- figure: temperature
    ...
    margins:
      top: 25%
      bottom: 100px
```

### Graph Items

Graph items are what contain all the data, labels, and the visual plot that is rendered on the graph, they are defined by keys within a figure

```yaml
- figure: temperature
  environment.temperature.temperature:
    labeled: true
    plot:
      ...
```

#### <div class='mono-header'>labeled:</div>

Determines if the plot is labeled. Currently this only labels the peaks and troughs but most of the logic is there for labeling for a specific internals.

#### <div class='mono-header'>plot:</div>

Each Graph Item has its own graphical representation many options.

##### <div class='mono-header'>color:</div>

<description>The color of the plot. Currently only supports rgb-hex values</description>

##### <div class='mono-header'>gradient:</div>

<description>Currently only supports named gradients</description>

##### <div class='mono-header'>dashPattern:</div>

<description>Dash pattern</description>

##### <div class='mono-header'>scale:</div>

<description>The size or weight of the plot</description>

##### <div class='mono-header'>type:</div>

<description>The type of plot. Currently only supports line-plots</description>





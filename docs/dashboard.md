# Dashboard

All dashboard configurations in the YAML format. You can get a general understanding of how these work by looking at
the [default dashboard](https://github.com/noblecloud/LevityDash/blob/main/src/LevityDash/example-config/saves/dashboards/default.levity).

The current anatomy of a dashboard file is strictly a list of modules like so:

```yaml
- type: graph
  ...
- type: clock
  ...
- group:
  items:
    - type: text
        ...
    - type: realtime.text
        ...
```

## Shared Parameters

There are a few config parameters that are shared across all modules

### <div class=mono>type:</div>

The type of module. This is used to determine which module is used to display the data. Subtypes are specified with a dot. For example: `realtime.text`.

```yaml
- type: realtime.text
  ...
```

The current options are:

- realtime[text]
- group
- graph
- text
- clock
- moon

### <div class=mono>key:</div>

```yaml
key: environment.temperature.temperature
```

The key is the key used to access the data. This is the key used to access the data in the source. All sources use the same key, so it will be the same regardless of the source. Keys use a hierarchical format. For example, the key
for the temperature in the 'environment.temperature.temperature'. Note the double 'temperature' in the key since category 'temperature' contains many measurements.

### <div class=mono>geometry:</div>

All modules have a geometry option, this defines the location and size. There are four sub-options: x, y, width and height. They can be proved with percentages or absolute pixel values. All relative values are to the immediate parent.

```yaml
geometry:
  height: 40%
  width: 50%
  x: 0%
  y: 20%
```

### <div class=mono>margins:</div>

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

- resizable: boolean
- movable: boolean
- frozen: boolean
- locked: boolean

> [!NOTE]
> The difference between `frozen` and `locked` is that `frozen` only freezes the contents of the module, while `locked` locks the module and prevents it from being moved or resized.

<br/>

# Modules

## Text

```yaml
- type: text
    ...
    text: Atmosphere
    alignment: center
    filters:
      - 2Title
```

This module is for displaying static text. It has all the shared options along with `text` and `alignment`. The alignment option is fairly flexable since fuzzy matching is used.

Alignment has horizontal and vertical sub-options, but a single string of can be provided to set both.
For example: `topLeft` or `bottom_center` will both work. However, on save, it will be changed to a proper value.

#### Text Filters

Text modules, and all modules that contain text for that matter, also have a `filter` option.  
The current available filters are:

- <span class=mono>0Ordinal:</span> Converts any number to its ordinal suffix, '1' -> 'st'
- <span class=mono>0Add Ordinal:</span> Adds the ordinal suffix to every number, '3' -> '3rd'
- <span class=mono>1Lower:</span> Converts the text to all lower case
- <span class=mono>1Upper:</span> Converts the text to all UPPER CASE
- <span class=mono>2Title:</span> Converts the text to Title Case

The numbers at the beginning are used to determine the order of operation and are fixed.

> [!NOTE]
> The current implementation of feature is very rough and could use some improvement. Pull requests are greatly encouraged.

## Realtime

Realtime currently only supports displaying text but other display types will be added in the future. For now, the type must be set to `realtime` or `realtime.text`.

The Realtime module essentially a grouping that contains a title and a display submodule.

```yaml
- type: realtime.text
    key: environment.temperature.temperature
    title: false
    display:
      ...
    geometry:
      ...
```

### <div class=mono>title:</div>

The title is just a text module and has the same options along with `visible` and `ratio`. Ratio is simply the size ratio between the display submodule and the title. To hide the title, you can either give the title a `ratio` of `0`,
or set `visible` to `false` or set the entire title option to `false` like in the example above.

Title also has an optional position option, it can either be `Above`/`Top` or `Below`/`Bottom`. If not provided, it will default to `Above`.

```yaml
- type: realtime.text
    ...
    title:
      text: Outdoor
      visible: true
      position: Below
    ...
```

### <div class=mono>display:</div>

The display section is used to determine how the data is displayed. The display section is optional, if it is not present, it will use the default.

------------------------------------------

#### <div class=mono>.text</div>

Like its parent module, the `text` display type is a grouping containing a **value** and a **unit** text submodule. Both sections are optional if you just want to leave it to the defaults.

Since they are both text modules, the display options are similar to the parent module where there is a ratio, position, and visibility options.
To avoid confusion, the position option is `unitPosition` and the ratio is `valueUnitRatio`.

In addition to `Above` and `Below`, the position option can also be `Inline`, `Auto`, `Hidden` or `Floating`. The `auto` option will place the unit inline if there is enough space, otherwise it will place it below, this is also the
default.

Note: The `Floating` option is not fully implemented yet.

```yaml
- type: realtime.text
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

#### <div class=mono>.gauge</div>

This display type is nearly complete, but was shelved for the initial release.

#### <div class=mono>.mini-graph</div>

Not implemented yet, but nothing is stopping you from making a really tiny graph!

## Graph

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

Normally the min/max of a figure is provided by the range of the actual data displayed, however, sometimes having a data defined min/max can cause some plots to be unreadable. You can define the upper and lower limits of a figure with
the `min:` and `max:` parameters.

```yaml
- figure: precipitationRate
    ...
    min: 0
    min: 3
    ...
```

The values provided to min/max are currently assumed to be of the same unit displayed. In this case the values are assumed to be 'in/hr' (inches per hour).
> [!WARNING]
> Min/Max does not currently limit the actual rendering of the plot so any values outside of that range will be drawn outside of the figure.

### Graph Items

Graph items are what contain all the data, labels, and the visual plot that is rendered on the graph, they are defined by keys within a figure

```yaml
- figure: temperature
  ...
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

<description>

The color of the plot. Currently only supports rgb-hex values. Since <span class=mono-bold>#</span> is used in YAML to denote a comment, the standard <span class=mono-bold>#C0FFEE</span> notation does not work and the <span class=mono-bold>
#</span> must be omitted.

``` yaml
color: ff2f20
```

</description>

##### <div class='mono-header'>gradient:</div>

<description>
Currently only supports hard coded, named gradients.

The available options are:

<span class=mono-bold>TemperatureGradient, PrecipitationProbabilityGradient, PrecipitationRateGradient</span>

``` yaml
gradient: TemperatureGradient
```

</description>

##### <div class='mono-header'>dashPattern:</div>

<description>
An alternating segment length, space length array that defines the dash pattern of the plot.  The actual length of each segment is relative to the width of the line.  Also, the array must be an even length, if not, the last item is ignored.  

In the example below, the dash pattern is a solid line for 2 (two) line widths and then empty space for 4 (four) line widths.

``` yaml
dashPattern: 2, 4
```

</description>

##### <div class='mono-header'>scale:</div>

<description>
The size or weight of the plot

``` yaml
weight: 0.3
```

</description>

##### <div class='mono-header'>type:</div>

<description>
The type of plot. Currently only supports line-plots

```yaml
type: plot
```

</description>

## Clock

The clock module is a special grouping that can contain any other type of module along with its own `ClockComponent` item. Items defined without a type are assumed to be of this type.

```yaml
  ...
  items:
  - format: '%A, %B %-d'
    ...
  - format : '%-I:%M'
    ...
  - type: moon
    ...
```

### ClockComponent

ClockComponent is a modified Text module that updated automatically based on the items within the format string. The format string is the standard strftime format with the one cavite that '-' is used to denote hiding the leading zero,
i.e. `%-d`. Because of this, the format string can contain whatever text you want and only the %_ flags will be replaced.

> [!TIP]
> The characters used for strftime can be fairly difficult to remember so it is recommended to use this reference [strfti.me](https://www.strfti.me)

```yaml
  - format: '%A, %B %-d'
    geometry:
      ...
    filters:
    - 0Add Ordinal
    alignment: CenterRight
```

### Moon Phase

This module currently has no configuration options aside from the shared parameters
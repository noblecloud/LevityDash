# Dashboard Configuration

All dashboard configurations in the YAML format with the extension `.levity`.
You can get a general understanding of how these work by looking at
the [template dashboards](https://github.com/noblecloud/LevityDash/tree/main/src/LevityDash/resources/example-config/templates/dashboards).

The current anatomy of a dashboard file is strictly a list of module attributes like so:

```yaml
- type: type[.subtype]
  attribute: value
  dict-attribute:
    sub-attr-a: 12px
    sub-attr-b: test
  items:  # <- child panels are defined here
  - type: type[.subtype]
    subitem_attr: 70%
- type: realtime.text
    ...
```

## Shared Parameters

There are a few config parameters that are shared across all modules


<!-- panels:start -->

<!-- div:left-panel -->

### <div class=mono>type:</div>

The type of module. This is used to determine which module is used to display the data. Subtypes are specified with a dot. For example: `realtime.text`.

The current options are:

<div class="multi-column">

- realtime[text]
- group
- graph
- text
- clock
- moon

</div>

<!-- div:right-panel -->


```yaml
- type: realtime.text
  ...
```

<!-- panels:end -->

<!-- panels:start -->

<!-- div:left-panel -->

### <div class=mono>key:</div>

The key is the key used to access the data. This is the key used to access the data in the source. All sources use the same key, so it will be the same regardless of the source. Keys use a hierarchical format. For example, the key
for the temperature in the 'environment.temperature.temperature'. Note the double 'temperature' in the key since category 'temperature' contains many measurements.

<!-- div:right-panel -->

```yaml
- type: realtime.text
  key: environment.temperature.temperature
```


<!-- panels:end -->

<!-- panels:start -->


<!-- div:left-panel -->

### <div class=mono>geometry:</div>

All modules have a geometry option, this defines the location and size.

There are four sub-options: `x`, `y`, `width` and `height`.

Any of these four attributes can be undefined, in which case the default value is used.
Default values depend on the module, but are usually `0px` for `x` and `y` and `100px` for `width` and `height`.

All of these attributes can be provided as percentages `'%'`, absolute pixel values `'px'` or with physical units such as inch `'in'`, centimeter `'cm'`, or millimeters `'mm'`.

Relative values are to the immediate parent.


<!-- div:right-panel -->

```yaml
- type: realtime.text
  key: environment.temperature.temperature
  geometry:
    height: 40%
    width: 50%
    x: 0%
    y: 20%
```

<!-- panels:end -->

<!-- panels:start -->

<!-- div:left-panel -->

### <div class=mono>margins:</div>

The margins are used to define the space between the module and the edge of the screen. Like Geometry, it can be provided with percentages or absolute pixel values.  Additionally, physical measurements (e.g. 1mm, 1cm, 1in) can be used.  For simplification, margins can be represented as a single value, which will be applied to all sides, two comma separated values, which will be applied to the top/bottom and left/right, or four comma separated values, which will be applied to the top, right, bottom, and left.  However, sub-options can also be provided individually.

### <div class=mono>padding:</div>

Similar to margins, padding is used to define the space between the edge of the module and it's contents.  It is represented in the same way as margins.


<!-- div:right-panel -->

```yaml
# All sides
margins: 0%

# Vertical, Horizontal
margins: 0%, 0%

# Top, Right, Bottom, Left
margins: 0%, 0%, 0%, 0%

# Named
padding:
  top: 0%
  right: 10px
  bottom: 0%
  left: 10px
```

<!-- panels:end -->



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
    text: str
    icon: [icon-pack]:[icon-name]
    alignment: [top|bottom|center][left|center|right]
    font: [font-name]
    weight: [normal|bold]|[100-900]
    color: [color-name|hex-value|rgb-value]
    height: [px|%|in|cm|mm] 
    filters:
      - [title | lower | upper | capitalize | addOrdinal | ordinal]
    modifiers:
    	atTime: [today]
```

This module is for displaying static text. It has all the shared options along with `text` and `alignment`.

### <div class=mono>text: str</div>

The text to be displayed in the module.

### <div class=mono>icon: Icon</div>

The glyph icon to be displayed in the module specified in the format `icon-pack-abbrivation:icon-name`.  The included icon packs are:

- Weather Icons: `wi`
- Font Awesome: `fa`
- Material Design Icons: `mdi`

For example, `fa:cloud` would display the cloud icon from the font awesome icon pack.

> [!NOTE]
> Both icon and text can not be used at the same time. If both are provided, only the icon will be displayed.

### <div class=mono>font: str</div>

The font family name to be used for the text.  This can be any font installed on the system, any bundled font, or any font placed in the fonts folder of the config directory.

### <div class=mono>weight: str | int</div>

The weight of the font.  This can be specified as a string (e.g. light, regular, bold) or an integer from 0 to 1000.

The string options with their equivalent int values:

- Thin: `100`
- ExtraLight: `200`
- Light: `300`
- Regular: `400`
- Medium: `500`
- DemiBold: `600`
- Bold: `700`
- ExtraBold: `800`
- Black: `900`
- ExtraBlack: `1000`

### <div class=mono>color: str | str[fuzzy]</div>

The color of the text.  This can be specified as a named css web color, a hex value (e.g. `#ffffff`), an 8 digit hex value for setting the alpha (e.g. `#ffffffff`), a comma separated string of 3/4 integers less than 255 or floats less than or equal to 1 (e.g. `255, 255, 255, 255`, `1.0, 1.0, 1.0`), or a dictionary with the keys `red`, `green`, `blue`, and `alpha` or their first letters.  If a value is not provided for alpha, it will default to 255.

```yaml
color: white
color: #ffffff
color: 255, 255, 255, 255
color: 1.0. 1.0, 1.0
color:
  red: 255
  green: 255
  blue: 255
```

### <div class=mono>alignment: str[fuzzy] | Alignment</div>

Alignment has horizontal and vertical sub-options, but a single string of can be provided to set both.
For example: `topLeft` or `bottom_center` will both work. However, on save, it will be changed to a proper value.

The string value can be any combination of `top`, `bottom`, `center`, `left`, `right`.
For fuzzy matching, order does matter.
The proper order is vertical alignment > center if applicable > horizontal.
For example, `top-left` will match `topLeft`, but `leftTop` will not.

```yaml
alignment: topLeft
alignment: CenterRight
alignment: bottom_center
```

### <div class=mono>filter: str[fuzzy]</div>

Text modules, and all modules that contain text for that matter, also have a `filter` option.
This option uses fuzzy text matching, so it is fairly flexable with what it is provided.

The current available filters are:

- <span class=mono>Ordinal:</span>Converts any number to its ordinal suffix, '1' -> 'st'
- <span class=mono>Add Ordinal:</span> Adds the ordinal suffix to every number, '3' -> '3rd'
- <span class=mono>Lower:</span> Converts the text to all lower case
- <span class=mono>Upper:</span> Converts the text to all UPPER CASE
- <span class=mono>Title:</span> Converts the text to Title Case

### <div class=mono>text-scale-type: str[fuzzy]</div>
Text in labels can have three different options for how the text is scaled and the anchor point for the scale.

#### <div class=mono>full</div> 
Scale the text item as large as it possibly fit inside the label and use a non font aware anchor point.  The items width and height are obtained from the bounds of the text path.

#### <div class=mono>font</div> 
Similar to fill, except the top, bottom and overall height is calculated using the font families accention and decention attributes.  The anchor is the fonts "stikeout" position.

#### <div class=mono>auto</div>
Like Font, the anchor point is the "strikeout" postition, but the height is either the path bounds or the height of a "|" character, whichever is larger.  This is the default mode for text.


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

### <div class=mono>title: Text</div>

The title is just a text module and has the same options along with `visible`, `size` and `position`.

```yaml
- type: realtime.text
    ...
    title:
      text: Outdoor
      visible: true
      position: below
    ...
```

<div class="indent">

#### <div class=mono>visible: bool</div>

Whether the title is visible.  If all other values are their defaults, `title:` is collapsed to this bool representation or hidden completely if `true` which is the default.

#### <div class=mono>size: RelativeValue | AbsolutePixelValue | AbsolutePhysicalValue </div>

Size the attribute can a relative/percentage, an absolute pixel, or an absolute physical value.
Relative values are represented either as a float between 0 and 1 or any numerical value followed by a `%`.
Absolute pixel values are represented as any numerical value followed by `px`.
Absolute physical values are represented as any numerical value followed by a metric or imperial distance unit

#### <div class=mono>position: str[fuzzy] | DisplayPosition</div>

The position of the title.
The options are `above`/`top`, `below`/`bottom`, `left`, or `right` with `above` being the default.

</div>

### <div class=mono>display:</div>

The display section is used to determine how the data is displayed. The display section is optional, if it is not present, it will use the default.

```yaml
display:
  precision: 0
  format-hint: 000k
  unitPosition: float-under
  unitSize: 8mm
  shorten: true
  valueLabel:
    color: lightseagreen
  unitLabel:
    color: lightskyblue
```

<div class="indent">

#### <div class=mono>type: str[fuzzy]</div>

#### <div class=mono>unit-string: str</div>

Overrides the unit string for the display.
This is useful for when the unit string is not correct, or you want to display a different unit string.

#### <div class=mono>precision: int</div>

The number of decimal places to display.  This is only used for numeric values.

#### <div class=mono>unitPosition: str[fuzzy] | DisplayPosition</div>

The position of the unit string.
The options are `auto`, `above`/`top`, `below`/`bottom`, `left`, `right`, `inline` or `float-under` with `auto` as the default.
The `auto` option will place the unit inline if there is enough space, otherwise it will place it below the value.
`float-under` places the unit directly under the value.
When `float-under` is set, `float-offset` is used to determine the offset of the unit from the value.

#### <div class=mono>unitSize: RelativeValue | AbsolutePixelValue | AbsolutePhysicalValue </div>

The size of the unit label.  Relative sizes are relative to the Realtime display submodule's size.

#### <div class=mono>shorten: bool </div>

Whether to shorten the very large numerical values.
This is useful for when the value regularly changes in several orders of magnitude.
The current implementation is not very smart and will just shorten the value to the nearest thousand, million, billion, etc and add the appropriate suffix.
Eventually this option will be expanded to allow for stepping up and down the order of magnitude via unit conversion, (e.g. 5823 ft -> 1.10 mi).

#### <div class=mono>floating-offset: RelativeValue | AbsolutePixelValue | AbsolutePhysicalValue </div>

The offset of the unit label when `unitPosition` is set to `float-under`.

#### <div class=mono>format: str </div>

The format string to use when formatting the value.

#### <div class=mono>format-hint: str </div>

This attribute is used to override the string used for sizing/alignment.
For example, wind speed frequently changes between 0 and some non-zero float causing the text to constantly resize.
To fix this, `format-hint` can be set to `'10.0'`.  Note, the quotes are required, without the quotes, the value will be interpreted as a float and the decimal will be dropped.  Since this string will be used to determine the size of the text, it is important that the string is the same length as the longest string that will be displayed.

#### <div class=mono>convertTo: str </div>

The unit to convert the value to.
This option accepts any unit name or abbreviation that is compatible with the original value.

#### <div class=mono>valueLabel: Text </div>

The Text submodule used to display the value.  All Text submodule options are available under this attribute except for `text` and `visible`.

#### <div class=mono>unitLabel: Text </div>

The Text submodule used to display the unit string. All Text submodule options are available under this attribute except for `text` and `visible`.

</div>

[//]: #
[//]: #
[//]: #
[//]: #
[//]: #
[//]: #
[//]: #
[//]: #
[//]: #
[//]: #
[//]: #
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

[//]: #
[//]: #
[//]: #
[//]: #
[//]: #
[//]: #
[//]: #
[//]: #
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

### Background Annotations

This section is how you adjust the background annotations, such as the hourly lines and timestamp markers.

```yaml
annotations:
  dayLabels:
    position: Bottom
    alignment: TopCenter
    opacity: 20%
    height: 20px
  hourLabels:
    position: Top
    alignment: BottomCenter
    opacity: 100%
    height: 2cm
    offset: 2%
  lines:
    weight: 0.3
```

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
> Min/Max does not currently limit the actual rendering of the plot so any values outside that range will be drawn outside the figure.

### Graph Items

Graph items are what contain all the data, labels, and the visual plot that is rendered on the graph, they are defined by keys within a figure

```yaml
- figure: temperature
  ...
  environment.temperature.temperature:
    labels:
      enabled: true
      opacity: 100%
      height: 1.5cm
      offset: 5px
    ------ or -------
    labels: false   
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

```yaml
color: ff2f20
```

</description>

##### <div class='mono-header'>gradient:</div>

<description>
Currently only supports hard coded, named gradients.

The available options are:

<span class=mono-bold>TemperatureGradient, PrecipitationProbabilityGradient, PrecipitationRateGradient</span>

```yaml
gradient: TemperatureGradient
```

</description>

##### <div class='mono-header'>dashPattern:</div>

<description>
An alternating segment length, space length array that defines the dash pattern of the plot.  The actual length of each segment is relative to the width of the line.  Also, the array must be an even length, if not, the last item is ignored.

In the example below, the dash pattern is a solid line for 2 (two) line widths and then empty space for 4 (four) line widths.

```yaml
dashPattern: 2, 4
```

</description>

##### <div class='mono-header'>scale:</div>

<description>
The size or weight of the plot

```yaml
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

<!-- panels:start -->

<!-- div:left-panel -->

The clock module is a special grouping that can contain any other type of module along with its own `ClockComponent` item.  Items defined without a type are assumed to be of this type.  


`ClockComponent` is a modified Text module that updated automatically based on the items within the format string.
The format string, defined by the `format` attribute, uses the [standard strftime format](https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes) with the one caveat that '-' is used to denote hiding the leading zero,
i.e. `%-d`.

The characters used for strftime can be fairly difficult to remember so it is recommended to use this reference [strfti.me](https://www.strfti.me)

> [!TIP]
> Use text filters to add ordinal suffixes to the day of the month

<!-- div:right-panel -->

```yaml
- type: clock
  items:
  
  - format: '%A, %B %-d'
    geometry:
      height: 1.5cm
    filters:
      - AddOrdinal 
    alignment: CenterRight
  
  - format : '%-I:%M'
    geometry:
      height: 1.5cm
      x: 1.5cm
  
  - type: moon
    ...
```

<!-- panels:end -->


## Moon Phase

Essentially, the Moon Phase you can only adjust the `glowStrength` and the update interval.

```yaml
- type: moon
  ...
  geometry:
    ...
  glowStrength: 2
  interval:
    minutes: 20
```
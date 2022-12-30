# Application Configuration

## Location  <!-- {docsify-ignore} -->

This section is pretty self-explanatory. If blank, Levity will guess the location based on the devices IP address.

```ini
[Location]
timezone = America/New_York
latitude = 37.8
longitude = -76.1
```

## Display

```ini
[Display]
dashboard = default.levity
frontend = Qt
fullscreen = False
width = 90%
height = 600px
```

### <div class=mono>dashboard</div>

The file name or path of the default dashboard.

### <div class=mono>frontend</div> 

The frontend that Levity will use. Currently, only PySide2 is supported.

### <div class=mono>fullscreen</div> 

When ```True```, Levity will run in fullscreen mode.

### <div class=mono>width/height</div> 

The starting width and height of the window in pixels `px`, percentage `%`, centimeters `cm`, millimeters `mm`, inches `in` or pretty much any length unit supported by WeatherUnits. For values without a unit, integers are assumed to be
pixels and floats, percentages.
If provided a real-world measurement like centimeters, the value will be estimated based on the displays reported DPI.

> [!TIP]
> Using real-world measurements is handy when you are customizing/testing a dashboard that will be used on a different, smaller display


## QtOptions

```ini
[QtOptions]
openGL = True
antialiasing = True
antialiasingSamples = 8
maxTextureSize = 10mb
pixmapCacheSize = 200mb
```

When ```True```, Levity will use OpenGL to render the UI. This is the default.

### <div class=mono>openGL</div> 

When ```True```, Levity will use OpenGL for rendering allowing for hardware acceleration and a much faster rendering performance.

### <div class=mono>antialiasing</div> 

When ```True```, Levity will use antialiasing for rendering.

### <div class=mono>antialiasingSamples</div> 

The number of samples to use for antialiasing. This is only applicable when openGL is enabled. Optionally, `antialiasing` and `antialiasingSamples` can be combined to a single option, where `0` is considered disabled and any non-zero
value is the number of samples to use.

### <div class=mono>maxTextureSize</div> 

The maximum size of textures in `[giga|mega|kilo]bytes`. This is currently only used by the Graph display module. Each graph item is rendered and stored as a bitmap in memory. Depending on the length of the timeseries plotted, size of the
dashboard, and pixel density of the display, these can get rather large which cause stuttering while scrolling. If the bitmap is larger than `maxTextureSize`, it will be scaled down to fit within the maximum size and then scaled back up to
the original size.

> [!TIP]
> Since this is a tradeoff between performance and visual fidelity. For dashboards that will not be interacted with, as long as the device can support it, the large the value the better.

### <div class=mono>pixmapCacheSize</div> 

The maximum size of the pixmap cache in `[giga|mega|kilo]bytes`. A few of the Qt modules, except items that render their own textures like Graph Plots, use caching to speed up performance and reduce redundant rendering. All of these bitmaps
are stored in a QPixmapCache, this option limits the size of that cache.


## Fonts

```ini
[Fonts]
default = Nunito
default.weight = Medium
compact = Nunito
compact.weight = Medium
```

This is where you can define the default font and it's properties. The default font will be used wherever the font is not explicitly defined.
The compact font is used when the text will be rendered in space with a height less than 120px. Eventually, this threshold will be adjustable by the user.


## Logging

```ini
[Logging]
level = INFO
verbosity = 0
encoding = utf-8
logFileFormat = %%Y-%%m-%%d_%%H-%%M-%%S
logFileWidth = 120

rolloverSize = 10mb
rolloverCount = 5
```

### <div class=mono>level</div> :id=log-level

The logging level to use. This can be one of the following: `VERBOSE`, `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` with the default being `INFO`. This only changes the level of logging that is written to the console. The log file is
always written at the `VERBOSE` level with a verbosity of `5`.

<!-- panels:start -->

<!-- div:left-panel -->

### <div class=mono>verbosity</div> :id=log-verbosity

The verbosity threshold for the `VERBOSE` level. This is a number between 0 and 5. The higher the number, the more verbose the log file. The default is `0`.


<!-- div:right-panel -->

``` Verbosity Levels
0. slightly verbose
1. sorta verbose
2. verbose
3. very verbose
4. extremely verbose
5. extremely extremely verbose
```

<!-- panels:end -->


### <div class=mono>encoding</div> 

The encoding to use for the log file. The default is `utf-8`.

### <div class=mono>logFileFormat</div> 

The format of the log file name It is a typical `strftime` format string. The default is `%Y-%m-%d_%H-%M-%S`.
> [!TIP]
> https://strftime.org/ is a wonderful cheatsheet for formatting dates and times. Placing a `-` between the `%` and the specifying digit like so `%-I` will remove leading zeros. The only consideration that needs to be made is when running
> on Windows, the correct character is `#` instead of `-`. A lot of the time, Levity will handle this for you, but it is not implemented everywhere.

### <div class=mono>logFileWidth</div> 

The width in characters of the log file. For log levels higher than VERBOSE, the default of 120 is plenty. Depending on the verbosity level, it might need to be expanded for readability.

### <div class=mono>rolloverSize</div> 

The logger uses a rolling file logger, when the log file reaches this size, it will be rolled over to a new file. Like the other memory size parameters, values are given as `[giga|mega|kilo]bytes`. The default is `10mb`.

### <div class=mono>rolloverCount</div> 

This is the number of files to keep with the rolling file logger. The default is `5`.


## WeatherUnits <!-- {docsify-ignore} -->

The sections below are for the WeatherUnit Module. WeatherUnits is what is used to convert/localize measurements for display. More information on how it's configured can be found in
the [WeatherUnits repo](https://github.com/noblecloud/WeatherUnits).

```ini
[Units]
wind = mi/hr
temperature = f
precipitationRate = inch/*
precipitationHourly = inch/hr
precipitation = inch
pressure = inHg
density = lbs/ft
pollutionDensity = ug/m
length = mi

[UnitDefaults]
precision = 1
max = 3

[UnitProperties]
temperature = precision=0, max=3, unitSpacer=False, shorten=False, kSeparator=True, decorator=º, showUnit=False
```
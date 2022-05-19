# Config

The config for Levity currently uses python's built in config parser. Eventually, this will be replaced with TOML or YAML.

```ini
[Location]
timezone = America/New_York
latitude = 37.8
longitude = -76.1

[MetaData] # This is the current dashboard
filepath = ~/.config/levity/saves/dashboards/default.levity

[Display]
frontend = PySide #Currently only supports PySide2
fullscreen = False #Set to True to start in fullscreen
width = 90%
height = 90%

[Fonts]
default = Nunito
default.weight = Medium
```

## WeatherUnits

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

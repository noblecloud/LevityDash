# Plugin Config

## The Basics
Plugin config files are currently INI files but will eventually be changed to TOML or YAML. The main config file, `plugins.ini` is located in the `plugins` directory of your config folder.

Every plugin has an optional `defaultFor` parameter that is used to give the plugin priority when choosing where to pull data for display. It is currently a space separated list of strings and the stings can be any part of a key.

```ini
; Any key with temperature or wind
defaultFor = temperature wind

; All indoor keys
defaultFor = indoor

; Only indoor temperatures
defaultFor = indoor.temperature
```

## Individual Plugin Config
Each plugin can be have

- its own config file of the same name
- a `config.ini` file within a folder of the same name
- or be a part of the main `plugin.ini`.

```
└── plugins
  ├── plugins.ini
  ├── WeatherFlow.ini
  └── Govee
    └── config.ini
```

> [!NOTE]
> Since these are all .ini files, they must contain at least one section. Therefor, all individual config files must contain a `[Config]` section.

---

[remote-md](https://raw.githubusercontent.com/noblecloud/LevityDash/main/docs/plugins/WeatherFlow.md)

---

# Open-Meteo

Other than `defaultFor`, there really isn't much to configure for Open-Meteo. Eventually, there will be parameters to define what fields the plugin requests, but currently those options are hard coded.

```ini
; CONFIG_DIR/plugins/plugins.ini
[OpenMeteo]
enabled = True
defaultFor = clouds
```

---

# Govee

Govee BLE devices announce their data via a payload within a BLE Advertizement. The location within the payload varies between models so the goal was to make this plugin work regardless of how the data is to parsed.
Additionally, how the values are calculated differ from model to model.

For the plugin to function, there must be an identifier for the device you want to use. If you do not have any of the possible identifiers you can provide either `closest` or `first` as `device.id` along with the model of the device
as `device.model` and the plugin will find the device and save the correct information to the config file.

```ini
; CONFIG_DIR/plugins/Govee/config.ini
[Config]
...
device.id = closest
device.model = GVH5102
...
```

There are a few options for setting the device identification.

```ini
; CONFIG_DIR/plugins/Govee/config.ini
[Config]
...
; Any of the following will work for identification
device.name =
device.uuid =
device.mac =
device.id =
```

As far as parsing the data, the slicing locations and expressions needed can usually be found by searching the model of the device on github.

As far as I can tell, the expression needed to extract temperature and humidity is relatively consistent across Govee's lineup. If for some reason, the expression is different they can easily be defined as any single line pythonic
expression with a single undefined variable as the payload.

``` ini
; CONFIG_DIR/plugins/Govee/config.ini
[Config]
...
temperature.slice = [4:10]
temperature.expression = val / 10000
humidity.slice = [4:10]
humidity.expression = payload % 1000 / 1000
battery.slice = [10:12]
```

> [!NOTE]
> Note that the payload variable name for temperature is different from the variable in humidify.
> The plugin will assume the first available non numeric atom to be the payload value.
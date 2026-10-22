# Plugin Configuration

## The Basics <!-- {docsify-ignore} -->
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

## Individual Plugin Config <!-- {docsify-ignore} -->
Each plugin can have its own config file of the same name or a `config.ini` file within a folder of the same name

```treeview
{config_dir}/
`-- config.ini
`-- plugins/
	|-- plugins.ini
	|-- WeatherFlow.ini
	|-- OpenMeteo.ini
	`-- Govee/
			`-- config.ini
```

---

## Astronomy

The sun, from the clock and the `[Location]` section of your [config](/config/app.md). It needs no network and no key. It publishes two keys for a sun-arc dial:

- `astronomy.sun.hour`: the local hour of day as a decimal, so 15.5 is 15:30.
- `astronomy.sun.remaining`: minutes of daylight left today. It is `0` at night.

The plugin is on by default. To turn it off, set `enabled = False` in `CONFIG_DIR/plugins/Astronomy.ini`. A scenario that defines either key wins over the plugin.

## Lost connections

REST plugins retry a failed request. The UDP listener and the WeatherFlow websocket also reconnect after a drop. They wait a little longer after each failed try, from 2 seconds up to 5 minutes, and then reconnect on their own. You do not need to restart the app.

## Saved history

A plugin that keeps a log (WeatherFlow and Govee) writes it to a small file as it runs. When the app starts again, it reads the last two days back, so a graph of what your sensors measured is not empty while the plugins warm up.

- The file is `history.sqlite3` in the app's cache folder. It is a cache. You can delete it and nothing else changes.
- A plugin writes at most once a minute. Rows older than two days are deleted.
- Only the log comes back. The current value of a key does not. It shows when the sensor next reports, so a value that is hours old never looks fresh.
- A restored value keeps the time it was recorded. If you change a unit setting, the old values show in the new unit.
- If the file cannot be opened or written, the plugins run without history and the app logs it once.
- Set `LEVITYDASH_HISTORY=off` to turn it off. Set `LEVITYDASH_HISTORY_DB` to a file path to keep it somewhere else.

---


[wf](plugins/WeatherFlow.md ':include')

---

[om](plugins/OpenMeteo.md ':include')

---

[pw](plugins/PirateWeather.md ':include')

---

[gov](plugins/Govee.md ':include')

---

[owm](plugins/OpenWeatherMap.md ':include')
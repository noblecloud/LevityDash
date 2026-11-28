# Plugin Configuration

## The Basics <!-- {docsify-ignore} -->
Plugin config files are TOML (older `.ini` files are converted on first start; see [Application Configuration](/config/config.md)). The main config file, `plugins.toml` is located in the `plugins` directory of your config folder.

Every plugin has an optional `defaultFor` parameter that is used to give the plugin priority when choosing where to pull data for display. It is currently a space separated list of strings and the stings can be any part of a key.

```toml
# Any key with temperature or wind
defaultFor = "temperature wind"

# All indoor keys
defaultFor = "indoor"

# Only indoor temperatures
defaultFor = "indoor.temperature"
```

### Which source wins

When several plugins publish the same key, a display shows the first of these that applies:

1. A plugin whose `defaultFor` names part of the key (the highest `priority` among them).
2. The plugin with the highest `priority`, counting only sources that are still reporting.
3. A source that has gone quiet (see `maxAge`), only if nothing else has the key.

`priority` is a number; higher wins, and the number of `defaultFor` entries only breaks ties. Built-in values: WeatherFlow 20 (your own station), PirateWeather and OpenMeteo 10, anything else 0, OpenWeatherMap -10 (last resort; its free tier was the least accurate). Set your own in the plugin's section:

```toml
[plugin]
priority = 15
```

`maxAge` is how many minutes a live reading may go without an update before the plugin stops being preferred for that key; `0` turns it off. WeatherFlow defaults to 30, so when a station's sensor dies (only the base still reports pressure, say) the other keys come from PirateWeather or OpenMeteo while the pressure stays the station's. A reading from a source with no `maxAge` is never treated as old.

```toml
[plugin]
maxAge = 15
```

A single item can still pin a source with `Source:key`, for example `OpenMeteo:environment.temperature.temperature`.

## Individual Plugin Config <!-- {docsify-ignore} -->
Each plugin can have its own config file of the same name or a `config.toml` file within a folder of the same name

```treeview
{config_dir}/
`-- config.toml
`-- plugins/
	|-- plugins.toml
	|-- WeatherFlow.toml
	|-- OpenMeteo.toml
	`-- Govee/
			`-- config.toml
```

---

## Astronomy

The sun, from the clock and the `[Location]` section of your [config](/config/app.md). It needs no network and no key. It publishes two keys for a sun-arc dial:

- `astronomy.sun.hour`: the local hour of day as a decimal, so 15.5 is 15:30.
- `astronomy.sun.remaining`: minutes of daylight left today. It is `0` at night.

The plugin is on by default. To turn it off, set `enabled = false` in `CONFIG_DIR/plugins/Astronomy.toml`. A scenario that defines either key wins over the plugin.

## Lost connections

REST plugins retry a failed request. The UDP listener and the WeatherFlow websocket also reconnect after a drop. They wait a little longer after each failed try, from 2 seconds up to 5 minutes, and then reconnect on their own. You do not need to restart the app.

## Saved history

LevityDash keeps what it pulls, so a restart does not empty the graphs and a display that boots before its wifi still shows the last forecast. The default is **InfluxDB 3 Core**, a time-series database that the supervisor (`LevityDash-run`) starts next to the app as a plain process (no container) and keeps running. QuestDB is the drop-in alternative, and a SQLite file is the fallback when no server can be reached, so the display never waits on a database.

What is kept, all in one table keyed by plugin, stream and key:

- **The log** of every plugin that has one (WeatherFlow and Govee), about once a minute. The last two days (`restore`) are read back when the plugins start, so graphs are not empty while the plugins warm up.
- **Snapshots** of every other plugin's current values (aircraft, host vitals and so on), every few minutes.
- **Responses**: the body of each REST response (forecasts, ...) as fetched, once every 15 minutes per endpoint. If a forecast cannot be fetched after a start, the stored one is used until a fetch succeeds.
- Only the log goes back into a plugin. The current value of a key is not restored, so a value that is hours old never looks fresh. A restored value keeps the time it was recorded, and shows in your current unit settings.

```toml
[History]
backend = "influxdb"    # influxdb, questdb or sqlite
retention = 30          # days to keep rows
restore = 2             # days read back at start-up
raw = true              # keep fetched responses
```

Every key is optional.

| Key | Default | |
| --- | --- | --- |
| `enabled` | `true` | `false` keeps nothing |
| `backend` | `influxdb` | `influxdb`, `questdb` or `sqlite` |
| `fallback` | `sqlite` | what to use when the server cannot be reached at start (`none` runs without history) |
| `host`, `port` | `localhost`, 8181 (InfluxDB) or 9000 (QuestDB) | where the server is; the supervisor only starts one that is on this machine |
| `database` | `levitydash` | InfluxDB database name |
| `token` | none | bearer token for a server you run with auth; the supervisor does not start a server for you then |
| `username`, `password` | none | QuestDB basic auth |
| `path` | the cache folder's `history.sqlite3` | the SQLite file |
| `retention` | `30` | days a row is kept (InfluxDB sets it on the database; QuestDB drops whole days; SQLite deletes rows) |
| `restore` | `2` | days read back into the plugins at start |
| `raw`, `raw-every` | `true`, `15` | keep fetched responses, at most one per endpoint per this many minutes |
| `snapshots`, `snapshot-every` | `true`, `5` | snapshots of plugins without a log, minutes apart |

### Running the database

Install it once on the machine that runs the display: `brew install influxdb3-core` (or download it from influxdata.com and set `binary` under `[History]`). `LevityDash-run` then starts it before the backend and the frontend, on `127.0.0.1:8181` without auth (nothing else can reach it, and its usage upload to InfluxData is switched off), keeps it up and stops it last. A file change restarts the app, never the database. The data is in the app's data folder under `history/influxdb`. Without the supervisor, run `influxdb3 serve --node-id levitydash --object-store file --data-dir DIR` yourself, or `LevityDash-run --no-history` to leave it alone.

InfluxDB 3 Core limits how much one query may read (about 72 hours of data; a quiet database reaches further). The default `restore` of two days is inside it. Its free at-home Enterprise licence lifts the limit.

To use QuestDB instead: `backend = "questdb"`, and either start it yourself or give `command` (a command that runs QuestDB in the foreground) so the supervisor keeps it up. The server's tables are made on first use.

The environment overrides the file: `LEVITYDASH_HISTORY=off`, `LEVITYDASH_HISTORY_BACKEND=sqlite|influxdb|questdb`, `LEVITYDASH_HISTORY_DB=/path/file.sqlite3` (SQLite at that path). If the database cannot be reached, the app logs it once, and keeps its history in the SQLite file for that run; restart the app after fixing the server to go back to it.

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
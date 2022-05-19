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


[remote-md](http://localhost:3000/plugins/WeatherFlow.md)
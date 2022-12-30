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


[wf](plugins/WeatherFlow.md ':include')

---

[om](plugins/OpenMeteo.md ':include')

---

[gov](plugins/Govee.md ':include')
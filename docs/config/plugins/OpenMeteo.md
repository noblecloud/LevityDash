## Open-Meteo

Other than `defaultFor`, there really isn't much to configure for Open-Meteo. Eventually, there will be parameters to define what fields the plugin requests, but currently those options are hard coded.

```ini
; CONFIG_DIR/plugins/plugins.ini
[Config]
enabled = True
defaultFor = clouds
```
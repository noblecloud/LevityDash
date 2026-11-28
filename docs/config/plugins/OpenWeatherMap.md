## OpenWeatherMap

Uses the free Current Weather Data endpoint — current conditions only, no forecast (OpenWeatherMap's forecast-capable One Call API requires a separate paid subscription). Off by default and ranked last: any other source that has the same key (PirateWeather, OpenMeteo, a station) is shown instead, because its readings were the least accurate in practice. Requires a free API key from https://openweathermap.org/api.

```toml
# CONFIG_DIR/plugins/OpenWeatherMap.toml
[plugin]
enabled = true
apikey = "{API Key}"
```

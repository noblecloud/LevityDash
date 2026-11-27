## OpenWeatherMap

Uses the free Current Weather Data endpoint — current conditions only, no forecast (OpenWeatherMap's forecast-capable One Call API requires a separate paid subscription). Off by default and ranked last: any other source that has the same key (PirateWeather, OpenMeteo, a station) is shown instead, because its readings were the least accurate in practice. Requires a free API key from https://openweathermap.org/api.

```ini
; CONFIG_DIR/plugins/OpenWeatherMap.ini
[plugin]
enabled = True
apikey = {API Key}
```

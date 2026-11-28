## PirateWeather

A drop-in replacement for the retired Dark Sky API. Requires a free API key from https://pirateweather.net/. Provides realtime, minutely, hourly, and daily forecast data.

```toml
# CONFIG_DIR/plugins/PirateWeather.toml
[plugin]
enabled = true
apikey = "{API Key}"
defaultFor = "temperature precipitation wind pressure humidity storm"
```

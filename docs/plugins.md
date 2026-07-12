# Plugins

## Built-In Plugins  <!-- {docsify-ignore} -->

### Open-Meteo  <!-- {docsify-ignore} -->

https://open-meteo.com/

Free API with no API key required. Provides global weather data sourced from National Weather Services.

### PirateWeather  <!-- {docsify-ignore} -->

https://pirateweather.net/

A drop-in replacement for the retired Dark Sky API. Requires a free API key. Provides realtime, hourly, and daily forecast data.

### WeatherFlow Tempest  <!-- {docsify-ignore} -->

https://tempestwx.com/

An API provided by WeatherFlow in conjunction with their Tempest WeatherStation.
Provides realtime data from your weather station from either a UDP or web socket.
Additionally, WeatherFlow provides historical data and both hourly and daily 10 forecasting.

### Govee BLE  <!-- {docsify-ignore} -->

Reads Govee BLE thermometer/hygrometer advertisements. Tested with the [GVH5102](https://www.amazon.com/Govee-Hygrometer-Thermometer-Temperature-Notification/dp/B087313N8F?th=1); device selection supports `closest`, `first`, or explicit MAC/UUID/name, and the payload parsing is configurable, so extending to other Govee BLE devices is usually just config.

### OpenWeatherMap  <!-- {docsify-ignore} -->

https://openweathermap.org/

Uses the free Current Weather Data endpoint (`data/2.5/weather`) — current conditions only, no hourly/daily forecast. OpenWeatherMap's One Call API (which does include forecasts) requires a separate paid subscription and isn't supported. Requires a free API key.

## Build Your Own  <!-- {docsify-ignore} -->

The plugin system was designed to be extensible, so you can build your own plugins. Most of the time it is as simple as extending the base plugin class type [Rest, BLE, Socket, etc.] and specifying urls, parameters and data schema
for the automatic parser.

To install a plugin, place the plugin in the `plugins` directory of your config folder.

### Plugin Data Sources  <!-- {docsify-ignore} -->

- REST API Pull
- Sockets (UDP, websocket, socket.io)
- BLE Advertisements

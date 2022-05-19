# Plugins

## Built-In Plugins

### Open-Meteo

https://open-meteo.com/

Free API with no API key required. Provides global weather data sourced from National Weather Services.

### WeatherFlow Tempest

https://tempestwx.com/

An API provided by WeatherFlow in conjunction with their Tempest WeatherStation.
Provides realtime data from your weather station from either a UDP or web socket.
Additionally, WeatherFlow provides historical data and both hourly and daily 10 forecasting.

### Govee BLE

Currently only implemented for [GVH5102](https://www.amazon.com/Govee-Hygrometer-Thermometer-Temperature-Notification/dp/B087313N8F?th=1) but extending to other Govee BLE devices should be fairly simple.

## Build Your Own

The plugin system was designed to be extensible, so you can build your own plugins. Most of the time it is as simple as extending the base plugin class type [Rest, BLE, Socket, etc.] and specifying urls, parameters and data/key maps
for the automatic parser.

To install a plugin, place the plugin in the `~/.config/levity/plugins` directory.

## Plugin Data Sources

- REST API Pull
- Sockets (UDP, websocket, socket.io)
- BLE Advertisements


<ml-generated>
LevityDash is designed for use with multiple plugins.  Plugins are used to pull data from various sources and provide it to the dashboard.  The dashboard is then able to display the data in a variety of ways.  Plugins are also used to provide the dashboard with information about the data that is being pulled.  This information is used to automatically parse the data and provide it to the dashboard in a usable format.
</ml-generated>

## Built-In Plugins  <!-- {docsify-ignore} -->

### Open-Meteo  <!-- {docsify-ignore} -->

https://open-meteo.com/

Free API with no API key required. Provides global weather data sourced from National Weather Services.

### WeatherFlow Tempest  <!-- {docsify-ignore} -->

https://tempestwx.com/

An API provided by WeatherFlow in conjunction with their Tempest WeatherStation.
Provides realtime data from your weather station from either a UDP or web socket.
Additionally, WeatherFlow provides historical data and both hourly and daily 10 forecasting.

### Govee BLE  <!-- {docsify-ignore} -->

Currently only implemented for [GVH5102](https://www.amazon.com/Govee-Hygrometer-Thermometer-Temperature-Notification/dp/B087313N8F?th=1) but extending to other Govee BLE devices should be fairly simple.

## Build Your Own  <!-- {docsify-ignore} -->

The plugin system was designed to be extensible, so you can build your own plugins. Most of the time it is as simple as extending the base plugin class type [Rest, BLE, Socket, etc.] and specifying urls, parameters and data schema
for the automatic parser.

To install a plugin, place the plugin in the `plugins` directory of your config folder.

### Plugin Data Sources  <!-- {docsify-ignore} -->

- REST API Pull
- Sockets (UDP, websocket, socket.io)
- BLE Advertisements
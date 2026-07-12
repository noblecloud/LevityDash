<p align="center">
	<p align="center">
   <img width="200" height="200" src="https://github.com/noblecloud/LevityDash/raw/gh-pages/docs/_images/favicons/android-chrome-512x512.png" alt="Logo">
  </p>
	<h1 align="center" color="505050">
		<strong><b>LevityDash</b></strong>
	</h1>
  <p align="center">
  	A lightweight, desktop native, multisource dashboard for macOS, Windows and Linux
  </p>
</p>

![Screenshot](https://github.com/noblecloud/LevityDash/raw/main/docs/_images/screenshot-readme.png)

LevityDash aims to be a lightweight, desktop native, multi-source dashboard without a required web frontend that is fun and easy to use. The current frontend is built on PySide6/Qt 6. A key goal of this project is to support multiple frontends and platforms, including embedded — the backend/frontend process split that enables this is actively in progress (see the [roadmap](docs/roadmap.md)).

*Note: This project is in beta – it works and is used daily, but expect rough edges.*

<p align="right">
<img src="https://img.shields.io/badge/license-MIT-blueviolet">
<img src="https://img.shields.io/badge/Python-3.11–3.14-blueviolet">
<img src="https://img.shields.io/badge/Qt-6-blueviolet">
<img src="https://img.shields.io/badge/aiohttp-3.14-blueviolet">

</p>

# Current Features

## Backend

- Plugin system for adding new sources
- Scheduling API pulls
- Data/key maps for automatically parsing ingested data
- Unit library for automatic localization/conversion
- Conditional value updates. i.e. if wind speed is zero do not log the wind direction

### Data Sources

- REST API Pull
- Sockets (UDP, websocket, socket.io)
- BLE Advertisements

### Builtin Plugins

- [Open-Meteo](https://open-meteo.com) [REST]
- [PirateWeather](https://pirateweather.net) [REST]
- [WeatherFlow Tempest](https://tempestwx.com) [REST, UDP, Websocket]
- Govee BLE Thermometers/Hygrometers [[GVH5102](https://www.amazon.com/Govee-Hygrometer-Thermometer-Temperature-Notification/dp/B087313N8F?th=1)]
- OpenWeatherMap [REST, experimental]

## Frontend

- Drag and drop dashboard design (This can be a little funky at times)
- YAML based dashboard specifications with support for both absolute and relative size/positioning
- Module grouping
- Editable Margins for text modules
- Resizable graph figures
- Custom, value mapped, gradients for figure items
- Text filters (i.e. lower, title, upper, digit to ordinal, etc.)

## Current Modules

- Realtime text with support for showing units and titles and mapping glyphs/emojis to values
- Gauges
- Timeseries Graph and Mini Graph
- Customizable Clock
- Moon Phase
- Groups, titled groups, stacks, and value stacks for organizing modules

## Planned Modules

- Weather Radar
- Multiline Text
- RSS Feeds
- Calendar
- More plot types

See the full [roadmap](docs/roadmap.md) for what's done, in progress, and planned.
# Getting Started

## Requirements  <!-- {docsify-ignore} -->

- Python 3.13 – 3.14 (3.14 recommended — it's noticeably faster)
- [Poetry](https://python-poetry.org) for installing from source

## Install  <!-- {docsify-ignore} -->

> [!WARNING]
> The package on PyPI is an old 0.1.x release from the PySide2 era. Until 0.2.0 ships, install from source.

```bash
git clone https://github.com/noblecloud/LevityDash.git
cd LevityDash
poetry install --without dev
```

> [!NOTE]
> The `dev` dependency group expects a sibling checkout of the WeatherUnits repo (`../WeatherUnits`) for library development. `--without dev` skips it and uses the released WeatherUnits from PyPI.

## Running LevityDash  <!-- {docsify-ignore} -->

LevityDash has two modes:

- **`live`** (default) — runs everything in one process: plugins, data pipeline, and the Qt window.
- **`remote`** — runs the Qt window as a frontend that attaches to a standalone backend over WebSocket.

### Live mode (single process)

```bash
poetry run LevityDash
# or
poetry run python -m LevityDash
```

### Remote mode (two processes)

Start the headless backend first:

```bash
poetry run LevityDash-backend
# or
poetry run python -m LevityDash.backend
```

Then set the frontend to attach to it. This is done in the config file (`config.ini`, `[Backend]` section):

```ini
[Backend]
mode = remote
```

Now launch the frontend normally — it connects to the backend and renders the dashboard:

```bash
poetry run LevityDash
```

The backend serves all five built-in plugins (OpenMeteo, PirateWeather, WeatherFlow, Govee BLE, OpenWeatherMap) and pushes realtime updates to any number of frontends.

### Other commands

To start over with a fresh configuration:

```bash
poetry run LevityDash-reset-config
```

## Running on ARM  <!-- {docsify-ignore} -->

PySide6 ships prebuilt ARM64 wheels (macOS universal2 and, in recent releases, Linux aarch64), so a 64-bit OS — e.g. Raspberry Pi OS 64-bit — installs like any other platform. 32-bit ARM is not supported by Qt 6.

## Config/Setup  <!-- {docsify-ignore} -->

On first run, LevityDash will create a configuration from the default settings and guess your location based on your IP address.
The default dashboard only uses data provided by Open-Meteo since it does not require authentication.

You can enable more sources/plugins by providing API keys and enabling them in their respective config files. See [here](/config/plugins.md) for more in-depth information

> [!WARNING]
> The current drag and drop implementation can be a bit funky at times so it is recommended to edit the dashboard file directly. Additionally, not all of the customization functionality is currently available from the GUI.
>
>More information can be found [here](/config/dashboard.md).

Once LevityDash is up and running, you can start rearranging and resizing the modules along with adding more by clicking on the **+** that appears when you hover over
the top left corner.
The data menu is organized by source and categories.
Once you find a module you want to use, you can click and hold until it pops out and place it anywhere on the dashboard.

> [!TIP]
> You can open up the config folder from the file menu.

## Common Issues <!-- {docsify-ignore} -->

### Unsupported Python Version

LevityDash requires Python 3.13 or newer (up to 3.14). If your OS ships an older Python, [pyenv](https://realpython.com/intro-to-pyenv/) is the easiest way to install a newer one alongside it.

### macOS Bluetooth Permission

If the Govee BLE plugin is enabled, macOS requires the *launching* application (your terminal) to have Bluetooth permission — without it the app is killed with an abort on startup. Grant it under **System Settings → Privacy & Security → Bluetooth**, or disable the Govee plugin.

### Unable to load QPA Platform Plugin

Essentially, with the transition from X11 to Wayland, Qt can get confused about the windowing system. When/if this
error occurs, it will list the available QPA Plugins. Once you have figured out the best plugin for your windowing system,
you have to set it with an environment flag. Note, xcb is the default which expects an X11 windowing system

```bash
export QT_QPA_PLATFORM=your_selection_here
```

## Compiling to an App  <!-- {docsify-ignore} -->

PyInstaller is used to build the app to a single file or a standalone executable. This flow has not been re-verified since the Python 3.14/Qt 6 migration, so expect to get your hands dirty.

```bash
git clone https://github.com/noblecloud/LevityDash.git
cd LevityDash
poetry install --with build-to-app
cd build-to-app
poetry run python build.py
```

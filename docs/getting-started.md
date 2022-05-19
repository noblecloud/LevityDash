# Getting Started

## Install

Installing LevityDash is easy with pip:

```bash
pip install LevityDash
```

## Running LevityDash

If you have your `PATH` set correctly, you can run it directly with:

```bash
LevityDash
```

Otherwise, it can be run as with the module flag:

```bash
python -m LevityDash
```

## Setup

On first run, LevityDash will create a configuration from the default settings and guess your location based on your IP address.
The default dashboard is only data provided by Open-Meteo since it does not require authentication.

You can provide API keys for the other sources in
the config which can be found in `~/.config/levity/plugins`

Once LevityDash is up and running, you can start rearranging and resizing the modules along with adding more by clicking on the **+**  that appears when you hover over
the top left corner.
The data menu is organized by source and categories.
Once you find a module you want to use, you can click and hold until it pops out and place it anywhere on the dashboard.

The current drag and drop implementation can be a bit funky at times so it is recommended to edit the dashboard config file directly. Saved dashboards are located in the `~/.config/levity/saves/dashboards` directory.

*Note: You can open up the config folder from the file menu.*

## Running on ARM

PySide2 does not have an ARM compatible module available in the PyPi repository, to fix this, you can either build the module yourself (See [here](https://github.com/piwheels/packages/issues/4#issuecomment-772058821) for more
information),
use
[piwheels.
org](https://piwheels.org/)
for non
64bit builds, or use your OS's package manager, which is recommended method.
Also,
PySide2 must be installed before installing LevityDash.

### Arch Linux

```bash
sudo pacman -S python-pyside2
```

### Debian

```bash
sudo apt-get install python3-pyside2
```

### Fedora

```bash
sudo dnf install python3-pyside2
```

## Compiling to an App

PyInstaller is used to build the app to a single file or a standalone executable. It is still in development, so it is not recommended for use.

```bash
git clone https://github.com/noblecloud/LevityDash.git
cd LevityDash
poetry install
cd build
poetry run python build.py
```

# Getting Started

## Install  <!-- {docsify-ignore} -->

Installing LevityDash is easy with pip:

```bash
pip install LevityDash
```

or update your current installation with:

```bash
pip install --upgrade LevityDash
```

## Running LevityDash  <!-- {docsify-ignore} -->

If you have your `PATH` set correctly, you can run it directly with:

```bash
LevityDash
```

Otherwise, it can be run as with the module flag:

```bash
python -m LevityDash
```

## Running on ARM  <!-- {docsify-ignore} -->

PySide2 does not have an ARM compatible module available in the PyPi repository, to fix this, you can either build the module yourself (See [here](https://github.com/piwheels/packages/issues/4#issuecomment-772058821) for more information),
use [piwheels.org](https://piwheels.org/) for non 64bit builds, or use your OS's package manager, which is recommended method. Also,
PySide2 must be installed before installing LevityDash.

<!-- tabs:start -->

### **Arch**

```bash
sudo pacman -S python-pyside2
```

### **Debian**

```bash
sudo apt-get install python3-pyside2
```

### **Fedora**

```bash
sudo dnf install python3-pyside2
```

<!-- tabs:end -->

## Config/Setup  <!-- {docsify-ignore} -->

On first run, LevityDash will create a configuration from the default settings and guess your location based on your IP address.
The default dashboard is only data provided by Open-Meteo since it does not require authentication.

You can enable more sources/plugins by providing API keys and enabling them in their respective config files. See [here](/plugin_config.md) for more in-depth information

> [!WARNING]
> The current drag and drop implementation can be a bit funky at times so it is recommended to edit the dashboard file directly. Additionally, not all of the customization functionality is currently available from the GUI.
>
>More information can be found [here](/dashboard.md).

Once LevityDash is up and running, you can start rearranging and resizing the modules along with adding more by clicking on the **+** that appears when you hover over
the top left corner.
The data menu is organized by source and categories.
Once you find a module you want to use, you can click and hold until it pops out and place it anywhere on the dashboard.

> [!TIP]
> You can open up the config folder from the file menu.

## Common Issues <!-- {docsify-ignore} -->

### Missing the Qt5 Runtime

The Qt5 runtime must be installed for LevityDash to run, if PySide2 was installed with your OS's package manager rather than pip, it should already be installed.
If not, you can install it with:
<!-- tabs:start -->

### **Arch**

```bash
sudo pacman -S qt5
```

### **Debian/Ubuntu/Mint/...**

```bash
sudo apt-get install qt5-default
```

### **Fedora**

```bash
sudo dnf install qt5-qtbase
```

<!-- tabs:end -->

### Unsupported Preinstalled Python Version

LevityDash is not compatible with Python 3.10. Despite 3.10 being released over 8 months ago, it seems most OS's still
come with Python some version of 3.9 or even 3.8. Python 3.10 can be downloaded directly from https://python.org, but
I've found pyenv to be the best way to install another version of Python. RealPython.com has a great article about it
pyenv [here](https://realpython.com/intro-to-pyenv/).

### Unable to load QPA Platform Plugin

Essentially, with the transition from X11 to Wayland, Qt can get confused about the windowing system. When/if this
error occurs, it will list the available QPA Plugins. Once you have figured out the best plugin for your windowing system,
you have to set it with an environment flag. Note, xcb is the default which expects an X11 windowing system

```bash
export QT_QPA_PLATFORM=your_selection_here
```

## Compiling to an App  <!-- {docsify-ignore} -->

PyInstaller is used to build the app to a single file or a standalone executable. It is still in development, so it is not recommended for use.

```bash
git clone https://github.com/noblecloud/LevityDash.git
cd LevityDash
poetry install
cd build
poetry run python build.py
```
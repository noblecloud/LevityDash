
There are a few common issues that you may run into when installing LevityDash. A few of the most common ones are listed below. If you run into an issue that is not listed here, please check the [Bug Reports]() page.

### Missing the Qt5 Runtime



### Unsupported Preinstalled Python Version

LevityDash is only compatible with Python 3.10 and newer.  Python 3.10 can be downloaded directly from https://python.org, but
I've found pyenv to be the best way to install another version of Python. RealPython.com has a great article about it
pyenv [here](https://realpython.com/intro-to-pyenv/).

### Unable to load QPA Platform Plugin

Essentially, with the transition from X11 to Wayland, Qt can get confused about the windowing system. When/if this
error occurs, it will list the available QPA Plugins. Once you have figured out the best plugin for your windowing system,
you have to set it with an environment flag. Note, xcb is the default which expects an X11 windowing system

```bash
export QT_QPA_PLATFORM=your_selection_here
```

There are a few common issues that you may run into when installing LevityDash. A few of the most common ones are listed below. If you run into an issue that is not listed here, please check the [Bug Reports]() page.

### Missing the Qt5 Runtime



### Unsupported Preinstalled Python Version

LevityDash requires Python 3.13–3.14 (3.14 recommended).  Python can be downloaded directly from https://python.org, but
I've found pyenv to be the best way to install another version of Python. RealPython.com has a great article about it
pyenv [here](https://realpython.com/intro-to-pyenv/).

### Unable to load QPA Platform Plugin

Essentially, with the transition from X11 to Wayland, Qt can get confused about the windowing system. When/if this
error occurs, it will list the available QPA Plugins. Once you have figured out the best plugin for your windowing system,
you have to set it with an environment flag. Note, xcb is the default which expects an X11 windowing system

```bash
export QT_QPA_PLATFORM=your_selection_here
```

### When an item fails to load

> [!NOTE]
> **Pending** ([#30](https://github.com/noblecloud/LevityDash/pull/30)). Before this change, one item that failed stopped the whole dashboard from loading.

If one item in a dashboard cannot load, LevityDash shows a red tile in its place. The tile has the size and position of the item. The rest of the dashboard loads as usual.

The tile shows the type of the item, or its key, and the first line of the error. Point at the tile to see the full text.

For example, a color that names a token that does not exist, such as `$acent`, gives this tile:

```yaml
- type: text
  text: Typo in a color
  color: $acent
  geometry: {x: 33%, y: 0%, width: 33%, height: 100%}
```

The tile says that the theme has no token `$acent` and lists the tokens that it has.

- The log has the full error with the traceback. Search it for `Item failed to load`.
- LevityDash does not save a dashboard while an error tile is on it. A save would write the tile out as nothing and remove the item from the file. Fix the item, then reload with `Ctrl+R`.

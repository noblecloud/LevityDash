> [!NOTE]
> This is the raw idea list. The organized, triaged version lives in [roadmap.md](roadmap.md) — every item here is placed, marked done, or parked there.

- conditional dashboards
- conditional Panels
- scrolling in overfilled stacks
- graph Y axis labeling
- proper device filtering for Govee ble plugin
- watch dogs for plugins
- dashboard level config options that override global config
- menu option to change log level for status bar updates
- menu option to change log level
- proper log names for all modules
- ability to use positions of other items for item positioning ie, center this item with the center of that item
- add delay or block signals for parent resized when loading
- carousel style direction display [w N e]
- value templates that are loaded from a file that combine multiple values
- string plots can be assigned a second key for plotting placement
- more than one plot can position match a key and with offsets can produce a little forcast infographic
- filter functions that can be filtered values by key, functions are added to a list or a hash map

- items menu that shows a little summery with a two-day graph of the item
- keys that can also include a source

- global colors that can be linked to a value gradient map

- conditional panels based on plugin status
- plugins with included templates

- size screen conditions for size options

# Replace indoor temperature with wind box

- add option to keep awake
  - macos
    - caffinate process
  - linux
    - xdg-screensaver
    - systemd-inhibit
  - windows
    - powercfg
    - SetThreadExecutionState
  - non-platform-specific
    - move mouse

- add option to condense titles
  - possibly by size

- fill object
  - accepts: 
    - colors
    - gradients
    - images
    - patterns
  - colors can be provided a gradient and a dynamic color function that changes the color based on a value
  - can be divided into sections with plot line
- 
- corner radius

Add past hour graph to wind section

- use named presets instead of shared

- add live value smoothing to plugin scheme

stateful prep_init 

AnyIO 

I think something in graph is not on the proper thread

#############
Consider making graph annotations an -item instead of a attr 

Cache graph renders

WeatherUnits get conversion factor

Pickle all items on close and load them on start and update with yaml state

# Self installer
- install python
  - [debian](https://github.com/tvdsluijs/sh-python-installer/blob/main/python.sh)

# Milestones
- Persistent data
- Truly separate processes for plugins


- proper network failure handling
- proper network recovery handling

- https://docs.python.org/3.10/library/asyncio-eventloop.html#asyncio.loop.shutdown_asyncgens

- look into setting source from context menu on with graph items

- Duo tone/color icons
- implement \_\_reduce\_\_ for all classes
  - https://github.com/uqfoundation/dill
  - https://marshmallow.readthedocs.io/en/stable/index.html
- event notifications
- data storage
- https://pypi.org/project/redis/
- https://pypi.org/project/keyring/
- check out sidekick https://plugins.jetbrains.com/plugin/20031-sidekick

- named object accessors

- add color list from rich https://rich.readthedocs.io/en/stable/appendix/colors.html

groups should assume a grid or stack unless specified.
an item's geometry overrieds if set' 

better regex https://github.com/mrabarnett/mrab-regex

replace MeasurementTimeSeries with https://grantjenks.com/docs/sortedcontainers/sorteddict.html

compare appdirs with platformdirs https://pypi.org/project/platformdirs/

look into https://pyparsing-docs.readthedocs.io/en/latest/whats_new_in_3_0_0.html\
Used for tokenizing and parsing strings

fix refresh handles that is possibly iterating through every child on every call by accessing the self.allHandles property (this is probably fixed)

# Test Bluetooth unavailable

# Store entire layout in a separate file

# Fonts
- https://www.fontsquirrel.com/fonts/arvo
- https://www.fontsquirrel.com/fonts/suprema
- https://nationalparktypeface.com
- https://www.fontsquirrel.com/fonts/tenso-slab
- Swiss 721
- https://www.fontshop.com/families/ff-din-round
- https://www.reddit.com/r/fonts/comments/c75a2e/font_similar_to_apple_sf_rounded/

## Build

### GitHub Actions
https://data-dive.com/multi-os-deployment-in-cloud-using-pyinstaller-and-github-actions


### Stateful

StateProperties that return another Stateful object should not need a setter and getter, just a factory and an update method
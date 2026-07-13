# LevityDash Basic Comprehension Check (Tier 0)

You are being evaluated as a potential AI assistant for a software project. Everything you need is in this document — read the material in each item and answer the questions about it. Be concrete and specific. Expected effort: 10–15 minutes.

---

## Item 0.1 — What is this project?

Here is the project's description and a summary of its source layout:

> LevityDash aims to be a lightweight, desktop native, multi-source dashboard without a required web frontend that is fun and easy to use. The current frontend is built on PySide6/Qt 6. A key goal of this project is to support multiple frontends and platforms, including embedded — it can easily be deployed on a Raspberry Pi or similar single board computer.
>
> Backend features: plugin system for adding new data sources (REST APIs, sockets, BLE sensors), scheduled API polling, data/key maps for automatically parsing ingested data, a unit library for automatic conversion/localization. Built-in plugins: Open-Meteo, PirateWeather, WeatherFlow Tempest, Govee BLE thermometers, OpenWeatherMap.
>
> Frontend features: drag-and-drop dashboard design, YAML-based dashboard layout files, resizable graph figures with value-mapped gradients, text/gauge/graph/clock/moon-phase display modules.

```
src/
  qolkit/      generic Python utilities — no domain or Qt coupling
  statekit/    declarative state + YAML persistence — Qt-free
  LevityDash/  the app
    lib/plugins/               data layer: plugins, schemas, dispatcher
    lib/ui/frontends/PySide/   the Qt frontend
```

**Questions:**
1. In one or two sentences: what is this software, and what would a person use it for?
2. What kind of data does it primarily display, based on the built-in plugins?
3. Suggest **one** feature or improvement that is not already mentioned above. One sentence is enough — it just has to make sense for this specific kind of software.

## Item 0.2 — Explain these functions

```python
def startTimerSafe(timer: QTimer, msec: int = None):
	if QThread.currentThread() is timer.thread():
		timer.start() if msec is None else timer.start(msec)
	elif msec is None:
		QtCore.QMetaObject.invokeMethod(timer, 'start', Qt.ConnectionType.QueuedConnection)
	else:
		QtCore.QMetaObject.invokeMethod(
			timer, 'start', Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(int, msec)
		)


def stopTimerSafe(timer: QTimer):
	if QThread.currentThread() is timer.thread():
		timer.stop()
	else:
		QtCore.QMetaObject.invokeMethod(timer, 'stop', Qt.ConnectionType.QueuedConnection)
```

**Questions:**
1. What do these functions do, in plain language?
2. Under what condition is the `elif`/`else` path taken instead of the direct call?
3. Why would a program need these instead of just calling `timer.start()` directly?

## Item 0.3 — Explain this class

```python
class IgnoreOr(object):

	def __init__(self, name: str):
		self.__name__ = name

	def __repr__(self):
		return f'<{self.__name__}>'

	def __or__(self, other):
		return other

	def __ror__(self, other):
		return other

	def __bool__(self):
		return False

	def __eq__(self, other):
		return self is other

	def __hash__(self):
		return hash((self.__name__, type(self)))

	def get(self, *args, **kwargs):
		return self


Unset = IgnoreOr('Unset')
```

**Questions:**
1. What is this class for? What general programming pattern is it?
2. What does `Unset | 5` evaluate to? What does `5 | Unset` evaluate to? Why?
3. Why does `.get()` return `self` — what does that let you do with an `Unset` value?

## Item 0.4 — What does this config produce?

This is an excerpt from one of the project's YAML dashboard layout files:

```yaml
- type: clock
  frozen: true
  geometry:
    height: 22.2%
    width: 36.5%
    x: 0%
    y: 1.6%
  items:
    - format: '%A, %B %-d'
      alignment: CenterRight
      filters:
        - 0Add Ordinal
    - format: '%-I:%M'
      alignment: CenterRight
    - type: moon
      glowStrength: 2
      interval:
        minutes: 20
    - format: '%p'
      filters:
        - 1Lower
```

**Questions:**
1. Describe what a user sees on screen from this block — what is it, where on the screen is it, and what are its four parts? (The `format` strings are standard `strftime` codes.)
2. Give one concrete example of what the first item would display for a real date.
3. What do you think `frozen: true` does, given this is a drag-and-drop dashboard?

---

*End of Tier 0. Total: 12 points (3 per item).*

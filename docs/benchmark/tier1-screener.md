# LevityDash Candidate Screener (Tier 1)

You are being evaluated as a potential AI contributor to **LevityDash**, a desktop-native, multi-source weather dashboard written in Python. The frontend is Qt (PySide6) built on a QGraphicsScene; the data layer is plugin-driven (REST/socket/BLE weather sources feeding a schema engine that maps raw API data to typed, unit-aware values). The codebase is beta but used daily, and it is dense with threading rules and conventions.

This screener is self-contained — everything you need is in this document. Answer in plain prose (code allowed where useful). Be specific; vague answers score zero. Expected effort: about 30 minutes.

---

## Section A — Working knowledge (6 questions, 2 points each)

**A1.** At startup the console sometimes prints:

```
QBasicTimer::start: Timers cannot be started from another thread
```

What has actually happened to the timer that triggered this warning — does it fire late, fire immediately, or never fire? Name two standard remedies for the underlying problem.

**A2.** The repo contains three Python packages with a strict dependency direction:

```
qolkit    — generic Python utilities, zero domain/Qt coupling
statekit  — declarative state + YAML persistence, Qt-free, depends only on qolkit
LevityDash — the app (Qt frontend, plugins), depends on both
```

Additionally, app code that needs `statekit`'s classes is expected to import them via a thin facade module inside the app (`LevityDash/lib/stateful.py`) rather than from `statekit` directly. For each of the following imports, say whether it is allowed, and if not, why:

1. `from PySide6.QtCore import QTimer` — inside a `statekit` module
2. `from LevityDash.lib.utils import clearCacheAttr` — inside a `statekit` module
3. `from statekit.core import StateProperty` — inside a LevityDash UI module
4. `from qolkit import DeepChainMap` — inside a `statekit` module

**A3.** Dashboard layouts are persisted to YAML through a declarative state system: each `StateProperty` may define an `.encode` hook that converts the live value into what gets written to the file. Suppose a property's `.encode` accidentally returns a `DeepChainMap` (a custom mapping type) instead of a plain `dict`. Nothing raises at save time. What actually ends up in the YAML file, and what is the consequence?

**A4.** A user edits their dashboard YAML and writes:

```yaml
plot:
  color: #C0FFEE
```

Their plot color silently breaks. Why, and what is the conventional way to write hex colors in this project's YAML files?

**A5.** The test suite's `conftest.py` begins like this, **above all other imports**:

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LEVITYDASH_CONFIG_DEBUG", "1")
```

Why must these two environment variables be set at module top level before anything else is imported, rather than inside a pytest fixture?

**A6.** The observation layer can auto-derive missing values — e.g., if a weather source provides temperature and humidity but no dewpoint, it computes dewpoint itself and inserts it as if the source had provided it. Before inserting a derived value under a key, what must the plugin's schema contain for that key, and what class of failure occurs if it doesn't?

---

## Section B — Find the bug (4 snippets, 5 points each)

Each snippet below is **real code from this repository's history** containing exactly one bug that was later found and fixed. For each: **(a)** identify the defect precisely (3 pts), **(b)** describe the trigger and consequence — what has to happen for it to misbehave, and what the misbehavior looks like (1 pt), **(c)** give the minimal correct fix (1 pt).

### B1

Context: `ScheduledEvent` schedules recurring plugin work (API polls, retries). Every plugin runs on its own real `threading.Thread`, and each plugin constructs several `ScheduledEvent`s during startup. `instances` is shared by all of them. A rare crash was chased for days; it only ever reproduced when plugins were started through their real thread path, never when a single plugin was driven directly on the main thread.

```python
class ScheduledEvent(object):
	instances: ClassVar[dict['Plugin', ['ScheduledEvent']]] = {}

	def __init__(self, interval, func, ...):
		...
		self.__owner = func.__self__
		if self.__owner in self.instances:
			self.instances[self.__owner].append(self)
		else:
			self.instances[self.__owner] = [self]
		self.__func = func
		...
```

### B2

Context: `LevityConfig` subclasses `configparser.ConfigParser`. `getOrSet` reads a key from a section, writing the default back if missing. `self[section]` returns a `SectionProxy` object.

```python
def getOrSet(self, section: str, key: str, default: str, getter: Callable | None = None) -> str:
	try:
		if section == self.default_section:
			section = self._proxies[self.default_section]
		else:
			section = self[section]
	except KeyError:
		self.add_section(section)

	if getter == self.getboolean or getter == bool:
		if (value := section.getboolean(key)) is None:
			section[key] = str(default)
			self.save()
			return default
		return value
	...
	try:
		value = section[key]
	except KeyError:
		section[key] = value = str(default)
		self.save()
	if getter is not None:
		return getter(value)
	return value
```

### B3

Context: the schema engine's key lookup. When an exact key isn't found, it fuzzy-matches against all known source keys and recurses on the closest match. `get_close_matches(word, possibilities, n, cutoff)` is `difflib`'s standard function.

```python
metaData = self.getExact(key)
if metaData is None:
	keys = [str(key) for k in self._source.keys()]
	closestMatch = get_close_matches(str(key), keys, n=1, cutoff=0.5)
	if closestMatch:
		log.warning(f'{key} was not found in {self} but {closestMatch[0]} was found as it\'s closest match')
		return self.getUnitMetaData(closestMatch[0], source)
	else:
		log.warning(f'{key} was not found in {self}')
		return None
return metaData
```

### B4

Context: the wire codec deserializes measurements sent between backend and frontend. `Measurement.timestamp` is a **read-only property** backed by a private `_timestamp` attribute. `ts` is an ISO 8601 string or None.

```python
def decode_measurement(payload: dict) -> Measurement | float:
	cls = _resolve_measurement_class(payload.get('cls'), payload.get('unit'))
	value = payload['value']
	if cls is None:
		return value
	measurement = cls(value)
	ts = payload.get('ts')
	if ts and hasattr(measurement, 'timestamp'):
		try:
			measurement.timestamp = datetime.fromisoformat(ts)
		except (ValueError, AttributeError):
			pass
	return measurement
```

---

*End of Tier 1. Total: 32 points.*

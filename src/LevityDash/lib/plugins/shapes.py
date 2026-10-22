"""The shape of a value: what kind of thing a key holds, apart from its unit and its name.

The set is closed. A schema entry says `shape:` with one of these, or leaves it out and the shape
comes from its `sourceUnit` (and `type`).

| Shape    | Holds                                              | Examples                                   |
|----------|----------------------------------------------------|--------------------------------------------|
| `number` | a number with a unit                               | temperature, wind speed, a battery level   |
| `enum`   | one of a fixed set of values                       | a condition icon, a health concern, on/off |
| `text`   | free text                                          | a forecast summary, a time zone name       |
| `time`   | a point in time                                    | sunrise, the last lightning strike         |
| `list`   | several values of one shape (reserved)             | a process table, a calendar                |
| `point`  | a place on the map (reserved)                      | a phone's position                         |

Numbers and enums are the shapes the rest of LevityDash is built around. `text` and `time` are named
because plugins already publish them. `list` and `point` are reserved: a schema may name them, and
the entry is kept, but nothing reads a list or a point yet.

Qt-free, so a tool can ask without booting the app.
"""
import logging
from typing import Any, Iterable, Optional, Tuple

__all__ = ['CLOSED', 'RESERVED', 'SHAPES', 'choicesOf', 'shapeOf']

log = logging.getLogger('LevityDash.shapes')

#: Every shape there is.
SHAPES: Tuple[str, ...] = ('number', 'enum', 'text', 'time', 'list', 'point')
#: Shapes that nothing reads yet.
RESERVED: Tuple[str, ...] = ('list', 'point')
#: Alias kept so a caller reads as a question: is this one of the shapes?
CLOSED = frozenset(SHAPES)

_TEXT_UNITS = frozenset({'str', 'timezone', 'tz'})
_TIME_UNITS = frozenset({'date', 'datetime', 'epoch', 'ISO8601'})
_ENUM_UNITS = frozenset({'bool', 'PrimaryPollutant', 'AQIHC', 'WeatherCode'})
_ENUM_TYPES = frozenset({'icon'})

_warned: set = set()


def _warnOnce(message: str) -> None:
	if message not in _warned:
		_warned.add(message)
		log.warning(message)


def shapeOf(entry: Any) -> str:
	"""The shape of a schema entry (a mapping with `shape`, `sourceUnit` and `type` as they are written).

	An explicit `shape:` wins. A name that is not in `SHAPES` is logged and ignored.
	"""
	get = entry.get if hasattr(entry, 'get') else (lambda name, default=None: default)
	if (declared := get('shape', None)) is not None:
		if declared in CLOSED:
			if declared in RESERVED:
				_warnOnce(f'shape {declared!r} is reserved: the entry is kept, but nothing reads it yet')
			return declared
		_warnOnce(f'{declared!r} is not a shape ({", ".join(SHAPES)}); using the one the unit gives')
	unit = get('sourceUnit', None)
	if isinstance(unit, str):
		if unit in _TEXT_UNITS:
			return 'text'
		if unit in _TIME_UNITS:
			return 'time'
		if unit in _ENUM_UNITS:
			return 'enum'
	if get('type', None) in _ENUM_TYPES:
		return 'enum'
	return 'number'


def choicesOf(entry: Any) -> Optional[Tuple[Any, ...]]:
	"""The values an `enum` entry can take, when the schema says: `choices: [...]`, or on and off for a `bool`. None when it does not."""
	get = entry.get if hasattr(entry, 'get') else (lambda name, default=None: default)
	if shapeOf(entry) != 'enum':
		return None
	declared: Optional[Iterable[Any]] = get('choices', None)
	if declared is not None:
		return tuple(declared)
	if get('sourceUnit', None) == 'bool':
		return (False, True)
	return None

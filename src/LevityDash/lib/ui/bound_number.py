"""A number that follows a value: ``opacity: {of: <key or expression>, from: [0, 100], to: [0.2, 1]}``.

Any numeric property may be written as a mapping in place of its number. ``of`` is read as a ``.levity`` value
source (``lib/valuesource.py``), so it may be an expression. The reading is placed on the ``from`` range and the
property takes the matching point of the ``to`` range, in a straight line. The ends of ``from`` may carry units
(``from: [32°F, 99°F]``), and are then converted to whatever unit the value arrives in, as gradient stops are.
The setting stays inside ``to`` unless ``clamp: false``. A value with no number yet leaves the ``fallback``, else
the number the item already had::

	opacity: {of: environment.humidity.humidity, from: [0, 100], to: [0.25, 1]}
	opacity: {of: system.cpu.load, from: [0.5, 1.0], to: [0, 1], fallback: 1}

This is the number counterpart of a colour that follows a value (``colors/bound.py``); both share
``follow.py``.
"""
from typing import Any, Callable, Mapping, Optional

from unitcorn import Measurement

from LevityDash.lib.stopunits import parseStop, toDataUnit
from LevityDash.lib.ui.follow import Followers, ValueFollower

__all__ = ('BoundNumber', 'NumberSlots', 'decodeNumber', 'isBound')

KEYS = frozenset({'of', 'from', 'to', 'clamp', 'fallback'})


def isBound(spec: Any) -> bool:
	"""A mapping with ``of``, ``from`` and ``to``: a number that follows a value."""
	return isinstance(spec, Mapping) and 'of' in spec and 'from' in spec and 'to' in spec


def _number(raw: Any, name: str) -> float:
	if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw != raw or raw in (float('inf'), float('-inf')):
		raise TypeError(f'{name} must be a finite number, not {raw!r}')
	return float(raw)


def _end(raw: Any, name: str) -> tuple[float, Optional[str]]:
	"""One end of ``from``: a number, or a measured number (``99°F``)."""
	if isinstance(raw, str):
		if (parsed := parseStop(raw)) is None:
			raise ValueError(f'{name} {raw!r} is not a number with an optional unit')
		return float(parsed[0]), parsed[1]
	return _number(raw, name), None


def _pair(raw: Any, name: str) -> list:
	if isinstance(raw, (str, bytes)) or not hasattr(raw, '__len__') or len(raw) != 2:
		raise ValueError(f'{name} is two values, low then high, not {raw!r}')
	return list(raw)


class BoundNumber:
	"""The decoded form of a bound number: where the value comes from and how it becomes a number."""

	__slots__ = ('spec', 'of', 'low', 'high', 'start', 'stop', 'clamp', 'fallback')

	def __init__(self, spec: Mapping):
		unknown = set(spec) - KEYS
		if unknown:
			raise ValueError(f'a bound number has of, from, to, clamp and fallback, not {", ".join(sorted(map(str, unknown)))}')
		of = spec['of']
		if isinstance(of, bool) or not isinstance(of, (str, int, float)):
			raise TypeError(f'of must be a key or an expression, not {of!r}')
		self.spec = dict(spec)
		self.of = of
		self.low, self.high = (_end(v, 'from') for v in _pair(spec['from'], 'from'))
		if self.low[0] == self.high[0]:
			raise ValueError(f'from {spec["from"]!r} has the same value at both ends')
		self.start, self.stop = (_number(v, 'to') for v in _pair(spec['to'], 'to'))
		clamp = spec.get('clamp', True)
		if not isinstance(clamp, bool):
			raise TypeError(f'clamp must be true or false, not {clamp!r}')
		self.clamp = clamp
		self.fallback = None if spec.get('fallback') is None else _number(spec['fallback'], 'fallback')

	def numberFor(self, value: Any) -> Optional[float]:
		"""The setting at ``value``, or None when it has no number to place."""
		if isinstance(value, bool) or value is None:
			return None
		try:
			if isinstance(value, Measurement):
				a, b = (toDataUnit(n, unit, type(value)) if unit else n for n, unit in (self.low, self.high))
				x = float(value)
			else:
				a, b = self.low[0], self.high[0]
				x = float(value)
		except (TypeError, ValueError):
			return None
		if a == b or x != x:
			return None
		t = (x - a) / (b - a)
		if self.clamp:
			t = min(1.0, max(0.0, t))
		return self.start + t * (self.stop - self.start)

	resolve = numberFor

	def __repr__(self):
		return f'BoundNumber({self.spec!r})'


def decodeNumber(spec: Any, plain: Callable[[Any], Any]) -> Any:
	"""``plain(spec)``, except that an ``{of, from, to}`` mapping gives a `BoundNumber`. For a StateProperty decoder."""
	return BoundNumber(spec) if isBound(spec) else plain(spec)


class NumberSlots(Followers):
	"""The bound numbers of one item, behind one door for every numeric StateProperty.

	A property keeps its number in an attribute. Its setter calls ``assign`` with what the decoder returned, its
	getter returns ``current(...)`` (the bound spec while one is followed, else the plain value) and its encoder
	``spec`` writes it back::

		@opacity.setter
		def opacity(self, value):
			self.numbers.assign(self, 'opacity', value, self.setOpacity)

	``store`` takes a plain value; ``convert`` turns each followed number into what ``store`` takes (a relative
	size, say); ``then`` runs after every change a followed value makes (a redraw).
	"""

	def __init__(self, label: str = 'number'):
		super().__init__()
		self._label = label
		self._bound: dict[Any, BoundNumber] = {}

	def assign(self, owner: Any, name: Any, value: Any, store: Callable[[Any], None],
	           convert: Callable[[float], Any] = float, then: Optional[Callable[[], None]] = None) -> None:
		"""Keep ``value`` (what a decoder returned): store it, or follow it if it is a `BoundNumber`."""
		key = (owner, name)
		if not isinstance(value, BoundNumber):
			self._bound.pop(key, None)
			self._release(owner, name)
			store(value)
			return
		self._bound[key] = value

		def apply(number: float) -> None:
			store(convert(number))
			if then is not None:
				then()

		self._attach(owner, name, ValueFollower(value, apply, f'{self._label} {name}'))
		if value.fallback is not None:
			store(convert(value.fallback))

	def current(self, owner: Any, name: Any, plain: Any) -> Any:
		"""For a getter: the bound spec while one is followed, else ``plain``."""
		return self._bound.get((owner, name), plain)

	@staticmethod
	def spec(value: Any) -> Any:
		"""For an encoder: the mapping of a bound number, else the value as it is."""
		return dict(value.spec) if isinstance(value, BoundNumber) else value

	def release(self, owner: Any = None) -> None:
		super().release(owner)
		for key in [k for k in self._bound if k[0] is owner]:
			del self._bound[key]

	def releaseAll(self) -> None:
		super().releaseAll()
		self._bound.clear()

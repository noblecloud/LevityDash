"""A label's variable-font axes that follow its own value: hot reads round and heavy, cold sharp and lean.

``font-axes`` on a ``label`` (and on a ``valueLabel``, so it cascades through ``shared:``) maps the value the label
shows onto the axes of a variable font. ``range`` is the span of the value that is mapped; each axis gives the setting
at the low end and at the high end of it, and takes a straight line between::

	font: Allo
	font-axes:
	  range: [20°F, 95°F]
	  wght: [500, 800]
	  ROND: [0, 100]

An axis may also be a number (held fixed, ``opsz: 32``) or a mapping ``{from, to, range}`` with a ``range`` of its own.
The ends of a ``range`` may carry units (as gradient stops do) and are converted to whatever unit the value arrives
in. The value is clamped to the range unless ``clamp: false``. A value with no number (text, empty) leaves the font's
own settings, or the ``fallback`` mapping if there is one (``fallback: {wght: 500, ROND: 50}``).

``corner`` is not a font axis but a treatment of the outlines, so it works with any font: the radius, in em, that
every convex corner and end of a stroke is rounded to. The text is drawn with a round-join pen twice that wide, and the
font's ``wght`` is lowered by as much, so the weight asked for is the weight drawn. A font's own ``ROND`` moves little
on most digits (an 8 not at all), so ``corner: [0, 0.05]`` is what makes hot read round and cold hard. About 0.05 is the
most a bold figure takes before its counters close.

Names: the four-letter tag of the font (``wght``, ``ROND``, ``opsz``, ``wdth``, ``slnt``, ...) or ``weight``,
``round`` / ``roundness``, ``optical-size``, ``width``, ``slant``. Qt-free: `FontAxes.resolve(value)` returns
``{tag: setting}``; `Text.font()` applies the four-letter ones with ``QFont.setVariableAxis`` (Qt 6.7+) and
`Text._applyCorner` the ``corner``.
"""
from typing import Any, Mapping, Optional

from unitcorn import Measurement

from LevityDash.lib.stopunits import toDataUnit
from LevityDash.lib.ui.bound_number import _end, _number, _pair

__all__ = ('FontAxes', 'decodeFontAxes')

ALIASES = {
	'weight':       'wght',
	'round':        'ROND',
	'roundness':    'ROND',
	'rond':         'ROND',
	'optical-size': 'opsz',
	'opticalsize':  'opsz',
	'width':        'wdth',
	'slant':        'slnt',
	'corner':       'corner',
	'corners':      'corner',
	'corner-radius': 'corner',
}
CORNER = 'corner'
OPTIONS = frozenset({'range', 'clamp', 'fallback'})


def _tag(name: Any) -> str:
	key = str(name).strip()
	tag = ALIASES.get(key.lower().replace('_', '-'), key)
	if tag != CORNER and (len(tag) != 4 or not tag.isascii()):
		raise ValueError(f'{name!r} is not a font axis: use its four-letter tag (wght, ROND, opsz...) or weight, round, optical-size, width, slant')
	return tag


class _Axis:
	"""One axis: held at ``fixed``, or ``start`` to ``stop`` over its own range (else the shared one)."""

	__slots__ = ('tag', 'fixed', 'start', 'stop', 'range')

	def __init__(self, tag: str, spec: Any):
		self.tag = tag
		self.fixed = self.start = self.stop = self.range = None
		if isinstance(spec, bool):
			raise TypeError(f'{tag} must be a number, [from, to] or {{from, to}}, not {spec!r}')
		if isinstance(spec, (int, float)):
			self.fixed = _number(spec, tag)
		elif isinstance(spec, Mapping):
			unknown = set(spec) - {'from', 'to', 'range'}
			if unknown or 'from' not in spec or 'to' not in spec:
				raise ValueError(f'{tag} takes from, to and an optional range, not {sorted(map(str, spec))}')
			self.start, self.stop = _number(spec['from'], f'{tag} from'), _number(spec['to'], f'{tag} to')
			if spec.get('range') is not None:
				self.range = _range(spec['range'], f'{tag} range')
		else:
			start, stop = _pair(spec, tag)
			self.start, self.stop = _number(start, f'{tag} from'), _number(stop, f'{tag} to')


def _range(raw: Any, name: str) -> tuple:
	low, high = (_end(v, name) for v in _pair(raw, name))
	if low[0] == high[0]:
		raise ValueError(f'{name} {raw!r} has the same value at both ends')
	return low, high


class FontAxes:
	"""The decoded ``font-axes`` of a label."""

	__slots__ = ('spec', 'axes', 'range', 'clamp', 'fallback', '_ends')

	def __init__(self, spec: Mapping):
		self.spec = dict(spec)
		self.range = None
		self.clamp = True
		self.fallback = {}
		self.axes: list[_Axis] = []
		for name, raw in spec.items():
			if name == 'range':
				self.range = _range(raw, 'range')
			elif name == 'clamp':
				if not isinstance(raw, bool):
					raise TypeError(f'clamp must be true or false, not {raw!r}')
				self.clamp = raw
			elif name == 'fallback':
				if not isinstance(raw, Mapping):
					raise TypeError(f'fallback is a mapping of axis to setting, not {raw!r}')
				self.fallback = {_tag(k): _number(v, f'fallback {k}') for k, v in raw.items()}
			else:
				self.axes.append(_Axis(_tag(name), raw))
		if not self.axes:
			raise ValueError('font-axes needs at least one axis (wght, ROND, opsz...)')
		for axis in self.axes:
			if axis.fixed is None and axis.range is None and self.range is None:
				raise ValueError(f'{axis.tag} varies with the value, so it needs a range (on font-axes, or on {axis.tag})')
		self._ends: dict = {}

	def _position(self, x: float, value: Measurement | float, ends: tuple) -> Optional[float]:
		"""Where ``x`` falls on ``ends``, 0 to 1 (not clamped)."""
		low, high = ends
		key = (low, high, type(value) if isinstance(value, Measurement) else None)
		if (pair := self._ends.get(key)) is None:
			if isinstance(value, Measurement):
				pair = tuple(toDataUnit(n, unit, type(value)) if unit else n for n, unit in (low, high))
			else:
				pair = (low[0], high[0])
			self._ends[key] = pair
		a, b = pair
		return None if a == b else (x - a) / (b - a)

	def resolve(self, value: Any) -> dict[str, float]:
		"""``{axis tag: setting}`` for ``value``; the ``fallback`` when it has no number."""
		x = None
		if not isinstance(value, bool) and value is not None:
			try:
				x = float(value)
			except (TypeError, ValueError):
				x = None
		if x is None or x != x:
			return dict(self.fallback)
		out = {}
		for axis in self.axes:
			if axis.fixed is not None:
				out[axis.tag] = axis.fixed
				continue
			t = self._position(x, value, axis.range or self.range)
			if t is None:
				continue
			if self.clamp:
				t = min(1.0, max(0.0, t))
			out[axis.tag] = round(axis.start + t * (axis.stop - axis.start), 3)
		return out

	def __repr__(self):
		return f'FontAxes({self.spec!r})'


def decodeFontAxes(spec: Any) -> Optional[FontAxes]:
	"""For the StateProperty decoder: None/false for off, a `FontAxes` otherwise."""
	if spec in (None, False):
		return None
	if isinstance(spec, FontAxes):
		return spec
	if not isinstance(spec, Mapping):
		raise TypeError(f'font-axes is a mapping of axis to setting, not {spec!r}')
	return FontAxes(spec)

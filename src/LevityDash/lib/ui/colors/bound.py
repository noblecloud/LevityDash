"""A colour that follows a value: ``{scale: $temperature, of: <key or expression>}``.

A property that takes a colour (``color:`` of a text, a title, a value) may name a scale (a theme scale token, a
preset gradient or a gradient written in place) and a value source (a key or an expression). The colour is the
scale's colour at the value, and it changes when the value does. A static colour is the same property with a
colour written in it, so nothing else about the item changes::

	color: $accent                                                          # one colour
	color: {scale: $temperature, of: environment.temperature.feelsLike}     # the colour of a reading
	color: {scale: $load, of: system.cpu.load, fallback: $muted}            # $muted until there is a value

``of`` is read as a ``.levity`` value source (``lib/valuesource.py``), so it may be an expression, and a scale
with unit stops (``{32°F: ..., 99°F: ...}``) places each stop by reading, whatever unit the value is in. A scale
with bare stops uses the unit its gradient is written in (the temperature preset is in Celsius). A value with no
colour yet (the source has none, or it is not a number) leaves the ``fallback``, else the default colour.
"""
from typing import Any, Callable, Mapping, Optional

from unitcorn import Measurement

from LevityDash.lib.ui.colors import theme as _theme
from LevityDash.lib.ui.colors.color import Color
from LevityDash.lib.ui.colors.gradient import Gradient

__all__ = ('BoundColor', 'ColorFollower', 'ColorSlots', 'LiveColor', 'decodeColor', 'isBound')

KEYS = frozenset({'scale', 'of', 'fallback'})


def isBound(spec: Any) -> bool:
	"""A mapping with both ``scale`` and ``of``: a colour that follows a value."""
	return isinstance(spec, Mapping) and 'scale' in spec and 'of' in spec


class BoundColor:
	"""The decoded form of a bound colour: where the value comes from and how it becomes a colour."""

	__slots__ = ('spec', 'of', 'gradient', 'fallback')

	def __init__(self, spec: Mapping):
		unknown = set(spec) - KEYS
		if unknown:
			raise ValueError(f'a bound colour has scale, of and fallback, not {", ".join(sorted(map(str, unknown)))}')
		of = spec['of']
		if isinstance(of, bool) or not isinstance(of, (str, int, float)):
			raise TypeError(f'of must be a key or an expression, not {of!r}')
		self.spec = dict(spec)
		self.of = of
		scale = spec['scale']
		if isinstance(scale, str) and not _theme.is_token(scale) and scale not in Gradient.__presets__ and scale not in _theme.active().names('scales'):
			raise ValueError(f'unknown scale {scale!r}; Gradient would quietly pick the closest preset')
		self.gradient = Gradient.decode(scale)
		self.fallback = Color.decode(spec['fallback']) if spec.get('fallback') is not None else None

	def colorFor(self, value: Any) -> Optional[Color]:
		"""The colour at ``value``, or None when it has no number to place."""
		if isinstance(value, bool) or value is None:
			return None
		gradient = self.gradient
		try:
			if isinstance(value, Measurement) and gradient.hasUnits:
				gradient = gradient.resolve(type(value))
				if not len(gradient):
					return None
				number = float(value)
			else:
				stop = gradient.itemCls.__item__
				number = float(stop(value)) if isinstance(value, Measurement) and isinstance(stop, type) and issubclass(stop, Measurement) else float(value)
		except (TypeError, ValueError):
			return None
		return gradient.get_color_for_value(number)

	def __repr__(self):
		return f'BoundColor({self.spec!r})'


def decodeColor(spec) -> Color | BoundColor:
	"""``Color.decode``, except that a ``{scale, of}`` mapping gives a ``BoundColor``. One argument, as a StateProperty decoder is called."""
	return BoundColor(spec) if isBound(spec) else Color.decode(spec)


class ColorFollower:
	"""Holds a bound colour's value source and hands each new colour to ``apply`` (on the GUI thread).

	``close()`` releases the source. With no source, or before a value arrives, ``apply`` is not called: the item
	keeps the colour it was given (its fallback).
	"""

	def __init__(self, bound: BoundColor, apply: Callable[[Color], None], label: str = 'colour'):
		from LevityDash.lib.valuesource import openValueSource
		from LevityDash.lib.stateful import Binding

		self._bound = bound
		self._apply = apply
		self._binding = None
		if (source := openValueSource(bound.of, f'{label} value', 'it keeps its fallback colour')) is not None:
			self._binding = Binding(source, self._deliver)

	def _deliver(self, value: Any) -> None:
		color = self._bound.colorFor(value)
		if color is None:
			if self._bound.fallback is not None:
				self._apply(self._bound.fallback)
			return
		self._apply(color)

	def close(self) -> None:
		if self._binding is not None:
			self._binding.unlink()
			self._binding = None


class LiveColor:
	"""A colour setting that follows a value. Reads like a `Color` (``.QColor``), but the colour changes."""

	__slots__ = ('color', 'spec')

	def __init__(self, color: Color, spec: Mapping):
		self.color = color
		self.spec = dict(spec)

	@property
	def QColor(self):
		return self.color.QColor

	def __repr__(self):
		return f'LiveColor({self.spec!r})'


class ColorSlots:
	"""Every colour setting of one item, plain or following a value, behind one door.

	An item that paints in several colours (a gauge, a bar) reads each colour spec through here, so a spec that
	is a ``{scale, of}`` mapping follows its value wherever it was written, and no element has its own copy of
	that logic. ``slot(raw)`` is a ``Color`` for a plain spec and a ``LiveColor`` for a bound one; both give
	``.QColor``, so a painter keeps the slot and reads ``.QColor`` each time it paints. ``qcolor(raw)`` is the
	one-shot form for code that decodes from the raw spec while painting. A StateProperty keeps its colour with
	``adopt`` (from its decoded value) and writes it back with ``spec``.

	``owner`` groups the slots of one element, so a rebuilt element lets go of its own value sources with
	``release(owner)``. ``changed`` is called (on the GUI thread) after a followed colour changes.
	"""

	def __init__(self, changed: Callable[[], None], label: str = 'colour'):
		self._changed = changed
		self._label = label
		self._followers: dict[Any, dict[Any, ColorFollower]] = {}
		self._byKey: dict[str, 'Color | LiveColor'] = {}

	def _follow(self, bound: BoundColor, owner: Any, name: Any) -> LiveColor:
		live = LiveColor(bound.fallback or Color.default, bound.spec)

		def apply(color: Color) -> None:
			live.color = color
			self._changed()

		self._release(owner, name)
		self._followers.setdefault(owner, {})[name] = ColorFollower(bound, apply, self._label)
		return live

	def slot(self, raw: Any, owner: Any = None, name: Any = None) -> 'Color | LiveColor':
		"""The colour for a raw spec. Several slots of one ``owner`` need different ``name``s."""
		if not isBound(raw):
			if name is not None:
				self._release(owner, name)
			return Color.decode(raw)
		return self._follow(BoundColor(raw), owner, name if name is not None else len(self._followers.get(owner, ())))

	def adopt(self, owner: Any, name: Any, value: 'Color | BoundColor | None') -> 'Color | LiveColor | None':
		"""For a StateProperty setter: keep ``value`` (what `decodeColor` returned), following it if it is bound."""
		if isinstance(value, BoundColor):
			return self._follow(value, owner, name)
		self._release(owner, name)
		return value

	@staticmethod
	def spec(value: 'Color | LiveColor | None'):
		"""For a StateProperty encoder: the text of a colour, or the mapping of a bound one."""
		if value is None:
			return None
		return dict(value.spec) if isinstance(value, LiveColor) else str(value)

	def qcolor(self, raw: Any):
		"""The QColor of ``raw`` now. A bound spec is followed once and remembered, whatever number of paints ask."""
		if not isBound(raw):
			return Color.decode(raw).QColor
		key = repr(sorted(raw.items(), key=lambda item: str(item[0])))
		if (found := self._byKey.get(key)) is None:
			found = self._byKey[key] = self.slot(raw, owner=self, name=key)
		return found.QColor

	def _release(self, owner: Any, name: Any) -> None:
		if (follower := self._followers.get(owner, {}).pop(name, None)) is not None:
			follower.close()

	def release(self, owner: Any = None) -> None:
		"""Let go of the value sources one element opened."""
		for follower in self._followers.pop(owner, {}).values():
			follower.close()
		if owner is self:
			self._byKey.clear()

	def releaseAll(self) -> None:
		for owner in list(self._followers):
			self.release(owner)
		self._byKey.clear()

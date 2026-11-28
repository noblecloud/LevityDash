"""`change-animation` on a label: how the text moves when the value it shows changes. Qt-free.

Styles:

- ``none``: the new text replaces the old at once (the default; nothing animates unless a dashboard asks).
- ``fade``: the old text fades out while the new one fades in.
- ``slide``: the old text leaves and the new one arrives a short way along the vertical, upward when the number
  rose and downward when it fell (a text that is not a number goes up). The travel follows the theme's ``motion``
  curve when the theme has one, so ``motion: spring`` lets it settle with a small overshoot.
- ``flash``: the new text replaces the old at once and glows in the theme's ``accent`` for a moment.
- ``tint``: like ``flash``, in the theme's ``good`` when the number rose and ``bad`` when it fell (a stock ticker).
- ``roll``: an odometer: only the characters that changed move, each rolling in its own column, up when the
  number rose and down when it fell. Text whose shape it cannot split (a warped label) slides instead.
- ``pop``: the new text springs in from a little smaller while the old one fades.
- ``flip``: a split-flap board: the old text folds away about its horizontal middle and the new one folds in.
- ``glow``: a soft halo in the theme's ``accent`` swells around the new text and fades.
- ``shake``: the new text shakes sideways a little and settles (for an alert).
- ``delta``: the new text shows at once and a small badge with the difference (``+3``, ``−0.4``) floats up from its
  top right corner, in ``good`` when the number rose and ``bad`` when it fell; text with no number tints instead.
- ``blur``: a numeric-text swap: the old text fades out stretching a little, the new one fades in from a stretch
  and settles upward, with faint offset copies for the motion.

Written as a style name, a style and a time (``slide 500ms``), or ``{style: slide, duration: 0.5s}``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

__all__ = ('STYLES', 'DEFAULT_DURATION', 'DURATIONS', 'ChangeSpec', 'defaultDuration', 'parse', 'direction', 'number', 'decimals', 'deltaText')

STYLES = ('none', 'fade', 'slide', 'flash', 'tint', 'roll', 'pop', 'flip', 'glow', 'shake', 'delta', 'blur')
DEFAULT_DURATION = 0.35
#: A style's time when the dashboard gives none: the ones with more to see take a little longer.
DURATIONS = {'roll': 0.6, 'pop': 0.45, 'flip': 0.5, 'tint': 0.8,
             'glow': 0.9, 'shake': 0.45, 'delta': 1.2, 'blur': 0.4}
#: Longest a change may take: a value that changes every second must have settled before the next one.
MAX_DURATION = 2.0

_DURATION = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*(ms|s)?\s*$')
_NUMBER = re.compile(r'[-−]?\d+(?:\.\d+)?')


@dataclass(frozen=True)
class ChangeSpec:
	style: str
	duration: float = None

	def __post_init__(self):
		if self.duration is None:
			object.__setattr__(self, 'duration', defaultDuration(self.style))

	@property
	def ms(self) -> int:
		return int(round(self.duration * 1000))

	def encode(self) -> str | dict:
		if self.duration == defaultDuration(self.style):
			return self.style
		return {'style': self.style, 'duration': f'{round(self.duration * 1000)}ms'}


def defaultDuration(style: str) -> float:
	return DURATIONS.get(style, DEFAULT_DURATION)


def _seconds(value: Any) -> float:
	if isinstance(value, bool):
		raise ValueError(f'change-animation duration must be a time like 350ms or 0.4s, not {value!r}')
	if isinstance(value, (int, float)):
		seconds = float(value)
	elif isinstance(value, str) and (match := _DURATION.match(value)):
		seconds = float(match.group(1)) / (1000 if match.group(2) == 'ms' else 1)
	else:
		raise ValueError(f'change-animation duration must be a time like 350ms or 0.4s, not {value!r}')
	if not 0 < seconds <= MAX_DURATION:
		raise ValueError(f'change-animation duration must be above 0 and at most {MAX_DURATION:g}s, not {value!r}')
	return seconds


def parse(value: Any) -> Optional[ChangeSpec]:
	"""A spec from what a dashboard wrote, or ``None`` for no animation. Raises ``ValueError`` with the reason."""
	if value is None or value is False:
		return None
	if isinstance(value, ChangeSpec):
		return None if value.style == 'none' else value
	duration: Any = None
	if isinstance(value, dict):
		unknown = set(value) - {'style', 'duration'}
		if unknown:
			raise ValueError(f'change-animation takes style and duration, not {", ".join(sorted(map(str, unknown)))}')
		style, duration = value.get('style', 'fade'), value.get('duration')
	elif value is True:
		style = 'fade'
	elif isinstance(value, str):
		style, _, duration = value.strip().partition(' ')
		duration = duration.strip() or None
	else:
		raise ValueError(f'change-animation must be {", ".join(STYLES)}, not {value!r}')
	style = str(style).strip().lower()
	if style not in STYLES:
		raise ValueError(f'change-animation must be {", ".join(STYLES)}, not {style!r}')
	if style == 'none':
		return None
	return ChangeSpec(style, None if duration is None else _seconds(duration))


def number(text: Optional[str]) -> Optional[float]:
	"""The first number in a displayed string (``'1,013.2 hPa'`` gives 1013.2), or ``None``."""
	if not text:
		return None
	match = _NUMBER.search(text.replace(',', '').replace(' ', ''))
	if match is None:
		return None
	return float(match.group(0).replace('−', '-'))


def direction(old: Optional[str], new: Optional[str]) -> int:
	"""+1 when the number shown rose, -1 when it fell, 0 when either text has none or they are equal."""
	a, b = number(old), number(new)
	if a is None or b is None or a == b:
		return 0
	return 1 if b > a else -1


def decimals(text: Optional[str]) -> int:
	"""How many digits follow the point in the first number of a displayed string."""
	if not text:
		return 0
	match = _NUMBER.search(text.replace(',', '').replace(' ', ''))
	if match is None or '.' not in match.group(0):
		return 0
	return len(match.group(0).split('.')[1])


def deltaText(old: Optional[str], new: Optional[str]) -> Optional[str]:
	"""The difference between two displayed numbers as ``+3`` or ``−0.4`` (U+2212), written with the new text's
	decimal places. ``None`` when either has no number or the difference shows as zero."""
	a, b = number(old), number(new)
	if a is None or b is None:
		return None
	places = decimals(new)
	diff = round(b - a, places)
	if diff == 0:
		return None
	return f'{"+" if diff > 0 else "−"}{abs(diff):.{places}f}'

"""Qt-free half of the text alignment harness: what a measurement is, and what it should say.

`_textalign.py` measures real text items and fills in a `Probe`; `text_alignment.py` runs the case catalogue
and writes the probes as JSON; the tests read that JSON and ask the functions here whether each probe is where
its alignment says it should be. Rects are `(x, y, width, height)` in scene pixels.

The vertical rule: the *fit rect* (`hint`: the band the size was fitted to, the format hint or the font's `|`,
never the live string) sits on the edge the alignment names: `Top` puts its top on the top of the limit rect,
`Bottom` its bottom on the bottom, `Center` its centre on the centre. The band is a property of the font and
the hint, so a descender does not move a baseline (`tests/ui/test_label_baselines.py`). The horizontal rule:
`Left` and `Right` put the *ink* edge on the edge of the limit rect, `Center` puts the ink centre on the centre.

What must hold on top of that is containment: the ink of a fitted text stays inside its limit rect (the box
less its margins). `overflow` reports where it does not.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Optional

Rect = tuple[float, float, float, float]

#: Sub-pixel slack for anti-aliasing and the integer rounding in `Text._update_path`.
POSITION_TOLERANCE = 1.5
#: Ink may leave the limit rect by this much (side bearings, anti-aliasing) before it counts as overflow.
OVERFLOW_TOLERANCE = 1.5


def left(r: Rect) -> float: return r[0]
def top(r: Rect) -> float: return r[1]
def right(r: Rect) -> float: return r[0] + r[2]
def bottom(r: Rect) -> float: return r[1] + r[3]
def centerX(r: Rect) -> float: return r[0] + r[2] / 2
def centerY(r: Rect) -> float: return r[1] + r[3] / 2
def isEmpty(r: Rect) -> bool: return r[2] <= 0 or r[3] <= 0


@dataclass
class Probe:
	"""One text item measured in scene pixels."""
	case: str
	role: str  # label | value | unit | title
	text: str
	horizontal: str  # Left | HorizontalCenter | Right
	vertical: str  # Top | VerticalCenter | Bottom
	box: Rect  # the owning label's whole rect
	limit: Rect  # where the text may go: the box less margins (and `text-height`)
	hint: Rect  # the rect the fit sized against (format hint unioned with the text)
	ink: Rect  # the pixels the item painted
	pathInk: Rect  # glyph outline bounds, the cross-check for `ink`
	scale: float
	fontPixels: float  # em size on screen
	baseline: float
	ascent: float  # scene y of the ascent line
	descent: float  # scene y of the descent line
	strikeout: float  # scene y of the strikeout line
	group: Optional[str] = None  # size group key, if the item has one
	overlay: Optional[str] = None
	extra: dict = field(default_factory=dict)

	def asDict(self) -> dict:
		return asdict(self)

	@classmethod
	def fromDict(cls, data: dict) -> 'Probe':
		names = {f.name for f in fields(cls)}
		values = {k: tuple(v) if isinstance(v, list) else v for k, v in data.items() if k in names}
		return cls(**values)

	def __str__(self):
		r = lambda rect: '(%.1f, %.1f, %.1fx%.1f)' % rect
		return (f'{self.case}/{self.role} {self.text!r} {self.horizontal}-{self.vertical} limit={r(self.limit)} '
		        f'ink={r(self.ink)} baseline={self.baseline:.1f} fontPx={self.fontPixels:.1f}'
		        + (f' overlay={self.overlay}' if self.overlay else ''))


def expected(probe: Probe) -> dict[str, float]:
	"""Where the alignment says things must be, as `{what: scene coordinate}`."""
	limit = probe.limit
	out: dict[str, float] = {}
	match probe.horizontal:
		case 'Left':
			out['ink.left'] = left(limit)
		case 'Right':
			out['ink.right'] = right(limit)
		case _:
			out['ink.centerX'] = centerX(limit)
	match probe.vertical:
		case 'Top':
			out['hint.top'] = top(limit)
		case 'Bottom':
			out['hint.bottom'] = bottom(limit)
		case _:
			out['hint.centerY'] = centerY(limit)
	return out


def actual(probe: Probe, key: str) -> float:
	match key:
		case 'ink.left':
			return left(probe.ink)
		case 'ink.right':
			return right(probe.ink)
		case 'ink.centerX':
			return centerX(probe.ink)
		case 'hint.top':
			return top(probe.hint)
		case 'hint.bottom':
			return bottom(probe.hint)
		case 'hint.centerY':
			return centerY(probe.hint)
	raise KeyError(key)


def deviations(probe: Probe) -> dict[str, float]:
	"""Signed distance of each expected position from where it landed (positive = too far right or down)."""
	if isEmpty(probe.ink):
		return {key: float('inf') for key in expected(probe)}
	return {key: actual(probe, key) - want for key, want in expected(probe).items()}


def misplaced(probe: Probe, tolerance: float = POSITION_TOLERANCE) -> dict[str, float]:
	"""The deviations that are beyond `tolerance`."""
	return {key: value for key, value in deviations(probe).items() if abs(value) > tolerance}


def overflow(probe: Probe, tolerance: float = OVERFLOW_TOLERANCE) -> dict[str, float]:
	"""How far the ink pokes out of the limit rect on each side, in pixels (only the sides beyond `tolerance`)."""
	ink, limit = probe.ink, probe.limit
	if isEmpty(ink):
		return {}
	sides = {
		'left': left(limit) - left(ink),
		'top': top(limit) - top(ink),
		'right': right(ink) - right(limit),
		'bottom': bottom(ink) - bottom(limit),
	}
	return {side: value for side, value in sides.items() if value > tolerance}


def inkAgrees(probe: Probe, tolerance: float = 1.0) -> bool:
	"""The painted ink and the glyph outlines should be the same box; if not, the harness is measuring something else."""
	return all(abs(a - b) <= tolerance for a, b in zip(probe.ink, probe.pathInk))

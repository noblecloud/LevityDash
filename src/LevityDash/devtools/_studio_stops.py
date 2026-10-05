"""Dev-only: gradient stops for Gauge Studio, shared by the stop editor and the drag handles on the meter.

A stop is a number, the unit it is written in (`°F`, `mph`; None for a bare number) and a colour. The
file holds it as a key: `99°F`, or a plain number when there is no unit. The gauge keeps its data in
one unit (its *native* unit); a stop in another unit converts to it. Both editors place a stop by
its native value, so the band in the panel and the nodes on the meter agree.
"""
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtGui import QColor

from LevityDash.lib.ui.colors.stopunits import StopUnitError, formatStop, parseStop, toDataUnit

__all__ = ['Stop', 'decode', 'encode', 'native', 'fromNative', 'place', 'sample', 'freshColor', 'niceStep', 'snapTo', 'PALETTE']

#: Colours a new stop picks from, in order, skipping any already in the gradient.
PALETTE = ['#2f81f7', '#3fb950', '#f5a524', '#ff7b72', '#a371f7', '#39c5cf', '#db61a2', '#ffd33d']


def niceStep(x: float) -> float:
	"""The round number (1, 2 or 5 times a power of ten) at or below `x`."""
	if x <= 0 or not math.isfinite(x):
		return 1.0
	power = 10 ** math.floor(math.log10(x))
	for m in (5, 2, 1):
		if x >= m * power:
			return m * power
	return power


def snapTo(value: float, step: float) -> float:
	return round(value / step) * step


@dataclass
class Stop:
	number: float
	unit: Optional[str]
	color: str

	def key(self) -> Any:
		"""What the file calls this stop: a number when bare (a whole number as an int), else text such as `99°F`."""
		if self.unit:
			return formatStop(self.number, self.unit)
		number = round(float(self.number), 4)
		return int(number) if number.is_integer() else number

	def copy(self) -> 'Stop':
		return Stop(self.number, self.unit, self.color)


def decode(mapping: Optional[dict]) -> List[Stop]:
	"""The stops of a saved gradient (`{key: colour}`), in the order the file has them."""
	stops = []
	for key, color in (mapping or {}).items():
		parsed = parseStop(key)
		if parsed is None:
			continue
		stops.append(Stop(parsed[0], parsed[1], str(color)))
	return stops


def encode(stops: List[Stop]) -> Optional[dict]:
	"""A saved gradient from stops. A key two stops share keeps the later one."""
	return {s.key(): s.color for s in stops} or None


_lines: Dict[Tuple[str, type], Optional[Tuple[float, float]]] = {}


def _line(unit: str, valueClass: type) -> Optional[Tuple[float, float]]:
	"""(offset, scale) of the straight line from `unit` to the native unit, or None when the unit does not fit the data.

	Every unit pair a gradient can hold is a straight line, so two samples find it.
	"""
	key = (unit, valueClass)
	if key not in _lines:
		try:
			a = toDataUnit(0.0, unit, valueClass)
			b = toDataUnit(1.0, unit, valueClass)
			_lines[key] = (a, b - a) if b != a else None
		except (StopUnitError, Exception):  # noqa: BLE001 - an odd unit must leave the stop unplaced, not stop the studio
			_lines[key] = None
	return _lines[key]


def native(stop: Stop, valueClass: Optional[type]) -> Optional[float]:
	"""Where the stop sits in the gauge's own unit. None when its unit does not fit the data."""
	if not stop.unit:
		return float(stop.number)
	if valueClass is None:
		return float(stop.number)
	line = _line(stop.unit, valueClass)
	return None if line is None else line[0] + line[1] * float(stop.number)


def fromNative(value: float, unit: Optional[str], valueClass: Optional[type]) -> float:
	"""`value` (in the gauge's own unit) as a number in `unit`."""
	if not unit or valueClass is None:
		return float(value)
	line = _line(unit, valueClass)
	return float(value) if line is None else (float(value) - line[0]) / line[1]


def sample(points: List[Tuple[float, str]], value: float) -> str:
	"""The colour of a gradient at `value`: straight blends between neighbouring stops, flat beyond the ends.

	`points` are (native value, colour). Qt blends the same way, so this is the colour the meter shows there.
	"""
	pts = sorted(points, key=lambda p: p[0])
	if not pts:
		return PALETTE[0]
	if value <= pts[0][0]:
		return QColor(pts[0][1]).name()
	if value >= pts[-1][0]:
		return QColor(pts[-1][1]).name()
	for (v0, c0), (v1, c1) in zip(pts, pts[1:]):
		if v0 <= value <= v1:
			t = 0.0 if v1 == v0 else (value - v0) / (v1 - v0)
			a, b = QColor(c0), QColor(c1)
			mix = QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
			             round(a.blue() + (b.blue() - a.blue()) * t))
			return mix.name()
	return QColor(pts[-1][1]).name()


def freshColor(used: List[str]) -> str:
	"""A colour no stop has yet, so a new stop reads as a new stop. Cycles when every one is taken."""
	taken = {QColor(c).name() for c in used}
	for color in PALETTE:
		if QColor(color).name() not in taken:
			return color
	return PALETTE[len(used) % len(PALETTE)]


def place(stop: Stop, value: float, valueClass: Optional[type], lo: float, hi: float, fine: bool = False) -> Stop:
	"""`stop` moved to `value` (in the gauge's own unit), in its own unit.

	The number snaps to a round step of that unit, one fiftieth of the range or so; `fine` keeps three decimals instead.
	"""
	number = fromNative(value, stop.unit, valueClass)
	span = abs(fromNative(hi, stop.unit, valueClass) - fromNative(lo, stop.unit, valueClass))
	number = round(number, 3) if fine else snapTo(number, niceStep(span / 50))
	return Stop(round(number, 4), stop.unit, stop.color)

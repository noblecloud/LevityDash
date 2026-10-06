"""The arithmetic of a polar plot: where a direction, an hour or a value lands.

A polar plot has two axes and no Qt in either. The **angle** says which way (a wind
direction) or when (an hour of the day); the **radius** says how much. Both go through
`meter.scale.Scale`, the same value-to-fraction object the dials use, so a polar plot and
a gauge agree on what `min`, `max` and a wrapping range mean.

Every angle here is in degrees **clockwise from the top** of the plot, the way a compass
and a clock face are read. `polarPoint` is the one place that turns it into x and y.

Nothing in this module imports Qt, `Gauge.py` or a plugin.
"""
import math
import re
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional, Sequence

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.scale import Scale

__all__ = [
	'COMPASS_16', 'RoseData', 'angleScale', 'bezierThrough', 'clockAngle', 'compassName', 'niceStep',
	'niceSpeedEdges', 'parseWindow', 'polarPoint', 'roseBins', 'timeOfDay', 'windowBounds',
]

COMPASS_16 = (
	'N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW',
)


def compassName(degrees: float, points: int = 16) -> str:
	"""``'NNW'`` for 337.5 to 348.75 degrees. ``points`` is 4, 8 or 16."""
	if points not in (4, 8, 16):
		raise ValueError(f'a compass has 4, 8 or 16 points, not {points}')
	index = round((float(degrees) % 360) / (360 / points)) % points
	return COMPASS_16[index * (16 // points)]


def polarPoint(cx: float, cy: float, radius: float, degrees: float) -> tuple[float, float]:
	"""The x, y of a point ``radius`` from the centre at ``degrees`` clockwise from the top."""
	radians = math.radians(degrees)
	return cx + radius * math.sin(radians), cy - radius * math.cos(radians)


def angleScale(kind: str) -> Scale:
	"""The scale the angle follows. A direction is 0 to 360 and wraps; a clock is 0 to 24 or 0 to 12 hours."""
	match kind:
		case 'direction':
			return Scale(0, 360, wrap=True)
		case 'clock' | 'clock24':
			return Scale(0, 24, wrap=True)
		case 'clock12':
			return Scale(0, 12, wrap=True)
	raise ValueError(f'the angle is a direction, clock24 or clock12, not {kind!r}')


def timeOfDay(when: datetime) -> float:
	"""Hours since midnight, with the minutes and seconds as a fraction. In the timestamp's own zone."""
	return when.hour + when.minute / 60 + when.second / 3600


def clockAngle(hours: float, span: int = 24, top: str = 'noon') -> float:
	"""The angle of a time of day on a clock face of ``span`` hours.

	A 24 hour face puts ``top`` at the top: ``'noon'`` keeps the day above the centre and the night
	below it, ``'midnight'`` reads like a 24 hour watch. A 12 hour face always has 12 at the top.
	"""
	if span not in (12, 24):
		raise ValueError(f'a clock face is 12 or 24 hours, not {span}')
	turn = (hours % span) / span * 360
	if span == 24 and top == 'noon':
		turn -= 180
	elif top not in ('noon', 'midnight'):
		raise ValueError(f'the top of a 24 hour face is noon or midnight, not {top!r}')
	return turn % 360


def niceStep(span: float, target: int = 4) -> float:
	"""A round ring spacing (1, 2, 2.5, 5, 10 times a power of ten) giving about ``target`` rings over ``span``."""
	if span <= 0 or target < 1:
		return 1.0
	raw = span / target
	scale = 10 ** math.floor(math.log10(raw))
	for factor in (1, 2, 2.5, 5, 10):
		if raw <= factor * scale:
			return factor * scale
	return 10 * scale


def niceSpeedEdges(top: float, bins: int = 5) -> list[float]:
	"""Bin edges ``[0, a, b, ...]`` of a round width that cover ``top``, at most ``bins`` bins plus an open last one."""
	if top <= 0:
		return [0.0, 1.0]
	width = niceStep(top, bins)
	edges = [0.0]
	while edges[-1] < top and len(edges) <= bins:
		edges.append(round(edges[-1] + width, 10))
	return edges


@dataclass(frozen=True)
class RoseData:
	"""A wind rose, counted. ``share[sector][bin]`` is the fraction of all samples, so the whole rose sums to 1.

	``edges`` are the speed bin edges; the last bin has no upper limit. ``calm`` is the fraction of
	samples below ``calmBelow``, which has no direction and is drawn as the centre dot.
	"""
	sectors: int
	edges: tuple[float, ...]
	share: tuple[tuple[float, ...], ...]
	calm: float
	samples: int

	@property
	def sectorTotals(self) -> tuple[float, ...]:
		return tuple(sum(row) for row in self.share)

	@property
	def peak(self) -> float:
		"""The largest sector's share: what the outer ring has to reach."""
		return max(self.sectorTotals, default=0.0)

	@property
	def dominant(self) -> Optional[int]:
		"""The sector most of the wind came from, or None when nothing was counted."""
		totals = self.sectorTotals
		return max(range(len(totals)), key=totals.__getitem__) if totals and max(totals) > 0 else None

	def sectorAngle(self, sector: int) -> float:
		return sector * 360 / self.sectors


def roseBins(
	directions: Sequence[float],
	speeds: Sequence[float],
	sectors: int = 16,
	edges: Optional[Iterable[float]] = None,
	calmBelow: float = 0.0,
) -> RoseData:
	"""Count paired direction and speed samples into a wind rose.

	A direction belongs to the sector it is nearest to, and sector 0 is centred on north, so 350 and
	10 degrees are both north. ``edges`` default to `niceSpeedEdges` of the fastest sample. A sample
	missing either half is skipped.
	"""
	if sectors < 4:
		raise ValueError('a rose needs at least 4 sectors')
	pairs = [
		(float(d) % 360, float(s))
		for d, s in zip(directions, speeds)
		if d is not None and s is not None and not (math.isnan(float(d)) or math.isnan(float(s)))
	]
	edgeList = sorted(set(edges)) if edges is not None else niceSpeedEdges(max((s for _, s in pairs), default=0.0))
	if not edgeList or edgeList[0] != 0:
		edgeList.insert(0, 0.0)
	bins = len(edgeList)
	counts = [[0] * bins for _ in range(sectors)]
	calm = 0
	width = 360 / sectors
	for direction, speed in pairs:
		if speed < calmBelow or (calmBelow == 0 and speed <= 0):
			calm += 1
			continue
		sector = round(direction / width) % sectors
		counts[sector][min(bins - 1, max(0, bisect_right(edgeList, speed) - 1))] += 1
	total = len(pairs)
	if not total:
		return RoseData(sectors, tuple(edgeList), tuple((0.0,) * bins for _ in range(sectors)), 0.0, 0)
	share = tuple(tuple(c / total for c in row) for row in counts)
	return RoseData(sectors, tuple(edgeList), share, calm / total, total)


def bezierThrough(
	points: Sequence[tuple[float, float]], closed: bool = False, tension: float = 0.5
) -> list[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]]:
	"""Cubic segments ``(control1, control2, end)`` of a Catmull-Rom curve through ``points``.

	The curve starts at ``points[0]``. A closed curve also runs from the last point back to the first,
	so a day's temperature meets itself at midnight without a corner. ``tension`` 0 is straight lines.
	"""
	count = len(points)
	if count < 2:
		return []
	k = tension / 3 * 2
	segments = []
	last = count if closed else count - 1
	for i in range(last):
		p0 = points[(i - 1) % count] if closed or i > 0 else points[i]
		p1 = points[i]
		p2 = points[(i + 1) % count]
		p3 = points[(i + 2) % count] if closed or i + 2 < count else p2
		c1 = (p1[0] + (p2[0] - p0[0]) * k / 2, p1[1] + (p2[1] - p0[1]) * k / 2)
		c2 = (p2[0] - (p3[0] - p1[0]) * k / 2, p2[1] - (p3[1] - p1[1]) * k / 2)
		segments.append((c1, c2, p2))
	return segments


_WINDOW = re.compile(r'^\s*([+-]?)\s*(\d+(?:\.\d+)?)\s*([hd])\s*$')


def parseWindow(text: str) -> tuple[str, timedelta]:
	"""A plot's time window as ``(kind, length)``.

	``today`` is the local calendar day. ``24h`` is the 24 hours up to now, ``+24h`` the 24 hours from
	now on (a forecast), ``3d`` three days back. The length of ``today`` is zero.
	"""
	text = str(text).strip().lower()
	if text == 'today':
		return 'today', timedelta(0)
	if not (found := _WINDOW.match(text)):
		raise ValueError(f'a window is today, 24h, +24h or 3d, not {text!r}')
	sign, number, unit = found.groups()
	length = timedelta(**{'hours' if unit == 'h' else 'days': float(number)})
	if length <= timedelta(0):
		raise ValueError(f'a window needs a length above zero, not {text!r}')
	return ('ahead' if sign == '+' else 'back'), length


def windowBounds(window: tuple[str, timedelta], now: datetime) -> tuple[datetime, datetime]:
	"""The start and end of a window around ``now``, in ``now``'s zone."""
	kind, length = window
	match kind:
		case 'today':
			start = now.replace(hour=0, minute=0, second=0, microsecond=0)
			return start, start + timedelta(days=1)
		case 'ahead':
			return now, now + length
		case _:
			return now - length, now

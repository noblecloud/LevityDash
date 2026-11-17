"""Plane silhouettes for the radar, chosen by what the aircraft is.

`classify(type, category)` is Qt-free and answers a `Glyph` (a shape name and a size). The order is the one the
open-source trackers use (tar1090 and its kin): the ICAO type designator first (`B738`), then a prefix that
names a family (`A32x`), then the ADS-B emitter category the aircraft broadcasts (`A3` large, `A7` rotorcraft),
then a plain arrowhead. `path(name)` builds the silhouette as a `QPainterPath` with the nose up, the length 1 and
the centre at the origin; the radar scales it, turns it to the heading and fills it.

The tables are written here from the designators themselves (ICAO Doc 8643 is public) and the shapes are drawn
in code, so nothing is copied from a GPL tracker.
"""
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Sequence

__all__ = ['Glyph', 'SHAPES', 'classify', 'path']

SHAPES = ('light', 'twinprop', 'bizjet', 'regional', 'narrow', 'wide', 'quad', 'fighter', 'heli', 'glider', 'balloon', 'unknown')

#: Size of each shape against a narrow-body: a Cessna is half the length of an Airbus, a 747 a third more.
SIZE = {
	'light': 0.55, 'twinprop': 0.7, 'bizjet': 0.7, 'regional': 0.8, 'narrow': 0.9, 'wide': 1.1, 'quad': 1.25,
	'fighter': 0.7, 'heli': 0.7, 'glider': 0.75, 'balloon': 0.55, 'unknown': 0.65,
}


@dataclass(frozen=True)
class Glyph:
	shape: str
	size: float


def _table(shape: str, designators: str) -> dict:
	return {code: shape for code in designators.split()}


_TYPES: dict = {}
for _shape, _codes in {
	'quad': 'B741 B742 B743 B744 B74D B74R B74S B748 A388 A124 A225 A342 A343 A345 A346 A340 IL96 C17 C5M C5 A400 C130 C30J '
	        'L100 P3 K35R B703 B52 E3CF E3TF E6 VC10 IL76 AN12 B701',
	'wide': 'B762 B763 B764 B772 B77L B77W B773 B788 B789 B78X A306 A310 A332 A333 A338 A339 A359 A35K MD11 DC10 L101 IL86',
	'narrow': 'A318 A319 A320 A321 A19N A20N A21N A221 A223 B731 B732 B733 B734 B735 B736 B737 B738 B739 B37M B38M B39M '
	          'B3XM B752 B753 BCS1 BCS3 C919 A220 B712 B722 B721',
	'regional': 'CRJ1 CRJ2 CRJ7 CRJ9 CRJX E135 E145 E45X E170 E75L E75S E190 E195 E290 E295 E35L F70 F100 RJ85 RJ1H RJ70 '
	            'MD80 MD81 MD82 MD83 MD87 MD88 MD90 DC93 DC95 BA46 B461 B462 B463 E170 AJ27 SU95',
	'twinprop': 'AT43 AT44 AT45 AT46 AT72 AT73 AT75 AT76 DH8A DH8B DH8C DH8D SF34 SB20 JS31 JS32 JS41 E120 B190 BE20 BE9L '
	            'BE9T BE99 BE10 SW3 SW4 DHC6 C441 C421 C340 C310 C402 BE58 BE55 BE76 PA34 PA44 PA27 DA42 DA62 AC90 AC95 '
	            'MU2 P180 PAY1 PAY2 PAY3 PAY4 AN24 AN26 AN32 L410 F27 F50 F60 SH36 D328 DO28 BN2P C212 CN35 '
	            'TBM7 TBM8 TBM9 PC12 C208 C206',
	'bizjet': 'C25A C25B C25C C25M C510 C525 C550 C560 C56X C650 C680 C68A C700 C750 CL30 CL35 CL60 GLF2 GLF3 GLF4 GLF5 GLF6 '
	          'GLEX GALX G150 G200 G280 FA10 FA20 FA50 FA5X FA6X FA7X FA8X F900 F2TH LJ23 LJ24 LJ25 LJ28 LJ31 LJ35 LJ40 LJ45 '
	          'LJ55 LJ60 LJ70 LJ75 H25A H25B H25C E50P E55P EA50 HDJT PRM1 SF50 ASTR WW24 BE40 C501 C510 PC24 MU30 DA50 '
	          'GA7C GA8C',
	'fighter': 'F16 F15 F18 F35 F22 FA18 F14 F5 F4 F111 A10 A4 EUFI EF2K TORN M346 T38 T45 T6 HAWK RFAL MIR2 MIR4 SU27 '
	           'SU30 SU35 MG29 B1 B2 A6 AV8 F117 J10 J20 JAS39 GR4 L39 L159 YK30 TEX2 PC21 PC9 S211 T37',
	'heli': 'R22 R44 R66 EC20 EC30 EC35 EC45 EC55 A109 A119 A139 A169 A189 AS50 AS55 AS65 AS32 B06 B06T B407 B412 B429 B430 '
	        'B105 S76 S92 S61 S64 H60 H64 H47 CH47 UH1 MD52 MD60 EXPL H500 H269 B222 B212 B214 SCOU EN28 EN48 R480 NH90 '
	        'MI8 KA32 LAMA GAZL AS3B',
	'glider': 'GLID ASK21 DG1T LS4 ASW2 DISC PW5 PIL4 ARCE',
	'balloon': 'BALL SHIP GBLN HAIR',
}.items():
	for _code in _codes.split():
		_TYPES.setdefault(_code, _shape)  # a code listed twice (B703, MD11, ...) keeps its first, most specific shape

#: What an emitter category says when the type is unknown (the `category` of an ADS-B message).
_CATEGORY = {
	'A1': 'light', 'A2': 'bizjet', 'A3': 'narrow', 'A4': 'narrow', 'A5': 'wide', 'A6': 'fighter', 'A7': 'heli',
	'B1': 'glider', 'B2': 'balloon', 'B4': 'light', 'B6': 'unknown',
}

#: A family named by its first letters, for a designator the table does not list.
_PREFIX = (
	('A31', 'narrow'), ('A32', 'narrow'), ('B73', 'narrow'), ('B75', 'narrow'), ('B74', 'quad'), ('B77', 'wide'),
	('B78', 'wide'), ('A33', 'wide'), ('A35', 'wide'), ('A38', 'quad'), ('CRJ', 'regional'), ('E1', 'regional'),
	('E2', 'regional'), ('AT', 'twinprop'), ('DH8', 'twinprop'), ('GL', 'bizjet'), ('LJ', 'bizjet'), ('FA', 'bizjet'),
	('H', 'heli'),
)


def classify(typeCode: Optional[str], category: Optional[str] = None) -> Glyph:
	"""The glyph for an aircraft, from its ICAO type designator and then its ADS-B category."""
	code = (typeCode or '').strip().upper()
	shape = _TYPES.get(code)
	if shape is None and code:
		# A single-engine light aircraft has no family worth listing: a `C1xx`, `PA2x`, `SR2x` is a light.
		shape = next((s for prefix, s in _PREFIX if code.startswith(prefix)), None)
	if shape is None:
		shape = _CATEGORY.get((category or '').strip().upper())
	if shape is None and code[:1] in ('C', 'P', 'S', 'D', 'M') and len(code) == 4 and code[1:].isalnum():
		shape = 'light'  # Cessna, Piper, Socata, Diamond, Mooney: all but the listed ones are light singles
	shape = shape or 'unknown'
	return Glyph(shape, SIZE[shape])


# -- drawing ---------------------------------------------------------------------------------------------------


def _mirrored(points: Sequence[tuple]):
	"""A closed polygon from the right-hand outline, nose to tail, and its mirror image."""
	from PySide6.QtCore import QPointF
	from PySide6.QtGui import QPainterPath, QPolygonF
	right = [QPointF(x, y) for x, y in points]
	left = [QPointF(-x, y) for x, y in reversed(points)]
	path = QPainterPath()
	path.addPolygon(QPolygonF(right + left))
	path.closeSubpath()
	return path


def _box(path, cx: float, top: float, width: float, height: float, round_: float = 0.0):
	from PySide6.QtCore import QRectF
	if round_:
		path.addRoundedRect(QRectF(cx - width / 2, top, width, height), round_, round_)
	else:
		path.addRect(QRectF(cx - width / 2, top, width, height))


def _airframe(fuse: float, nose: float, wingRoot: float, rootChord: float, span: float, tipChord: float, sweep: float,
              tailRoot: float, tailSpan: float, tailChord: float, tailSweep: float = 0.03, tail: float = 0.5):
	"""A fuselage with one wing and one tailplane, nose at -0.5 and tail at ``tail``, as the right-hand outline."""
	return [
		(0.0, -0.5), (fuse * 0.55, -0.5 + nose * 0.25), (fuse, -0.5 + nose),
		(fuse, wingRoot), (span, wingRoot + sweep), (span, wingRoot + sweep + tipChord), (fuse, wingRoot + rootChord),
		(fuse, tailRoot), (tailSpan, tailRoot + tailSweep), (tailSpan, tailRoot + tailSweep + tailChord),
		(fuse * 0.7, tailRoot + tailChord), (fuse * 0.5, tail), (0.0, tail),
	]


@lru_cache(maxsize=None)
def path(shape: str):
	"""The silhouette of ``shape`` as a `QPainterPath`: nose up, length 1, centred on the origin."""
	from PySide6.QtCore import QPointF, QRectF
	from PySide6.QtGui import QPainterPath, QPainterPathStroker, QPolygonF
	if shape not in SHAPES:
		shape = 'unknown'
	p = QPainterPath()
	match shape:
		case 'light':
			p = _mirrored(_airframe(0.05, 0.10, -0.10, 0.20, 0.50, 0.17, 0.0, 0.36, 0.17, 0.09, 0.0))
		case 'twinprop':
			p = _mirrored(_airframe(0.05, 0.10, -0.08, 0.17, 0.50, 0.12, 0.0, 0.36, 0.18, 0.10, 0.0))
			for sign in (-1, 1):
				_box(p, sign * 0.17, -0.20, 0.06, 0.30, 0.02)
		case 'bizjet':
			p = _mirrored(_airframe(0.05, 0.12, -0.02, 0.16, 0.46, 0.09, 0.14, 0.36, 0.14, 0.08, 0.06))
			for sign in (-1, 1):
				_box(p, sign * 0.095, 0.20, 0.06, 0.22, 0.025)
		case 'regional':
			p = _mirrored(_airframe(0.05, 0.11, -0.05, 0.17, 0.46, 0.09, 0.16, 0.36, 0.15, 0.08, 0.07))
			for sign in (-1, 1):
				_box(p, sign * 0.10, 0.20, 0.06, 0.24, 0.025)
		case 'narrow':
			p = _mirrored(_airframe(0.05, 0.11, -0.05, 0.17, 0.50, 0.09, 0.19, 0.36, 0.17, 0.08, 0.08))
			for sign in (-1, 1):
				_box(p, sign * 0.17, -0.0, 0.055, 0.17, 0.025)
		case 'wide':
			p = _mirrored(_airframe(0.062, 0.12, -0.08, 0.20, 0.50, 0.10, 0.23, 0.35, 0.18, 0.09, 0.08))
			for sign in (-1, 1):
				_box(p, sign * 0.19, -0.02, 0.07, 0.20, 0.03)
		case 'quad':
			p = _mirrored(_airframe(0.068, 0.13, -0.10, 0.23, 0.50, 0.10, 0.25, 0.34, 0.19, 0.09, 0.08))
			for sign in (-1, 1):
				_box(p, sign * 0.15, -0.04, 0.06, 0.17, 0.025)
				_box(p, sign * 0.29, 0.03, 0.06, 0.17, 0.025)
		case 'fighter':
			p = _mirrored([
				(0.0, -0.5), (0.03, -0.38), (0.05, -0.15), (0.07, -0.05), (0.46, 0.34), (0.46, 0.40), (0.10, 0.34),
				(0.075, 0.46), (0.17, 0.50), (0.17, 0.53), (0.0, 0.5 + 0.03),
			])
		case 'heli':
			body = _mirrored([(0.0, -0.46), (0.085, -0.40), (0.10, -0.15), (0.085, 0.10), (0.03, 0.18), (0.03, 0.44), (0.12, 0.48),
			                  (0.12, 0.50), (0.0, 0.50)])
			p.addPath(body)
			disc = QPainterPath()
			disc.addEllipse(QPointF(0, -0.05), 0.40, 0.40)  # the rotor disc, as a thin ring around the body
			stroker = QPainterPathStroker()
			stroker.setWidth(0.035)
			p.addPath(stroker.createStroke(disc))
		case 'glider':
			p = _mirrored(_airframe(0.03, 0.12, -0.06, 0.09, 0.62, 0.05, 0.0, 0.40, 0.14, 0.06, 0.0, 0.5))
		case 'balloon':
			p.addEllipse(QPointF(0, -0.12), 0.34, 0.38)
			_box(p, 0, 0.30, 0.14, 0.14, 0.02)
		case _:  # an arrowhead says "something is here, heading this way"
			p = _mirrored([(0.0, -0.5), (0.30, 0.40), (0.0, 0.22)])
	return p if shape in ('heli', 'balloon') else p.simplified()

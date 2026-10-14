"""Dev-only: the snap targets a Studio drag can land on. Qt-free, so the maths tests without a window.

The targets are data. A new ratio is one line in `RATIOS`, a new fraction one line in `FRACTIONS`, a new
angle rule one line in `ANGLE_STEPS`. Each belongs to a family the Studio can switch on or off.

A *fraction* drag (radius, weight, value along the arc) is a share of a reference length and lands on a
fraction or a design ratio of it. An *offset* drag is the same but signed (a label's distance from the
dial's centre, in dial diameters). An *angle* drag lands on multiples of 15° and 45° and on the golden angle.
"""
import math
from dataclasses import dataclass
from typing import Iterable, Optional

PHI = (1 + math.sqrt(5)) / 2
GOLDEN_ANGLE = 360 * (1 - 1 / PHI)

FRACTIONS_FAMILY = 'fractions'
RATIOS_FAMILY = 'ratios'
ANGLES_FAMILY = 'angles'
FAMILIES = (FRACTIONS_FAMILY, RATIOS_FAMILY, ANGLES_FAMILY)
FAMILY_TITLES = {FRACTIONS_FAMILY: 'Fractions', RATIOS_FAMILY: 'Design ratios', ANGLES_FAMILY: 'Angles'}

#: (name, share). Whole percents are the Snap step itself, not a target.
FRACTIONS = (
	('0', 0.0), ('1/8', 1 / 8), ('1/4', 1 / 4), ('1/3', 1 / 3), ('3/8', 3 / 8), ('1/2', 1 / 2),
	('5/8', 5 / 8), ('2/3', 2 / 3), ('3/4', 3 / 4), ('7/8', 7 / 8), ('1', 1.0),
)

#: (name, value, name of the reciprocal). Both the value and its reciprocal are targets.
RATIOS = (
	('φ', PHI, '1/φ'),
	('φ²', PHI ** 2, '1/φ²'),
	('√2', math.sqrt(2), '1/√2'),
	('√3', math.sqrt(3), '1/√3'),
	('3:2', 3 / 2, '2:3'),
	('4:3', 4 / 3, '3:4'),
	('16:9', 16 / 9, '9:16'),
)

#: (step in degrees, name of one step). The first rule that reaches a value names it.
ANGLE_STEPS = ((45, '45°'), (15, '15°'))
#: The golden angle and its complement, as angles on either side of up.
GOLDEN_ANGLES = (GOLDEN_ANGLE, 360 - GOLDEN_ANGLE)


@dataclass(frozen=True)
class Target:
	name: str
	value: float
	family: str


def _shareTargets(families: Iterable[str]) -> list:
	out = []
	if FRACTIONS_FAMILY in families:
		out += [Target(n, v, FRACTIONS_FAMILY) for n, v in FRACTIONS]
	if RATIOS_FAMILY in families:
		for name, value, inverse in RATIOS:
			out += [Target(name, value, RATIOS_FAMILY), Target(inverse, 1 / value, RATIOS_FAMILY)]
	return out


def _angleTargets(x: float) -> list:
	out = []
	for step, name in ANGLE_STEPS:
		k = round(x / step)
		out.append(Target(name if abs(k) == 1 else f'{abs(k)}×{name}', k * step, ANGLES_FAMILY))
	for base in GOLDEN_ANGLES:
		for sign in (1, -1):
			turns = round((x - sign * base) / 360)
			out.append(Target('golden angle', sign * base + 360 * turns, ANGLES_FAMILY))
	return out


def near(kind: str, x: float, tol: float, families: Iterable[str] = FAMILIES) -> Optional[Target]:
	"""The closest target to `x` within `tol`, or None.

	`kind` is `'fraction'` (a share, unsigned), `'offset'` (a share with a sign) or `'angle'` (degrees).
	Ties go to the earlier entry of the data tables, so a plain fraction beats a ratio at the same value.
	"""
	families = set(families)
	if kind == 'angle':
		found = _angleTargets(x) if ANGLES_FAMILY in families else []
		sign = 1
	else:
		sign = -1 if (kind == 'offset' and x < 0) else 1
		found = _shareTargets(families)
		x = abs(x) if kind == 'offset' else x
	best = None
	for t in found:
		d = abs(t.value - x)
		if d <= tol and (best is None or d < best[0] - 1e-12):
			best = (d, t)
	if best is None:
		return None
	t = best[1]
	return Target(t.name, sign * t.value, t.family) if sign != 1 else t


def describe(target: Target, kind: str) -> str:
	"""`1/φ · 61.8%` for a share, `golden angle · 137.5°` for an angle."""
	if kind == 'angle':
		return f'{target.name} · {target.value:.1f}°'.replace('.0°', '°')
	return f'{target.name} · {target.value * 100:.1f}%'.replace('.0%', '%')

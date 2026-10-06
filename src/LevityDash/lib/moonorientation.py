"""
How the Moon is tilted in the sky for an observer.

Pure maths on top of `ephem`, which the project already depends on through pylunar.
No Qt, so the backend can use it too.

Meeus, Astronomical Algorithms: chapter 48 gives the position angle `chi` of the
bright limb (from celestial north, through east), and chapter 14 the parallactic
angle `q` (celestial north against the local zenith). A zenith-up view of the Moon,
which is what you see looking at it, has the bright limb at `chi - q` from the top,
counterclockwise (east is on the left when you face the Moon's sky from the ground).
"""

from datetime import datetime, timezone
from math import atan2, cos, degrees, radians, sin, tan

import ephem

__all__ = ['brightLimbAngle', 'parallacticAngle', 'brightLimbFromZenith', 'moonIllumination']


def _observer(lat: float, lon: float, when: datetime) -> ephem.Observer:
	observer = ephem.Observer()
	observer.lat = str(lat)
	observer.lon = str(lon)
	observer.elevation = 0
	observer.pressure = 0
	if when.tzinfo is not None:
		when = when.astimezone(timezone.utc)
	observer.date = when.strftime('%Y/%m/%d %H:%M:%S')
	return observer


def _sunMoon(lat: float, lon: float, when: datetime):
	observer = _observer(lat, lon, when)
	moon = ephem.Moon(observer)
	sun = ephem.Sun(observer)
	return observer, moon, sun


def brightLimbAngle(lat: float, lon: float, when: datetime) -> float:
	"""Position angle of the Moon's bright limb, degrees from celestial north through east. [0, 360)"""
	_, moon, sun = _sunMoon(lat, lon, when)
	a, d = float(moon.ra), float(moon.dec)
	a0, d0 = float(sun.ra), float(sun.dec)
	y = cos(d0)*sin(a0 - a)
	x = sin(d0)*cos(d) - cos(d0)*sin(d)*cos(a0 - a)
	return degrees(atan2(y, x))%360


def parallacticAngle(lat: float, lon: float, when: datetime) -> float:
	"""Angle between celestial north and the zenith at the Moon, degrees, positive west of the meridian. (-180, 180]"""
	observer, moon, _ = _sunMoon(lat, lon, when)
	hourAngle = float(observer.sidereal_time()) - float(moon.ra)
	d = float(moon.dec)
	phi = radians(lat)
	return degrees(atan2(sin(hourAngle), tan(phi)*cos(d) - sin(d)*cos(hourAngle)))


def brightLimbFromZenith(lat: float, lon: float, when: datetime) -> float:
	"""
	Direction of the bright limb as it appears to an observer: degrees counterclockwise from straight up
	(zenith), in the sky as seen from the ground. 0 = lit side up, 90 = lit side to the left (east
	when the Moon is in the south), 270 = lit side to the right. [0, 360)
	"""
	return (brightLimbAngle(lat, lon, when) - parallacticAngle(lat, lon, when))%360


def moonIllumination(lat: float, lon: float, when: datetime) -> float:
	"""Fraction of the disc that is lit, 0..1."""
	_, moon, _ = _sunMoon(lat, lon, when)
	return float(moon.phase)/100

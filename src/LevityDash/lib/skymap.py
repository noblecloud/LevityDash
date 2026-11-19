"""The night sky above a place and time: real stars, planets and the moon's light. Qt-free.

The stars are the Yale Bright Star Catalogue (``resources/data/stars.csv``, magnitude 5.8 and brighter, J2000;
see ``stars.NOTICE.md``). :func:`project` turns them into positions on a flat chart of the whole sky for a latitude,
longitude and instant: a stereographic projection centred on the zenith, north up and east to the left (the way a
star chart is held over your head), scaled so the horizon is the unit circle. Constellations come out the right shape
and turn through the night; the chart is good to a fraction of a degree (precession is applied, nutation, aberration
and refraction are not).

Colour comes from the catalogue's colour temperature (:func:`color`), size and brightness from the magnitude
(:func:`flux`). Everything here is cheap enough to run every few minutes on a slow machine.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

CATALOG = Path(__file__).resolve().parent.parent / 'resources' / 'data' / 'stars.csv'
J2000_JD = 2451545.0
#: The magnitude ``stars: true`` draws to. Under a city sky about 4.5 is honest; a dark sky shows 6.
DEFAULT_LIMIT = 5.5


@lru_cache(maxsize=1)
def catalog() -> tuple:
	"""``(ra, dec, V, K)`` for every star, angles in radians, sorted brightest first."""
	rows = []
	for line in CATALOG.read_text(encoding='utf-8').splitlines():
		if not line or line.startswith('#'):
			continue
		ra, dec, mag, kelvin = line.split(',')
		rows.append((math.radians(float(ra)), math.radians(float(dec)), float(mag), int(kelvin)))
	return tuple(rows)


def julianDay(when: datetime) -> float:
	when = when.astimezone(timezone.utc) if when.tzinfo else when.replace(tzinfo=timezone.utc)
	return when.timestamp() / 86400.0 + 2440587.5


def localSiderealTime(when: datetime, lon: float) -> float:
	"""Local mean sidereal time in radians for longitude ``lon`` (degrees east)."""
	d = julianDay(when) - J2000_JD
	return math.radians((280.46061837 + 360.98564736629 * d + lon) % 360.0)


def _precess(ra: float, dec: float, years: float) -> tuple:
	"""J2000 position moved forward ``years`` (first order, fine for decades)."""
	m, n = math.radians(46.1 / 3600), math.radians(20.04 / 3600)
	return ra + (m + n * math.sin(ra) * math.tan(dec)) * years, dec + n * math.cos(ra) * years


def horizontal(ra: float, dec: float, lst: float, lat: float) -> tuple:
	"""``(altitude, azimuth)`` in radians (azimuth from north through east) of a place on the sky."""
	hour = lst - ra
	sinAlt = math.sin(dec) * math.sin(lat) + math.cos(dec) * math.cos(lat) * math.cos(hour)
	alt = math.asin(max(-1.0, min(1.0, sinAlt)))
	az = math.atan2(-math.cos(dec) * math.sin(hour), math.sin(dec) * math.cos(lat) - math.cos(dec) * math.sin(lat) * math.cos(hour))
	return alt, az % (2 * math.pi)


def chart(alt: float, az: float) -> tuple:
	"""A sky position on the chart: stereographic about the zenith, horizon at radius 1, north up, east left."""
	r = math.tan((math.pi / 2 - alt) / 2)
	return -r * math.sin(az), -r * math.cos(az)


def project(lat: float, lon: float, when: Optional[datetime] = None, limit: float = DEFAULT_LIMIT) -> list:
	"""Every star of magnitude ``limit`` or brighter that is above the horizon, as ``(x, y, V, K)`` on :func:`chart`."""
	when = when or datetime.now(timezone.utc)
	lst, phi = localSiderealTime(when, lon), math.radians(lat)
	years = (julianDay(when) - J2000_JD) / 365.25
	out = []
	for ra, dec, mag, kelvin in catalog():
		if mag > limit:
			break
		ra, dec = _precess(ra, dec, years)
		alt, az = horizontal(ra, dec, lst, phi)
		if alt > -0.02:
			x, y = chart(alt, az)
			out.append((x, y, mag, kelvin))
	return out


def planets(lat: float, lon: float, when: Optional[datetime] = None) -> list:
	"""The naked-eye planets above the horizon as ``(x, y, magnitude, name)`` on :func:`chart`."""
	import ephem
	when = when or datetime.now(timezone.utc)
	observer = ephem.Observer()
	observer.lat, observer.lon, observer.pressure = str(lat), str(lon), 0
	observer.date = when.astimezone(timezone.utc).replace(tzinfo=None) if when.tzinfo else when
	out = []
	for body in (ephem.Venus(), ephem.Mars(), ephem.Jupiter(), ephem.Saturn(), ephem.Mercury()):
		body.compute(observer)
		if float(body.alt) > 0:
			x, y = chart(float(body.alt), float(body.az))
			out.append((x, y, float(body.mag), body.name))
	return out


def moonlight(lat: float, lon: float, when: Optional[datetime] = None) -> float:
	"""How much the moon washes the sky out, 0 (down, or new) to 1 (full and high)."""
	import ephem
	when = when or datetime.now(timezone.utc)
	observer = ephem.Observer()
	observer.lat, observer.lon, observer.pressure = str(lat), str(lon), 0
	observer.date = when.astimezone(timezone.utc).replace(tzinfo=None) if when.tzinfo else when
	moon = ephem.Moon(observer)
	if float(moon.alt) <= 0:
		return 0.0
	return (float(moon.phase) / 100.0) * math.sin(float(moon.alt)) ** 0.5


def flux(mag: float) -> float:
	"""Brightness against a magnitude-0 star (Vega), the physical ratio."""
	return 10 ** (-0.4 * mag)


def color(kelvin: int, whiteness: float = 0.55) -> tuple:
	"""A star's colour as 0-255 RGB from its colour temperature (a blackbody fit), pulled towards white by
	``whiteness`` because the eye sees starlight as nearly colourless: only a hint of blue or orange is left."""
	if kelvin <= 0:
		kelvin = 6000
	t = max(1000, min(40000, kelvin)) / 100.0
	r = 255.0 if t <= 66 else 329.698727446 * (t - 60) ** -0.1332047592
	g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * (t - 60) ** -0.0755148492
	b = 255.0 if t >= 66 else 0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
	rgb = [max(0.0, min(255.0, c)) for c in (r, g, b)]
	return tuple(int(round(c + (255 - c) * whiteness)) for c in rgb)


__all__ = ('catalog', 'chart', 'color', 'flux', 'horizontal', 'julianDay', 'localSiderealTime', 'moonlight', 'planets', 'project', 'DEFAULT_LIMIT')

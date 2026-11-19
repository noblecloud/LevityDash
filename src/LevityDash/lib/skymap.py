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


# --- the Milky Way -------------------------------------------------------------------------------------------------

NGP_RA, NGP_DEC, L_NCP = math.radians(192.85948), math.radians(27.12825), math.radians(122.93192)


def _lattice(seed: int, lstep: float, bstep: float):
	import numpy as np
	rng = np.random.RandomState(seed)
	cols, rows = int(round(360 / lstep)), int(round(80 / bstep)) + 1
	grid = rng.random_sample((rows, cols + 1))
	grid[:, cols] = grid[:, 0]  # wraps in longitude
	return grid


def _noise(l, b, seed: int, lstep: float, bstep: float):
	"""Smooth value noise over galactic longitude and latitude (degrees), 0 to 1."""
	import numpy as np
	grid = _lattice(seed, lstep, bstep)
	u = (l % 360.0) / lstep
	v = (np.clip(b, -40, 40) + 40) / bstep
	i0, j0 = np.minimum(u.astype(int), grid.shape[1] - 2), np.minimum(v.astype(int), grid.shape[0] - 2)
	fu, fv = u - i0, v - j0
	fu, fv = fu * fu * (3 - 2 * fu), fv * fv * (3 - 2 * fv)
	top = grid[j0, i0] * (1 - fu) + grid[j0, i0 + 1] * fu
	bottom = grid[j0 + 1, i0] * (1 - fu) + grid[j0 + 1, i0 + 1] * fu
	return top * (1 - fv) + bottom * fv


def galactic(ra, dec):
	"""Galactic longitude and latitude (radians) of equatorial coordinates (radians; numpy arrays or floats)."""
	import numpy as np
	d = ra - NGP_RA
	sinb = np.sin(dec) * math.sin(NGP_DEC) + np.cos(dec) * math.cos(NGP_DEC) * np.cos(d)
	y = np.cos(dec) * np.sin(d)
	x = np.sin(dec) * math.cos(NGP_DEC) - np.cos(dec) * math.sin(NGP_DEC) * np.cos(d)
	return (L_NCP - np.arctan2(y, x)) % (2 * math.pi), np.arcsin(np.clip(sinb, -1, 1))


def milkyway(lat: float, lon: float, when: Optional[datetime], x, y) -> tuple:
	"""The Milky Way at points of the chart (arrays ``x``, ``y`` as :func:`chart` gives): ``(brightness, warmth, r)``.

	The band is the galactic plane (|b| around 5 to 8 degrees thick, thickest and brightest towards the centre at
	l = 0, with a second bright reach in Cygnus and one in the south), broken up by two scales of noise and the dark
	dust of the Great Rift along the plane from Cygnus to Sagittarius. Brightness is 0 to 1, warmth 0 (blue-white arms)
	to 1 (yellow bulge); ``r`` is the distance from the zenith on the chart, so the caller can cut at the horizon."""
	import numpy as np
	when = when or datetime.now(timezone.utc)
	phi = math.radians(lat)
	lst = localSiderealTime(when, lon)
	r = np.hypot(x, y)
	alt = math.pi / 2 - 2 * np.arctan(r)
	az = np.arctan2(-x, -y)
	sinDec = math.sin(phi) * np.sin(alt) + math.cos(phi) * np.cos(alt) * np.cos(az)
	dec = np.arcsin(np.clip(sinDec, -1, 1))
	h = np.arctan2(-np.cos(alt) * np.sin(az), math.cos(phi) * np.sin(alt) - math.sin(phi) * np.cos(alt) * np.cos(az))
	l, b = galactic(lst - h, dec)
	l, b = np.degrees(l), np.degrees(b)
	lw = (l + 180.0) % 360.0 - 180.0
	bulge = np.exp(-(lw / 55.0) ** 2)
	width = 4.5 + 4.5 * bulge
	band = np.exp(-0.5 * (b / width) ** 2)
	reach = np.maximum.reduce([0.22 + 0.78 * np.exp(-(lw / 60.0) ** 2), 0.62 * np.exp(-((lw - 80.0) / 32.0) ** 2) + 0.2, 0.55 * np.exp(-((lw + 95.0) / 35.0) ** 2) + 0.2])
	broad = _noise(l, b, 11, 14.0, 5.0)
	fine = _noise(l, b, 23, 4.0, 1.6)
	mottle = (0.45 + 0.9 * broad) * (0.65 + 0.7 * fine)
	rift = np.exp(-(((b - 0.8) / 1.7) ** 2)) * np.clip((lw + 12.0) / 14.0, 0, 1) * np.clip((62.0 - lw) / 22.0, 0, 1)
	dust = 1.0 - 0.7 * rift * (0.45 + 0.55 * _noise(l, b, 37, 6.0, 2.0))
	brightness = np.clip(band * reach * mottle * dust * 0.95, 0.0, 1.0)
	warmth = np.clip(bulge * 1.2, 0.0, 1.0)
	return brightness, warmth, r


__all__ = ('galactic', 'milkyway', 'catalog', 'chart', 'color', 'flux', 'horizontal', 'julianDay', 'localSiderealTime', 'moonlight', 'planets', 'project', 'DEFAULT_LIMIT')

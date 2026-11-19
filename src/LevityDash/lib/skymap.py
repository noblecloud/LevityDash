"""The night sky above a place and time: real stars, planets and the moon's light. Qt-free.

The stars are the HYG database (``resources/data/stars.npy``, every star of magnitude 8 and brighter, about 41,000,
J2000; see ``NOTICE.md`` there). :func:`project` turns them into positions on a flat chart of the whole sky for a
latitude, longitude and instant: a stereographic projection centred on the zenith, north up and east to the left (the
way a star chart is held over your head), scaled so the horizon is the unit circle. Constellations come out the right
shape and turn through the night; the chart is good to a fraction of a degree (precession is applied, nutation,
aberration and refraction are not).

Colour comes from the B-V colour index through a colour temperature (:func:`kelvin`, :func:`color`), size and
brightness from the magnitude (:func:`flux`). Everything is numpy over the whole catalogue at once, cheap enough to run
every few minutes on a slow machine.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np

CATALOG = Path(__file__).resolve().parent.parent / 'resources' / 'data' / 'stars.npy'
J2000_JD = 2451545.0
#: The magnitude ``stars: true`` stands for: the naked-eye limit under a fairly dark sky. Fainter stars, to
#: :data:`FAINTEST`, are drawn too, as the dust a long exposure picks up, but this is what twilight, cloud and the moon
#: take away from.
DEFAULT_LIMIT = 5.5
FAINTEST = 8.0


@lru_cache(maxsize=1)
def catalog() -> tuple:
	"""``(ra, dec, V, B-V)`` arrays for every star, angles in radians, sorted brightest first.

	The file packs each star in six bytes: right ascension as a 16 bit fraction of the circle, declination as a signed
	16 bit fraction of 90 degrees, magnitude in 1/25ths from -2 and B-V in 1/50ths."""
	raw = np.load(CATALOG)
	ra = raw['ra'].astype(np.float64) * (2 * math.pi / 65536)
	dec = raw['dec'].astype(np.float64) * (math.pi / 2 / 32767)
	mag = raw['mag'].astype(np.float64) / 25.0 - 2.0
	bv = raw['ci'].astype(np.float64) / 50.0
	return ra, dec, mag, bv


def julianDay(when: datetime) -> float:
	when = when.astimezone(timezone.utc) if when.tzinfo else when.replace(tzinfo=timezone.utc)
	return when.timestamp() / 86400.0 + 2440587.5


def localSiderealTime(when: datetime, lon: float) -> float:
	"""Local mean sidereal time in radians for longitude ``lon`` (degrees east)."""
	d = julianDay(when) - J2000_JD
	return math.radians((280.46061837 + 360.98564736629 * d + lon) % 360.0)


def _precess(ra, dec, years: float) -> tuple:
	"""J2000 position moved forward ``years`` (first order, fine for decades). Floats or arrays."""
	m, n = math.radians(46.1 / 3600), math.radians(20.04 / 3600)
	return ra + (m + n * np.sin(ra) * np.tan(dec)) * years, dec + n * np.cos(ra) * years


def horizontal(ra, dec, lst: float, lat: float) -> tuple:
	"""``(altitude, azimuth)`` in radians (azimuth from north through east) of a place on the sky. Floats or arrays."""
	hour = lst - ra
	sinAlt = np.sin(dec) * math.sin(lat) + np.cos(dec) * math.cos(lat) * np.cos(hour)
	alt = np.arcsin(np.clip(sinAlt, -1.0, 1.0))
	az = np.arctan2(-np.cos(dec) * np.sin(hour), np.sin(dec) * math.cos(lat) - np.cos(dec) * math.sin(lat) * np.cos(hour))
	return alt, az % (2 * math.pi)


def chart(alt, az) -> tuple:
	"""A sky position on the chart: stereographic about the zenith, horizon at radius 1, north up, east left."""
	r = np.tan((math.pi / 2 - alt) / 2)
	return -r * np.sin(az), -r * np.cos(az)


def unchart(x, y, lat: float, lst: float) -> tuple:
	"""The inverse of :func:`chart` and :func:`horizontal`: ``(ra, dec, alt)`` in radians at chart points ``x``, ``y``."""
	r = np.hypot(x, y)
	alt = math.pi / 2 - 2 * np.arctan(r)
	az = np.arctan2(-x, -y)
	sinDec = math.sin(lat) * np.sin(alt) + math.cos(lat) * np.cos(alt) * np.cos(az)
	dec = np.arcsin(np.clip(sinDec, -1, 1))
	hour = np.arctan2(-np.cos(alt) * np.sin(az), math.cos(lat) * np.sin(alt) - math.sin(lat) * np.cos(alt) * np.cos(az))
	return lst - hour, dec, alt


def airmass(alt):
	"""How much air the light crosses at altitude ``alt`` (radians), 1 at the zenith, about 38 at the horizon (Kasten and Young)."""
	h = np.degrees(np.maximum(alt, 0.0))
	return 1.0 / (np.sin(np.radians(h)) + 0.50572 * (h + 6.07995) ** -1.6364)


def project(lat: float, lon: float, when: Optional[datetime] = None, limit: float = DEFAULT_LIMIT) -> tuple:
	"""Every star of magnitude ``limit`` or brighter that is above the horizon, as arrays ``(x, y, V, B-V)`` on
	:func:`chart`, brightest first."""
	when = when or datetime.now(timezone.utc)
	lst, phi = localSiderealTime(when, lon), math.radians(lat)
	years = (julianDay(when) - J2000_JD) / 365.25
	ra, dec, mag, bv = catalog()
	n = int(np.searchsorted(mag, limit, side='right'))
	ra, dec = _precess(ra[:n], dec[:n], years)
	alt, az = horizontal(ra, dec, lst, phi)
	up = alt > -0.02
	x, y = chart(alt[up], az[up])
	return x, y, mag[:n][up], bv[:n][up]


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


def kelvin(bv):
	"""Colour temperature from the B-V colour index (Ballesteros 2012). Floats or arrays."""
	bv = np.clip(bv, -0.4, 2.0)
	return 4600.0 * (1.0 / (0.92 * bv + 1.7) + 1.0 / (0.92 * bv + 0.62))


def color(kelvin: float, whiteness: float = 0.55) -> tuple:
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


def galactic(ra, dec):
	"""Galactic longitude and latitude (radians) of equatorial coordinates (radians; numpy arrays or floats)."""
	d = ra - NGP_RA
	sinb = np.sin(dec) * math.sin(NGP_DEC) + np.cos(dec) * math.cos(NGP_DEC) * np.cos(d)
	y = np.cos(dec) * np.sin(d)
	x = np.sin(dec) * math.cos(NGP_DEC) - np.cos(dec) * math.sin(NGP_DEC) * np.cos(d)
	return (L_NCP - np.arctan2(y, x)) % (2 * math.pi), np.arcsin(np.clip(sinb, -1, 1))


def galacticChart(lat: float, lon: float, when: Optional[datetime], x, y) -> tuple:
	"""Galactic longitude and latitude (degrees) and altitude (radians) at points of the chart (arrays ``x``, ``y`` as
	:func:`chart` gives), for looking the Milky Way up in a map of it."""
	when = when or datetime.now(timezone.utc)
	ra, dec, alt = unchart(x, y, math.radians(lat), localSiderealTime(when, lon))
	l, b = galactic(ra, dec)
	return np.degrees(l), np.degrees(b), alt


__all__ = ('airmass', 'galactic', 'galacticChart', 'catalog', 'chart', 'color', 'flux', 'horizontal', 'julianDay', 'kelvin', 'localSiderealTime', 'moonlight', 'planets', 'project', 'unchart', 'DEFAULT_LIMIT', 'FAINTEST')

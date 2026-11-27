"""Where a weather map gets its pictures and numbers. No Qt: plain functions that block, meant for a worker thread.

- **Base map**: Esri's grey canvas tiles (no key), read as land and sea and redrawn in the dashboard's own colours.
- **Radar**: RainViewer's composite of national radars, worldwide, no key. Its tiles arrive already coloured, so
  `palette.rainviewerIntensity` reads the colour back as an echo strength and the item paints that in our palette.
- **Fields** (temperature, wind, cloud): one Open-Meteo request for a coarse grid of points over the view. No key either.

Tiles are kept on disk (`<cache>/maps/`) so a restart, or a second map, does not ask again.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

__all__ = [
	'BASEMAPS', 'Basemap', 'Frame', 'FieldGrid', 'basemapUrl', 'cacheDirectory', 'fetch', 'radarFrames', 'radarUrl',
	'parseRadarIndex', 'fieldUrl', 'parseFields', 'fetchFields', 'FIELDS', 'RADAR_MAX_ZOOM',
]

USER_AGENT = 'LevityDash (weather map; https://github.com/noblecloud/LevityDash)'
TIMEOUT = 15.0
RADAR_INDEX = 'https://api.rainviewer.com/public/weather-maps.json'
#: The free RainViewer tiles stop at this zoom; deeper views stretch the zoom-7 tile.
RADAR_MAX_ZOOM = 7


@dataclass(frozen=True)
class Basemap:
	name: str
	template: str  #: `{z}/{x}/{y}` the tile, `{s}` a subdomain, `{r}` the retina suffix `@2x`
	max_zoom: int
	dark: bool  #: the tile is drawn light-on-dark, which decides how it is tinted
	attribution: str = 'Esri, HERE, Garmin, © OpenStreetMap contributors'
	subdomains: tuple[str, ...] = ('a',)
	#: the grey of the sea and of the land in the tile, 0..1 luma; the item stretches them across the theme's colours
	water: float = 0.0
	land: float = 1.0


_ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/{name}/MapServer/tile/{{z}}/{{y}}/{{x}}'

#: Esri's grey canvas maps: no key, made to sit under data. (CARTO's equivalents now want an API key; give `tiles:` a
#: template to use those, or any other XYZ source, instead.)
BASEMAPS: dict[str, Basemap] = {
	'dark': Basemap('dark', _ESRI.format(name='World_Dark_Gray_Base'), 16, True, water=0.138, land=0.256),
	'light': Basemap('light', _ESRI.format(name='World_Light_Gray_Base'), 16, False, water=0.814, land=0.938),
	'dark-labels': Basemap('dark-labels', _ESRI.format(name='World_Dark_Gray_Reference'), 16, True),
	'light-labels': Basemap('light-labels', _ESRI.format(name='World_Light_Gray_Reference'), 16, False),
}


def basemapUrl(base: Basemap, z: int, x: int, y: int, retina: bool = False) -> str:
	"""The URL of one base-map tile; the subdomain is picked from the tile so a tile always asks the same host."""
	sub = base.subdomains[(x + y) % len(base.subdomains)]
	return base.template.format(s=sub, z=z, x=x, y=y, r='@2x' if retina else '')


def cacheDirectory() -> Path:
	"""Where tiles are kept. `LEVITY_MAP_CACHE` overrides it (tests, and a read-only home)."""
	if override := os.environ.get('LEVITY_MAP_CACHE'):
		return Path(override)
	from LevityDash import LevityDashboard
	return Path(LevityDashboard.paths.user_cache_dir) / 'maps'


def fetch(url: str, ttl: float = 0.0, directory: Optional[Path] = None, timeout: float = TIMEOUT) -> bytes:
	"""The bytes at `url`, from disk when a copy younger than `ttl` seconds is there. Raises on a failed request."""
	directory = directory or cacheDirectory()
	path = None
	if ttl > 0:
		path = directory / (hashlib.sha1(url.encode()).hexdigest() + '.bin')
		try:
			if time.time() - path.stat().st_mtime < ttl:
				return path.read_bytes()
		except OSError:
			pass
	request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
	with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - https URLs built in this file
		body = response.read()
	if path is not None:
		try:
			directory.mkdir(parents=True, exist_ok=True)
			tmp = path.with_suffix('.tmp')
			tmp.write_bytes(body)
			tmp.replace(path)
		except OSError:
			pass  # a full or read-only disk only costs the next request
	return body


# -- radar ----------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Frame:
	"""One radar picture: when it is for and where its tiles are."""
	time: int  #: unix seconds
	path: str
	host: str
	forecast: bool = False


def parseRadarIndex(text: str | bytes) -> list[Frame]:
	"""The frames in RainViewer's `weather-maps.json`, oldest first. Nowcast frames, when offered, come last."""
	data = json.loads(text)
	host = data.get('host') or 'https://tilecache.rainviewer.com'
	radar = data.get('radar') or {}
	frames = [Frame(int(f['time']), f['path'], host) for f in radar.get('past') or []]
	frames += [Frame(int(f['time']), f['path'], host, True) for f in radar.get('nowcast') or []]
	return sorted(frames, key=lambda f: f.time)


def radarFrames() -> list[Frame]:
	return parseRadarIndex(fetch(RADAR_INDEX, timeout=TIMEOUT))


def radarUrl(frame: Frame, z: int, x: int, y: int) -> str:
	"""A radar tile. The `2` and `1_0` ask for the service's smoothed picture; it ignores them if it cannot."""
	return f'{frame.host}{frame.path}/256/{z}/{x}/{y}/2/1_0.png'


# -- fields ---------------------------------------------------------------------------------------------------------

#: The fields one request brings back: name -> Open-Meteo's name for it.
FIELDS = {
	'temperature': 'temperature_2m',
	'wind': 'wind_speed_10m',
	'direction': 'wind_direction_10m',
	'clouds': 'cloud_cover',
}


@dataclass
class FieldGrid:
	"""Values on a `rows` x `columns` grid laid evenly across a view, plus when they are from."""
	values: dict[str, np.ndarray]  #: name -> `(rows, columns)` floats, NaN where the service gave nothing
	time: Optional[int] = None


def fieldUrl(points: list[list[tuple[float, float]]]) -> str:
	flat = [p for row in points for p in row]
	lats = ','.join(f'{lat:.3f}' for lat, _ in flat)
	lons = ','.join(f'{lon:.3f}' for _, lon in flat)
	current = ','.join(FIELDS.values())
	return (
		f'https://api.open-meteo.com/v1/forecast?latitude={lats}&longitude={lons}&current={current}'
		f'&wind_speed_unit=ms&temperature_unit=celsius&timeformat=unixtime'
	)


def parseFields(text: str | bytes, rows: int, columns: int) -> FieldGrid:
	"""Open-Meteo's answer (a list with one entry per point, or one entry for one point) as grids."""
	data = json.loads(text)
	if isinstance(data, dict):
		if data.get('error'):
			raise ValueError(f'Open-Meteo: {data.get("reason", "request refused")}')
		data = [data]
	if len(data) != rows*columns:
		raise ValueError(f'Open-Meteo gave {len(data)} points for a {columns}x{rows} grid')
	values = {name: np.full(rows*columns, np.nan) for name in FIELDS}
	stamp = None
	for i, point in enumerate(data):
		current = point.get('current') or {}
		stamp = stamp or current.get('time')
		for name, source in FIELDS.items():
			value = current.get(source)
			if value is not None:
				values[name][i] = value
	return FieldGrid({name: array.reshape(rows, columns) for name, array in values.items()}, stamp)


def fetchFields(points: list[list[tuple[float, float]]], ttl: float = 600.0) -> FieldGrid:
	body = fetch(fieldUrl(points), ttl=ttl)
	return parseFields(body, len(points), len(points[0]))

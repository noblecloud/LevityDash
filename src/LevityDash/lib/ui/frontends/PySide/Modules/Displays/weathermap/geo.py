"""Web-Mercator geometry for slippy-map tiles. Plain Python, no Qt.

A *world pixel* is a position on the whole map at a zoom, in units of tiles: at zoom `z` the map is `2**z` tiles
across, and `(x, y)` counts tiles from the north-west corner. Fractional zoom is fine; tiles are fetched at a whole
zoom and drawn scaled.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ['MAX_LAT', 'toWorld', 'toLonLat', 'Viewport', 'TileSpot']

#: Web Mercator stops here; the poles are infinitely far away.
MAX_LAT = 85.0511287798066


def toWorld(lat: float, lon: float, zoom: float) -> tuple[float, float]:
	"""`(x, y)` in tiles from the north-west corner of the map at `zoom`."""
	lat = max(-MAX_LAT, min(MAX_LAT, lat))
	n = 2.0**zoom
	x = (lon + 180.0)/360.0*n
	rad = math.radians(lat)
	y = (1.0 - math.asinh(math.tan(rad))/math.pi)/2.0*n
	return x, y


def toLonLat(x: float, y: float, zoom: float) -> tuple[float, float]:
	"""`(lat, lon)` of a world position in tiles at `zoom`."""
	n = 2.0**zoom
	lon = x/n*360.0 - 180.0
	lat = math.degrees(math.atan(math.sinh(math.pi*(1.0 - 2.0*y/n))))
	return lat, lon


@dataclass(frozen=True)
class TileSpot:
	"""One tile and where it lands on the item: `left`, `top` and `size` are in item pixels."""
	z: int
	x: int
	y: int
	left: float
	top: float
	size: float

	@property
	def key(self) -> tuple[int, int, int]:
		return self.z, self.x, self.y


@dataclass(frozen=True)
class Viewport:
	"""What the map shows: a centre, a zoom and the size of the item in pixels."""
	lat: float
	lon: float
	zoom: float
	width: float
	height: float

	#: Pixels one tile spans on screen at whole-number zoom. A map reads best near this.
	TILE = 256.0

	def tileZoom(self, limit: int = 19) -> int:
		"""The whole zoom to fetch tiles at: the nearest to `zoom`, no deeper than `limit`."""
		return max(0, min(limit, int(math.floor(self.zoom + 0.5))))

	def origin(self, zoom: int) -> tuple[float, float]:
		"""The world position, in tiles at `zoom`, of the item's top-left corner."""
		cx, cy = toWorld(self.lat, self.lon, zoom)
		size = self.TILE*2.0**(self.zoom - zoom)  # a tile of this zoom on screen
		return cx - self.width/2.0/size, cy - self.height/2.0/size

	def tiles(self, limit: int = 19) -> list[TileSpot]:
		"""The tiles that cover the item, nearest the centre first, with where each is drawn."""
		z = self.tileZoom(limit)
		size = self.TILE*2.0**(self.zoom - z)
		ox, oy = self.origin(z)
		n = 2**z
		first_x, last_x = math.floor(ox), math.floor(ox + self.width/size)
		first_y, last_y = max(0, math.floor(oy)), min(n - 1, math.floor(oy + self.height/size))
		spots = []
		for ty in range(first_y, last_y + 1):
			for tx in range(first_x, last_x + 1):
				spots.append(TileSpot(z, tx % n, ty, (tx - ox)*size, (ty - oy)*size, size))
		cx, cy = self.width/2.0, self.height/2.0
		spots.sort(key=lambda s: (s.left + s.size/2.0 - cx)**2 + (s.top + s.size/2.0 - cy)**2)
		return spots

	def project(self, lat: float, lon: float) -> tuple[float, float]:
		"""Item pixels of a place."""
		z = self.zoom
		cx, cy = toWorld(self.lat, self.lon, z)
		x, y = toWorld(lat, lon, z)
		n = 2.0**z
		dx = x - cx
		if dx > n/2:  # the short way across the date line
			dx -= n
		elif dx < -n/2:
			dx += n
		return self.width/2.0 + dx*self.TILE, self.height/2.0 + (y - cy)*self.TILE

	def unproject(self, px: float, py: float) -> tuple[float, float]:
		"""`(lat, lon)` under an item pixel."""
		z = self.zoom
		cx, cy = toWorld(self.lat, self.lon, z)
		lat, lon = toLonLat(cx + (px - self.width/2.0)/self.TILE, cy + (py - self.height/2.0)/self.TILE, z)
		return lat, ((lon + 180.0) % 360.0) - 180.0

	def grid(self, columns: int, rows: int) -> list[list[tuple[float, float]]]:
		"""`rows` lists of `columns` `(lat, lon)` points, evenly spaced across the item *in pixels* (so evenly in Mercator).

		A field sampled here lands on the picture with a plain linear stretch.
		"""
		return [
			[self.unproject(self.width*c/(columns - 1), self.height*r/(rows - 1)) for c in range(columns)]
			for r in range(rows)
		]

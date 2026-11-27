"""Colour for weather maps: ramps written in Oklch, baked into 256-entry lookup tables.

Qt-free (numpy only), so the maths is testable without a display. Every ramp is a short list of
stops `(t, L, C, h, alpha)` in Oklch: lightness, chroma, hue in degrees and opacity at position
`t` in 0..1. Between stops `L`, `C` and alpha mix straight and the hue turns the short way round, so
a ramp stays vivid through the middle where an sRGB mix would go muddy. `lut()` bakes a ramp into
`(256, 4)` straight-alpha bytes, and `colorize()` pushes a field of values through one.

The look is original: light things are airy and nearly see-through, heavy things are saturated and
opaque, and the hot end stays in the neon family of the rest of the dashboards (magenta only near the
top). The lightness is chosen to sit on a dark sky and on a pale one.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional, Sequence

import numpy as np

from LevityDash.lib.ui.colors import comfort
from LevityDash.lib.ui.colors.oklch import oklch_srgb

__all__ = ['Stop', 'RAMPS', 'ramp', 'lut', 'colorize', 'temperatureRamp', 'rainviewerIntensity', 'swatch']

#: `(t, L, C, h, alpha)`
Stop = tuple[float, float, float, float, float]

#: Precipitation, from the first trace of drizzle to a hail core. `t` is the fraction of the reflectivity scale.
PRECIP: tuple[Stop, ...] = (
	(0.00, 0.84, 0.060, 200, 0.00),
	(0.03, 0.88, 0.110, 195, 0.50),
	(0.16, 0.82, 0.150, 208, 0.78),
	(0.34, 0.70, 0.170, 235, 0.76),
	(0.52, 0.58, 0.220, 270, 0.86),
	(0.70, 0.60, 0.260, 320, 0.92),
	(0.88, 0.78, 0.190, 40, 0.95),
	(1.00, 0.95, 0.120, 95, 0.98),
)

#: Wind speed, still air to a gale. `t` is the fraction of `range`.
WIND: tuple[Stop, ...] = (
	(0.00, 0.80, 0.060, 200, 0.00),
	(0.12, 0.84, 0.100, 195, 0.14),
	(0.35, 0.84, 0.150, 160, 0.58),
	(0.55, 0.88, 0.170, 105, 0.74),
	(0.75, 0.76, 0.190, 55, 0.82),
	(1.00, 0.64, 0.250, 15, 0.92),
)

#: Cloud cover, clear to overcast: cool white that thickens.
CLOUDS: tuple[Stop, ...] = (
	(0.00, 0.97, 0.008, 250, 0.00),
	(0.30, 0.96, 0.012, 250, 0.22),
	(0.65, 0.93, 0.020, 255, 0.56),
	(1.00, 0.88, 0.030, 260, 0.86),
)

RAMPS: dict[str, tuple[Stop, ...]] = {'precip': PRECIP, 'wind': WIND, 'clouds': CLOUDS}


def _mix_hue(a: float, b: float, f: float) -> float:
	delta = ((b - a + 180.0) % 360.0) - 180.0
	return (a + delta*f) % 360.0


def ramp(stops: Sequence[Stop], t: float) -> tuple[float, float, float, float]:
	"""`(r, g, b, a)` in 0..1 (encoded sRGB, straight alpha) at position `t` along `stops`."""
	stops = sorted(stops, key=lambda s: s[0])
	t = min(max(t, stops[0][0]), stops[-1][0])
	for low, high in zip(stops, stops[1:]):
		if t <= high[0]:
			span = (high[0] - low[0]) or 1.0
			f = (t - low[0])/span
			L = low[1] + (high[1] - low[1])*f
			C = low[2] + (high[2] - low[2])*f
			h = _mix_hue(low[3], high[3], f)
			a = low[4] + (high[4] - low[4])*f
			r, g, b = oklch_srgb(L, C, h)
			return r, g, b, a
	last = stops[-1]
	r, g, b = oklch_srgb(last[1], last[2], last[3])
	return r, g, b, last[4]


@lru_cache(maxsize=32)
def _lut(stops: tuple[Stop, ...], size: int) -> np.ndarray:
	table = np.empty((size, 4), dtype=np.uint8)
	for i in range(size):
		r, g, b, a = ramp(stops, i/(size - 1))
		table[i] = (round(r*255), round(g*255), round(b*255), round(a*255))
	table.setflags(write=False)
	return table


def lut(stops: Sequence[Stop], size: int = 256) -> np.ndarray:
	"""`stops` baked into a read-only `(size, 4)` uint8 table of straight-alpha RGBA."""
	return _lut(tuple(tuple(s) for s in stops), size)


def colorize(values: np.ndarray, table: np.ndarray, lo: float = 0.0, hi: float = 1.0, opacity: float = 1.0) -> np.ndarray:
	"""A field of values as `(h, w, 4)` RGBA bytes: each value goes to `table` at `(v - lo)/(hi - lo)`.

	NaN is fully transparent. `opacity` scales the table's own alpha.
	"""
	values = np.asarray(values, dtype=np.float64)
	span = (hi - lo) or 1.0
	t = (values - lo)/span
	bad = ~np.isfinite(t)
	index = np.clip(np.nan_to_num(t, nan=0.0)*(len(table) - 1) + 0.5, 0, len(table) - 1).astype(np.intp)
	out = table[index].copy()
	if opacity != 1.0:
		out[..., 3] = np.clip(out[..., 3]*float(opacity), 0, 255).astype(np.uint8)
	out[bad, 3] = 0
	return out


# -- temperature ------------------------------------------------------------------------------------------------

#: `(°C on the built-in scale, L, C, h, alpha)`. The two stops at the comfort band's edges slide with `[Comfort]`
#: (`comfort.shift`), so the quiet middle of the map is always the range you call comfortable.
_TEMPERATURE: tuple[tuple[float, float, float, float, float], ...] = (
	(-30.0, 0.60, 0.200, 300, 0.86),
	(-15.0, 0.62, 0.200, 270, 0.86),
	(-2.0, 0.74, 0.150, 225, 0.84),
	(comfort.DEFAULT_LOW, 0.84, 0.120, 175, 0.74),
	(comfort.DEFAULT_HIGH, 0.88, 0.150, 120, 0.74),
	(30.0, 0.82, 0.190, 75, 0.84),
	(37.0, 0.70, 0.240, 38, 0.88),
	(45.0, 0.62, 0.260, 8, 0.90),
	(52.0, 0.58, 0.240, 340, 0.92),
)


def temperatureRamp(low: Optional[float] = None, high: Optional[float] = None) -> tuple[tuple[Stop, ...], float, float]:
	"""`(stops, lo, hi)`: the temperature ramp for a comfort band, and the °C its ends stand for.

	Without `low` and `high` the band comes from `[Comfort]` in the user's config.
	"""
	if low is None or high is None:
		low, high = comfort.configured()
	celsius = [comfort.shift(c, low, high) for c, *_ in _TEMPERATURE]
	lo, hi = celsius[0], celsius[-1]
	stops = tuple(((c - lo)/(hi - lo), L, C, h, a) for c, (_, L, C, h, a) in zip(celsius, _TEMPERATURE))
	return stops, lo, hi


# -- RainViewer ---------------------------------------------------------------------------------------------------

#: The 73 colours RainViewer's tiles use, weakest echo first. The service paints a fixed scheme, so to draw its data in
#: another palette the colour is mapped back to its place on this scale.
def _build_rainviewer() -> np.ndarray:
	faint = [  # a sandy grey that gains opacity: (r, g, b, alpha)
		(99, 97, 89, 20), (102, 99, 90, 25), (105, 102, 92, 30), (108, 104, 93, 36), (111, 107, 95, 41),
		(114, 110, 97, 46), (117, 112, 98, 52), (120, 115, 100, 57), (124, 117, 101, 62), (127, 120, 103, 68),
		(130, 123, 105, 73), (133, 125, 106, 78), (136, 128, 108, 84), (139, 130, 109, 89), (142, 133, 111, 94),
		(146, 136, 113, 100), (158, 147, 117, 110), (170, 158, 121, 120), (182, 169, 126, 130),
		(194, 180, 130, 140), (206, 192, 135, 150), (210, 196, 139, 160), (214, 200, 143, 170),
		(218, 204, 147, 180), (222, 208, 151, 190),
	]
	blues = [(136, 221, 238), (108, 209, 235), (81, 197, 232), (54, 186, 229), (27, 174, 226), (0, 163, 224),
		(0, 154, 213), (0, 145, 202), (0, 136, 191), (0, 127, 180), (0, 119, 170), (0, 112, 163), (0, 105, 156),
		(0, 98, 149), (0, 91, 142), (0, 85, 136), (0, 81, 128), (0, 78, 120), (0, 74, 112), (0, 71, 104)]
	warm = [(255, 238, 0), (255, 224, 0), (255, 210, 0), (255, 197, 0), (255, 183, 0), (255, 170, 0), (255, 159, 0),
		(255, 149, 0), (255, 139, 0), (255, 129, 0), (255, 68, 0), (242, 54, 0), (230, 40, 0), (217, 27, 0),
		(205, 13, 0), (193, 0, 0), (168, 0, 0), (143, 0, 0), (118, 0, 0), (93, 0, 0)]
	hot = [(255, 170, 255), (255, 159, 255), (255, 139, 255), (255, 129, 255), (255, 119, 255), (255, 108, 255),
		(255, 255, 255)]
	rows = faint + [(*c, 255) for c in blues + warm + hot]
	return np.array(rows, dtype=np.int16)


_RAINVIEWER = _build_rainviewer()
#: Where the service's colours sit on the 0..1 scale. Its sandy greys are 25 of the 72 colours but only drizzle, so the
#: groups (greys, blues, yellow to red, pinks) are given the share of the scale they deserve, not the share of the table.
_RANK = [0, 24, 25, 44, 45, 64, 65, 71]
_SCALE = [0.02, 0.16, 0.18, 0.52, 0.54, 0.86, 0.88, 1.0]


def rainviewerIntensity(rgba: np.ndarray) -> np.ndarray:
	"""Where each pixel of a RainViewer tile sits on the echo scale: `(h, w)` floats in 0..1, 0 where it is clear.

	`rgba` is `(h, w, 4)` bytes. A colour that is not one of the service's (a resampled edge) goes to its nearest.
	"""
	rgba = np.ascontiguousarray(rgba, dtype=np.uint8)
	h, w = rgba.shape[:2]
	packed = rgba.reshape(-1, 4).view(np.uint32).reshape(-1)
	unique, inverse = np.unique(packed, return_inverse=True)
	colors = unique.view(np.uint8).reshape(-1, 4).astype(np.int16)
	# alpha counts more than a channel does: it is what tells the sandy greys apart
	weight = np.array([1, 1, 1, 2], dtype=np.int32)
	diff = (colors[:, None, :] - _RAINVIEWER[None, :, :]).astype(np.int32)
	nearest = ((diff*diff)*weight).sum(axis=2).argmin(axis=1)
	scale = np.interp(nearest, _RANK, _SCALE)
	scale[colors[:, 3] == 0] = 0.0
	return scale[inverse].reshape(h, w).astype(np.float32)


def swatch(stops: Sequence[Stop], count: int = 5) -> list[str]:
	"""`count` hex colours along a ramp, light to heavy, for documentation and tests."""
	out = []
	for i in range(count):
		r, g, b, _ = ramp(stops, i/max(1, count - 1))
		out.append('#%02x%02x%02x' % (round(r*255), round(g*255), round(b*255)))
	return out


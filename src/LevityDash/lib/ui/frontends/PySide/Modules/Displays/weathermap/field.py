"""Turning a coarse grid of numbers into a smooth picture. numpy only, no Qt."""
from __future__ import annotations

import numpy as np

__all__ = ['upsample', 'fillGaps', 'wrapDegrees']


def _catmull_rom(p0, p1, p2, p3, f):
	f2, f3 = f*f, f*f*f
	return 0.5*((2*p1) + (-p0 + p2)*f + (2*p0 - 5*p1 + 4*p2 - p3)*f2 + (-p0 + 3*p1 - 3*p2 + p3)*f3)


def _along(grid: np.ndarray, count: int, axis: int) -> np.ndarray:
	"""Resample `grid` to `count` samples along `axis` with a Catmull-Rom spline through every grid value."""
	n = grid.shape[axis]
	if n == 1:
		return np.repeat(grid, count, axis=axis)
	pos = np.linspace(0, n - 1, count)
	i1 = np.minimum(np.floor(pos).astype(int), n - 2)
	f = pos - i1
	idx = [np.clip(i1 + k, 0, n - 1) for k in (-1, 0, 1, 2)]
	take = [np.take(grid, i, axis=axis) for i in idx]
	shape = [1, 1]
	shape[axis] = count
	return _catmull_rom(*take, f.reshape(shape))


def fillGaps(grid: np.ndarray) -> np.ndarray:
	"""`grid` with NaN replaced by the mean of what is there, so one missing point cannot blank the map."""
	grid = np.asarray(grid, dtype=np.float64)
	bad = ~np.isfinite(grid)
	if not bad.any():
		return grid
	if bad.all():
		return grid
	out = grid.copy()
	out[bad] = grid[~bad].mean()
	return out


def upsample(grid: np.ndarray, height: int, width: int) -> np.ndarray:
	"""A smooth `(height, width)` picture from a `(rows, columns)` grid. Values pass through the grid's own points.

	The spline can overshoot between points; it is clipped to the grid's own range so a map never claims a
	temperature nobody measured.
	"""
	grid = fillGaps(grid)
	low, high = float(grid.min()), float(grid.max())
	out = _along(_along(grid, width, 1), height, 0)
	return np.clip(out, low, high)


def wrapDegrees(delta):
	"""Difference of two compass bearings folded into -180..180."""
	return (np.asarray(delta) + 180.0) % 360.0 - 180.0

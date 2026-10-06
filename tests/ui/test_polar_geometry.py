"""The arithmetic behind the polar plots: pure, so these are small and exact."""
from datetime import datetime, timedelta

import pytest

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.geometry import (
	angleScale, bezierThrough, clockAngle, compassName, niceSpeedEdges, niceStep, parseWindow, polarPoint,
	roseBins, windowBounds,
)


def test_compass_names_round_to_the_nearest_point():
	assert [compassName(d) for d in (0, 11, 12, 349, 90, 225)] == ['N', 'N', 'NNE', 'N', 'E', 'SW']
	assert compassName(23, 8) == 'NE'
	assert compassName(44, 4) == 'N' and compassName(46, 4) == 'E'
	with pytest.raises(ValueError):
		compassName(10, 5)


def test_a_point_at_zero_degrees_is_straight_up_and_90_is_right():
	assert polarPoint(10, 10, 5, 0) == pytest.approx((10, 5))
	assert polarPoint(10, 10, 5, 90) == pytest.approx((15, 10))


def test_a_24_hour_face_puts_noon_or_midnight_on_top():
	assert [clockAngle(h) for h in (0, 6, 12, 18)] == [180, 270, 0, 90]
	assert [clockAngle(h, top='midnight') for h in (0, 6, 12)] == [0, 90, 180]
	assert clockAngle(3, 12) == 90 and clockAngle(15, 12) == 90


def test_the_angle_scale_wraps_so_359_and_one_are_neighbours():
	scale = angleScale('direction')
	assert scale.toT(360) == 0 and scale.toT(450) == pytest.approx(0.25)
	assert angleScale('clock12').span == 12


def test_nice_steps_are_round():
	assert niceStep(22, 4) == 10 and niceStep(9, 4) == 2.5 and niceStep(0.37, 4) == 0.1
	assert niceSpeedEdges(22) == [0.0, 5.0, 10.0, 15.0, 20.0, 25.0]
	assert niceSpeedEdges(0) == [0.0, 1.0]


def test_a_rose_counts_each_sample_once_and_north_straddles_zero():
	rose = roseBins([350, 10, 90, 180], [5, 5, 10, 0], edges=[0, 6, 12])
	assert rose.samples == 4 and rose.calm == 0.25
	assert rose.share[0] == pytest.approx((0.5, 0.0, 0.0))
	assert rose.share[4] == pytest.approx((0.0, 0.25, 0.0))
	assert rose.dominant == 0
	assert sum(rose.sectorTotals) + rose.calm == pytest.approx(1.0)


def test_a_rose_skips_samples_missing_a_half():
	assert roseBins([10, None, 20], [5, 5, None]).samples == 1
	assert roseBins([], []).dominant is None


def test_a_closed_curve_runs_back_to_its_start():
	points = [(0, 0), (1, 1), (2, 0), (1, -1)]
	assert len(bezierThrough(points)) == 3
	closed = bezierThrough(points, closed=True)
	assert len(closed) == 4 and closed[-1][2] == points[0]
	assert bezierThrough(points[:1]) == []


def test_windows():
	noon = datetime(2026, 10, 6, 12, 30)
	assert windowBounds(parseWindow('today'), noon) == (datetime(2026, 10, 6), datetime(2026, 10, 7))
	assert windowBounds(parseWindow('24h'), noon) == (noon - timedelta(hours=24), noon)
	assert windowBounds(parseWindow('+6h'), noon) == (noon, noon + timedelta(hours=6))
	assert parseWindow('3d') == ('back', timedelta(days=3))
	for bad in ('soon', '0h', '5m'):
		with pytest.raises(ValueError):
			parseWindow(bad)

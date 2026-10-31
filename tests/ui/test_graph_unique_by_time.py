import numpy as np

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import _uniqueByTime


def test_repeated_time_with_different_values_keeps_the_last_row():
	arr = np.array([(3.0, 30.0), (1.0, 10.0), (2.0, 20.0), (2.0, 25.0)])
	assert _uniqueByTime(arr).tolist() == [[1.0, 10.0], [2.0, 25.0], [3.0, 30.0]]


def test_result_is_strictly_increasing_in_time():
	arr = np.array([(5.0, 1.0), (5.0, 2.0), (5.0, 3.0), (4.0, 0.0)])
	x = _uniqueByTime(arr)[:, 0]
	assert (np.diff(x) > 0).all()


def test_a_single_row_is_unchanged():
	arr = np.array([(1.0, 2.0)])
	assert _uniqueByTime(arr).tolist() == [[1.0, 2.0]]

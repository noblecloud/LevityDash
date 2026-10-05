from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Gauge import _isWholeSteps


def test_whole_steps_tolerates_float_error():
	assert _isWholeSteps(4, 1)
	assert _isWholeSteps(0.6, 0.2)  # 0.6 / 0.2 is 2.9999999999999996
	assert _isWholeSteps(0.7, 0.1)
	assert not _isWholeSteps(0.6, 1)
	assert not _isWholeSteps(4, 0.75)
	assert not _isWholeSteps(4, 0)

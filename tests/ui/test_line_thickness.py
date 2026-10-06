"""Variable-thickness lines."""
import numpy as np
import pytest


def test_widths_follow_the_other_series_and_clamp():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import variableWidths

	times = np.array([0.0, 10.0, 20.0])
	widths = variableWidths(times, np.array([0.0, 20.0]), [0, 10], [0.2, 1.0], None)
	assert widths == pytest.approx([0.2, 0.6, 1.0])
	pinned = variableWidths(times, np.array([0.0, 20.0]), [0, 10], [0.2, 1.0], [0, 5])
	assert pinned == pytest.approx([0.2, 1.0, 1.0])


def test_widths_give_up_on_text_values():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import variableWidths

	assert variableWidths(np.array([0.0]), np.array([0.0]), ['rain'], [0.2, 1.0], None) is None


def test_ribbon_is_as_thick_as_asked():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import ribbonPath

	box = ribbonPath(np.array([0.0, 10.0, 20.0]), np.array([5.0, 5.0, 5.0]), np.array([2.0, 4.0, 6.0])).boundingRect()
	assert box.height() == pytest.approx(6.0)
	assert box.width() == pytest.approx(20.0)

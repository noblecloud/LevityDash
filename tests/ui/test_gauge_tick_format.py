"""Tick label decimals follow the tick spacing: exact, never more than needed."""
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Gauge import GaugeTickTextGroup


class _Ticks:
	def __init__(self, values):
		self.tick_values = values


def _places(values):
	group = GaugeTickTextGroup.__new__(GaugeTickTextGroup)
	group._ticks = _Ticks(values)
	return group._spacingPrecision()


def test_decimals_follow_the_spacing():
	assert _places([28.0, 29.0, 30.0, 31.0, 32.0]) == 0
	assert _places([0.0, 0.1, 0.2, 0.3, 0.4, 0.5]) == 1
	assert _places([29.0 + 0.25 * i for i in range(5)]) == 2
	# Float addition gives 29.950000000000003; that still needs 2 places, not 3.
	assert _places([29.9 + 0.05 * i for i in range(5)]) == 2

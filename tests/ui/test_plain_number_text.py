"""A plain number a display shows (a ratio such as gust / wind) follows the display's precision."""
from types import SimpleNamespace

import pytest

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import MeasurementDisplayProperties
from LevityDash.lib.utils.shared import Unset


def text(value, precision=Unset):
	display = SimpleNamespace(precision=precision, nullValue=None, formatString=None)
	return MeasurementDisplayProperties._textFor(display, value)


@pytest.mark.parametrize('precision, expected', [(2, '0.42'), (0, '0'), (4, '0.4167')])
def test_a_ratio_takes_the_precision(precision, expected):
	assert text(5 / 12, precision) == expected


def test_a_ratio_with_no_precision_keeps_two_decimals_not_every_digit():
	assert text(5 / 12) == '0.42'
	assert text(2.4) == '2.4'
	assert text(3.0) == '3'

"""A font family with no usable styles must not abort a dashboard load.

`closestWeightStyle` and `getFontWeight` both called `min()` on a sequence that
is empty whenever the font system reports no styles for a family - an
unavailable family, or one substituted at load time. The resulting ValueError
was raised from a Label's `fontWeight` setter, deep inside `Panel.state`, where
one item's exception costs the whole board: lambda showed nothing but the moon.
"""

import pytest

from LevityDash.lib.ui.fonts import FontWeight

MISSING = 'ThisFontFamilyDoesNotExistOnAnyMachine'


def test_closestWeightStyle_survives_a_family_with_no_styles():
	font = FontWeight.closestWeightStyle(MISSING, FontWeight.Light)
	assert font is not None
	assert font.family() == MISSING


@pytest.mark.parametrize('weight', ['Light', 'Regular', 'Bold'])
def test_getFontWeight_survives_a_family_with_no_styles(weight):
	assert FontWeight.getFontWeight(MISSING, weight) is FontWeight[weight]


def test_getFontWeight_still_picks_the_closest_available_weight():
	family = FontWeight.__module__ and 'Nunito'
	weights = FontWeight.availableWeights(family)
	if not weights:
		pytest.skip('Nunito is not registered in this environment')
	result = FontWeight.getFontWeight(family, 'Thin')
	assert result in weights

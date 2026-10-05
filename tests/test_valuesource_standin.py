from LevityDash.lib import valuesource
from LevityDash.lib.valuesource import installStandIn, openValueSource
from statekit.binding import Constant


def test_stand_in_answers_every_lookup_until_removed():
	seen = []

	def standIn(value, label='', effect=''):
		seen.append((value, label))
		return Constant(7)

	installStandIn(standIn)
	try:
		assert openValueSource('environment.temperature.high', 'fill').get() == 7
		assert seen == [('environment.temperature.high', 'fill')]
	finally:
		installStandIn(None)
	assert valuesource._standIn is None
	assert isinstance(openValueSource(3), Constant)

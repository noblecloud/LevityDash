"""A percent class cannot tell 0.1 % from 10 % by the size of the number, so the
schema says which scale a source reports. Percent is the default; PirateWeather
reports 0-1 fractions and says so."""
import copy

import pytest

from LevityDash.lib.plugins.builtin import OpenMeteo, PirateWeather
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.schema import Schema
from LevityDash.lib.wire.codec import decode_measurement, encode_measurement


class FakePlugin:
	name = 'Fake'

	def __hash__(self):
		return 1

	def __contains__(self, item):
		return False


def convert(module, key):
	schema = Schema(plugin=FakePlugin(), source=copy.deepcopy(module.schema))
	return schema[CategoryItem(key)].getConvertFunc()


def test_percent_source_reads_sub_one_as_percent():
	assert float(convert(OpenMeteo, 'environment.humidity.humidity')(0.1)) == pytest.approx(0.001)


def test_percent_source_reads_whole_numbers_as_percent():
	assert float(convert(OpenMeteo, 'environment.humidity.humidity')(55)) == pytest.approx(0.55)


@pytest.mark.parametrize('key', ['environment.humidity.humidity', 'environment.clouds.cover'])
def test_fraction_source_reads_zero_to_one(key):
	convertFunc = convert(PirateWeather, key)
	assert float(convertFunc(0.1)) == pytest.approx(0.1)
	assert float(convertFunc(1.0)) == pytest.approx(1.0)


def test_wire_round_trip_keeps_a_small_percentage_small():
	small = convert(OpenMeteo, 'environment.humidity.humidity')(0.1)
	assert float(decode_measurement(encode_measurement(small))) == pytest.approx(0.001)

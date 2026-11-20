"""The comfort range: one setting moves the neutral band of the temperature scale everywhere."""
import pytest
from unitcorn.temperature import Temperature

from LevityDash.lib.ui.colors import comfort
from LevityDash.lib.ui.colors.gradient import Gradient


def test_default_band_is_unchanged():
	assert comfort.configured({}) == (comfort.DEFAULT_LOW, comfort.DEFAULT_HIGH)
	assert comfort.shift(30, 12, 22) == 30


def test_units():
	assert comfort.configured({'low': '55°F', 'high': '72°F'})[0] == pytest.approx(12.78, abs=0.01)
	assert comfort.configured({'low': '15', 'high': '25'}, default_unit='C') == (15.0, 25.0)
	low, high = comfort.configured({'low': '60', 'high': '80'}, default_unit='F')
	assert (low, high) == (pytest.approx(15.56, abs=0.01), pytest.approx(26.67, abs=0.01))


def test_one_end_alone_and_bad_values():
	assert comfort.configured({'high': '25 C'}) == (12.0, 25.0)
	seen = []
	assert comfort.configured({'low': '30', 'high': '20'}, 'C', seen.append) == (12.0, 22.0)
	assert comfort.configured({'low': 'warm'}, 'C', seen.append) == (12.0, 22.0)
	assert len(seen) == 2


def test_shift_stretches_band_and_slides_ends():
	assert comfort.shift(12, 16, 26) == 16
	assert comfort.shift(22, 16, 26) == 26
	assert comfort.shift(17, 16, 26) == 21
	assert comfort.shift(7, 16, 26) == 11     # 5 under the low stays 5 under
	assert comfort.shift(28, 16, 26) == 32    # 6 over the high stays 6 over


@pytest.mark.parametrize('spec', ['TemperatureGradient', '$temperature'])
def test_scale_follows_setting(monkeypatch, spec):
	plain = Gradient.decode(spec)
	monkeypatch.setattr(comfort, 'configured', lambda **_: (16.0, 26.0))
	shifted = Gradient.decode(spec)
	white = plain.get_color_for_value(Temperature.Celsius(17)).hex
	assert shifted.get_color_for_value(Temperature.Celsius(21)).hex == white
	assert plain.get_color_for_value(Temperature.Celsius(21)).hex != white  # moved: 21 °C was warm, is comfortable now
	assert float(shifted.min.value) == pytest.approx(float(plain.min.value) + 4)

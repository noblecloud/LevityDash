from types import SimpleNamespace

from unitcorn import Length, Temperature
from unitcorn.derived.precipitation import PrecipitationRate

from LevityDash.lib.utils.data import _rainSpan


def _plot(value):
	return SimpleNamespace(hasData=True, timeseries=SimpleNamespace(first=SimpleNamespace(value=value)))


def test_rain_span_in_the_unit_of_the_plot():
	assert _rainSpan([_plot(PrecipitationRate.Hourly(Length.Inch(0.02), 1))]) == 0.1
	assert round(_rainSpan([_plot(PrecipitationRate.Hourly(Length.Millimeter(0.5), 1))]), 2) == 2.54


def test_other_data_has_no_rain_span():
	assert _rainSpan([_plot(Temperature.Celsius(20))]) is None
	assert _rainSpan([]) is None

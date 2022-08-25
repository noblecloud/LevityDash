from .color import Color
from .gradient import Gradient
from WeatherUnits import Measurement, Temperature, Probability, Length, Time, DerivedMeasurement
from WeatherUnits.derived.precipitation import Hourly
from WeatherUnits.length import Centimeter, Millimeter, Inch
from WeatherUnits.derived.rate import MilesPerHour
from WeatherUnits.others.light import Lux, Irradiance

TemperatureGradient = Gradient[Temperature.Celsius](
	name='TemperatureGradient',
	freezing=(-10, '#94B7FF'),
	cold=(7, '#B2CBFF'),
	chilly=(12, '#F2F2FF'),
	comfortableStart=(17, '#F2F2FF'),
	comfortable=(22, '#FFFEFA'),
	hot=(28, '#ffb75d'),
	veryHot=(30, '#f3a469'),
	a=(32, '#f18271'),
	b=(38, '#cc6b8e'),
	c=(40, '#a86aa4'),
	d=(50, '#8f6aae'),
)

FabledSunsetGradientLux = Gradient[Lux](
	'FabledSunsetGradientLux',
	(0, '#23155700'),
	(3600, '#44107A55'),
	(6000, '#8F6AAEAA '),
	(7200, '#CC6B8E'),
	(10800, '#F3A469'),
	(18000, '#F7B731'),
	(36000, '#FFFEFA'),
)

FabledSunsetGradientWattsPerSquareMeter = Gradient[Irradiance](
	'FabledSunsetGradientWattsPerSquareMeter',
	(0, '#23155700'),
	(30, '#44107A55'),
	(50, '#8F6AAEAA '),
	(60, '#CC6B8E'),
	(90, '#F3A469'),
	(150, '#F7B731'),
	(300, '#FFFEFA'),
)
RipeMalinkaGradient = Gradient[MilesPerHour](
	'RipeMalinkaGradient',
	(0, '#f093fb'),
	(10, '#f5576c'),
	(20, '#f7b731'),
	(30, '#f9f64f'),
	(40, '#a9f7a9'),
	(50, '#5ff781'),
	(60, '#00e756'),
	(70, '#00b7eb'),
	(80, '#0052f3'),
	(90, '#0f00f9'),
	(100, '#7b00d4'),
)

PrecipitationProbabilityGradient = Gradient[Probability](
	name='PrecipitationProbabilityGradient',
	none=(0, '#00c6fb00'),
	Low=(.10, '#00c6fb'),
	high=(1, '#005bea'),
	one=(1, '#7b00d4'),
)

# Source https://webgradients.com/ 061 Sweet PeriodGet
PrecipitationRateGradient = Gradient[Hourly[Millimeter]](
	name='PrecipitationRateGradient',
	none=(0.1, '#3f51b100'),
	veryLight=(0.2, '#3f51b1'),
	light=(1, '#5a55ae'),
	moderate=(1.5, '#7b5fac'),
	heavy=(3, '#8f6aae'),
	veryHeavy=(5, '#a86aa4'),
	extreme=(12, '#cc6b8e'),
	storm=(24, '#f18271'),
	hurricane=(30, '#f3a469'),
	tornado=(35, '#f7c978'),
)


def __getattr__(name):
	if name == 'gradients':
		return [i for i in locals() if isinstance(i, Gradient)]
	elif name == 'colors':
		return [i for i in locals() if isinstance(i, Color)]


__all__ = tuple(i for i in locals() if isinstance(i, (Gradient, Color)))

from datetime import datetime

import pytz
import WeatherUnits as wu
from typing import Dict, Type, Union

from LevityDash.lib.utils.shared import SmartString

__all__ = ['unitDict']
unitDict: Dict[str, Union[Type[wu.Measurement], Type[bool], Dict[str, Union[Type[wu.base.Measurement], Type[wu.base.DerivedMeasurement]]]]] = {
	'f':                wu.temperature.Fahrenheit,
	'c':                wu.temperature.Celsius,
	'kelvin':           wu.temperature.Kelvin,
	'%':                wu.others.Humidity,
	'%h':               wu.others.Humidity,
	'%c':               wu.others.Coverage,
	'%p':               wu.others.Probability,
	'%%':               wu.others.Percentage,
	'%bat':             wu.others.BatteryPercentage,
	'º':                wu.others.Direction,
	'ºa':               wu.others.Angle,
	'str':              SmartString,
	'int':              wu.base.Measurement,
	'mmHg':             wu.pressure.MillimeterOfMercury,
	'inHg':             wu.pressure.InchOfMercury,
	'W/m^2':            wu.others.light.Irradiance,
	'lux':              wu.others.light.Illuminance,
	'mb':               wu.Pressure.Millibar,
	'mbar':             wu.Pressure.Millibar,
	'bar':              wu.Pressure.Bar,
	'hPa':              wu.Pressure.Hectopascal,
	'in':               wu.length.Inch,
	'mi':               wu.length.Mile,
	'mm':               wu.length.Millimeter,
	'm':                wu.length.Meter,
	'km':               wu.length.Kilometer,
	'month':            wu.Time.Month,
	'week':             wu.Time.Week,
	'day':              wu.Time.Day,
	'hr':               wu.Time.Hour,
	'min':              wu.Time.Minute,
	's':                wu.Time.Second,
	'ug':               wu.mass.Microgram,
	'μg':               wu.mass.Microgram,
	'mg':               wu.mass.Milligram,
	'g':                wu.mass.Gram,
	'kg':               wu.mass.Kilogram,
	'lb':               wu.mass.Pound,
	'm^3':              wu.Volume.CubicMeter,
	'ft^3':             wu.Volume.CubicFoot,
	'volts':            wu.Voltage,
	'date':             datetime,
	'uvi':              wu.others.light.UVI,
	'strike':           wu.others.Strikes,
	'timezone':         pytz.timezone,
	'datetime':         datetime,
	'epoch':            datetime.fromtimestamp,
	'rssi':             wu.RSSI,
	'ppt':              wu.derived.PartsPer.Thousand,
	'ppm':              wu.derived.PartsPer.Million,
	'ppb':              wu.derived.PartsPer.Billion,
	'pptr':             wu.derived.PartsPer.Trillion,
	'bool':             bool,
	'PI':               wu.PollutionIndex,
	'PrimaryPollutant': wu.PrimaryPollutant,
	'AQI':              wu.AQI,
	'AQIHC':            wu.HeathConcern,
	'MoonPhase':        wu.Measurement,
	"WeatherCode":      wu.Measurement,
	'tz':               pytz.timezone,
	'special':          {
		'precipitation':       wu.Precipitation,
		'precipitationDaily':  wu.Precipitation.Daily,
		'precipitationHourly': wu.Precipitation.Hourly,
		'precipitationRate':   wu.Precipitation.Hourly,
		'wind':                wu.derived.Wind,
		'airDensity':          wu.derived.Density,
		'pollutionDensity':    wu.derived.Density,
		'precipitationType':   wu.Precipitation.Type,
		'pressureTrend':       SmartString
	}
}

# for unit in unitDict:
#
# 	unit['sourceUnit'] = APIValue(unit['sourceUnit'])
#
# del unit

from datetime import datetime

from pytz import timezone

from _easyDict import SmartDictionary
from measurments import Light, ObservationSection, Precipitation, Pressure, Temperature, Wind
from src.translators import Translator


class Observation(SmartDictionary):
	time: datetime
	timezone: timezone
	temperature: Temperature
	pressure: Pressure
	wind: Wind
	light: Light
	precipitation: Precipitation
	_translator: Translator

	def __init__(self, data: dict, *args, **kwargs):
		super(Observation, self).__init__(*args, **kwargs)
		classes = self.translator.units.groups
		time = self.translator.pop('time')
		for group, typeTranslator in self.translator.items():
			typeClass: ObservationSection = classes[group]
			self[group] = typeClass(data, self.translator)

	def localize(self, measurement, value):
		t = self._translator
		name = t[measurement]
		type, unit = t.units[name]
		if type in t.converter:
			value, unit = t.converter[type](value, unit)
		return name, value

	@property
	def translator(self):
		return self._translator

	@property
	def t(self):
		return self._translator



	# @property
	# def precipitation(self):
	# 	return self._precipitation
	#
	# @property
	# def temperature(self):
	# 	return self._temperature
	#
	# @property
	# def wind(self):
	# 	return self._wind
	#
	# @property
	# def pressure(self):
	# 	return self._pressure
	#
	# @property
	# def light(self):
	# 	return self._light



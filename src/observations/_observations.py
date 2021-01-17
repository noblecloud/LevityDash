import logging
from datetime import datetime
from typing import Any, Union

from pytz import timezone, UTC
from _easyDict import SmartDictionary
from src.translators import Translator
from units.rate import Wind, Precipitation
from src import config
from src import utils


class Observation(SmartDictionary):
	time: datetime
	_time: datetime
	timezone: timezone
	_timezone: timezone

	_translator: Translator

	def __init__(self, *args, **kwargs):
		super(Observation, self).__init__(*args, **kwargs)

	def dataUpdate(self, data):

		valueDictionary = self.translator.flat.copy()
		unitDictionary = self.translator.units.flat.copy()

		classDictionary = self.translator.classes
		for dataName, name in valueDictionary.items():
			try:
				value = data[dataName]
				type, unit = unitDictionary[name].values()
				classType = classDictionary[unit]

				if isinstance(classType, list):
					if type == 'rate':
						compoundClass = Precipitation
					elif type == 'wind':
						compoundClass = Wind
					else:
						logging.warn('Unknown compound class type \'{}\', defaulting to Wind'.format(type))
						compoundClass = Wind
					numerator, denominator = classType
					measurement = compoundClass(numerator(value), denominator(1))
				elif type == 'date':
					tz = self.t.tz()
					format = self.t.dateFormatString
					measurement = utils.formatDate(value, tz.zone, format=format, utc=True)
				else:
					measurement = classType(value)
				self[name] = measurement
			except KeyError:
				logging.warn('{} is not a valid key for {} of {}'.format(dataName, self.name, self.t.__class__.__name__))

	# for group, typeTranslator in self.translator.items():
	# 	typeClass: ObservationSection = classes[group]
	# 	self[group] = typeClass(data, self.translator)

	def udpUpdate(self, data):
		self.update(data)

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



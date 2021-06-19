import logging
from datetime import datetime
from typing import Any, Union

import WeatherUnits.derived
from PySide2.QtCore import Signal
from pytz import timezone, UTC
from WeatherUnits import Measurement, DerivedMeasurement as Derived

import utils
from src._easyDict import SmartDictionary
from src.translators import Translator
from src import SmartDictionary, utils


class Observation(SmartDictionary):

	def __init__(self, *args, **kwargs):
		self.signals: dict[str, [Signal]] = {}
		self.source = 'tcp'
		super(Observation, self).__init__(*args, **kwargs)

	def dataUpdate(self, data):

		valueDictionary = self.translator.flat.copy()
		unitDictionary = self.translator.units.flat.copy()

		classDictionary = self.translator.classes
		for dataName, name in valueDictionary.items():
			try:
				value = data[dataName]
				typeString, unit, title = unitDictionary[name].values()
				# if unit in classDictionary.keys():
				unitClass: type = classDictionary[unit]
				# elif typeString in classDictionary['special'].keys():
				# 	unitClass: type = classDictionary['special'][typeString]
				# else:
				# 	unitClass: type = Measurement

				if typeString in self.translator.specialClasses.keys():
					compoundClass: type = self.translator.specialClasses[typeString]
					if issubclass(compoundClass, Derived):
						numerator: type
						denominator: type
						numerator, denominator = unitClass
						measurement = compoundClass(numerator(value), denominator(1))
					elif issubclass(compoundClass, Measurement):
						measurement = unitClass(value)
						measurement._type = typeString
						measurement._max = 2
						measurement._precision = 2
					else:
						self._log.warn('Unknown compound class type \'{}\', skipping'.format(typeString))
						break
				elif typeString == 'date':
					tz = self.t.tz()
					format = self.t.dateFormatString
					measurement = utils.formatDate(value, tz.zone, format=format, utc=True)
				else:
					measurement = unitClass(value)
				try:
					if isinstance(measurement, Measurement):
						measurement.title = title
						measurement = measurement.localized
				except AttributeError as e:
					print(e)
				self.update({name: measurement})
			except KeyError:
				self._log.warn('{} is not a valid key for {} of {}'.format(dataName, self.name, self.t.__class__.__name__))

	def update(self, values, **kwargs):
		for key, item in values.items():
			self.emit(key)
		super(Observation, self).update(values, **kwargs)

	def emit(self, key):
		if key in self.signals.keys():
			for signal in self.signals[key]:
				# 	print(f'{key} set to {self[key]} via {self.source}')
				signal.emit(self[key])

	def localize(self, measurement, value):
		t = self._translator
		name = t[measurement]
		type, unit = t.units[name]
		if type in t.converter:
			value, unit = t.converter[type](value, unit)
		return name, value

	@property
	def t(self):
		return self._translator

	# def __getattr__(self, item):
	# 	item = super().__getattr__(item)
	# 	if isinstance(item, Measurement):
	# 		self.makeSignal(item)
	# 		return item, self.makeSignal(item)
	# 	else:
	# 		return item
	#
	# def makeSignal(self, measurement):
	# 	if measurement.title not in self.signals.keys():
	# 		self.signals.update({measurement.title: Signal(Measurement)})
	# 	return self.signals[measurement.title]

	@property
	def translator(self):
		return self._translator

	def subscribe(self, *receiver):
		if isinstance(receiver, tuple):
			for item in receiver:
				if item.subscriptionKey in self.signals.keys():
					self.signals[item.subscriptionKey].append(item.updateSignal)
				else:
					self.signals.update({item.subscriptionKey: [item.updateSignal]})
				item.updateSignal.emit(self[item.subscriptionKey])


class ObservationSingle(Observation):
	time: datetime
	timezone: timezone
	translator: Translator

	def udpUpdate(self, data):
		self.update(data)

	def __init__(self, *args, **kwargs):
		super(ObservationSingle, self).__init__(*args, **kwargs)


class ObservationSingleSet(ObservationSingle):
	_translator: Translator

	def __init__(self, *args, **kwargs):
		super(ObservationSingleSet, self).__init__(*args, **kwargs)

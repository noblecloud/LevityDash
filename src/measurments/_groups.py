import logging
from datetime import datetime
from typing import Union

from pytz import timezone

from src import SmartDictionary
from measurments._measurment import _Light, _Lightning, _Precipitation, _Pressure, _Temperature, _WindWF
from units.rate import Wind as WindUnit
from units.rate import Precipitation as PrecipitationUnit
from . import Measurement


class ObservationSection(SmartDictionary):
	# global units
	# global config

	def __init__(self, data: dict[str, Union[str, int, float, datetime, timezone]], t):

		section = self.name.lower()
		units = t.units[section]
		valueDefinitions = t[section]
		typeClasses = t.units.types
		print('trying section {}'.format(section))
		for dataName, name in valueDefinitions.items():
			print('working on', name)
			try:
				value = data[dataName]
				type, unit = units[name].values()
				print('has a type of {}, a unit of {} and a value of {}'.format(type, unit, value))
				classType = typeClasses[unit]
				print('class type is', classType)


				if isinstance(classType, list):

					if section == 'precipitation':
						compoundClass = PrecipitationUnit
					elif section == 'wind':
						compoundClass = WindUnit
					else:
						logging.warn('Unknown compound class type \'{}\', defaulting to Wind'.format(section))
						compoundClass = WindUnit
					numerator, denominator = classType
					measurement = compoundClass(numerator(value), denominator(1))
				elif type == 'date':
					measurement = t.formatDate(value)
				else:
					measurement = classType(value)
				self[name] = measurement
			except KeyError:
				logging.warn('{} is not a valid key for {} of {}'.format(dataName, self.name, t.__class__.__name__))

	# for item in t.keys():
	# 	name = t[item]
	# 	if meta[name]['type'] == 'speed':
	# 		try:
	# 			d, time = tuple(config['Units']['wind'].split(','))
	# 			time = units[time](1)
	# 			distance = units[d]
	# 			value = rate.Wind(distance(data[item]), time)
	# 			setattr(self, '_' + name, value)
	# 		except KeyError:
	# 			print('what is this?')
	# 	else:
	# 		try:
	# 			dataType = units[meta[name]['unit']]
	# 		except KeyError:
	# 			print('pass', name)
	# 		try:
	# 			if dataType:
	# 				value = dataType(data[item])
	# 			# value = dataType(data[item], meta[name])
	# 			else:
	# 				value = Measurement(data[item], meta[name])
	# 			setattr(self, '_' + name, value)
	# 		except KeyError:
	# 			logging.warning('Unable to find key: {}'.format(item))
	# 			pass

	def _setAttribute(self, name, value):
		self.__setattr__('_' + name, value)

	@property
	def name(self):
		return self.__class__.__name__


## Deprecated
class Heat(Measurement):
	_symbol = 'º'
	_value = float


class Temperature(ObservationSection, _Temperature):
	pass


class Wind(ObservationSection, _WindWF):
	pass


class Pressure(ObservationSection, _Pressure):
	pass


class Precipitation(ObservationSection, _Precipitation):
	pass


class Lightning(ObservationSection,_Lightning):
	pass


class Light(ObservationSection, _Light):
	pass

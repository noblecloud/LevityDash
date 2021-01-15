import logging
from typing import Union

from src import config
from units.errors import BadConversion


class SmartFloat(float):
	_config: dict
	_precision: int = 1
	_real: int = 2
	_maxDigits: int = 3
	_minDigits: int = 0

	_unit: str = ''
	_suffix: str = ''
	_isInt: bool = False

	def __new__(cls, value):
		return float.__new__(cls, value)

	def __init__(self, value):
		float.__init__(value)
		self._isInt = True if self.is_integer() else False

	def __str__(self) -> str:
		string = self.formatString.format(self).rstrip('0').rstrip('.')
		return '{}{} {}'.format(str(string), self.suffix, self.unit)

	def strip(self):
		return self._format.format(str(self)).rstrip('0').rstrip('.')

	def __repr__(self):
		return str(self)
		# if self.is_integer() or self._isInt:
		# 	return int(self)
		# else:
		# 	return self

	'''This is broken'''
	@property
	def formatString(self) -> str:
		# TODO: fix this SmartFloat formatter
		p = self._precision

		# value = round(self, self._precision)

		# how long is the number
		# digit, flts = (len(n) for n in str(value).strip('0').split('.'))

		# if precision is more than 1 always show at least
		# one decimal even if it's zero unless precision
		# is zero then set because 1%0 results in division error
		# forcedPrecision = bool(1 % self._precision if self._precision else 0)

		# only if the precision is more than N display decimals
		# n = 1
		# twoOrMore = p if (p//n) else 0
		#
		# flts = 1 if forcedPrecision and not flts else flts
		# flts = self._precision if flts < self._precision

		## remaining = self._maxDigits - (digit + flts) # 1

		# if the precision is less than the
		# left over space, give the extra space
		# to the digit
		## digit += fl - self._precision
		## fl -= fl - self._precision

		return '{:1.' + str(self._precision) + 'f}'

	@property
	def withUnit(self):
		return '{}{} {}'.format(str(self), self.suffix, self.unit)

	@property
	def unit(self) -> str:
		return self._unit

	@property
	def suffix(self):
		return self._suffix

	@property
	def int(self):
		return int(self)

	@property
	def name(self):
		return self.__class__.__name__


class Measurement(SmartFloat):

	def __new__(cls, value):
		return SmartFloat.__new__(cls, value)

	def __init__(self, value):
		self._config = config.Units
		SmartFloat.__init__(self, value)

	def __getitem__(self, item):
		try:
			return self.__getattribute__(item)
		except ValueError:
			raise BadConversion

	def __str__(self) -> str:
		string = self.formatString.format(self.localized).rstrip('0').rstrip('.')
		return '{}{} {}'.format(str(string), self.localized.suffix, self.localized.unit)

	@property
	def localized(self):
		try:
			return self[self._config[self.name.lower()]]
		except KeyError:
			return self


class AbnormalScale(Measurement):
	_value: Union[int, float]
	_factors = list[int, float]
	_scale: int

	def changeScale(self, newScale: Union[int, float]):
		newScale += 1
		newValue = self
		if newScale < self._scale + 1:
			for x in self._factors[newScale:self._scale + 1]:
				newValue *= x
		elif newScale > self._scale + 1:
			for x in self._factors[self._scale + 1:newScale]:
				newValue /= x

		return newValue

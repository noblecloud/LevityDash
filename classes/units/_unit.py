from typing import Union

from units.errors import BadConversion


class Unit:
	_format = "{:3.1f}"
	_value: Union[int, float]
	_unit: str

	def __init__(self, value):
		self._value = value

	def __float__(self):
		return self._value

	def __str__(self) -> str:
		return self._format.format(self._value)

	@property
	def value(self) -> Union[int, float]:
		return self._value

	@property
	def raw(self) -> Union[int, float]:
		return self._value

	@property
	def format(self) -> str:
		return self._format

	@property
	def unit(self) -> str:
		return self._unit

	def __getitem__(self, item):
		try:
			self.__getattribute__(item)
		except ValueError:
			raise BadConversion


class AbnormalScale(Unit):
	_value: Union[int, float]
	_factors = list[int, float]
	_scale: int

	def changeScale(self, newScale: Union[int, float]):
		newScale += 1
		newValue = self._value
		if newScale < self._scale + 1:
			for x in self._factors[newScale:self._scale + 1]:
				newValue *= x
		elif newScale > self._scale + 1:
			for x in self._factors[self._scale + 1:newScale]:
				newValue /= x

		return newValue

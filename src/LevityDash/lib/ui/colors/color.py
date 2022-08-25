import re
from numbers import Number
from typing import Tuple, Iterable

from PySide2.QtGui import QColor

from .utils import randomColor, kelvinToRGB


class Color:
	__slots__ = ('__red', '__green', '__blue', '__alpha')
	__red: Number
	__green: Number
	__blue: Number
	__alpha: Number

	@classmethod
	@property
	def randomColor(cls) -> 'Color':
		return cls(randomColor())

	@classmethod
	def random(cls, min=0, max=255) -> 'Color':
		return cls(randomColor(min, max))

	@classmethod
	def fromTemperature(cls, temp: int | float) -> 'Color':
		return cls(kelvinToRGB(temp))

	def __init__(self, color: str | Tuple[Number, ...] = None, /, red: Number = None, green: Number = None, blue: Number = None, alpha: Number = None):
		if any(i is not None for i in (red, green, blue)):
			self.red = red or 0
			self.green = green or 0
			self.blue = blue or 0
		else:
			self.__parse(color)

		self.alpha = alpha or 255

	def __parse(self, color: str | Tuple[int | float, ...]):
		match color:
			case str(color):
				colors = [int(i, 16) for i in re.findall(r'([A-Fa-f\d]{2})', color)]
				if len(colors) == 3:
					red, green, blue = colors
					alpha = 255
				elif len(colors) == 4:
					red, green, blue, alpha = colors
				else:
					raise ValueError(f'Invalid colors string: {color}')
			case [int(red), int(green), int(blue)]:
				alpha = 255
			case [int(red), int(green), int(blue), int(alpha)]:
				pass
			case _:
				raise TypeError(f'Color must be a string, tuple of ints, or hexadecimal value, not {type(color)}')
		self.__red, self.__green, self.__blue, self.__alpha = red, green, blue, alpha

	@property
	def red(self) -> Number:
		return self.__red

	@red.setter
	def red(self, value):
		if value < 1:
			value *= 255
		self.__red = sorted((0, value, 255))[1]

	@property
	def green(self) -> Number:
		return self.__green

	@green.setter
	def green(self, value):
		if value < 1:
			value *= 255
		self.__green = sorted((0, value, 255))[1]

	@property
	def blue(self) -> Number:
		return self.__blue

	@blue.setter
	def blue(self, value):
		if value < 1:
			value *= 255
		self.__blue = sorted((0, value, 255))[1]

	@property
	def alpha(self) -> Number:
		return self.__alpha

	@alpha.setter
	def alpha(self, value):
		if value < 1:
			value *= 255
		self.__alpha = sorted((0, value, 255))[1]

	@property
	def QColor(self) -> QColor:
		return QColor(self.red, self.green, self.blue, self.alpha)

	def __str__(self):
		if self.alpha == 255:
			return f'#{self.__red:02x}{self.__green:02x}{self.__blue:02x}'
		return f'#{self.__red:02x}{self.__green:02x}{self.__blue:02x}{self.__alpha:02x}'

	def __eq__(self, other):
		if isinstance(other, Color):
			return self.red == other.red and self.green == other.green and self.blue == other.blue and self.alpha == other.alpha
		elif isinstance(other, str):
			try:
				return self == Color(other)
			except Exception:
				return False
		elif isinstance(other, QColor):
			return self.QColor == other
		return False

	@classmethod
	def representer(cls, dumper, data):
		return dumper.represent_str(str(data))


__all__ = ('Color',)

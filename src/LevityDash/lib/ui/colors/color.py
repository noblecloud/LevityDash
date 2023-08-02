from functools import lru_cache

import re
from numbers import Number
from typing import ClassVar, Dict, Literal, Tuple, Iterable, Union, Sequence, Type

from PySide6.QtGui import QColor
from rich.repr import rich_repr

from LevityDash.lib.ui.colors.utils import randomColor, kelvinToRGB
from LevityDash.lib.utils import get, split

_knownColors: Dict[str, 'Color'] = {}

_BASE_COLOR = Literal['r', 'g', 'b', 'a', 'red', 'green', 'blue', 'alpha']
_ColorDict = Dict[_BASE_COLOR, int | float]


@rich_repr
class Color:

	__slots__ = ('__red', '__green', '__blue', '__alpha', '__name')
	__match_args__ = ('')
	__red: int
	__green: int
	__blue: int
	__alpha: int
	__name: str

	presets: ClassVar['Preset']

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

	@classmethod
	@property
	def text(cls) -> 'Color':
		return cls.presets.white

	@classmethod
	@property
	def default(cls) -> 'Color':
		return cls.presets.white

	def __init__(
		self,
		color: str | Tuple[int | float, ...] | _ColorDict = None, /,
		red: Number = None,
		green: Number = None,
		blue: Number = None,
		alpha: Number = None,
		name: str = None
	):
		if any(i is not None for i in (red, green, blue)):
			self.__red = self.__ensureCorrectValue(red) or 0
			self.__green = self.__ensureCorrectValue(green) or 0
			self.__blue = self.__ensureCorrectValue(blue) or 0
		else:
			self.__parse(color)

		if alpha is None:
			alpha = 255
		self.__alpha = self.__ensureCorrectValue(255 if alpha is None else alpha)

		if name:
			_knownColors[name] = self
		self.__name = name or self.hex

	def __hash__(self):
		if self.__name != self.hex:
			return hash((self.__name, self.hex, type(self)))
		return hash((self.__name, type(self)))

	def __parse(self, color: str | Tuple[int | float, ...] | _ColorDict):
		match color:
			case str(color):
				if hexVal := next(iter(re.findall(r"[A-Fa-f0-9]+", color)), None):
					length = len(hexVal)
					if length > 8:
						hexVal = hexVal[:8]
					n = 3 if length % 3 == 0 else 4
					hexVal = [i.rjust(2, '0') for i in split(hexVal, n)]
					if len(hexVal) == 3:
						hexVal = *hexVal, 'ff'
					colors = tuple(int(i, 16) for i in hexVal)
				else:
					raise ValueError(f'Invalid colors string: {color}')
			case [int(red), int(green), int(blue)] as rgb:
				colors = rgb + (255,)
			case [int(red), int(green), int(blue), int(alpha)] as rgba:
				colors = rgba
			case QColor() as qc:
				colors = qc.getRgb()
			case dict() if set(color) & set(_ColorDict.__args__):
				colors = tuple(
					get(color, *i, expectedType=float|int, default=255)
					for i in (
						('r', 'red'),
						('g', 'green'),
						('b', 'blue'),
						('a', 'alpha')
					)
				)
			case _:
				raise ValueError(f'Invalid colors string: {color}')
		self.__red, self.__green, self.__blue, self.__alpha = tuple(self.__ensureCorrectValue(i) for i in colors)

	@staticmethod
	def __ensureCorrectValue(value: int | float | Number) -> int:
		match value:
			case int(value):
				return sorted((0, value, 255))[1]
			case float(value) if value <= 1:
				return int(round(value * 255))
			case float(value) | Number(value):
				return sorted((0, int(round(value)), 255))[1]
			case _:
				return 255

	@property
	def red(self) -> int:
		return self.__red

	@property
	def green(self) -> int:
		return self.__green

	@property
	def blue(self) -> int:
		return self.__blue

	@property
	def alpha(self) -> int:
		return self.__alpha

	@property
	def rgb(self) -> Tuple[int, int, int]:
		return self.__red, self.__green, self.__blue

	@property
	def rgbF(self) -> Tuple[float, float, float]:
		return self.__red / 255, self.__green / 255, self.__blue / 255

	@property
	def rbga(self) -> Tuple[int, int, int, int]:
		return self.__red, self.__green, self.__blue, self.__alpha

	@property
	def rgbaF(self) -> Tuple[float, float, float, float]:
		return self.__red / 255, self.__green / 255, self.__blue / 255, self.__alpha / 255

	@property
	def QColor(self) -> QColor:
		return QColor(self.red, self.green, self.blue, self.alpha)

	@property
	def hex(self) -> str:
		if self.alpha == 255:
			return f'#{self.__red:02x}{self.__green:02x}{self.__blue:02x}'
		return f'#{self.__red:02x}{self.__green:02x}{self.__blue:02x}{self.__alpha:02x}'

	@property
	def name(self) -> str:
		return self.__name

	def __str__(self):
		return self.__name

	def __repr__(self):
		return f'Color({self.__name or self.hex})'

	def __rich_repr__(self):
		yield 'name', self.__name, self.hex
		yield 'red', self.__red
		yield 'green', self.__green
		yield 'blue', self.__blue
		yield 'alpha', self.__alpha, 255

	def __iter__(self) -> Iterable[int]:
		yield self.__red
		yield self.__green
		yield self.__blue
		if self.__alpha != 255:
			yield self.__alpha

	def __eq__(self, other):
		if isinstance(other, Color):
			return tuple(self) == tuple(other)
		elif isinstance(other, str):
			try:
				return self == Color(other)
			except Exception:
				return False
		elif isinstance(other, QColor):
			return self.QColor == other
		return False

	def __transform_other(self, other: 'SupportsColor') -> 'Color':
		if isinstance(other, Color):
			return other

		elif isinstance(other, str):
			return Color(other)

		elif isinstance(other, Number):
			return Color(red=other, green=other, blue=other)

		elif isinstance(other, Sequence):
			match len(other):
				case 3:
					return Color(red=other[0], green=other[1], blue=other[2])
				case 4:
					return Color(red=other[0], green=other[1], blue=other[2], alpha=other[3])
				case 1:
					color = other[0]
					return Color(red=color, green=color, blue=color)
				case 2:
					color, alpha = other
					return Color(red=color, green=color, blue=color, alpha=alpha)

		elif isinstance(other, dict):
			return Color(**other)

		raise TypeError(f'Unsupported type: {type(other)}')

	def __add__(self, other: 'SupportsColor') -> 'Color':
		other = self.__transform_other(other)
		alpha = other.alpha / 255
		return Color(
			red=self.red + (other.red * alpha),
			green=self.green + (other.green * alpha),
			blue=self.blue + (other.blue * alpha),
			alpha=self.alpha
		)

	def __sub__(self, other: 'SupportsColor') -> 'Color':
		other = self.__transform_other(other)
		alpha = other.alpha / 255
		return Color(
			red=self.red - (other.red * alpha),
			green=self.green - (other.green * alpha),
			blue=self.blue - (other.blue * alpha),
			alpha=self.alpha
		)

	def __mul__(self, other: 'SupportsColor') -> 'Color':
		other: Color = self.__transform_other(other)
		red, green, blue, alpha = other.rgbaF
		return Color(
			red=self.__red * (red * alpha),
			green=self.__green * (green * alpha),
			blue=self.__blue * (blue * alpha),
			alpha=self.alpha
		)

	def __truediv__(self, other: 'SupportsColor') -> 'Color':
		other = self.__transform_other(other)
		red, green, blue, alpha = self.rgbaF
		return Color(
			red=other.red / (red * alpha),
			green=other.green / (green * alpha),
			blue=other.blue / (blue * alpha),
			alpha=self.alpha
		)

	def __iadd__(self, other):
		other = self.__transform_other(other)
		alpha = other.alpha / 255
		self.__red = self.__ensureCorrectValue(self.__red + (other.red * alpha))
		self.__green = self.__ensureCorrectValue(self.__green + (other.green * alpha))
		self.__blue = self.__ensureCorrectValue(self.__blue + (other.blue * alpha))
		return self

	def __isub__(self, other):
		other = self.__transform_other(other)
		alpha = other.alpha / 255
		self.__red = self.__ensureCorrectValue(self.__red - (other.red * alpha))
		self.__green = self.__ensureCorrectValue(self.__green - (other.green * alpha))
		self.__blue = self.__ensureCorrectValue(self.__blue - (other.blue * alpha))
		return self

	@classmethod
	def representer(cls, dumper, data):
		return dumper.represent_str(str(data))

	@classmethod
	# @lru_cache(maxsize=128)
	def interp_colors(cls, c1: 'Color', c2: 'Color', mid_point: float) -> 'Color':
		"""
		Interpolate between two colors.

		:param c1: The first color.
		:param c2: The second color.
		:param mid_point: The midpoint of the interpolation.
		:return: The interpolated color.
		"""
		red1, green1, blue1, alpha1 = c1.rgbaF
		red2, green2, blue2, alpha2 = c2.rgbaF
		red = red1 + (red2 - red1) * mid_point
		green = green1 + (green2 - green1) * mid_point
		blue = blue1 + (blue2 - blue1) * mid_point
		alpha = alpha1 + (alpha2 - alpha1) * mid_point
		return Color(red=red, green=green, blue=blue, alpha=alpha)


SupportsColor = Union[
	Color,
	Number,
	Tuple[Number, Number],
	Tuple[Number, Number, Number],
	Tuple[Number, Number, Number, Number],
	str,
	_ColorDict
]


__all__ = ('Color',)

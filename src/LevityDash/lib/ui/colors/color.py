import re
from numbers import Number
from typing import ClassVar, Dict, Literal, Tuple, Iterable

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

	def __init__(
		self,
		color: str | Tuple[int | float, ...] | _ColorDict = None, /,
		red: int = None,
		green: int = None,
		blue: int = None,
		alpha: int = None,
		name: str = None
	):
		if any(i is not None for i in (red, green, blue)):
			self.__red = self.__ensureCorrectValue(red) or 0
			self.__green = self.__ensureCorrectValue(green) or 0
			self.__blue = self.__ensureCorrectValue(blue) or 0
		else:
			self.__parse(color)
		self.__alpha = alpha or 255

		if name:
			_knownColors[name] = self
		self.__name = name or self.hex

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
		if value < 1 or (isinstance(value, float) and value <= 1):
			value = round(value * 255)
		return sorted((0, value, 255))[1]

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

	@classmethod
	def representer(cls, dumper, data):
		return dumper.represent_str(str(data))


__all__ = ('Color',)

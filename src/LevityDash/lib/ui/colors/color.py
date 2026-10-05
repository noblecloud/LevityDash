import re
from numbers import Number
from typing import ClassVar, Dict, Literal, Tuple, Iterable, Union, Sequence, Optional, TYPE_CHECKING

import numpy as np
from PySide6.QtGui import QColor
from rich.repr import rich_repr

from LevityDash.lib.ui.colors import oklch as _oklch
from LevityDash.lib.ui.colors.utils import randomColor, kelvinToRGB
from LevityDash.lib.utils import get, split, classproperty
from LevityDash.lib.ui import UILogger as log

if TYPE_CHECKING:
	from LevityDash.lib.ui.colors.presets import Preset

log = log.getChild('Color')

_knownColors: Dict[str, 'Color'] = {}

_BASE_COLOR = Literal['r', 'g', 'b', 'a', 'red', 'green', 'blue', 'alpha']
ColorDict = Dict[_BASE_COLOR, int | float]

COLOR_REG = re.compile(r"([A-Fa-f0-9]{8}|[A-Fa-f0-9]{6}|[A-Fa-f0-9]{4}|[A-Fa-f0-9]{3})")

#: A whole string that is a hex colour: ``#ff8800``, ``0xff8800``, ``ff8800``, ``#f80``, and the forms with alpha.
_HEX_REG = re.compile(r"(?:#|0[xX])?([A-Fa-f0-9]{8}|[A-Fa-f0-9]{6}|[A-Fa-f0-9]{4}|[A-Fa-f0-9]{3})")
#: A whole string of three or four channel numbers: ``255 0 0``, ``255, 0, 0, 128``, ``1.0 0.5 0``.
_NUMBERS_REG = re.compile(r"\s*\d+(?:\.\d+)?(?:\s*[,\s]\s*\d+(?:\.\d+)?){2,3}\s*")

#: Keys of a mapping colour that mean red, green, blue and alpha.
_RGBA_KEYS = frozenset({'r', 'g', 'b', 'a', 'red', 'green', 'blue', 'alpha'})


def _decodeHex(hexVal: str) -> Tuple[int, int, int, int]:
	"""Read 3, 4, 6 or 8 hex digits. Short forms double each digit, as CSS does: ``f80`` is ``ff8800``."""
	if len(hexVal) in (3, 4):
		hexVal = ''.join(c * 2 for c in hexVal)
	channels = tuple(int(hexVal[i:i + 2], 16) for i in range(0, len(hexVal), 2))
	if len(channels) == 3:
		channels = *channels, 255
	return channels


#: Keys of a mapping colour that mean a colour made from Oklch values, not red/green/blue.
_OKLCH_KEYS = frozenset({'hue', 'oklch', 'palette', 'emission'})


def _emission(value) -> Optional[float]:
	"""``emission:`` as a number. ``true`` means the demo's default; ``false`` and ``None`` mean none."""
	if value is None or value is False:
		return None
	if value is True:
		return _oklch.EMISSION
	emission = float(value)
	if emission <= 0:
		raise ValueError(f'emission must be above 0, not {value!r}')
	return emission


def _toBytes(triple, alpha: float = 1.0) -> Tuple[int, int, int, int]:
	return (*(int(round(min(1.0, max(0.0, c)) * 255)) for c in triple), int(round(min(1.0, max(0.0, alpha)) * 255)))


def _decodeOklchSpec(color, decodePlain) -> Optional[Tuple[int, int, int, int]]:
	"""Read the Oklch and emissive colour forms. Gives ``None`` for any other value.

	- ``oklch(0.70 0.20 145)``: a string. The chroma is lowered into sRGB when it does not fit.
	- ``{hue: 145}``: a hue on the palette ring, at the default lightness and chroma
	  (``lightness:`` and ``chroma:`` change them).
	- ``{oklch: 'oklch(0.70 0.20 145)'}``, ``{oklch: [0.70, 0.20, 145]}``.
	- ``{palette: {hue: 145, scheme: triadic}, index: 1}`` picks one colour of a palette;
	  ``at: 0.5`` mixes along it instead (0 first colour, 1 last).
	- ``{color: '#ff8800', emission: 2}`` on any colour: add ``emission`` to run it through
	  the emissive display chain. ``saturation:`` goes with it.

	Without ``emission`` the colour is shown as it is. A colour with ``emission`` is final: it
	has already been tone mapped.
	"""
	if isinstance(color, str):
		if not _oklch.is_oklch(color):
			return None
		L, C, h, alpha = _oklch.parse_oklch(color)
		return _toBytes(_oklch.oklch_srgb(L, C, h), alpha)
	if not isinstance(color, dict) or not (set(color) & _OKLCH_KEYS or ('color' in color and 'emission' in color)):
		return None
	if set(color) & {'r', 'g', 'b', 'red', 'green', 'blue'}:
		return None
	data = dict(color)
	data.pop('name', None)
	emission = _emission(data.pop('emission', None))
	saturation = float(data.pop('saturation', 1.0))
	alpha = 1.0
	if 'palette' in data:
		from LevityDash.lib.ui.colors.palette import Palette
		palette = Palette.decode(data.pop('palette'))
		linear = palette.sample(index=data.pop('index', None), at=data.pop('at', None))
	elif 'color' in data:
		r, g, b, a = decodePlain(data.pop('color'))
		linear = _oklch.srgb_to_linear((r / 255, g / 255, b / 255))
		alpha = a / 255
	else:
		L = float(data.pop('lightness', _oklch.OKLCH_L))
		C = float(data.pop('chroma', _oklch.OKLCH_C))
		if 'oklch' in data:
			raw = data.pop('oklch')
			if isinstance(raw, str):
				L, C, h, alpha = _oklch.parse_oklch(raw)
			else:
				L, C, h = (float(v) for v in raw)
		elif 'hue' in data:
			h = float(data.pop('hue'))
		else:
			raise ValueError(f'a colour with emission needs a hue, oklch or color: {color!r}')
		linear = _oklch.oklch_color(h, L, C)
	if 'alpha' in data:
		alpha = float(data.pop('alpha'))
	if data:
		raise ValueError(f'unknown colour keys {sorted(map(str, data))}')
	if emission is None:
		triple = _oklch.linear_to_srgb(linear)
	else:
		triple = _oklch.display_color(linear, saturation, emission)
	return _toBytes(triple, alpha)


@rich_repr
class Color:

	__slots__ = ('__red', '__green', '__blue', '__alpha', '__name')
	__match_args__ = ('red', 'green', 'blue', 'alpha')

	__red: int
	__green: int
	__blue: int
	__alpha: int
	__name: Optional[str]

	presets: ClassVar['Preset']

	@classproperty
	def randomColor(cls) -> 'Color':
		return cls(randomColor())

	@classmethod
	def random(cls, min=0, max=255) -> 'Color':
		return cls(randomColor(min, max))

	@classmethod
	def fromTemperature(cls, temp: int | float) -> 'Color':
		return cls(kelvinToRGB(temp))

	@classproperty
	def text(cls) -> 'Color':
		return cls.presets.white

	@classproperty
	def default(cls) -> 'Color':
		return cls.presets.white

	def __init__(
		self,
		color: str | Tuple[int | float, ...] | ColorDict = None, /,
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

	def __parse(self, color: str | Tuple[int | float, ...] | ColorDict):
		colors = self.__decode(color)
		self.__red, self.__green, self.__blue, self.__alpha = tuple(self.__ensureCorrectValue(i) for i in colors)

	@staticmethod
	def __decode(color) -> Tuple[int, int, int, int]:
		if (spec := _decodeOklchSpec(color, Color.__decode)) is not None:
			return spec
		match color:
			case str(color):
				text = color.strip()
				if match := _HEX_REG.fullmatch(text):
					return _decodeHex(match.group(1))
				if _NUMBERS_REG.fullmatch(text):
					return Color.__decode([float(i) if '.' in i else int(i) for i in re.split(r'[,\s]+', text)])
				if QColor.isValidColorName(text):
					return QColor.fromString(text).getRgb()
				# A hex colour inside other text, such as 'Color(#ff8800)'
				if match := COLOR_REG.search(text):
					return _decodeHex(match.group(1))
				raise ValueError(f'Invalid colors string: {color}')
			case [Number(), Number(), Number()] as rgb:
				return *rgb, 255
			case [Number(), Number(), Number(), Number()] as rgba:
				return tuple(rgba)
			case QColor() as qc:
				return qc.getRgb()
			case dict() if set(color) & _RGBA_KEYS:
				rgb = tuple(
					get(color, *i, expectedType=float | int, default=0)
					for i in (
						('r', 'red'),
						('g', 'green'),
						('b', 'blue'),
					)
				)
				a = get(color, 'a', 'alpha', expectedType=float | int, default=255)
				return *rgb, a
			case int(i) if i <= 255:
				return (i, i, i, 255)
			case int(rgba_hex) if 0xffffff < rgba_hex <= 0xffffffff:
				return tuple(int(i, 16) for i in split(hex(rgba_hex)[2:], 2))
			case int(rgb_hex) if rgb_hex <= 0xffffff:
				return tuple(int(i, 16) for i in split(hex(rgb_hex)[2:], 2)) + (255,)

			case _:
				raise ValueError(f'Invalid color value: {type(color).__name__}({color})')
		return colors

	@staticmethod
	def __ensureCorrectValue(value: int | float | Number) -> int:
		match value:
			case int(value) | np.integer(value):
				return sorted((0, value, 255))[1]
			case float(value) if value <= 1:
				return int(round(value * 255))
			case float(value):
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
	def hue(self) -> float:
		# Verified against the standard HSL/HSV hue formula - correct.
		r, g, b = self.rgbF
		maximum = max(r, g, b)
		minimum = min(r, g, b)
		if maximum == minimum:
			return 0
		elif maximum == r:
			hue = (g - b) / (maximum - minimum)
		elif maximum == g:
			hue = 2 + (b - r) / (maximum - minimum)
		else:
			hue = 4 + (r - g) / (maximum - minimum)
		hue *= 60
		if hue < 0:
			hue += 360
		return hue

	@property
	def saturation(self) -> float:
		# Was the HSV saturation formula ((max-min)/max) in a class that's
		# otherwise HSL (see `lightness` below) - no callers anywhere in the
		# tree, so zero regression risk fixing it to the correct HSL formula
		# (delta / (1 - |2L-1|), equivalently delta/(max+min) for L<=0.5 or
		# delta/(2-max-min) for L>0.5).
		r, g, b = self.rgbF
		maximum = max(r, g, b)
		minimum = min(r, g, b)
		delta = maximum - minimum
		lightness = (maximum + minimum) / 2
		if delta == 0 or lightness in (0, 1):
			return 0
		return delta / (maximum + minimum) if lightness <= 0.5 else delta / (2 - maximum - minimum)

	@property
	def lightness(self) -> float:
		# Verified against the standard HSL lightness formula - correct.
		r, g, b = self.rgbF
		return (max(r, g, b) + min(r, g, b)) / 2

	@property
	def gamma(self) -> float:
		# Not actually a gamma-correction value (there's no exponent/curve
		# applied here) - this is an unweighted mean of the RGB channels, a
		# crude brightness approximation at best (real luminance weights
		# channels unequally, e.g. ITU-R BT.601's 0.299/0.587/0.114). No
		# callers anywhere in the tree; left as-is rather than guessing what
		# a "real" gamma property should compute here.
		r, g, b = self.rgbF
		return (r + g + b) / 3

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
	def decode(cls, color: str | Tuple[int | float, ...] | ColorDict, name: str = None) -> 'Color':
		"""Decode method for deserializing a color from various formats.

		Accepts
		-------
		- Strings
			- RBG/RGBA hex strings (e.g. '#FF0000', '#FF0000FF', '0xFF0000')
			- RGB/RGBA values (e.g. '255 0 0', '255, 0, 0, 255')
			- Web color names (e.g. 'red', 'green', 'blue', 'white', 'black', etc.)
		- List
			- RGB/RGBA integers [0-255] (e.g. [255, 0, 0], [255, 0, 0, 255])
			- RGB/RGBA floats [0-1] (e.g. [1.0, 0.0, 0.0], [1.0, 0.0, 0.0, 1.0])
		- Mapping
			- RGB/RGBA dicts (e.g. {'red': 255, 'green': 0, 'blue': 0}, {'red': 255, 'green': 0, 'blue': 0, 'alpha': 255})

		Parameters
		----------
		color : SupportsColor
			Value to decode into a color object.
		name: str, optional
			Optional name to give the decoded color object.

		Returns
		-------
		Color
			A Color object initialized with the given color.

		Examples
		--------
		>>> Color.decode('#FF0000')
		Color('#FF0000')

		>>> Color.decode((255, 0, 0))
		Color('#FF0000')

		>>> Color.decode({'red': 255, 'green': 0, 'blue': 0})
		Color('#FF0000')

		>>> Color.decode('red')
		Color('#FF0000')
		"""
		if isinstance(color, dict) and 'name' in color:
			color = dict(color)
			name = color.pop('name')
		return cls(**{k: v for k, v in zip(('red', 'green', 'blue', 'alpha'), cls.__decode(color))}, name=name)

	@classmethod
	def representer(cls, dumper, data):
		return dumper.represent_str(str(data))

	def cubehelix_colors(self, count: int = 3) -> Sequence[QColor]:
		from .cubehelix import cubehelix
		colors = cubehelix(count, hue=self.hue/360*3, reverse=True, lightness=(0.1, 0.9), rotations=6)
		return [Color([int(c) for c in i]).QColor for i in colors]



SupportsColor = Union[
	Color,
	Number,
	Tuple[Number, Number],
	Tuple[Number, Number, Number],
	Tuple[Number, Number, Number, Number],
	str,
	ColorDict
]


__all__ = ('Color', 'SupportsColor')

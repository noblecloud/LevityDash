import re
from _warnings import warn
from abc import ABC
from collections import namedtuple
from enum import IntFlag, auto, Enum, EnumMeta
from functools import cached_property
from numbers import Number

import numpy as np
from math import sqrt, nan, inf, degrees as mathDegrees, atan2
from PySide2.QtGui import QTransform, QPolygonF, QPolygon, QPainterPath

from typing import Iterable, List, Optional, Union, Tuple, Set, ClassVar, Type, overload, Callable, TypeVar, TYPE_CHECKING, runtime_checkable, Protocol, Any, SupportsFloat

from PySide2.QtCore import QObject, QPoint, QPointF, QRect, QRectF, QSize, QSizeF, Signal, QMarginsF, QMargins, Qt
from PySide2.QtWidgets import QGraphicsItem
from rich.console import Console
from rich.repr import auto as auto_rich_repr
from yaml import Dumper

from LevityDash.lib.log import LevityUtilsLog as log
from LevityDash.lib.ui import UILogger as guiLog
from LevityDash.lib.utils import ClosestMatchEnumMeta, clearCacheAttr, camelCase, DType, IgnoreOr, Axis
from WeatherUnits import Length

from LevityDash.lib.utils.shared import mostly, clamp, _Panel, joinCase

if TYPE_CHECKING:
	from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel

log = guiLog.getChild('geometry')


def determineAbsolute(value) -> bool:
	absolute = None
	if isinstance(value, MultiDimension):
		absolute = value.absolute
	if isinstance(value, dict):
		absolute = value.get("absolute", None)
		if absolute is None:
			absolute = not value.get("relative", None)
	return absolute


console = Console()


class LocationEnumMeta(ClosestMatchEnumMeta):

	@classmethod
	def all(self):
		return [self.Left, self.TopLeft, self.Top, self.TopRight, self.Right, self.BottomRight, self.Bottom, self.BottomLeft, self.Center]

	@cached_property
	def isCenter(self):
		return not bool(self & (self.Left | self.Top | self.Right | self.Bottom))

	@cached_property
	def isBottomLeft(self):
		return self.isBottom and self.isLeft

	@cached_property
	def isBottomRight(self):
		return self.isBottom and self.isRight

	@cached_property
	def isTopLeft(self):
		return self.isTop and self.isLeft

	@cached_property
	def isBottom(self):
		return bool(self & self.Bottom)

	@cached_property
	def isRight(self):
		return bool(self & self.Right)

	@cached_property
	def isLeft(self):
		return bool(self & self.Left)

	@cached_property
	def isCentered(self):
		return bool((self & LocationFlag.HorizontalCenter) | (self & LocationFlag.VerticalCenter))

	@cached_property
	def isTopRight(self):
		return self.isTop and self.isRight

	@cached_property
	def isTop(self):
		return bool(self & self.Top)

	@cached_property
	def isCorner(self):
		return bool(self & (self.Left | self.Right | self.Top | self.Bottom)) & (bool(self & self.Vertical) == bool(self & self.Horizontal))

	@cached_property
	def isEdge(self):
		return bool(self & (self.Left | self.Right | self.Top | self.Bottom)) & (bool(self & self.Vertical) != bool(self & self.Horizontal))

	def __str__(self):
		if self in self.__members__:
			return self.name
		return type(self).__name__


T = TypeVar('T', bound=IntFlag)


@runtime_checkable
class Directional(Protocol[T]):
	Vertical: T
	Horizontal: T

	isVertical: bool
	isHorizontal: bool
	asAxis: Axis


class LocationFlag(IntFlag, metaclass=LocationEnumMeta):
	Bottom = auto()
	Top = auto()
	Right = auto()
	Left = auto()
	VerticalCenter = auto()
	HorizontalCenter = auto()

	BottomRight = Bottom | Right
	TopRight = Top | Right
	BottomLeft = Bottom | Left
	TopLeft = Top | Left

	CenterRight = VerticalCenter | Right
	CenterLeft = VerticalCenter | Left
	BottomCenter = Bottom | HorizontalCenter
	TopCenter = Top | HorizontalCenter

	Horizontal = Top | Bottom
	Vertical = Left | Right

	Center = VerticalCenter | HorizontalCenter
	Edges = Top | Bottom | Left | Right

	@cached_property
	def isVertical(self) -> bool:
		return bool(self & self.Vertical)

	@cached_property
	def isHorizontal(self) -> bool:
		return bool(self & self.Horizontal)

	@cached_property
	def asAxis(self) -> Axis:  # Horizontal and Vertical are reversed since LocationFlag
		x, y = 0, 0  # describes the nature of the edge rather than direction of change
		if self.isVertical:
			x = Axis.X
		if self.isHorizontal:
			y = Axis.Y
		return Axis(x | y)

	@cached_property
	def action(self) -> Callable:

		def left(rect):
			return QPointF(rect.left(), rect.center().y())

		def top(rect: QRectF):
			return QPointF(rect.center().x(), rect.top())

		def right(rect: QRectF):
			return QPointF(rect.right(), rect.center().y())

		def bottom(rect: QRectF):
			return QPointF(rect.center().x(), rect.bottom())

		def center(rect: QRectF):
			return rect.center()

		def topLeft(rect: QRectF):
			return QPointF(rect.left(), rect.top())

		def topRight(rect: QRectF):
			return QPointF(rect.right(), rect.top())

		def bottomLeft(rect: QRectF):
			return QPointF(rect.left(), rect.bottom())

		def bottomRight(rect: QRectF):
			return QPointF(rect.right(), rect.bottom())

		if self.isLeft and self.isEdge:
			return left
		elif self.isTop and self.isEdge:
			return top
		elif self.isRight and self.isEdge:
			return right
		elif self.isBottom and self.isEdge:
			return bottom
		elif self.isCenter:
			return center
		elif self.isTopLeft:
			return topLeft
		elif self.isTopRight:
			return topRight
		elif self.isBottomLeft:
			return bottomLeft
		elif self.isBottomRight:
			return bottomRight
		else:
			return center

	@classmethod
	def corners(self) -> list['LocationFlag']:
		return [self.TopLeft, self.TopRight, self.BottomLeft, self.BottomRight]

	@classmethod
	def edges(self) -> list['LocationFlag']:
		return [self.Left, self.Top, self.Right, self.Bottom]

	def fromRect(self, rect: QRect):
		if self.isEdge:
			if self.isTop:
				return rect.top()

			elif self.isBottom:
				return rect.bottom()

			elif self.isLeft:
				return rect.left()

			elif self.isRight:
				return rect.right()

		elif self.isCorner:
			if self.isTop and self.isLeft:
				return rect.topLeft()

			elif self.isTop and self.isRight:
				return rect.topRight()

			elif self.isBottom and self.isLeft:
				return rect.bottomLeft()

			elif self.isBottom and self.isRight:
				return rect.bottomRight()

		elif self.isCenter:
			return rect.center()
		else:
			return False

	def sharesDirection(self, other: 'LocationFlag'):
		return self.isEdge and other.isEdge and self.isVertical == other.isVertical

	def inverted(self):
		if self.isLeft:
			x = self.Right
		elif self.isRight:
			x = self.Left
		else:
			x = self.Center

		if self.isTop:
			y = self.Bottom
		elif self.isBottom:
			y = self.Top
		else:
			y = self.Center

		return x | y

	def __wrapPosition(self, position: 'Position'):
		if position.x == 0.5:
			x = self.Center
		elif position.x <= 0.5:
			x = self.Left
		else:
			x = self.Right

		if position.y == 0.5:
			y = self.Center
		elif position.y <= 0.5:
			y = self.Top
		else:
			y = self.Bottom

			return x | y

	def __and__(self, other):
		if isinstance(other, Position) and other.relative:
			other = self.__wrapPosition(other)
		return super(LocationFlag, self).__and__(other)

	def __xor__(self, other):
		if isinstance(other, Position) and other.relative:
			other = self.__wrapPosition(other)
		return super(LocationFlag, self).__xor__(other)

	def __or__(self, other):
		if isinstance(other, Position) and other.relative:
			other = self.__wrapPosition(other)
		return super(LocationFlag, self).__or__(other)


class Direction(int, Enum, metaclass=ClosestMatchEnumMeta):
	Auto = 0
	Vertical = LocationFlag.Vertical.value
	Horizontal = LocationFlag.Horizontal.value

	@cached_property
	def isVertical(self) -> bool:
		return bool(self is self.Vertical)

	@cached_property
	def isHorizontal(self) -> bool:
		return bool(self is self.Horizontal)

	@cached_property
	def asAxis(self) -> Axis:
		if self.isVertical:
			return Axis.Vertical
		else:
			return Axis.Horizontal

	@cached_property
	def dimension(self) -> 'DimensionType':
		if self.isVertical:
			return DimensionType.y
		else:
			return DimensionType.x


class AlignmentFlag(IntFlag, metaclass=LocationEnumMeta):
	Auto = 0
	Bottom = auto()
	Top = auto()
	Right = auto()
	Left = auto()
	VerticalCenter = auto()
	HorizontalCenter = auto()

	BottomRight = Bottom | Right
	TopRight = Top | Right
	BottomLeft = Bottom | Left
	TopLeft = Top | Left

	CenterRight = VerticalCenter | Right
	CenterLeft = VerticalCenter | Left
	BottomCenter = Bottom | HorizontalCenter
	TopCenter = Top | HorizontalCenter

	Vertical = Top | Bottom | VerticalCenter
	Horizontal = Left | Right | HorizontalCenter

	Center = HorizontalCenter | VerticalCenter

	@cached_property
	def asQtAlignment(self):
		if self.isLeft:
			return Qt.AlignLeft
		elif self.isRight:
			return Qt.AlignRight
		elif self.isTop:
			return Qt.AlignTop
		elif self.isBottom:
			return Qt.AlignBottom
		elif self.isCenter:
			if self.isHorizontal:
				return Qt.AlignHCenter
			else:
				return Qt.AlignVCenter
		else:
			return Qt.AlignCenter

	@cached_property
	def isVertical(self):
		return bool(self & (self.Top | self.Bottom | self.VerticalCenter))

	@cached_property
	def isHorizontal(self):
		return bool(self & (self.Left | self.Right | self.HorizontalCenter))

	@cached_property
	def simplified(self):
		if self.isVertical:
			return self.asVertical
		elif self.isHorizontal:
			return self.asHorizontal
		elif self.isCenter:
			return self.Center.a
		return self

	@cached_property
	def isCenter(self):
		return bool(self & self.Center)

	@cached_property
	def asVertical(self):
		value = self.Vertical & self
		if value:
			return value
		else:
			return AlignmentFlag.VerticalCenter

	@cached_property
	def asHorizontal(self):
		value = self.Horizontal & self
		if value:
			return value
		else:
			return AlignmentFlag.HorizontalCenter


@auto_rich_repr
class Alignment:
	# __slots__ = ('__horizontal', '__vertical', '__dict__')

	@overload
	def __init__(self, alignment: AlignmentFlag): ...

	def __init__(self, horizontal: Union[str, int, AlignmentFlag], vertical: Union[str, int, AlignmentFlag] = None):
		if horizontal is None:
			horizontal = AlignmentFlag.Center
		if vertical is None:
			if isinstance(horizontal, AlignmentFlag):
				self.horizontal = horizontal
				self.vertical = horizontal
			else:
				self.horizontal = AlignmentFlag[horizontal]
				self.vertical = self.horizontal
		else:
			self.horizontal = AlignmentFlag[horizontal]
			self.vertical = AlignmentFlag[vertical]

	@property
	def horizontal(self):
		return AlignmentFlag(self.__horizontal)

	@horizontal.setter
	def horizontal(self, value: Union[str, int, AlignmentFlag]):
		if not isinstance(value, AlignmentFlag):
			value = AlignmentFlag[value]
		value = value.asHorizontal
		assert value.isHorizontal, 'Horizontal alignment can only be horizontal'
		self.__horizontal = value
		clearCacheAttr(self, 'multipliers', 'multipliersAlt')

	@property
	def vertical(self):
		return AlignmentFlag(self.__vertical)

	@vertical.setter
	def vertical(self, value: Union[str, int, AlignmentFlag]):
		if not isinstance(value, AlignmentFlag):
			value = AlignmentFlag[value]
		value = value.asVertical
		assert value.isVertical, 'Vertical alignment must be a vertical flag'
		self.__vertical = value
		clearCacheAttr(self, 'multipliers', 'multipliersAlt')

	def asDict(self):
		return {'horizontal': self.horizontal.simplified.name, 'vertical': self.vertical.simplified.name}

	@property
	def asQtAlignment(self):
		return self.horizontal.asQtAlignment | self.vertical.asQtAlignment

	@cached_property
	def multipliers(self) -> Tuple[float, float]:
		if self.horizontal.isLeft:
			x = -1
		elif self.horizontal.isRight:
			x = 0
		elif self.horizontal.isCenter:
			x = -0.5
		else:
			x = -0.5
		if self.vertical.isTop:
			y = -1
		elif self.vertical.isBottom:
			y = 0
		elif self.vertical.isCenter:
			y = -0.5
		else:
			y = -0.5
		return x, y

	@cached_property
	def multipliersAlt(self) -> Tuple[float, float]:
		if self.horizontal.isLeft:
			x = 0
		elif self.horizontal.isRight:
			x = 1
		elif self.horizontal.isCenter:
			x = 0.5
		else:
			x = 0.5
		if self.vertical.isTop:
			y = 0
		elif self.vertical.isBottom:
			y = 1
		elif self.vertical.isCenter:
			y = 0.5
		else:
			y = 0.5
		return x, y

	@property
	def multipliersCentered(self) -> 'Position':
		if self.horizontal.isLeft:
			x = 0.5
		elif self.horizontal.isRight:
			x = -0.5
		elif self.horizontal.isCenter:
			x = 0
		else:
			x = 0
		if self.vertical.isTop:
			y = 0.5
		elif self.vertical.isBottom:
			y = -0.5
		elif self.vertical.isCenter:
			y = 0
		else:
			y = 0
		return Position(x, y)

	def translationFromCenter(self, rect: QRectF) -> QPointF:
		return self.multipliersCentered*rect.size()

	def __getstate__(self):
		return self.asDict()

	def __setstate__(self, state):
		self.__init__(**state)

	def __rich_repr__(self):
		if (a := self.horizontal.simplified | self.vertical.simplified) in AlignmentFlag:
			yield a.name
		else:
			yield 'horizontal', self.horizontal.name
			yield 'vertical', self.vertical.name

	def __eq__(self, other):
		if isinstance(other, str):
			other = AlignmentFlag[other]
		if isinstance(other, Alignment):
			return self.horizontal == other.horizontal and self.vertical == other.vertical
		if isinstance(other, AlignmentFlag):
			return self.horizontal == other or self.vertical == other or (self.horizontal | self.vertical) == other
		return False

	@classmethod
	def default(cls):
		return cls(AlignmentFlag.Center)

	def isDefault(self) -> bool:
		return self == self.default()

	@classmethod
	def representer(cls, dumper, data: 'Alignment'):
		vertical = data.vertical.simplified
		horizontal = data.horizontal.simplified
		if (a := (horizontal | vertical)) in AlignmentFlag:
			return dumper.represent_str(a.name)
		d = data.asDict()
		# if d['horizontal'] == AlignmentFlag.HorizontalCenter:
		# 	d['horizontal'] = 'Center'
		# if d['vertical'] == AlignmentFlag.VerticalCenter:
		# 	d['vertical'] = 'Center'
		return dumper.represent_dict(d)


class DisplayPosition(str, Enum, metaclass=ClosestMatchEnumMeta):
	# secondaryPositions: ClassVar[Set['DisplayPosition']]

	Auto = 'auto'  # Places the unit in a new line if results in better readability
	Inline = 'inline'  # Always displays the unit in the same line as the value
	NewLine = 'newline'  # Always displays the unit on a new line
	Above = 'above'  # Displays the unit above the value
	Below = 'below'  # Displays the unit below the value
	Hidden = 'hidden'  # Hides the unit completely
	Floating = 'floating'  # Displays the unit in a separate label that can be placed anywhere
	FloatUnder = 'float-under'
	Center = 'center'  # Displays the unit in the center of the value
	Left = 'left'  # Displays the unit to the left of the value
	Right = 'right'  # Displays the unit to the right of the value
	Top = Above
	Bottom = Below

	def getOpposite(self):
		if self is DisplayPosition.Above:
			return DisplayPosition.Below
		elif self is DisplayPosition.Below:
			return DisplayPosition.Above
		elif self is DisplayPosition.Left:
			return DisplayPosition.Right
		elif self is DisplayPosition.Right:
			return DisplayPosition.Left
		elif self is DisplayPosition.Inline:
			return DisplayPosition.NewLine
		else:
			return None


DisplayPosition.secondaryPositions = {
	DisplayPosition.Below,
	DisplayPosition.Auto,
	DisplayPosition.Hidden,
	DisplayPosition.Inline,
	DisplayPosition.Floating,
	DisplayPosition.FloatUnder
}


class MutableFloat:
	__slots__ = ('__value')
	__value: float

	def __init__(self, value: float):
		self.value = value

	@classmethod
	def representer(cls, dumper, data):
		return dumper.represent_float(round(data.__value, 5))

	@property
	def value(self) -> float:
		if not isinstance(self.__value, float):
			self.__value = float(self.__value)
		return self.__value

	@value.setter
	def value(self, value):
		if isinstance(value, type(self)):
			self._absolute = value._absolute
		self.__value = self.__parseValue(value)

	def _setValue(self, value):
		if value is None:
			value = nan
		try:
			value = float.__float__(self, value)
		except ValueError:
			raise ValueError(f'{value} is not a number')
		self.__value = value

	def __parseValue(self, value) -> float:
		# ! This function must only be used for the object's own value
		# ! if a value needs to be parsed, use __parseOther
		mul = 1
		if value is None:
			return nan
		if isinstance(value, str):
			if '%' in value:
				self._absolute = False
				value = value.replace('%', '')
				mul = 0.01
			elif 'px' in value:
				self._absolute = True
				value = value.replace('px', '')
			value = re.sub(r'[^0-9.]', '', value, 0, re.DOTALL)
		try:
			return float(value)*mul
		except ValueError:
			raise ValueError(f'{value} is not a number')

	def __parseOther(self, value: float | str | int) -> float:
		mul = 1
		if value is None:
			return nan
		if isinstance(value, str):
			if '%' in value:
				value = value.replace('%', '')
				mul = 0.01
			elif 'px' in value:
				value = value.replace('px', '')
			value = re.sub(r'[^0-9.]', '', value, 0, re.DOTALL)
		elif isinstance(value, MutableFloat):
			value = value.value
		elif isinstance(value, int | float | np.number):
			pass
		else:
			raise ValueError(f'{value} is not a number')
		return float(value)*mul

	# def __get__(self, instance, owner):
	# 	return self.__value
	#
	# def __set__(self, instance, value):
	# 	self._setValue(value)

	def __call__(self):
		return self.__value

	def __add__(self, other):
		return self.__class__(self.__value + float(other))

	def __radd__(self, other):
		return self.__add__(other)

	def __iadd__(self, other):
		self.__value += float(other)
		return self

	def __sub__(self, other):
		return self.__class__(self.__value - float(other))

	def __rsub__(self, other):
		return self.__class__(float(other) - self.__value)

	def __isub__(self, other):
		self.__value -= float(other)
		return self

	def __mul__(self, other):
		return self.__class__(self.__value*float(other))

	def __rmul__(self, other):
		return self.__mul__(other)

	def __imul__(self, other):
		self.__value *= float(other)
		return self

	def __truediv__(self, other):
		try:
			return self.__class__(self.__value/float(other))
		except ZeroDivisionError:
			return self.__class__(0)

	def __rtruediv__(self, other):
		return self.__truediv__(other)

	def __itruediv__(self, other):
		self.__value /= float(other)
		return self

	def __floordiv__(self, other):
		return self.__class__(self.__value//float(other))

	def __rfloordiv__(self, other):
		return self.__floordiv__(other)

	def __ifloordiv__(self, other):
		self.__value //= float(other)
		return self

	def __mod__(self, other):
		return self.__class__(self.__value%float(other))

	def __rmod__(self, other):
		return self.__mod__(other)

	def __imod__(self, other):
		self.__value %= float(other)
		return self

	def __pow__(self, other):
		return self.__class__(self.__value ** float(other))

	def __rpow__(self, other):
		return self.__pow__(other)

	def __neg__(self):
		return self.__class__(-self.__value)

	def __pos__(self):
		return self.__class__(+self.__value)

	def __abs__(self):
		return self.__class__(abs(self.__value))

	def __invert__(self):
		return self.__class__(~self.__value)

	def __round__(self, n=None):
		return self.__class__(round(self.__value, n))

	def __floor__(self):
		return self.__class__(self.__value.__floor__())

	def __ceil__(self):
		return self.__class__(self.__value.__ceil__())

	def __trunc__(self):
		return self.__class__(self.__value.__trunc__())

	def __lt__(self, other):
		return self.__value < float(other)

	def __le__(self, other):
		return self.__value <= float(other)

	def __eq__(self, other):
		try:
			return self.__value == self.__parseOther(other)
		except TypeError:
			return False
		except ValueError:
			return False

	def __ne__(self, other):
		return not self.__eq__(other)

	def __gt__(self, other):
		return self.__value > float(other)

	def __ge__(self, other):
		return self.__value >= float(other)

	def __hash__(self):
		return hash(self.__value)

	def __str__(self):
		return str(round(self.__value, 3)).rstrip('0').rstrip('.')

	def __repr__(self):
		return f'<{self.__class__.__name__}({self.__str__()})>'

	def __bool__(self):
		return bool(self.__value)

	def __int__(self):
		return int(self.__value)

	def __float__(self):
		return float(self.__value)

	def __complex__(self):
		return complex(self.__value)

	def __index__(self):
		return int(self.__value)

	def __len__(self):
		return 1

	def is_integer(self) -> bool:
		return self.__value.is_integer()


class DimensionTypeMeta(EnumMeta):

	def __getitem__(cls, name):
		try:
			return super(DimensionTypeMeta, cls).__getitem__(name)
		except KeyError:
			pass
		names = name.split('.')
		names.reverse()
		for name in names:
			name = name.lower()
			if name in cls.__members__:
				return cls.__members__[name]
		if name[0].isalpha() and name[1:].isdigit():
			return cls(int(name[1:]))
		raise KeyError(name)


class DimensionType(int, Enum, metaclass=DimensionTypeMeta):
	x = 1
	y = 2
	z = 3
	w = 4
	t = w
	width = x
	height = y
	depth = z
	column = x
	row = y
	layer = z
	columns = x
	rows = y
	layers = z
	left = x
	top = y
	right = z
	bottom = w


class Dimension(MutableFloat):
	__slots__ = ('_absolute')
	__match_args__ = ('value', 'absolute', 'relative')
	_absolute: bool

	def __init_subclass__(cls, **kwargs):
		super().__init_subclass__()
		if (relativeDecorator := kwargs.get('relativeDecorator', None)) is not None:
			cls.__relativeDecorator__ = relativeDecorator
		if (absoluteDecorator := kwargs.get('absoluteDecorator', None)) is not None:
			cls.__absoluteDecorator__ = absoluteDecorator
		if (dimension := kwargs.get('dimension', None)) is not None:
			cls.__dimension__ = dimension

	@classmethod
	def representer(cls, dumper: Dumper, data):
		return dumper.represent_str(str(data))

	def __init__(self, value: Union[int, float], absolute: bool = None, relative: bool = None):
		super().__init__(value)
		absolute = getattr(self, '_absolute', absolute) if absolute is None else absolute
		# If absolute is not specified, absolute is True
		if relative is None and absolute is None:
			if hasattr(self, '_absolute'):
				absolute = self._absolute
			else:
				if isinstance(value, float) and not value.is_integer() or value <= 1:
					absolute = False
				else:
					absolute = True

		# If both absolute and relative are specified, absolute takes precedence
		elif relative is not None and absolute is not None:
			absolute = relative

		# If Relative is specified, absolute is the opposite of relative
		elif relative is not None:
			absolute = not relative

		# If Absolute is specified, absolute is the same as absolute
		elif absolute is not None:
			pass

		self._absolute = absolute

	def __str__(self):
		if self._absolute:
			string = super(Dimension, self).__str__()
			if self.__absoluteDecorator__:
				string = f'{string}{self.__absoluteDecorator__}'
			# string = Text.assemble((string, 'bold magenta'), (self.__absoluteDecorator__, 'white')).render(console)
			return string

		string = f'{str(round(self.value*100, 1)).rstrip("0").rstrip(".")}'
		if self.__relativeDecorator__:
			string = f'{string}{self.__relativeDecorator__}'
		return string

	@property
	def absolute(self) -> bool:
		return self._absolute

	def toggleAbsolute(self, parentSize: Union[int, float] = None, value: bool = None):
		if value is not None and parentSize is not None:
			if value:
				self.toAbsolute(parentSize)
			else:
				self.toRelative(parentSize)
		elif parentSize is not None:
			if self._absolute:
				self.toRelative(parentSize)
			else:
				self.toAbsolute(parentSize)
		else:
			self._absolute = not self._absolute

	def toggleRelative(self, parentSize: Union[int, float] = None, value: bool = None):
		if value is not None:
			value = not self.relative
		self.toggleAbsolute(parentSize, value)

	@property
	def relative(self) -> bool:
		return not self._absolute

	@classmethod
	@property
	def name(cls) -> str:
		return cls.__name__.split('.')[-1]

	@classmethod
	@property
	def fullName(cls):
		return cls.__name__

	@classmethod
	@property
	def dimension(cls) -> DimensionType:
		return cls.__dimension__

	def __dict__(self):
		return {
			'value':    self.value,
			'absolute': self._absolute,
		}

	def toAbsolute(self, value: float | Number) -> 'Dimension':
		if not self._absolute:
			return self.__class__(self*value, True)
		return self

	def toAbsoluteF(self, value: float | Number) -> float:
		if not self._absolute:
			return self.value*value
		return self

	def toRelative(self, value: float) -> 'Dimension':
		if self._absolute:
			return self.__class__(self/value, False)
		return self

	def toRelativeF(self, value: float) -> float:
		if self._absolute:
			if value:
				return self.value/value
			return 0
		return self

	def setAbsolute(self, value: float):
		self._absolute = True
		self.value = value

	def setRelative(self, value: float):
		self._absolute = False
		self.value = value

	def __truediv__(self, other):
		if isinstance(other, Dimension):
			return self.__class__(self.value/other.value, absolute=not (self.absolute and other.absolute))
		absolute = self > 1 and other > 1
		return self.__class__(self.value/other, absolute=absolute)

	def __mul__(self, other):
		if isinstance(other, Dimension):
			return self.__class__(self.value*other.value, absolute=not (self.absolute and other.absolute))
		absolute = other > 1
		return self.__class__(self.value*other, absolute=absolute)

	def __and__(self, other):
		absolute = other > 1
		if self.relative:
			return self.__class__(self.value*float(other), absolute=absolute)
		return self.__class__(other, absolute=absolute)

	def __or__(self, other):
		absolute = other > 1
		if self.relative:
			return self.__class__(self.value*float(other), absolute=absolute)
		return self.__class__(self.value, absolute=absolute)


class NamedDimension(type):

	def __new__(mcs, name: str, dimension: int, relativeDecorator: str = '%', absoluteDecorator: str = 'px'):
		mcs = type(name, (Dimension,), {})
		mcs.__dimension__ = DimensionType(dimension)
		mcs.__relativeDecorator__ = relativeDecorator
		mcs.__absoluteDecorator__ = absoluteDecorator
		return mcs


_X = TypeVar('_X', bound=Dimension)
_Y = TypeVar('_Y', bound=Dimension)
_Z = TypeVar('_Z', bound=Dimension)
_T = TypeVar('_T', bound=Dimension)


class Validator(ABC):

	def __init__(self, cls: Type[NamedDimension]):
		self.cls = cls
		self.valueSet = False

	def __set_name__(self, owner, name):
		self.private_name = '__' + name

	def __get__(self, obj, objtype=None):
		return getattr(obj, self.private_name)

	def __set__(self, obj, value):
		if not self.valueSet or not hasattr(obj, self.private_name):
			setattr(obj, self.private_name, value)
			self.valueSet = True
		elif self.valueSet:
			getattr(obj, self.private_name).value = value
		elif isinstance(value, self.cls):
			setattr(obj, self.private_name, value)
			self.valueSet = True
		else:
			log.warning(f'IMPROPER VALUE TYPE FOP {self.cls} {self.private_name}')
			setattr(obj, self.private_name, value)
			self.valueSet = True


class MultiDimensionMeta(type):

	def __new__(
		mcs,
		name: str,
		bases: tuple,
		attrs: dict,
		dimensions: int | float | Iterable[int | float | DimensionType] = None,
		separator: str = None,
		relativeDecorator: str = None,
		absoluteDecorator: str = None,
		extend: bool = False
	):
		if absoluteDecorator is None:
			absoluteDecorator = "px"
		if relativeDecorator is None:
			relativeDecorator = "%"

		if separator is not None:
			pass
		elif separator is None and bases:
			separator = bases[0].__separator__
		else:
			separator = ','

		if isinstance(dimensions, int):
			dimensions = MultiDimensionMeta.parseInt(dimensions)
		if dimensions:
			pass
		elif dimensions is None and bases:
			dimensionBases = [i for i in bases if hasattr(i, '__dimensions__')]
			dimensions = [a for a in dimensionBases[0].__dimensions__.keys()]
		elif dimensions is None:
			dimensions = []

		# Example: for Size {'width': Dimension, 'height': Dimension(100, True)}
		__dimensions__ = {d: NamedDimension(f'{name}.{d.title()}', i + 1, relativeDecorator, absoluteDecorator) for i, d in enumerate(dimensions)}
		if extend:
			__dimensions__ = {**[i for i in bases if hasattr(i, '__dimensions__')][0].__dimensions__, **__dimensions__}

		if name != 'MultiDimension':
			if '__annotations__' in attrs:
				attrs['__annotations__'].update(__dimensions__)
			else:
				attrs['__annotations__'] = __dimensions__
			attrs['__dimensions__'] = __dimensions__

			# Adds the dimension classes to the class
			attrs.update({camelCase(k): v for k, v in __dimensions__.items()})

			for k, v in __dimensions__.items():
				attrs[k] = Validator(v)
				attrs[k.title()] = v

		attrs['__separator__'] = separator
		attrs['__count__'] = len(__dimensions__)

		mcs = type.__new__(mcs, name, bases, attrs)
		mcs.__slots__ = tuple((*__dimensions__, *[f'__{i}' for i in __dimensions__]))
		mcs.__match_args__ = tuple(__dimensions__.keys(), )
		mcs.cls = mcs
		return mcs

	@staticmethod
	def parseInt(dimensions) -> list[str]:
		if 0 < dimensions < 5:
			dimensions = ['x', 'y', 'z', 't'][:dimensions]
		elif dimensions == 0:
			raise ValueError('Dimensions cannot be 0')
		else:
			dimensions = [f'd{i}' for i in range(1, dimensions + 1)]
		return dimensions

	@classmethod
	def representer(cls, dumper, data):
		return dumper.represent_dict(data.__dimensions__)

	def get_dimension(cls, dimension: int | str | DimensionType) -> Dimension:
		match dimension:
			case int(value):
				if value < 1:
					if value < 0:
						raise ValueError('Dimension cannot be negative')
					raise ValueError('Dimension cannot be 0')
				value = sorted([1, value, cls.__count__])[1]
				return list(cls.__dimensions__.values())[value - 1]
			case str(value):
				try:
					return cls.__dimensions__[value]
				except KeyError:
					raise ValueError('Dimension does not exist')
			case DimensionType() as value:
				if type(value) is cls:
					return value
				return cls.get_dimension(value.value)
		raise ValueError('Dimension does not exist')


class MultiDimension(metaclass=MultiDimensionMeta):
	__separator__: ClassVar[str]
	__dimensions__: ClassVar[dict]
	__count__: ClassVar[int]

	def __init__(self,
		*V: Union[int, float, QPoint, QPointF, QSize, QSizeF, dict | Dimension],
		absolute: bool = None,
		relative: bool = None,
		**kwargs):
		if len(V) == 1:
			V = V[0]
		if isinstance(V, (int, float)):
			V = [V]*len(self.__dimensions__)
		elif isinstance(V, dict):
			V = tuple(V[k] for k in self.__dimensions__)
		elif isinstance(V, (QPoint, QPointF, QSize, QSizeF)):
			V = V.toTuple()
		elif len(V) != len(self.__dimensions__):
			V = tuple(kwargs.get(k, 0) for k in self.__dimensions__)
		else:
			V = list(V)

		if kwargs.get('unsorted', False) or all(isinstance(i, tuple(self.__dimensions__.values())) for i in V):
			V_ = V
			V = sorted(V, key=lambda i: type(i).dimension)

			# Warn if the dimensions were not in the correct order
			if any(V[i] is not V_[i] for i in range(len(V))) and not kwargs.get('unsorted', False):
				warn(f'Dimensions were not in the correct order: {V_} -> {V}', UserWarning)
				del V_

		if relative is None and absolute is None:
			# if relative and absolute are both unset, infer from the _values
			# if any of the _values are integers and greater than 50, then the dimension is absolute
			if isinstance(V, Iterable) and len(V) == 1:
				_T = V[0]
			else:
				_T = V
			if isinstance(_T, (QPoint, QPointF, QSize, QSizeF)):
				_T = _T.toTuple()
			elif any(isinstance(i, str) for i in _T):
				_T = [float(i) for i in re.findall(r'[\d|\.]+', ''.join(str(i) for i in _T))]

			if not len(re.findall(r'[^\d|^\.|^\,^\s]+', ''.join(str(i) for i in V))):
				absolute = any((isinstance(t, int) or t.is_integer()) and t > 1 for t in _T)

		elif relative is not None and absolute is not None:
			raise ValueError('Cannot set both absolute and relative')
		elif relative is not None:
			absolute = not relative
		elif absolute is not None:
			pass

		annotations = [i for k, i in self.__annotations__.items() if k in self.__dimensions__]
		for cls, t, s in zip(annotations, V, self.__slots__):
			# if isinstance(t, Dimension):
			# 	if absolute is not None:
			# 		t._absolute = absolute
			if not isinstance(t, dict):
				t = {'value': t}
			if absolute is not None:
				t['absolute'] = absolute
			value = cls(**t)
			setattr(self, s, value)

	@classmethod
	def representer(cls, dumper, data):
		return dumper.represent_str(cls.__separator__.join(tuple(str(i) for i in data.toTuple())))

	@property
	def absolute(self) -> bool:
		return any([x.absolute for x in self])

	@property
	def relative(self) -> bool:
		return any([x.relative for x in self])

	@classmethod
	def get_orthogonal(cls, *dimension: int | DimensionType, value: float | int | None = None, **kwargs) -> Tuple[Dimension, ...]:
		dimensionTypes = list({type(i) for i in dimension})
		if len(dimensionTypes) > 1:
			raise ValueError('Dimensions must be of the same type')
		dimensionType = dimensionTypes.pop()
		dimensions = {cls.get_dimension(i) for i in dimension}
		if value is not None:
			value = float(value)
			return tuple(i(value, **kwargs) for i in cls.__dimensions__.values() if i not in dimensions)
		return tuple(i for i in cls.__dimensions__.values() if i not in dimensions)

	def toRelative(self: DType, *V) -> DType:
		assert len(V) == len(self)
		if any(d is None for d in V):
			raise ValueError('Expected at least one argument')
		value = []
		for i, d in enumerate(self):
			if d is not None:
				value.append(d.toRelative(V[i]))
		return self.cls(*value, relative=True)

	def setRelative(self, *V) -> None:
		assert len(V) == len(self)
		if any(d is None for d in V):
			raise ValueError('Expected at least one argument')
		for v, d in zip(V, self):
			d.setRelative(v)

	def toAbsolute(self: DType, *V, setValue: bool = False) -> DType:
		assert len(V) == len(self)
		if any(d is None for d in V):
			raise ValueError('Expected at least one argument')
		value = []
		for i, d in enumerate(self):
			if d is not None:
				value.append(d.toAbsolute(V[i]))
		return self.cls(*value, absolute=True)

	def setAbsolute(self, *V) -> None:
		assert len(V) == len(self)
		if any(d is None for d in V):
			raise ValueError('Expected at least one argument')
		for v, d in zip(V, self):
			d.setAbsolute(v)

	def toTuple(self: DType) -> tuple[DType]:
		return tuple(self)

	def scoreSimilarity(self, other: DType) -> float:
		if not isinstance(other, type(self)):
			other = type(self)(other)
		if len(self) != len(other):
			return inf
		return sum(abs(i - j) for i, j in zip(self, other))

	def keys(self):
		return self.__dimensions__.keys()

	def values(self):
		return {v: getattr(self, v) for v in self.__dimensions__}.values()

	def items(self):
		return {v: getattr(self, v) for v in self.__dimensions__}.items()

	def __int__(self) -> int:
		return int(self.size)

	def __hash__(self) -> int:
		return hash(tuple(self))

	def __repr__(self) -> str:
		return f'{self.__class__.__name__}({self})'

	def __str__(self) -> str:
		return self.__separator__.join(str(d) for d in self)

	def __iter__(self) -> Iterable:
		return iter(getattr(self, v) for v in self.__dimensions__)

	def __len__(self) -> int:
		return type(self).__count__

	def __wrapOther(self, other: Any) -> tuple[float]:
		if isinstance(other, MultiDimension):
			pass
		elif other is None:
			return tuple([inf]*len(self))
		elif isinstance(other, Iterable):
			other = tuple(other)
		elif isinstance(other, (QPoint, QPointF, QSize, QSizeF)):
			other = other.toTuple()
		elif isinstance(other, (int, float)):
			other = tuple(other)
		elif isinstance(other, dict):
			other = tuple(float(d) for d in other.values())
		elif all(hasattr(other, dimension) for dimension in self.__dimensions__):
			other = tuple(getattr(other, dimension) for dimension in self.__dimensions__)
		s = len(self)
		o = len(other)
		if s == o or o == 1:
			return other
		elif s > o and (mul := s%o)%2 == 0:
			return tuple(i for j in ([*other] for x in range(mul)) for i in j)

		raise TypeError(f'Cannot convert {type(other)} to Size')

	def __bool__(self):
		return all(d is not None for d in self)

	def __add__(self, other: 'MultiDimension') -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(*map(lambda x, y: x + y, self, other))

	def __sub__(self, other: 'MultiDimension') -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(*map(lambda x, y: x - y, self, other))

	def __mul__(self, other: int) -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(*map(lambda x, y: x*y, self, other))

	def __truediv__(self, other: int) -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(*map(lambda x, y: x/y, self, other))

	def __floordiv__(self, other: int) -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(*map(lambda x, y: x//y, self, other))

	def __mod__(self, other: int) -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(*map(lambda x, y: x%y, self, other))

	def __pow__(self, other: int) -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(*map(lambda x, y: x ** y, self, other))

	def __gt__(self, other: 'MultiDimension') -> bool:
		other = self.__wrapOther(other)
		return all(x > y for x, y in zip(self, other))

	def __lt__(self, other: 'MultiDimension') -> bool:
		other = self.__wrapOther(other)
		return all(x < y for x, y in zip(self, other))

	def __ge__(self, other: 'MultiDimension') -> bool:
		other = self.__wrapOther(other)
		return all(x >= y for x, y in zip(self, other))

	def __le__(self, other: 'MultiDimension') -> bool:
		other = self.__wrapOther(other)
		return all(x <= y for x, y in zip(self, other))

	def __eq__(self, other: 'MultiDimension') -> bool:
		if isinstance(other, IgnoreOr) or other is None:
			return False
		other = self.__wrapOther(other)
		return all(x == y for x, y in zip(self, other))

	def __ne__(self, other: 'MultiDimension') -> bool:
		other = self.__wrapOther(other)
		return all(x != y for x, y in zip(self, other))

	def __and__(self, other: 'MultiDimension') -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(*map(lambda x, y: x & y, self, other))

	def __or__(self, other: 'MultiDimension') -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(*map(lambda x, y: x | y, self, other))


class TwoDimensional(Protocol):
	X: ClassVar[Type[_X]]
	Y: ClassVar[Type[_Y]]
	x: _X
	y: _Y


class Size(MultiDimension, dimensions=('width', 'height'), separator=', '):
	Width: ClassVar[Type[Dimension]]
	Height: ClassVar[Type[Dimension]]

	@overload
	def __init__(self, width: float, height: float, **kwargs) -> None: ...

	@overload
	def __init__(self, *args: Dimension, **kwargs) -> None: ...

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	def asQSize(self):
		return QSize(self.x, self.y)

	def asQSizeF(self):
		return QSizeF(self.x, self.y)


class Position(MultiDimension, dimensions=('x', 'y'), separator=', '):
	X: ClassVar[Type[Dimension]]
	Y: ClassVar[Type[Dimension]]

	def __init__(self, x: float, y: float) -> None:
		...

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	def asQPoint(self):
		return QPoint(self.x, self.y)

	def asQPointF(self):
		return QPointF(self.x, self.y)

	@property
	def relativeLocation(self) -> LocationFlag:
		if self.x > 0.5:
			x = LocationFlag.Right
		elif self.x < 0.5:
			x = LocationFlag.Left
		else:
			x = LocationFlag.Center

		if self.y > 0.5:
			y = LocationFlag.Bottom
		elif self.y < 0.5:
			y = LocationFlag.Top
		else:
			y = LocationFlag.Center

		return x | y

	def __and__(self, other: Union['MultiDimension', LocationFlag]) -> 'MultiDimension':
		if isinstance(other, LocationFlag):
			return self.relativeLocation & other
		return self.cls(*map(lambda x, y: x & y, self, other))


class Margins(MultiDimension, dimensions=('left', 'top', 'right', 'bottom'), separator=', '):
	surface: 'Panel'
	default: 'Margins'

	@classmethod
	def representer(cls, dumper, data):
		if (defaults := getattr(data.surface, '__defaults__', {})) and (default := defaults.get('margins', None)):
			nonDefaults = {k: v for i, (k, v) in enumerate(zip(data.__dimensions__, data)) if v != default[i]}
			if len(nonDefaults) == len(data.__dimensions__) or nonDefaults:
				return dumper.represent_dict(nonDefaults)
		return dumper.represent_str(", ".join(tuple(str(i) for i in data.toTuple())))

	@overload
	def __init__(self, surface: 'Panel', /, left: float, top: float, right: float, bottom: float) -> None:
		...

	@overload
	def __init__(self, geometry: 'Geometry', /, left: float, top: float, right: float, bottom: float) -> None:
		...

	def __init__(self, *args, **kwargs):
		parent, *args = args
		# if (geometry := getattr(parent, 'geometry', None)) and not isinstance(geometry, Callable):
		# 	self.geometry = geometry
		# elif
		self.surface: 'Panel' = parent
		super().__init__(*args, **kwargs)

	@classmethod
	def validate(cls, item: Union[dict, tuple, list, str]) -> bool:
		if isinstance(item, str):
			digits = [float(i) for i in re.findall(r'[\d|\.]+', item)]
			return len(digits) == 4
		if isinstance(item, (set, list)):
			return len(item) == 4
		if isinstance(item, dict):
			return len(item) == 4 and all(k in item for k in ('left', 'top', 'right', 'bottom'))
		return False

	@property
	def horizontalSpan(self) -> float:
		if mostly(self.left.relative, self.right.relative):
			return self.relativeHorizontalSpan
		return self.absoluteHorizontalSpan

	@property
	def relativeHorizontalSpan(self) -> float:
		return round(1 - self.relativeLeft - self.relativeRight, 3)

	@property
	def absoluteHorizontalSpan(self) -> float:
		return round(self.surface.geometry.absoluteWidth - (self.absoluteLeft + self.absoluteRight), 3)

	@property
	def verticalSpan(self) -> float:
		if mostly(self.top.relative, self.bottom.relative):
			return self.relativeVerticalSpan
		return self.absoluteVerticalSpan

	@property
	def relativeVerticalSpan(self) -> float:
		return round(1 - self.relativeTop - self.relativeBottom, 3)

	@property
	def absoluteVerticalSpan(self) -> float:
		return round(self.surface.geometry.absoluteHeight - (self.absoluteTop + self.absoluteBottom), 3)

	def __getMargin(self, attr: Union[str, LocationFlag]) -> Union['Margins.Left', 'Margins.Right', 'Margins.Top', 'Margins.Bottom']:
		if isinstance(attr, LocationFlag) and attr.isEdge:
			return getattr(self, attr.name.lower())
		elif isinstance(attr, str) and attr.lower() in self.__dimensions__:
			return getattr(self, attr.lower())
		raise AttributeError(f'{attr} is not a valid attribute')

	def __values(self, *attrs: Union[str, LocationFlag], absolute: bool = True, values: tuple[float] = None) -> Union[List[float], float]:
		attrs = [self.__getMargin(attr) for attr in attrs]

		if values:
			if not isinstance(values, Iterable):
				values = [values]
			assert len(attrs) == len(values) or len(values) == 1
			if len(values) == 1:
				values *= len(attrs)

		surfaceSize = self.surface.geometry.absoluteSize()

		if values:
			for i, attr in enumerate(attrs):
				if attr.absolute == absolute:
					attr.value = values[i]
				elif attr.relative != absolute:
					attr.value = values[i]
				else:
					other = surfaceSize.width.value if attr.name.lower() in ('left', 'right') else surfaceSize.height.value
					attr.value = clamp(other*values[i], 0, other) if attr.absolute else clamp(values[i]/other, 0, 1)
			return None

		for i, attr in enumerate(attrs):
			if attr.absolute and absolute:
				attrs[i] = attr.value
			elif attr.relative and not absolute:
				attrs[i] = attr.value
			else:
				other = surfaceSize.width.value if attr.name.lower() in ('left', 'right') else surfaceSize.height.value
				attrs[i] = attr.value/other if attr.absolute else attr.value*other

		if len(attrs) == 1:
			return attrs[0]
		return attrs

	@property
	def absoluteLeft(self):
		if self.left.absolute:
			return self.left.value
		return self.surface.rect().width()*self.left.value  # /self.surface.scene().viewScale.x

	@absoluteLeft.setter
	def absoluteLeft(self, value):
		if self.left.absolute:
			self.left = value
		else:
			self.left = value/self.surface.rect().width()

	@property
	def absoluteTop(self):
		if self.top.absolute:
			return self.top
		return self.surface.rect().height()*self.top.value

	@absoluteTop.setter
	def absoluteTop(self, value):
		if self.top.absolute:
			self.top = value
		else:
			self.top = value/self.surface.rect().height()

	@property
	def absoluteRight(self):
		if self.right.absolute:
			return self.right.value
		return self.surface.rect().width()*self.right.value  # /self.surface.scene().viewScale.x

	@absoluteRight.setter
	def absoluteRight(self, value):
		if self.right.absolute:
			self.right = value
		else:
			self.right = value/self.surface.rect().width()

	@property
	def absoluteBottom(self):
		if self.bottom.absolute:
			return self.bottom
		return self.surface.rect().height()*self.bottom.value

	@absoluteBottom.setter
	def absoluteBottom(self, value):
		if self.bottom.absolute:
			self.bottom = value
		else:
			self.bottom = value/self.surface.rect().height()

	@property
	def relativeLeft(self):
		if self.left.relative:
			return self.left.value
		return self.left.toRelativeF(self.surface.rect().width())

	@relativeLeft.setter
	def relativeLeft(self, value):
		if self.left.relative:
			self.left = value
		else:
			self.left = value*self.surface.rect().width()

	@property
	def relativeTop(self):
		if self.top.relative:
			return self.top.value
		return self.top.toRelativeF(self.surface.rect().height())

	@relativeTop.setter
	def relativeTop(self, value):
		if self.top.relative:
			self.top = value
		else:
			self.top = value*self.surface.rect().height()

	@property
	def relativeRight(self):
		if self.right.relative:
			return self.right.value
		return self.right.toRelativeF(self.surface.rect().width())

	@relativeRight.setter
	def relativeRight(self, value):
		if self.right.relative:
			self.right = value
		else:
			self.right = value*self.surface.rect().width()

	@property
	def relativeBottom(self):
		if self.bottom.relative:
			return self.bottom.value
		return self.bottom.toRelativeF(self.surface.rect().height())

	@relativeBottom.setter
	def relativeBottom(self, value):
		if self.bottom.relative:
			self.bottom = value
		else:
			self.bottom = value*self.surface.rect().height()

	def absoluteValues(self, edges: List[Union[str, LocationFlag]] = LocationFlag.edges()) -> List[float]:
		return self.__values(*edges)

	def setAbsoluteValues(self, values: list[float], edges: List[Union[str, LocationFlag]] = LocationFlag.edges()) -> List[float]:
		return self.__values(*edges, values=values)

	def relativeValues(self, edges: List[Union[str, LocationFlag]] = LocationFlag.edges()) -> List[float]:
		return self.__values(*edges, absolute=False)

	def setRelativeValues(self, values: list[float], edges: List[Union[str, LocationFlag]] = LocationFlag.edges()) -> List[float]:
		return self.__values(*edges, absolute=False, values=values)

	def asQMarginF(self) -> QMarginsF:
		return QMarginsF(self.absoluteLeft, self.absoluteTop, self.absoluteRight, self.absoluteBottom)

	def asQMargin(self) -> QMargins:
		return QMargins(*[int(i) for i in self.absoluteValues()])

	def asTransform(self) -> QTransform:
		x = self.absoluteLeft
		y = self.absoluteTop
		w = self.relativeHorizontalSpan
		h = self.relativeVerticalSpan
		return QTransform().translate(x, y).scale(w, h)

	@property
	def state(self):
		return {
			'left':   self.left,
			'top':    self.top,
			'right':  self.right,
			'bottom': self.bottom,
		}

	@state.setter
	def state(self, value: dict):
		if isinstance(value, Margins):
			value = value.state
		self.__init__(self.surface, **value)

	def isDefault(self) -> bool:
		return self == self.default()

	@classmethod
	def zero(cls):
		return Margins(_Panel(), 0, 0, 0, 0)

	@classmethod
	def default(cls):
		return Margins(_Panel(), 0.0, 0.0, 0.0, 0.0)


@runtime_checkable
class SupportsDirection(Protocol):
	direction: Direction


class Padding(Margins):
	surface: SupportsDirection

	def __init_old__(self, *args, **kwargs):
		geometry, *args = args
		names = tuple(i.name.casefold() for i in self.dimensions)
		if kwargs:
			if any(name in kwargs for name in names):
				positions = {name: kwargs.pop(name, 0) for name in names}
			elif any(name in kwargs for name in ('horizontal', 'vertical')):
				h = kwargs.pop('horizontal', 0)
				v = kwargs.pop('vertical', 0)
				positions = {'left': h, 'top': v, 'right': h, 'bottom': v}
			elif 'value' in kwargs:
				value = kwargs.pop('value')
				positions = {name: value for name in names}
			else:
				raise ValueError('Invalid arguments')
		else:
			if len(args) == 1:
				args = args[0]
				if isinstance(args, str):
					args = args.split(',')
				if isinstance(args, (float, int)):
					args = [args]*4

			if len(args) == 1:
				args = [args[0]]*4

			elif len(args) == 2:
				args *= 2
			elif len(args) == 4:
				pass
			else:
				raise ValueError('Invalid number of arguments')

			positions = {name: arg for arg, name in zip(args, names)}

		self.geometry = geometry
		super().__init__(**positions)

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if not isinstance(self.surface, SupportsDirection):
			raise TypeError('Surface must support direction')

	@property
	def direction(self) -> Direction:
		return self.surface.direction

	@property
	def primarySpan(self) -> float:
		if self.direction.isVertical:
			return 1 - (self.top + self.bottom)
		return 1 - (self.left + self.right)

	@property
	def orthogonalSpan(self) -> float:
		if self.direction.isVertical:
			return 1 - (self.left + self.right)
		return 1 - (self.top + self.bottom)

	@property
	def primaryLeading(self) -> float:
		if self.direction.isVertical:
			return self.top
		return self.left

	@property
	def primaryTrailing(self) -> float:
		if self.direction.isVertical:
			return self.bottom
		return self.right

	@property
	def orthogonalLeading(self) -> float:
		if self.direction.isVertical:
			return self.left
		return self.top

	@property
	def orthogonalTrailing(self) -> float:
		if self.direction.isVertical:
			return self.right
		return self.bottom


class SizeWatchDog:
	callback: Callable
	step: int
	value: List[int]
	thresholds: List[int]

	def __init__(self, callback: Callable, step: int = 20):
		self.__exc = False
		self.__callback = callback
		self.step = step

	@property
	def step(self):
		return self._step

	@step.setter
	def step(self, value):
		self._step = value
		if isinstance(self.value, float):
			pass

	def relativeCheck(self, value):
		diff = any()

	def setAbsoluteThresholds(self, relative: float):
		self.thresholds = [int(x*relative) for x in self.value]

	def checkValue(self, value: Union[QSizeF, QSize, QPointF, QPoint, QRect, QRectF]):
		if isinstance(value, (QRect, QRectF)):
			value = value.size()
		self.width, self.height = value.toTuple()[-2:]

	@property
	def height(self):
		return self.__height

	@height.setter
	def height(self, value):
		value = int(value)
		if self.valueAtThreshold(self.__height, value):
			self.callback()
			self.__height = value

	def update(self, value: Union[QSizeF, QSize, QPointF, QPoint, QRect, QRectF]):
		self.x, self.y = value.toTuple()

	@property
	def width(self):
		return self.__width

	@width.setter
	def width(self, value):
		value = round(value)
		if self.valueAtThreshold(self.__width, value):
			self.callback()
			self.__width = value

	def valueAtThreshold(self, originalValue: int, value: int) -> bool:
		"""
		Returns True if the value has increased or decreased by the threshold
		:param value: The value to check
		:type value: int
		:param originalValue: The original value
		:type originalValue: int
		:return: True if the value has changed by the step amount
		:rtype: bool
		"""
		return abs(value - originalValue) >= self.step


class GeometrySignals(QObject):
	"""
	A QObject that emits signals for Geometry.
	"""
	#: Signal emitted when the item is moved.
	moved = Signal(Position)
	#: Signal emitted when the item is resized.
	resized = Signal(Size)
	#: Signal emitted when the x-coordinate of the item is changed.
	xChanged = Signal(float)
	#: Signal emitted when the y-coordinate of the item is changed.
	yChanged = Signal(float)
	#: Signal emitted when the width of the item is changed.
	widthChanged = Signal(float)
	#: Signal emitted when the height of the item is changed.
	heightChanged = Signal(float)


class Geometry:
	signals: GeometrySignals
	'''
	Represents the position and size of a Panel.
	'''

	__slots__ = ('_position', '_size', '_surface', '_absolute', 'subGeometries', 'signals', '_aspectRatio', '_fillParent')
	_size: Size
	_position: Position
	_surface: 'Panel'
	subGeometries: List['Geometry']
	_absolute: bool
	_aspectRatio: Optional[float]
	_fillParent: bool

	def __init__(self, /, **kwargs):
		"""
		:key surface: Parent surface
		:type surface: Panel

		:key size: Size of the geometry
		:type size: Size
		:key position: Position of the geometry
		:type position: Position

		:key rect: Rect to use for positioning and sizing
		:type rect: QRectF

		:key absolute: Absolute positioning enabled
		:type absolute: bool
		:key relative: Relative positioning enabled
		:type relative: bool
		"""
		self.surface = kwargs.get('surface', None)
		self._aspectRatio = kwargs.get('aspectRatio', None)
		self.signals = GeometrySignals()

		self.subGeometries = []

		self._absolute = self.__parseAbsolute(kwargs)

		self.size = self.__parseSize(kwargs)
		self.position = self.__parsePosition(kwargs)

	def __parseAbsolute(self, kwargs) -> bool:
		absolute = kwargs.get('absolute', None)
		relative = kwargs.get('relative', None)
		if relative is None and absolute is None:
			absolute = None
		elif absolute != relative:
			pass
		elif relative is not None:
			absolute = not relative
		elif absolute is not None:
			pass
		return absolute

	def __parsePosition(self, kwargs):
		absolute = self.__parseAbsolute(kwargs)
		match kwargs:
			case {'fillParent': True, **rest}:
				return Position(0, 0, absolute=False)
			case {'x': x, 'y': y, **rest}:
				return Position(x=x, y=y, absolute=absolute)
			case {'position': rawPos, **rest} | {'pos': rawPos, **rest}:
				match rawPos:
					case {'x': x, 'y': y, **posRest}:
						absolute = posRest.get('absolute', absolute)
						return Position(x=x, y=y, absolute=absolute)
					case list(rawSize) | tuple(rawSize) | set(rawSize) | frozenset(rawSize):
						return Position(rawPos, absolute=absolute)
					case str(rawPos):
						raise NotImplementedError("Position string parsing not implemented", rawPos)
					case QPointF(x, y) | QPoint(x, y) | QRectF(x, y, _, _) | QRect(x, y, _, _):
						return Position(x, y, absolute=absolute)
					case Position(x, y):
						return rawPos
			case _:
				return Position(0, 0, absolute=absolute)

	def __parseSize(self, kwargs):
		absolute = self.__parseAbsolute(kwargs)
		match kwargs:
			case {'fillParent': True, **rest}:
				return Size(1, 1, absolute=False)
			case {'width': w, 'height': h, **rest} | {'w': w, 'h': h, **rest}:
				return Size(w, h, absolute=absolute)
			case {'size': rawSize, **rest}:
				match rawSize:
					case {'width': w, 'height': h, **sizeRest} | {'w': w, 'h': h, **sizeRest}:
						absolute = sizeRest.get('absolute', absolute)
						return Size(w, h, absolute=absolute)
					case list(rawSize) | tuple(rawSize) | set(rawSize) | frozenset(rawSize):
						return Size(*rawSize, absolute=absolute)
					case str(rawSize):
						raise NotImplementedError("Size string parsing not implemented", rawSize)
					case QSizeF(x, y) | QSize(x, y) | QRectF(_, _, x, y) | QRect(_, _, x, y):
						return Size(x, y, absolute=absolute)
					case Size(x, y):
						return rawSize

			case _:
				return Size(1, 1, absolute=False)

	@classmethod
	def validate(cls, item: dict) -> bool:
		"""
		Validates the geometry item.

		:param item: Geometry item to validate
		:type item: dict
		:return: True if the geometry item is valid, False otherwise
		:rtype: bool
		"""

		size = False
		position = False
		if 'size' in item:
			size = True
		else:
			size = 'width' in item and 'height' in item
		if 'position' in item:
			position = True
		else:
			position = 'x' in item and 'y' in item
		return size and position

	@classmethod
	def representer(cls, dumper: 'StatefulDumper', data: 'Geometry') -> 'MappingNode':
		value = {
			'width':  data.size.width,
			'height': data.size.height,
			'x':      data.position.x,
			'y':      data.position.y
		}
		if data.relativeWidth == 1 and data.relativeHeight == 1 and data.relativeX == 0 and data.relativeY == 0:
			return dumper.represent_dict({'fillParent': True})
		return dumper.represent_dict({k: str(v) for k, v in value.items()})

	@property
	def surface(self):
		return self._surface

	@surface.setter
	def surface(self, value):
		# if self._fillParent:
		# 	size = Size(1, 1, absolute=False)
		# 	position = Position(0, 0)
		# elif self.onGrid:
		# 	if self.size is None:
		# 		size = GridItemSize(1, 1)
		# if self._size is None:
		self._surface = value

	@property
	def size(self) -> Size:
		return self._size

	@size.setter
	def size(self, value):
		if value is None:
			if hasattr(self, '_size') and self._size is not None:
				return
			value = Size(1, 1, absolute=False)
		self._size = value

	@property
	def position(self) -> Position:
		return self._position

	@position.setter
	def position(self, value):
		if value is None:
			if hasattr(self, '_position') and self._position is not None:
				return
			value = Position(0, 0)
		self._position = value

	@property
	def relative(self) -> bool:
		return not self.absolute

	@relative.setter
	def relative(self, value):
		size = self.surface.parent.size().toTuple()
		if value:
			sizeValues = [v.value if v.relative else v.value/i for i, v in zip(size, self.size)]
			positionValues = [v.value if v.relative else v.value/i for i, v in zip(size, self.position)]
			self.size.setRelative(*sizeValues)
			self.position.setRelative(*positionValues)
		else:
			sizeValues = [v.value if v.absolute else v.value*i for i, v in zip(size, self.size)]
			positionValues = [v.value if v.absolute else v.value*i for i, v in zip(size, self.position)]
			self.size.setAbsolute(*sizeValues)
			self.position.setAbsolute(*positionValues)

	def toggleRelative(self, *T):
		"""
		Toggles relative/absolute positioning.
		"""
		size = self.surface.parent.size().toTuple()
		if 'width' in T:
			self.size.width.toggleRelative(size[0])
		if 'height' in T:
			self.size.height.toggleRelative(size[1])
		if 'x' in T:
			self.position.x.toggleRelative(size[0])
		if 'y' in T:
			self.position.y.toggleRelative(size[1])

	def toggleSnapping(self, *T):
		"""
		Toggles snapping.
		"""
		if 'width' in T:
			self.size.width.toggleSnapping()
		if 'height' in T:
			self.size.height.toggleSnapping()
		if 'x' in T:
			self.position.x.toggleSnapping()
		if 'y' in T:
			self.position.y.toggleSnapping()
		self.surface.updateFromGeometry()

	def rectFromParentRect(self, parentRect: QRectF):
		width = self.width if self.size.width.absolute else self.width*parentRect.width()
		height = self.height if self.size.height.absolute else self.height*parentRect.height()
		return QRectF(0, 0, width, height)

	def updateSurface(self, parentRect: QRectF = None, set: bool = False):
		if parentRect is not None:
			if self.size.relative:
				self.surface.setRect(self.rectFromParentRect(parentRect))
			if self.position.relative:
				self.surface.setPos(self.posFromParentPos(parentRect))
		else:
			if parent := self.surface.parent:
				if not parent.rect().isValid():
					parent.geometry.updateSurface()
				self.surface.setRect(self.absoluteRect())
				self.surface.setPos(self.absolutePosition().asQPointF())

	def posFromParentPos(self, parentRect: QRectF):
		if self.position.x.absolute:
			x = self.x
		else:
			x = self.x*parentRect.width()

		# if self.position.y.snapping:
		# 	y = self.gridItem.y
		if self.position.y.absolute:
			y = self.y
		else:
			y = self.y*parentRect.height()
		return QPointF(x, y)

	@property
	def aspectRatio(self):
		return self._aspectRatio

	@aspectRatio.setter
	def aspectRatio(self, value):
		if isinstance(value, bool):
			if value:
				if self._aspectRatio:
					pass
				else:
					self._aspectRatio = self.size.width.value/self.size.height.value
			else:
				self._aspectRatio = False
		elif isinstance(value, float):
			self._aspectRatio = value
		elif isinstance(value, int):
			self._aspectRatio = value/100
		elif isinstance(value, str):
			contains = list(filter(lambda x: x in value, [':', 'x', '*', '/', '\\', '%', ' ', '-', '+']))
			if len(contains) == 0:
				try:
					self._aspectRatio = float(value)
				except ValueError:
					self._aspectRatio = False
			if len(contains) == 1:
				w, h = value.split(contains[0])
				self._aspectRatio = int(w)/int(h)
		else:
			self._aspectRatio = False

	@property
	def absolute(self) -> bool:
		return self.size.absolute and self.position.absolute

	@absolute.setter
	def absolute(self, value):
		size = self.surface.parent.size().toTuple()
		if value:
			sizeValues = [v.value if v.absolute else v.value*i for i, v in zip(size, self.size)]
			positionValues = [v.value if v.absolute else v.value*i for i, v in zip(size, self.position)]
			self.size.setAbsolute(*sizeValues)
			self.position.setAbsolute(*positionValues)
		else:
			sizeValues = [v.value if v.relative else v.value/i for i, v in zip(size, self.size)]
			positionValues = [v.value if v.relative else v.value/i for i, v in zip(size, self.position)]
			self.size.setRelative(*sizeValues)
			self.position.setRelative(*positionValues)

	@property
	def width(self) -> Size.Width:
		return self.size.width

	@width.setter
	def width(self, value):
		self.size.width = value

	@property
	def absoluteWidth(self) -> Size.Width:
		if self.size.width.absolute:
			return self.width
		return self.width.toAbsolute(self.surface.parent.size().width())

	@absoluteWidth.setter
	def absoluteWidth(self, value):
		self.size.width.setAbsolute(value)

	@property
	def relativeWidth(self) -> Size.Width:
		if self.size.width.relative:
			return self.width
		return self.width.toRelative(self.surface.parent.size().width())

	@relativeWidth.setter
	def relativeWidth(self, value):
		self.size.width.setRelative(value)

	@property
	def height(self) -> Size.Height:
		if self.aspectRatio:
			return self.size.width.value*self.aspectRatio
		return self.size.height

	@height.setter
	def height(self, value):
		self.size.height.value = value

	@property
	def absoluteHeight(self) -> Size.Height:
		if self.size.height.absolute:
			return self.height
		return self.height.toAbsolute(self.surface.parent.size().height())

	@absoluteHeight.setter
	def absoluteHeight(self, value):
		self.size.height.setAbsolute(value)

	@property
	def relativeHeight(self) -> Size.Height:
		if self.size.height.relative:
			return self.height
		return self.height.toRelative(self.surface.parent.size().height())

	@relativeHeight.setter
	def relativeHeight(self, value):
		self.size.height.setRelative(value)

	@property
	def x(self) -> Position.X:
		return self.position.x

	@x.setter
	def x(self, value):
		self.position.x.value = value

	@property
	def absoluteX(self) -> Position.X:
		if self.position.x.absolute:
			return self.x
		return self.x.toAbsolute(self.surface.parent.size().width())

	@absoluteX.setter
	def absoluteX(self, value):
		self.position.x.setAbsolute(value)

	@property
	def relativeX(self) -> Position.X:
		if self.position.x.relative:
			return self.x
		return self.x.toRelative(self.surface.parent.size().width())

	@relativeX.setter
	def relativeX(self, value):
		self.position.x.setRelative(value)

	@property
	def y(self) -> Position.Y:
		return self.position.y

	@y.setter
	def y(self, value):
		self.position.y.value = value

	@property
	def absoluteY(self) -> Position.Y:
		if self.position.y.absolute:
			return self.y
		return self.y.toAbsolute(self.surface.parent.size().height())

	@absoluteY.setter
	def absoluteY(self, value):
		self.y.toAbsolute(value)

	@property
	def relativeY(self) -> Position.Y:
		if self.position.y.relative:
			return self.y
		return self.y.toRelative(self.surface.parent.size().height())

	@relativeY.setter
	def relativeY(self, value):
		self.position.y.setRelative(value)

	def rect(self):
		width = self.width
		height = self.height
		return QRectF(0, 0, width, height)

	def setRect(self, rect: QRectF):
		if any(i < 0 for i in rect.size().toTuple()):
			log.warn(f"Trying to set a negative size for panel {self.surface.name}")
			# rect.setRect(rect.x(), rect.y(), 0, 0)
			if any(i < 0 for i in rect.topLeft().toTuple()):
				log.warn(f"Trying to set a negative position for panel {self.surface.name}")
		# rect.setRect(0, 0, rect.width(), rect.height())

		width = rect.width()
		height = rect.height()

		if self.size.width.relative:
			width = width/self.surface.parent.size().width()
		self.size.width = width

		if self.size.height.relative:
			height = height/self.surface.parent.size().height()
		self.size.height = height

	def absoluteRect(self, parentRect: QRectF = None):
		return QRectF(0, 0, self.absoluteWidth, self.absoluteHeight)

	def setAbsoluteRect(self, rect: QRectF):
		self.setRect(rect)

	def setGeometry(self, rect: QRectF):
		p = rect.topLeft()
		rect.moveTo(0, 0)
		self.setRect(rect)
		self.setPos(p)
		self.updateSurface()

	def setAbsoluteGeometry(self, rect: QRectF):
		p = rect.topLeft()
		rect.moveTo(0, 0)
		self.setAbsoluteRect(rect)
		self.setAbsolutePos(p)
		self.updateSurface()

	def setRelativeGeometry(self, rect: QRectF):
		p = rect.topLeft()
		rect.moveTo(0, 0)
		self.setRelativeRect(rect)
		self.setRelativePosition(p)
		self.updateSurface()

	def relativeRect(self) -> QRectF:
		width = self.relativeWidth
		height = self.relativeHeight
		return QRectF(0, 0, width, height)

	def setRelativeRect(self, rect: QRectF):
		self.relativeWidth = rect.width()
		self.relativeHeight = rect.height()

	def pos(self):
		return QPointF(self.x, self.y)

	def setPos(self, pos: QPointF):
		if any(i < 0 for i in pos.toTuple()):
			log.warn(f"Trying to set a negative position for panel {self.surface.name}")

		x = pos.x()
		y = pos.y()

		if self.position.x.relative:
			x = x/self.surface.parent.size().width()
		self.position.x = x

		if self.position.y.relative:
			y = y/self.surface.parent.size().height()
		self.position.y = y

	def toTransform(self) -> QTransform:
		transform = QTransform()
		transform.translate(self.relativeX, self.relativeY)
		transform.scale(self.relativeWidth, self.relativeHeight)
		return transform

	def rectToTransform(self, rect: Union[QRectF, QRect]) -> QTransform:
		sT = self.surface.sceneTransform()
		currentRect = self.surface.rect()
		transform = QTransform()
		transform.scale(rect.width()/currentRect.width(), rect.height()/currentRect.height())
		# transform.translate(sT.dx() - rect.x(), sT.dy() - rect.y())
		return transform

	def absolutePosition(self) -> Position:
		return Position(self.absoluteX, self.absoluteY, absolute=True)

	def setAbsolutePosition(self, pos: QPointF):
		self.absoluteX = pos.x()
		self.absoluteY = pos.y()

	def relativePosition(self):
		return QPointF(self.relativeX, self.relativeY)

	def setRelativePosition(self, pos: QPointF):
		self.relativeX = pos.x()
		self.relativeY = pos.y()

	def absoluteSize(self) -> Size:
		return Size(self.absoluteWidth, self.absoluteHeight, absolute=True)

	def setAbsoluteSize(self, size: QSizeF):
		self.absoluteWidth = size.width()
		self.absoluteHeight = size.height()

	def relativeSize(self) -> Size:
		return Size(self.relativeWidth, self.relativeHeight, absolute=False)

	def setRelativeSize(self, *size: Union[QSizeF, Size, int, float]):
		if len(size) == 1:
			if isinstance(size[0], QSizeF):
				width = size[0].width()
				height = size[0].height()
			elif isinstance(size[0], Size):
				width = size[0].width
				height = size[0].height
			elif isinstance(size[0], (int, float)):
				width = size[0]
				height = size[0]
			else:
				raise TypeError(f"Invalid type {type(size[0])}")
		elif len(size) == 2 and isinstance(size[0], (int, float)) and isinstance(size[1], (int, float)):
			width = size[0]
			height = size[1]
		else:
			raise TypeError(f"Invalid type {type(size)}")

		self.relativeWidth = width
		self.relativeHeight = height

	@property
	def fillParent(self):
		return self.relativeWidth == 1 and self.relativeHeight == 1 and self.relativeX == 0 and self.relativeY == 0

	@fillParent.setter
	def fillParent(self, value):
		if value:
			self.relativeWidth = 1
			self.relativeHeight = 1
			self.relativeX = 0
			self.relativeY = 0

	@property
	def snapping(self) -> bool:
		return self.onGrid

	def __bool__(self) -> bool:
		return bool(self.size) or bool(self.position)

	def __eq__(self, other) -> bool:
		match other:
			case (x, y, width, height):
				return self.x == x and self.y == y and self.width == width and self.height == height
			case {'x': x, 'y': y, 'width': width, 'height': height}:
				return self.x == x and self.y == y and self.width == width and self.height == height
			case Geometry():
				return super().__eq__(other)
			case _:
				return False

	def __iter__(self):
		return iter({
			**self.position,
			**self.size
		}.items())

	def __repr__(self):
		return f'<{self.__class__.__name__}(position=({self.position}), size=({self.size}) for {type(self.surface).__name__})>'

	def addSubGeometry(self, geometry: 'Geometry'):
		self.subGeometries.append(geometry)

	def removeSubGeometry(self, geometry: 'Geometry'):
		self.subGeometries.remove(geometry)

	def copy(self) -> 'Geometry':
		"""
		Returns a copy of the geometry with absolute _values
		:return: Absolute geometry
		:rtype: Geometry
		"""
		return self.__class__(surface=self.surface, size=self.absoluteSize(), position=self.absolutePosition(), absolute=True)

	@property
	def parentGeometry(self) -> Optional['Geometry']:
		surface = self.surface
		parent = getattr(surface, 'parent', None)
		return getattr(parent, 'geometry', None)

	def absoluteGeometrySize(self) -> QSizeF:
		if self.surface.parent is not None and hasattr(self.surface.parent, 'geometry') and hasattr(self.surface.parent.geometry, 'absoluteGeometrySize'):
			parentGeometrySize = self.surface.parent.geometry.absoluteGeometrySize()
			if self.size.relative:
				return QSizeF(parentGeometrySize.width()*self.size.width, parentGeometrySize.height()*self.size.height)
			else:
				return QSizeF(self.size.width, self.size.height)

	@property
	def area(self):
		return self.size.width*self.size.height

	@property
	def absoluteArea(self):
		return self.absoluteWidth*self.absoluteHeight

	@property
	def relativeArea(self):
		if self.parentGeometry:
			return self.parentGeometry.absoluteArea/self.absoluteArea
		w = 100*float(self.relativeWidth)
		h = 100*float(self.relativeHeight)
		return h*w/100

	@property
	def state(self):
		return self.toDict()

	@state.setter
	def state(self, value: dict):
		self.size = self.__parseSize(value)
		self.position = self.__parsePosition(value)
		self.updateSurface()

	def scoreSimilarity(self, other: 'Geometry') -> float:
		"""
		Returns a similarity score between this geometry and another geometry
		:param other: The other geometry
		:type other: Geometry
		:return: The similarity score
		:rtype: float
		"""
		if isinstance(other, dict):
			other = Geometry(surface=self.surface, **other)
		if other.surface is None:
			other.surface = self.surface
		diffX = self.absoluteX - other.absoluteX
		diffY = self.absoluteY - other.absoluteY
		diffWidth = self.absoluteWidth - other.absoluteWidth
		diffHeight = self.absoluteHeight - other.absoluteHeight
		return float((diffX ** 2 + diffY ** 2 + diffWidth ** 2 + diffHeight ** 2) ** 0.5)

	@property
	def sortValue(self) -> tuple[float, float]:
		return self.distanceFromOrigin

	@property
	def distanceFromOrigin(self) -> float:
		return sqrt(self.absoluteX ** 2 + self.absoluteY ** 2)


class StaticGeometry(Geometry):

	def setRect(self, rect):
		self.size.width.value = rect.width()
		self.size.height.value = rect.height()

	@property
	def width(self):
		return self.size.width.value

	@property
	def absoluteWidth(self):
		return self.size.width.value

	@property
	def height(self):
		return self.size.height.value

	@property
	def absoluteHeight(self):
		return self.size.height.value

	@property
	def x(self):
		return self.position.x.value

	@property
	def absoluteX(self):
		return self.position.x.value

	@property
	def y(self):
		return self.position.y.value

	@property
	def absoluteY(self):
		return self.position.y.value

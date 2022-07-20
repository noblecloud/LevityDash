import re
from types import FunctionType

import numpy as np
from abc import ABC
from collections import namedtuple

from functools import cached_property
from math import atan2, degrees as mathDegrees, nan, inf
from PySide2.QtGui import QPainterPath, QPolygon, QPolygonF, QTransform
from PySide2.QtWidgets import QGraphicsItem

from typing import Any, Callable, Iterable, List, Optional, overload, Tuple, Union, Type, ClassVar

from enum import auto, Enum, EnumMeta, IntFlag

from PySide2.QtCore import QMargins, QMarginsF, QPoint, QPointF, QRect, QRectF, QSize, QSizeF, Qt
from WeatherUnits import Length
from yaml import Dumper
from rich.repr import auto as auto_rich_repr

from .shared import _Panel, Auto, clearCacheAttr, ClosestMatchEnumMeta, DType, mostly, Unset, clamp, IgnoreOr, camelCase
from .shared import utilLog as log


class Axis(IntFlag):
	Neither = 0
	Vertical = auto()
	Horizontal = auto()
	Both = Vertical | Horizontal
	Y = Vertical
	X = Horizontal

	@classmethod
	def fromSize(cls, size: Union[QSize, QSizeF]) -> 'Axis':
		axis = Axis.Neither
		if size.width() != 0:
			axis |= Axis.Horizontal
		if size.height() != 0:
			axis |= Axis.Vertical
		return axis


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
		return self.name


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

	@cached_property
	def isVertical(self):
		return bool(self & self.Vertical)

	@cached_property
	def isHorizontal(self):
		return bool(self & self.Horizontal)

	@cached_property
	def asAxis(self):  # Horizontal and Vertical are reversed since LocationFlag
		x, y = 0, 0  # describes the nature of the edge rather than direction of change
		if self.isVertical:
			x = Axis.X
		if self.isHorizontal:
			y = Axis.Y
		return Axis(x | y)

	@cached_property
	def action(self) -> Callable:
		# left = lambda rect: QPointF(rect.left(), rect.center().y())
		# right = lambda rect: QPointF(rect.right(), rect.center().y())
		# top = lambda rect: QPointF(rect.center().x(), rect.top())
		# bottom = lambda rect: QPointF(rect.center().x(), rect.bottom())
		# center = lambda rect: rect.center()
		# topLeft = lambda rect: QPointF(rect.topLeft())
		# topRight = lambda rect: QPointF(rect.topRight())
		# bottomLeft = lambda rect: QPointF(rect.bottomLeft())
		# bottomRight = lambda rect: QPointF(rect.bottomRight())

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
		if isinstance(other, Alignment):
			return self.horizontal == other.horizontal and self.vertical == other.vertical
		if isinstance(other, AlignmentFlag):
			return self.horizontal == other or self.vertical == other or (self.horizontal | self.vertical) == other

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
	Auto = 'auto'  # Places the unit in a new line if results in better readability
	Inline = 'inline'  # Always displays the unit in the same line as the value
	NewLine = 'newline'  # Always displays the unit on a new line
	Above = 'above'  # Displays the unit above the value
	Below = 'below'  # Displays the unit below the value
	Hidden = 'hidden'  # Hides the unit completely
	Floating = 'floating'  # Displays the unit in a separate label that can be placed anywhere
	Center = 'center'  # Displays the unit in the center of the value
	Left = 'left'  # Displays the unit to the left of the value
	Right = 'right'  # Displays the unit to the right of the value
	Top = Above
	Bottom = Below


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

	def __get__(self, instance, owner):
		return self.__value

	def __set__(self, instance, value):
		self._setValue(value)

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


class DimensionType(Enum, metaclass=DimensionTypeMeta):
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
	__slots__ = ('_absolute', '_parent')
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

	@property
	def name(self) -> str:
		return self.__class__.__name__.split('.')[-1]

	@property
	def fullName(self):
		return self.__class__.__name__

	@property
	def dimension(self) -> DimensionType:
		return self.__class__.__dimension__

	def __dict__(self):
		return {
			'value':    self.value,
			'absolute': self._absolute,
		}

	def toAbsolute(self, value: float) -> 'Dimension':
		if not self._absolute:
			return self.__class__(self*value, True)
		return self

	def toAbsoluteF(self, value: float) -> float:
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


class NamedDimension(type):

	def __new__(mcs, name: str, dimension: int, relativeDecorator: str = '%', absoluteDecorator: str = 'px'):
		mcs = type(name, (Dimension,), {})
		mcs.__dimension__ = DimensionType(dimension)
		mcs.__relativeDecorator__ = relativeDecorator
		mcs.__absoluteDecorator__ = absoluteDecorator
		return mcs


# ?TODO: This needs to be merged to the NamedDimension class
class Validator(ABC):

	def __init__(self, cls: NamedDimension):
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


class MultiDimension(metaclass=MultiDimensionMeta):
	__separator__: ClassVar[str]
	__dimensions__: ClassVar[dict]
	__count__: ClassVar[int]

	def __init__(self,
		*V: Union[int, float, QPoint, QPointF, QSize, QSizeF, dict],
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

		assumedAbsolute = Unset
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
				assumedAbsolute = any((isinstance(t, int) or t.is_integer()) and t > 1 for t in _T)
		elif relative is not None and absolute is not None:
			raise ValueError('Cannot set both absolute and relative')
		elif relative is not None:
			absolute = not relative
		elif absolute is not None:
			pass

		annotations = [i for k, i in self.__annotations__.items() if k in self.__dimensions__]
		for cls, t, s in zip(annotations, V, self.__slots__):
			if isinstance(t, Dimension):
				t._absolute = absolute
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
		elif isinstance(other, Iterable):
			other = tuple(other)
		elif isinstance(other, (QPoint, QPointF, QSize, QSizeF, QRect, QRectF)):
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
		return self.cls(map(lambda x, y: x + y, self, other))

	def __sub__(self, other: 'MultiDimension') -> 'MultiDimension':
		other = self.__wrapOther(other)
		return self.cls(map(lambda x, y: x - y, self, other))

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
		if isinstance(other, IgnoreOr):
			return False
		other = self.__wrapOther(other)
		return all(x == y for x, y in zip(self, other))

	def __ne__(self, other: 'MultiDimension') -> bool:
		other = self.__wrapOther(other)
		return all(x != y for x, y in zip(self, other))

	def __and__(self, other: 'MultiDimension') -> 'MultiDimension':
		return self.cls(map(lambda x, y: x & y, self, other))


class Size(MultiDimension, dimensions=('width', 'height'), separator='×'):
	Width: ClassVar[NamedDimension]
	Height: ClassVar[NamedDimension]

	@overload
	def __init__(self, width: float, height: float, **kwargs) -> None: ...

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	def asQSize(self):
		return QSize(self.x, self.y)

	def asQSizeF(self):
		return QSizeF(self.x, self.y)


class Position(MultiDimension, dimensions=('x', 'y'), separator=', '):

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
	surface: _Panel
	default: 'Margins'

	@classmethod
	def representer(cls, dumper, data):
		if (defaults := getattr(data.surface, '__defaults__', {})) and (default := defaults.get('margins', None)):
			nonDefaults = {k: v for i, (k, v) in enumerate(zip(data.__dimensions__, data)) if v != default[i]}
			if len(nonDefaults) == len(data.__dimensions__) or nonDefaults:
				return dumper.represent_dict(nonDefaults)
		return dumper.represent_str(", ".join(tuple(str(i) for i in data.toTuple())))

	@overload
	def __init__(self, surface: _Panel, left: float, top: float, right: float, bottom: float) -> None:
		...

	def __init__(self, surface: _Panel, *args, **kwargs):
		# assert isinstance(surface, QGraphicsItem)
		self.surface: 'Panel' = surface
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
		return self.surface.rect().width()*self.left.value

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
		return self.surface.rect().width()*self.right.value

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

	def isDefault(self) -> bool:
		return self == self.default()

	@classmethod
	def zero(cls):
		return Margins(_Panel(), 0, 0, 0, 0)

	@classmethod
	def default(cls):
		return Margins(_Panel(), 0.1, 0.1, 0.1, 0.1)


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


class GridItemSize(Size):
	pass


class GridItemPosition(Position, dimensions=('column', 'row')):
	index: Optional[int] = None

	def __init__(self, *args: int, grid: 'Grid' = None):
		if isinstance(args[0], GridItemPosition):
			super(GridItemPosition, self).__init__(args[0].column, args[0].row)
		elif isinstance(args[0], Iterable):
			args = args[0]
		if len(args) == 1:
			if grid is None:
				raise ValueError('Grid must be specified when passing index')
			self.index = args[0]
			column, row = self.index%grid.columns, self.index//grid.columns
		else:
			column, row = args[0], args[1]

		if grid is not None:
			self.index = row*grid.columns + column
		super().__init__(column, row)


def offsetAngle(point: tuple, angle: Union[float, int], offset: Union[float, int], radians: bool = False):
	'''
	:param point: tuple of x,y coordinates
	:type point: tuple[int, int]
	:param angle: angle in radians
	:type angle: float, int
	:param offset: distance to offset
	:type offset: float, int
	:return: x and y coordinates of point rotated by theta
	:rtype: tuple
	'''
	if not radians:
		angle = np.radians(angle)
	return (point[0] + offset*np.cos(angle), point[1] + offset*np.sin(angle))


def angleBetweenPoints(pointA: Union[QPointF, QPoint, tuple], pointB: Union[QPointF, QPoint, tuple] = None, degrees: bool = True) -> float:
	if isinstance(pointA, (QPointF, QPoint)):
		pointA = pointA.toTuple()
	if isinstance(pointB, (QPointF, QPoint)):
		pointB = pointB.toTuple()
	if pointB is None:
		pointB = (0, 0)

	xDiff = pointB[0] - pointA[0]
	yDiff = pointB[1] - pointA[1]
	if degrees:
		return mathDegrees(atan2(yDiff, xDiff))
	return atan2(yDiff, xDiff)


def relativePosition(item: 'Panel', relativeTo: QRectF = None) -> LocationFlag:
	if isinstance(item, QGraphicsItem):
		center = item.sceneRect().center()
	elif isinstance(item, QPointF):
		center = item
	if relativeTo is None and isinstance(item, QGraphicsItem):
		relativeTo = item.scene().sceneRect().center()
	elif isinstance(relativeTo, QPointF):
		pass
	if center.x() < relativeTo.x():
		x = LocationFlag.Left
	else:
		x = LocationFlag.Right
	if center.y() < relativeTo.y():
		y = LocationFlag.Top
	else:
		y = LocationFlag.Bottom
	return x | y


def makePropertyGetter(key):
	def get(self):
		return getattr(self, f'__{key}')

	return get


def makePropertySetter(key):
	if isinstance(key, str) and key.isdigit():
		key = int(key)

	def set(self, value):
		try:
			getattr(self, f'__{key}').value = value
		except AttributeError:
			cls = self.__dimensions__[key]
			setattr(self, f'__{key}', cls(value))

	return set


_Position = Union[QPoint, QPointF, Tuple[float, float], Position]
_Size = Union[QSize, QSizeF, Tuple[float, float], Size]
_Rect = Union[QRect, QRectF, Tuple[float, float, float, float]]
SimilarEdges = namedtuple('SimilarEdges', 'edge, otherEdge')
Edge = namedtuple('Edge', 'parent, location, pix')


class ResizeRect(QRectF):

	def __normalizeInput(self, other: Union[QSize, QSizeF, QPoint, QPointF, QRect, QRectF, tuple, MultiDimension]) -> tuple[float, float]:
		if isinstance(other, (QSize, QSizeF, QPoint, QPointF)):
			other = other.toTuple()
		elif isinstance(other, (QRect, QRectF)):
			if any(other.toTuple()):
				other.translate(*(other.topLeft()*-1).toPoint().toTuple())
			other = other.size().toTuple()
		elif isinstance(other, Iterable):
			other = tuple(other)
		elif isinstance(other, MultiDimension):
			other = tuple(other)
		return other[:2]

	def __add__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width() + other[0], self.height() + other[1])

	def __iadd__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		self.setWidth(self.width() + other[0])
		self.setHeight(self.height() + other[1])
		return self

	def __sub__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width() - other[0], self.height() - other[1])

	def __isub__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		self.setWidth(self.width() - other[0])
		self.setHeight(self.height() - other[1])
		return self

	def __mul__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width()*other[0], self.height()*other[1])

	def __imul__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		self.setWidth(self.width()*other[0])
		self.setHeight(self.height()*other[1])
		return self

	def __truediv__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width()/other[0], self.height()/other[1])

	def __itruediv__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		self.setWidth(self.width()/other[0])
		self.setHeight(self.height()/other[1])
		return self

	def __floordiv__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width()//other[0], self.height()//other[1])

	def __mod__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width()%other[0], self.height()%other[1])

	def __divmod__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width()//other[0], self.height()//other[1])

	def __pow__(self, other: QPointF) -> 'ResizeRect':
		other = self.__normalizeInput(other)
		return QRectF(0, 0, self.width() ** other[0], self.height() ** other[1])

	def changeWidth(self, other):
		other = self.__normalizeInput(other)
		self.setWidth(self.width() + other[0])

	def changeHeight(self, other):
		other = self.__normalizeInput(other)
		self.setHeight(self.height() + other[1])

	def changeSize(self, other):
		other = self.__normalizeInput(other)
		self.setWidth(self.width() + other[0])
		self.setHeight(self.height() + other[1])

	def setLeft(self, other: float):
		if self.right() - other < 20:
			return
		super(ResizeRect, self).setLeft(other)

	def setRight(self, other: float):
		if other - self.left() < 20:
			return
		super(ResizeRect, self).setRight(other)

	def setTop(self, other: float):
		if self.bottom() - other < 20:
			return
		super(ResizeRect, self).setTop(other)

	def setBottom(self, other: float):
		if other - self.top() < 20:
			return
		super(ResizeRect, self).setBottom(other)


def polygon_area(path: Union[QPolygonF, QPolygon, QPainterPath, list, tuple]) -> float:
	if isinstance(path, (QPolygonF, QPolygon)):
		path = path.toList()
	elif isinstance(path, QPainterPath):
		path.closeSubpath()
		path = path.toFillPolygon().toList()
	if len(path) < 3:
		return 0
	x = [p.x() for p in path]
	y = [p.y() for p in path]

	"""https://stackoverflow.com/a/49129646/2975046"""
	correction = x[-1]*y[0] - y[-1]*x[0]
	main_area = np.dot(x[:-1], y[1:]) - np.dot(y[:-1], x[1:])
	return 0.5*np.abs(main_area + correction)


SizeInput = str | float | int
SizeOutput = Length | Size.Height | Size.Width
SizeParserSignature = Callable[[SizeInput, SizeOutput, ...], SizeOutput]


def parseSize(value: SizeInput, default: SizeOutput, /, defaultCaseHandler: SizeParserSignature | None = None, dimension: DimensionType = DimensionType.height) -> SizeOutput:
	match value:
		case str(value):
			unit = ''.join(re.findall(r'[^\d\.\,]+', value)).strip(' ')
			match unit:
				case 'cm':
					value = Length.Centimeter(float(value.strip(unit)))
					value.precision = 3
					value.max = 10
					return value
				case 'mm':
					value = Length.Millimeter(float(value.strip(unit)))
					value.precision = 3
					value.max = 10
					return value
				case 'in':
					value = Length.Inch(float(value.strip(unit)))
					value.precision = 3
					value.max = 10
					return value
				case 'pt' | 'px':
					if dimension == DimensionType.height:
						return Size.Height(float(value.strip(unit)), absolute=True)
					return Size.Width(float(value.strip(unit)), absolute=True)
				case '%':
					numericValue = float(value.strip(unit))/100
					if dimension == DimensionType.height:
						return Size.Height(numericValue, relative=True)
					return Size.Width(numericValue, relative=True)
				case _ if defaultCaseHandler is None:
					try:
						if dimension == DimensionType.height:
							return Size.Height(float(value), absolute=True)
						return Size.Width(float(value), absolute=True)
					except Exception as e:
						log.error(e)
						return default
				case _:
					return defaultCaseHandler(value, default, dimension=dimension)
		case float(value) | int(value):
			if value <= 1:
				if dimension == DimensionType.height:
					return Size.Height(value, relative=True)
				return Size.Width(value, relative=True)
			if dimension == DimensionType.height:
				return Size.Height(value, absolute=True)
			return Size.Width(value, absolute=True)
		case _:
			log.error(f'{value} is not a valid value for labelHeight.  Using default value of {default} for now.')
			return default

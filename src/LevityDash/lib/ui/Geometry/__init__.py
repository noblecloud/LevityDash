from math import sqrt
from PySide2.QtGui import QTransform

from typing import Iterable, List, Optional, Union, Tuple, Set

from PySide2.QtCore import QObject, QPoint, QPointF, QRect, QRectF, QSize, QSizeF, Signal
from LevityDash.lib.ui import UILogger as guiLog
from .utils import *

from LevityDash.lib.utils.geometry import MultiDimension, Position, Size

__all__ = ('Geometry', 'StaticGeometry')

log = guiLog.getChild('Geometry')


def determineAbsolute(value) -> bool:
	absolute = None
	if isinstance(value, MultiDimension):
		absolute = value.absolute
	if isinstance(value, dict):
		absolute = value.get("absolute", None)
		if absolute is None:
			absolute = not value.get("relative", None)
	return absolute


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

	__slots__ = ('_position', '_size', '_surface', '_gridItem', '_absolute', 'subGeometries', 'signals', '_aspectRatio', '_fillParent')
	_size: Size
	_position: Position
	gridItem: Optional[GridItem]
	onGrid: bool
	_surface: 'Panel'
	subGeometries: List['Geometry']
	_absolute: bool
	_aspectRatio: Optional[float]
	_fillParent: bool

	def __init__(self, *_, **kwargs):
		"""
		:param surface: Parent surface
		:type surface: Panel
		:param gridItem: GridItem to use for positioning
		:type gridItem: GridItem
		:param size: GSize of the geometry
		:type size: GSize
		:param position: GPosition of the geometry
		:type position: GPosition
		:param rect: Rect to use for positioning and sizing
		:type rect: QRectF
		:param absolute: Absolute positioning enabled
		:type absolute: bool
		:param relative: Relative positioning enabled
		:type relative: bool
		"""
		if _:
			raise TypeError("Geometry takes no positional arguments")
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

	# if size is None:
	# 	if 'width' in kwargs and 'height' in kwargs:
	# 		size = (kwargs['width'], kwargs['height'])
	# 	else:
	# 		size = surface.rect().size()
	# 		if prod(size.toTuple()) == 0:
	# 			size = (100, 100)
	# 			absolute = True
	# 	size = Size(size, absolute=absolute)

	# self.signals.moved.connect(self.repositionSurface)
	# self.signals.resized.connect(self.resizeSurface)

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
	def representer(cls, dumper, data):
		value = {
			'width':  data.size.width,
			'height': data.size.height,
			'x':      data.position.x,
			'y':      data.position.y
		}
		# value =
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

	def __dict__(self):
		return {
			**self.position,
			**self.size
		}

	def __repr__(self):
		return f'<{self.__class__.__name__}(position=({self.position}), size=({self.size}) for {type(self.surface).__name__})>'

	# return f'<{self.__class__.__name__}(position=({self.position}), size=({self.size}) zPosition={round(self.surface.zValue(), 4)})>'

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
		# self.absolute = value.get('absolute', self.position.absolute and self.size.absolute)
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

from PySide2.QtGui import QTransform

from math import prod
from typing import Iterable, List, Optional, Union

from PySide2.QtCore import QObject, QPoint, QPointF, QRect, QRectF, QSize, QSizeF, Signal
from LevityDash.lib.log import LevityGUILog as guiLog
from LevityDash.lib.utils.shared import _Panel
from .utils import *
from LevityDash.lib.utils.geometry import GridItemPosition, GridItemSize, MultiDimension, Position, Size

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

	def __init__(self, surface: 'Panel',
		gridItem: GridItem = None,
		size: Size = None,
		position: Position = None,
		rect: QRectF = None,
		absolute: bool = None,
		relative: bool = None,
		onGrid: bool = None,
		aspectRatio: float = None,
		updateSurface: bool = True,
		fillParent: bool = False,
		**kwargs):
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

		self.signals = GeometrySignals()
		self.aspectRatio = kwargs.get('aspectRatio', False)

		self.subGeometries = []

		if relative is None and absolute is None:
			absolute = None
		elif absolute != relative:
			pass
		elif relative is not None:
			absolute = not relative
		elif absolute is not None:
			pass

		self._absolute = absolute

		if position is None and rect is not None:
			position = Position(rect.pos())
		if size is None and rect is not None:
			size = Size(rect.size())

		del rect

		if onGrid is None and (isinstance(size, GridItemSize) or isinstance(position, GridItemPosition)):
			onGrid = True

		if fillParent:
			size = Size(1, 1, absolute=False)
			position = Position(0, 0)
		elif onGrid:
			if size is None:
				size = GridItemSize(1, 1)
			if position is None:
				grid = None if surface is None else surface.parentGrid
				position = GridItemPosition(None, None, grid)
		else:
			if size is None:
				if 'width' in kwargs and 'height' in kwargs:
					size = (kwargs['width'], kwargs['height'])
				else:
					size = surface.rect().size()
					if prod(size.toTuple()) == 0:
						size = (100, 100)
						absolute = True
				size = Size(size, absolute=absolute)
			elif isinstance(size, GridItemSize):
				size = size
			elif isinstance(size, dict):
				if absolute is not None:
					size['absolute'] = absolute
				size = Size(**size)
			elif isinstance(size, (QSize, QSizeF)):
				size = Size(self, size, absolute=absolute)
			elif isinstance(size, Iterable) and len(size) == 2:
				size = Size(*size, absolute=absolute)

			if position is None:
				if 'x' in kwargs and 'y' in kwargs:
					position = (kwargs['x'], kwargs['y'])
				else:
					position = Position(surface.pos(), absolute=absolute)
				position = Position(position, absolute=absolute)
			elif isinstance(position, GridItemPosition):
				pass
			elif isinstance(position, dict):
				if absolute is not None:
					position['absolute'] = absolute
				position = Position(**position)
			elif isinstance(position, (QPoint, QPointF)):
				position = Position(position, absolute=absolute)
			elif isinstance(position, Iterable) and len(position) == 2:
				position = Position(*position, absolute=absolute)

		# self.gridItem = gridItem
		self._gridItem = gridItem
		self.surface = surface
		if self.surface is not None:
			surface.geometry = self
			if onGrid:
				gridItem = self.surface.parentGrid.createGridItem(self)
		else:
			gridItem = GridItem(self)
		self.size = size
		self.position = position

		if self.absolute and not absolute is None and not absolute:
			self.relative = True

		# if updateSurface and surface is not None:
		# 	self.updateSurface()
		# self.absolute = absolute

		if isinstance(gridItem, dict):
			gridItem = GridItem(**gridItem, surface=surface)
		self._gridItem = gridItem

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
		if self.onGrid:
			value.parentGrid.insert(self)

	@property
	def onGrid(self):
		return self.gridItem is not None

	@property
	def size(self) -> Size:
		return self._size

	@size.setter
	def size(self, value):
		self._size = value

	@property
	def position(self) -> Position:
		return self._position

	@position.setter
	def position(self, value):
		self._position = value

	@property
	def gridItem(self) -> GridItem:
		return self._gridItem

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
			if self.surface.parent:
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
		if self.onGrid:
			if self.size.width.absolute:
				return self.gridItem.absoluteWidth
			return self.gridItem.relativeWidth
		return self.size.width

	@width.setter
	def width(self, value):
		self.size.width = value
		if self.onGrid:
			self.gridItem.absoluteWidth = self.absoluteWidth

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
		if self.onGrid:
			if self.size.height.absolute:
				return self.gridItem.absoluteHeight
			return self.gridItem.relativeHeight
		return self.size.height

	@height.setter
	def height(self, value):
		self.size.height.value = value
		if self.onGrid:
			self.gridItem.absoluteHeight = self.absoluteHeight

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
		if self.position.x.absolute:
			if self.gridItem is not None:
				self.gridItem.x = value
		else:
			if self.gridItem is not None:
				self.gridItem.relativeX = value

	@property
	def absoluteX(self) -> Position.X:
		if self.onGrid:
			return self.gridItem.x
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
		if self.position.y.absolute:
			if self.gridItem is not None:
				self.gridItem.y = value
		else:
			if self.gridItem is not None:
				self.gridItem.relativeY = value

	@property
	def absoluteY(self) -> Position.Y:
		if self.onGrid:
			return self.gridItem.y
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
		if self.onGrid:
			width = self.gridItem.absoluteWidth
			height = self.gridItem.absoluteHeight
		else:
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

		try:
			self.gridItem.absoluteHeight = height
			self.gridItem.absoluteWidth = width
		except AttributeError:
			pass

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

		try:
			self.gridItem.absoluteX = x
			self.gridItem.absoluteY = y
		except AttributeError:
			pass

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
	def snapping(self) -> bool:
		return self.onGrid

	def __bool__(self) -> bool:
		return bool(self.size) or bool(self.position)

	def toDict(self):
		pos = self.position.toDict()
		size = self.size.toDict()
		if 'absolute' in pos and 'absolute' in size and size['absolute'] != pos['absolute']:
			di = {'position': pos, 'size': size}
		else:
			di = {**size, **pos}
		if self.onGrid:
			di['gridItem'] = self.gridItem
		for k, v in di.items():
			if isinstance(v, float):
				di[k] = round(v, 4)
		return di

	def asAbsoluteGeometry(self):
		return {}

	def __repr__(self):
		return f'<{self.__class__.__name__}(position=({self.position}), size=({self.size}) {f", {self.gridItem}," if False else ""} zPosition={round(self.surface.zValue(), 4)})>'

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
		return self.__class__(surface=self.surface, size=self.absoluteSize(), position=self.absolutePosition(), absolute=True, onGrid=self.onGrid, gridItem=self.gridItem)

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

import re
from collections import defaultdict
from dataclasses import dataclass
from functools import partial, cached_property
from typing import List, Dict, Any, Type, Tuple, NamedTuple, SupportsFloat, Set, ClassVar

from PySide2.QtCore import Qt, QPointF, QRectF
from PySide2.QtGui import QPainter, QPen, QColor, QPainterPath
from PySide2.QtWidgets import QGraphicsSceneWheelEvent, QGraphicsPathItem, QGraphicsItem

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.stateful import StateProperty, Stateful
from LevityDash.lib.ui import Color
from LevityDash.lib.ui.frontends.PySide.Modules import Panel, Realtime
from LevityDash.lib.ui.frontends.PySide.utils import DisplayType, DebugPaint, itemLoader
from LevityDash.lib.ui.Geometry import (Geometry, Size, Position, parseSize, size_px, LocationFlag, Direction, AlignmentFlag, Alignment, DisplayPosition, DimensionType, Dimension, size_float, TwoDimensional, parseHeight, parseWidth,
                                        RelativeFloat, Padding)
from LevityDash.lib.utils import recursiveDictUpdate, recursiveRemove, deepCopy, DeepChainMap, mostSimilarDict, sortDict
from LevityDash.lib.ui import UILogger as log
from WeatherUnits import Length

import difflib


@dataclass(frozen=True, slots=True, order=True)
class DimensionSizePosition:
	size: Size.Width | Size.Height
	position: Position.X | Position.Y

	@property
	def sizeName(self) -> str:
		return self.size.name.casefold()

	@property
	def positionName(self) -> str:
		return self.position.name.casefold()

	def __iter__(self):
		return iter((self.size, self.position))


VerticalDimensionSizePosition = DimensionSizePosition(Size.Height, Position.Y)
HorizontalDimensionSizePosition = DimensionSizePosition(Size.Width, Position.X)


class Divider(QGraphicsPathItem, Stateful, tag='divider'):
	direction: Direction
	color: Color
	size: Size.Height | Size.Width | Length
	weight: Size.Height | Size.Width | Length
	opacity: float
	position: Position.X | Position.Y
	leading: Panel | None
	trailing: Panel | None
	stack: "Stack"
	offset: Size.Height | Size.Width | Length | None = 0

	_size: Size.Height | Size.Width | Length = Size.Height(1, relative=True)
	_weight: Size.Height | Size.Width | Length = Size.Height(1, relative=True)
	_color: Color = Color("#FFFFFF")
	_opacity: float = 1.0

	def __init__(self, stack: 'Stack', **kwargs):
		super().__init__()
		self.setParentItem(stack)
		self.stack = stack
		self.position = 0
		self.leading = None
		self.trailing = None
		self.state = self.prep_init(**kwargs)

	def updatePath(self):
		path = self.path()
		direction = self.direction

		stackSize = self.stack.size()
		stackSize = stackSize.width() if direction == Direction.Horizontal else stackSize.height()

		if self.size.relative:
			lineSize = float(self.size*stackSize)
		else:
			lineSize = float(self.size)

		start = -lineSize/2
		stop = lineSize/2

		if self.direction.isVertical:
			pos = float(self.position), stackSize/2
			startX, startY = start, 0
			stopX, stopY = stop, 0
		else:
			pos = stackSize/2, float(self.position)
			startX, startY = 0, start
			stopX, stopY = 0, stop

		self.setPos(*pos)
		path.moveTo(startX, startY)
		path.lineTo(stopX, stopY)

		if self.offset:
			offset = (0, self.offset) if self.direction.isVertical else (self.offset, 0)
			path.translate(*offset)

		self.setPath(path)

	def updateAppearance(self):
		color = self.color
		weight = self.weight
		weight = size_px(weight, self.stack.geometry)
		opacity = sorted((0, self.opacity, 1))[1]
		self.setPen(QPen(QColor(color), weight))
		self.setOpacity(opacity)

	def update(self, **kwargs):
		super().update(**kwargs)

	@StateProperty(
		default=Size.Height(1, relative=True),
		after=updatePath,
		decoder=partial(parseHeight, default=Size.Height(1, relative=True)),
	)
	def size(self) -> Size.Height | Size.Width | Length:
		return self._size

	@size.setter
	def size(self, value: Size.Height | Size.Width | Length):
		self._size = value

	@StateProperty(
		default=Size.Width(1, relative=False),
		after=updatePath,
		decoder=partial(parseWidth, default=Size.Width(1, absolute=True)),
	)
	def weight(self) -> Size.Height | Size.Width | Length:
		return self._weight

	@weight.setter
	def weight(self, value):
		self._weight = value

	@StateProperty(
		default=Color("#FFFFFF"),
		after=update,
	)
	def color(self) -> Color:
		return self._color

	@color.setter
	def color(self, value: Color):
		self._color = value

	@color.decode
	def color(self, value: str | QColor) -> Color:
		match value:
			case str(value):
				try:
					return Color(value)
				except Exception:
					# log.error(f'{value} is not a valid value for Color.  Using default value of #ffffff for now.')
					return Color('#ffffff')
			case QColor():
				value: QColor
				return Color(value.toRgb().toTuple())
			case _:
				# log.error(f'{value} is not a valid value for Color.  Using default value of #ffffff for now.')
				return Color('#ffffff')

	@property
	def direction(self) -> Direction:
		return self.stack.direction

	@property
	def position(self) -> Position.X | Position.Y:
		return self._position

	@position.setter
	def position(self, value: Position.X | Position.Y):
		self._position = value
		self.updatePath()


class DividerProperties(Stateful, tag=...):
	color: Color
	size: Size.Height | Size.Width | Length
	weight: Size.Height | Size.Width | Length
	opacity: float
	offset: Size.Height | Size.Width | Length | None = 0.0
	pen: QPen = QPen(Qt.white, 1)

	_size: Size.Height | Size.Width | Length = Size.Height(1, relative=True)
	_weight: Size.Height | Size.Width | Length = Size.Width(1, absolute=True)
	_color: Color = Color("#FFFFFF")
	_opacity: float = 1.0
	_enabled: bool = False

	def __init__(self, stack: 'Stack', **kwargs):
		super().__init__()
		self.stack = stack
		self.state = self.prep_init(kwargs)

	def __bool__(self) -> bool:
		return self._enabled

	def updatePath(self):
		pass

	def updateAppearance(self):
		color: QColor = self.color.QColor
		weight = self.weight
		weight = size_px(weight, self.stack.geometry)
		opacity = sorted((0, self.opacity, 1))[1]
		color.setAlphaF(opacity)
		pen = QPen(QColor(color), weight)
		self.pen = pen

	@StateProperty(default=False, after=updateAppearance)
	def enabled(self) -> bool:
		return self._enabled

	@enabled.setter
	def enabled(self, value: bool):
		self._enabled = value

	def parseHeight(self, value: str | Size.Height | Size.Width | Length) -> Size.Height | Size.Width | Length:
		return parseHeight(value, Size.Height(1, relative=True))

	def parseWidth(self, value: str | Size.Height | Size.Width | Length) -> Size.Height | Size.Width | Length:
		return parseWidth(value, Size.Width(1, relative=False))

	@StateProperty(
		default=Size.Height(1, relative=True),
		after=updatePath,
		decoder=parseHeight,
	)
	def size(self) -> Size.Height | Size.Width | Length:
		return self._size

	@size.setter
	def size(self, value: Size.Height | Size.Width | Length):
		self._size = value

	@StateProperty(
		default=Size.Width(1, relative=False),
		after=updatePath,
		decoder=parseWidth,
	)
	def weight(self) -> Size.Height | Size.Width | Length:
		return self._weight

	@weight.setter
	def weight(self, value):
		self._weight = value

	@StateProperty(
		default=Color("#FFFFFF"),
		after=updateAppearance,
	)
	def color(self) -> Color:
		return self._color

	@color.setter
	def color(self, value: Color):
		self._color = value

	@color.decode
	def color(self, value: str | QColor) -> Color:
		match value:
			case str(value):
				try:
					return Color(value)
				except Exception:
					# log.error(f'{value} is not a valid value for Color.  Using default value of #ffffff for now.')
					return Color('#ffffff')
			case QColor():
				value: QColor
				return Color(value.toRgb().toTuple())
			case _:
				# log.error(f'{value} is not a valid value for Color.  Using default value of #ffffff for now.')
				return Color('#ffffff')

	@StateProperty(
		default=1.0,
		after=updateAppearance
	)
	def opacity(self) -> float:
		return self._opacity

	@opacity.setter
	def opacity(self, value: float | str):
		if isinstance(value, str):
			value = parseSize(value, 1.0)
		self._opacity = value


class StackedItem(Stateful, tag=...):
	__size = None
	__sizeRatio = None

	__type_cache__ = {}

	statefulParent: 'Stack'
	parent: 'Stack'

	@property
	def hasFixedSize(self) -> bool:
		return self.__size is not None or self.__sizeRatio is not None

	@StateProperty(key='size', default=None, sortOrder=2)
	def _fixedSize(self) -> Size.Height | Size.Width | Length | None:
		return self.__size

	@_fixedSize.setter
	def _fixedSize(self, value: Size.Height | Size.Width | Length | None):
		self.__size = value

	@_fixedSize.decode
	def _fixedSize(self, value: str | int | float) -> Size.Height | Size.Width | Length:
		return parseSize(value, None, dimension=self.parent.direction.dimension)

	@property
	def fixedSize(self) -> Size.Height | Size.Width | None:
		size = self._fixedSize
		if not isinstance(size, Dimension):
			size = size_px(size, self.parent.geometry, dimension=self.parent.direction.dimension)
		if size is not None:
			return size
		sizeRatio = self._sizeRatio
		if sizeRatio is not None:
			if self.parent.direction is Direction.Horizontal:
				sizeRatio = self.geometry.height*sizeRatio
			else:
				sizeRatio = self.parent.geometry.absoluteWidth*self.scene().viewScale.x/sizeRatio
			sizeRatio = self.parent.primaryDimension.size(sizeRatio)
		return sizeRatio

	@StateProperty(key='size-ratio', default=None, sortOrder=2)
	def _sizeRatio(self) -> float | None:
		return self.__sizeRatio

	@_sizeRatio.setter
	def _sizeRatio(self, value: float | None):
		if value is not None:
			Stack.toUpdate.add(self.parent)
		self.__sizeRatio = value

	@_sizeRatio.decode
	def _sizeRatio(self, value: str | int | float) -> float:
		return float(value)

	@_sizeRatio.encode
	def _sizeRatio(self, value: float) -> str:
		if value:
			return f'{value:g}'
		return '0'

	@property
	def sizeRatio(self) -> float | None:
		return self._sizeRatio

	@classmethod
	def get_subclass(cls, sub_cls: Type[Stateful]) -> Type['StackedItem']:
		if issubclass(sub_cls, StackedItem):
			return sub_cls
		if (stacked_sub_cls := StackedItem.__type_cache__.get(sub_cls, None)) is None:
			cls.__type_cache__[sub_cls] = stacked_sub_cls = type(f'Stacked{sub_cls.__name__}', (sub_cls, StackedItem), {})
		return stacked_sub_cls


# @DebugPaint(False)
class Stack(Panel, tag='stack'):
	spacing: Size.Height | Size.Width | float | int | Length
	size: Size.Height | Size.Width | float | int | Length
	direction: Direction
	geometries: Dict[int, Geometry]
	items: List[Panel]

	toUpdate: ClassVar[Set['Stack']] = set()

	_direction: Direction = Direction.Vertical
	_defaultType: Type[Panel] = None
	_size: Size.Height | Size.Width | Length = None
	_minSize: Size.Height | Size.Width | Length = None
	_maxSize: Size.Height | Size.Width | Length = None
	_dividerProps: DividerProperties

	primaryDimension: DimensionSizePosition = DimensionSizePosition(Size.Height, Position.Y)
	orthogonalDimension: DimensionSizePosition = DimensionSizePosition(Size.Width, Position.X)

	presets: Dict[Direction, Dict[str, Dict]] = {
		Direction.Vertical:   {'movable': False},
		Direction.Horizontal: {'movable': False}
	}

	__defaults__ = {
		'defaultType': _defaultType,
	}

	__child_exclude__ = {
		'movable',
		'geometry'
	}

	def __init_subclass__(cls, **kwargs):
		super().__init_subclass__(**kwargs)
		presetDicts = DeepChainMap(*[preset_ for i in cls.mro()[1:] if issubclass(i, Stack) and (preset_ := getattr(i, 'presets', None)) is not None])
		presetDicts.update(cls.presets)
		cls.presets = presetDicts

	def __init__(self, *args, **kwargs):
		self._dividers: List[Tuple[Position, ...]] = []
		self.geometries = defaultdict(partial(Geometry, self))
		Panel.__init__(self, *args, **kwargs)

	# self.signals.resized.connect(self.updateGeometries)

	@cached_property
	def nonStackParent(self) -> Panel:
		up = self.parent
		while isinstance(up, Stack):
			up = up.parent
		return up

	@StateProperty(key='defaultType', sortOrder=0)
	def defaultType(self) -> Type[Panel]:
		stackType = self._defaultType
		if stackType is None and (parentStackType := getattr(self.nonStackParent, 'defaultStackType', None)) is not None:
			stackType = parentStackType
		return stackType or Panel

	@defaultType.setter
	def defaultType(self, value: Type[Panel]):
		if value is not None:
			self._defaultType = value
		else:
			self.__dict__.pop('_defaultType', None)

	@defaultType.encode
	def defaultType(value: Type[Panel]) -> str:
		if (subTag := getattr(value, 'subtag', None)) is not None and isinstance(subTag, str):
			return f'{value.__tag__}.{subTag}'
		return value.__tag__

	@defaultType.decode
	def defaultType(value: str) -> Type[Panel] | None:
		subclasses = tuple(i for i in (Panel, *Panel.__subclasses__()) if getattr(i, "__tag__", '_') == value or i.__name__.casefold() == value.casefold())
		if len(subclasses):
			return subclasses[0]
		return None

	def setGeometries(self, manualSize: Size.Height | Size.Width | float | int | Length = None):
		if not self.geometries:
			return  # no items

		self._dividers.clear()

		dimension = self.direction.dimension

		PrimarySize, PrimaryPosition = self.primaryDimension
		OrthogonalSize, OrthogonalPosition = self.orthogonalDimension
		fixedSizes = [f for i in self.geometries.values() if (f := getattr(i.surface, 'fixedSize', None)) is not None]

		def getSize(item: Panel) -> PrimarySize:
			if self.direction == Direction.Vertical:
				return item.height(), item.width()
			return item.width(), item.height()

		absoluteSpacing = self.spacing_px

		padding = self.padding

		spacing = self.spacing
		if isinstance(spacing, Length):
			spacing = size_px(self.spacing, self.geometry)

		own_size_px, own_ortho_size_px = getSize(self)
		totalFixeSizes = PrimarySize(sum(i.toRelativeF(own_size_px) for i in fixedSizes), absolute=False)

		if manualSize is not None:
			cellSize = manualSize
		else:
			cellSize = self.cellSize

		if cellSize is not None and cellSize < 0:
			self.setGeometries(manualSize=PrimarySize(1, absolute=False))
			cellSize = getSize(max((i.boundingRect() for i in self._attrGroups['text'].items), key=lambda i: getSize(i)))
		if cellSize is None:
			breaks = len(self.geometries) - 1
			spacingTotal = breaks*absoluteSpacing
			remainingSpace = padding.primarySpan - (float(spacingTotal)/own_size_px) - float(totalFixeSizes)
			cellSize = PrimarySize(remainingSpace/((len(self.geometries) - len(fixedSizes)) or remainingSpace), absolute=False)

		if self.minCellSize is not None:
			cellSize = max(cellSize, self.minCellSize)
		if self.maxCellSize is not None:
			cellSize = min(cellSize, self.maxCellSize)

		if isinstance(cellSize, (Length, int, float)):
			size = size_px(cellSize, dimension)
			cellSize = PrimarySize(size, absolute=True)

		orthoOffset = OrthogonalPosition(0, absolute=False)  # This should always be 0 unless diagonal
		orthoPosition = OrthogonalPosition(0 + padding.orthogonalLeading, absolute=False)
		orthoLeading = OrthogonalPosition(0, absolute=False)
		orthoTrailing = OrthogonalPosition(1, absolute=False)

		if dividers := self.dividers:
			dividerSize = dividers.size
			if isinstance(dividerSize, Length) or dividerSize.absolute:
				dividerSize = size_float(dividerSize, self.geometry, dimension)

			dividerOffset = (1 - dividerSize)/2

			dividerLeading = orthoLeading + dividerOffset
			dividerTrailing = orthoTrailing - dividerOffset
		else:
			dividerLeading = orthoLeading
			dividerTrailing = orthoTrailing

		orthoSize = OrthogonalSize(padding.orthogonalSpan, absolute=False)

		if cellSize.relative and spacing.absolute:
			spacing = spacing.toRelative(own_size_px)

		size = Size(cellSize, orthoSize, unsorted=True)

		defaultOffset = Position(PrimaryPosition(cellSize + spacing), orthoOffset, unsorted=True)
		position = Position(PrimarySize(0 + padding.primaryLeading), orthoPosition, unsorted=True)

		for index, geometry in enumerate(self.geometries.values()):
			geometry.position = Position(position)
			if (fixedSize := getattr(geometry.surface, 'fixedSize', None)) is not None:
				fixedSize = fixedSize.toRelativeF(own_size_px)
				geometry.size = Size(PrimarySize(fixedSize), orthoSize, unsorted=True)
				offset = Position(PrimaryPosition(fixedSize + spacing), orthoOffset, unsorted=True)
			else:
				geometry.size = size
				offset = defaultOffset
			geometry.updateSurface()
			position += offset
			if dividers and index < len(self.geometries) - 1:
				if self._dividers:
					firstPoint, secondPoint = [i + offset for i in self._dividers[-1]]
				else:
					itemSize, _ = getSize(geometry)
					itemSize += padding.primaryLeading
					firstPoint = Position(PrimaryPosition(itemSize + (spacing/2)), dividerLeading, unsorted=True)
					secondPoint = Position(PrimaryPosition(itemSize + (spacing/2)), dividerTrailing, unsorted=True)
				self._dividers.append((firstPoint, secondPoint))

	def updateValueTypes(self):
		dimension = self.direction.dimension
		sizeType, positionType = Size.get_dimension(dimension), Position.get_dimension(dimension)
		orthoPosType, orthoSizeType = Position.get_orthogonal(dimension)[0], Size.get_orthogonal(dimension)[0]
		self.primaryDimension = DimensionSizePosition(sizeType, positionType)
		self.orthogonalDimension = DimensionSizePosition(orthoSizeType, orthoPosType)

	@StateProperty(default=Stateful, allowNone=False)
	def dividers(self) -> DividerProperties:
		return self._dividerProps

	@dividers.setter
	def dividers(self, value: DividerProperties):
		self._dividerProps = value

	@dividers.factory
	def dividers(self) -> DividerProperties:
		return DividerProperties(self)

	@property
	def hasChildren(self) -> bool:
		return len(self.geometries) > 0

	@StateProperty(after=setGeometries, sort=False, dependancies={..., 'size', 'spacing', 'padding', 'dividers'})
	def items(self) -> List[Dict[str, Any]]:
		items = list(geometry.surface for geometry in self.geometries.values())
		return items

	@items.setter
	def items(self, value: List[CategoryItem]):
		existing = [item for item in self.childPanels]
		self.geometries.clear()
		direction = self.direction
		preset = self.presets[direction]
		defaultType = self.defaultType

		self.itemSetter(defaultType, existing, preset, value)

		for item in existing:
			self.scene().removeItem(item)

	def itemSetter(self, defaultType, existing, preset, value):
		for index, item in enumerate(value):
			if isinstance(item, str):
				key = CategoryItem(item)
				state = DeepChainMap({'key': key}, preset).to_dict()
				item = self.extractExisting(state, existing) or defaultType(self, **state)

			elif isinstance(item, dict):
				match item:
					case {'type': str(itemTypeStr), **state}:
						itemType = Stack.defaultType.decodeValue(itemTypeStr, self)
					case dict(state):
						itemType = self.defaultType
					case _:
						continue
				state = DeepChainMap(state, preset).to_dict()

				if (existingItem := self.extractExisting(state, existing)) is not None:
					existingItem.state = state
					item = existingItem
				else:
					itemType = StackedItem.get_subclass(itemType)
					item = itemType(self, **state)
			else:
				continue
			if (geometry := getattr(item, 'geometry', None)) is not None:
				self.geometries[index] = geometry
			else:
				print(f'{item} has no geometry')

	def extractExisting(self, state_: dict, existing_: List[Panel], itemType: Type[Panel] = None) -> Panel | None:
		if itemType is None:
			itemType = self.defaultType
		sameTypeItems = tuple(item for item in existing_ if isinstance(item, itemType))
		match len(sameTypeItems):
			case 0:
				return None
			case 1:
				return existing_.pop(existing_.index(sameTypeItems[0]))
			case _:
				# TODO: This is probably the worst way to do this but it works for now...
				refState = sortDict(state_)
				refState.pop('items', None)
				choices = [i.encodedYAMLState({'items'}, sort=True) for i in existing_]
				index, _ = mostSimilarDict(refState, choices)
				choice = existing_.pop(index)
				return choice

	def _parseCellSize(self, value: str) -> Size.Height | Size.Width | Length:
		dimension = self.primaryDimension.size
		return parseSize(value, dimension(0, absolute=False), dimension=self.direction.dimension)

	@StateProperty(key='item-size', default=None, after=setGeometries, dependancies={'geometry'}, decoder=_parseCellSize)
	def cellSize(self) -> Size.Height | Size.Width | Length | None:
		"""
		The size for each item in the list.
		"""
		return self._size

	@cellSize.setter
	def cellSize(self, value: Size.Height | Size.Width | Length | None):
		self._size = value

	@StateProperty(key='item-size-min', default=None, after=setGeometries, dependancies={'geometry'}, decoder=_parseCellSize)
	def minCellSize(self) -> Size.Height | Size.Width | Length | None:
		"""
		The minimum size for each item in the list.
		"""
		return self._minSize

	@minCellSize.setter
	def minCellSize(self, value: Size.Height | Size.Width | Length | None):
		self._minSize = value

	@StateProperty(key='item-size-max', default=None, after=setGeometries, dependancies={'geometry'}, decoder=_parseCellSize)
	def maxCellSize(self) -> Size.Height | Size.Width | Length | None:
		"""
		The maximum size for each item in the list.
		"""
		return self._maxSize

	@maxCellSize.setter
	def maxCellSize(self, value: Size.Height | Size.Width | Length | None):
		self._maxSize = value

	@property
	def size_px(self) -> int | float:
		return size_px(self.size, self.geometry)

	@StateProperty(key='spacing', default=Size.Height(5, absolute=True), allowNone=False, after=setGeometries, dependancies={'geometry'})
	def spacing(self) -> Size.Height | Size.Width | Length:
		"""
		The spacing between items in the list.
		"""
		return getattr(self, '_spacing', None)

	@spacing.setter
	def spacing(self, value: Size.Height | Size.Width | Length | None):
		self._spacing = value

	@spacing.decode
	def spacing(value: str | int | float) -> Size.Height | Size.Width | Length:
		return parseSize(value, Size.Height(5, absolute=True))

	@property
	def spacing_px(self) -> int | float:
		return size_px(self.spacing, self.geometry)

	@StateProperty(key='padding', default=Size.Height(0, absolute=True), after=setGeometries, dependancies={'geometry'})
	def padding_data(self) -> Size.Height | Size.Width | Length:
		"""
		The padding around the stack.
		"""
		return getattr(self, '_padding', self.primaryDimension.size(0, absolute=True))

	@padding_data.setter
	def padding_data(self, value: Size.Height | Size.Width | Length):
		self._padding = value

	@padding_data.decode
	def padding_data(value: str | int | float) -> Size.Height | Size.Width | Length:
		return parseSize(value, Size.Height(0, absolute=True))

	@property
	def padding(self) -> Padding:
		value = size_float(self.padding_data, self.geometry)
		return Padding(self, value, value, value, value)

	def getItemGeometry(self, index: int | None) -> Geometry:
		if index is None:
			index = len(self.geometries)
		index = sorted((0, index, len(self.geometries)))[1]
		return self.geometries[index]

	@StateProperty(key='direction',
		default=Direction.Vertical,
		after=setGeometries,
		dependancies={'geometry'},
		allowNone=False
	)
	def direction(self) -> Direction:
		"""
		The orientation of the stack.
		"""
		_direction = getattr(self, '_direction', None)
		if _direction is None or _direction is Direction.Auto:
			_direction = Direction.Vertical if self.width() < self.height() else Direction.Horizontal
		return _direction

	@direction.setter
	def direction(self, value: Direction):
		self._direction = value
		self.updateValueTypes()

	@direction.decode
	def direction(value: str) -> Direction:
		return Direction[value.casefold()]

	# Section: itemChange
	def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
		if change is self.ItemTransformHasChanged and any(i.surface.hasFixedSize for i in self.geometries.values()):
			self.updateGeometries()
		return super().itemChange(change, value)

	# Section .paint
	def paint(self, painter: QPainter, option, widget):
		super().paint(painter, option, widget)
		if self.dividers.enabled:
			pen = self.dividers.pen
			painter.setPen(pen)
			ownSize = self.size()
			for divider in self._dividers:
				divider: Position
				first, second = [i.toAbsolute(*ownSize.toTuple()).asQPointF() for i in divider]
				painter.drawLine(first, second)

	def _debug_paint(self, painter, *args, **kwargs):
		self._normal_paint(painter, *args, **kwargs)
		pen = painter.pen()
		pen.setColor(self.debugColor)
		painter.setPen(self.debugPen)
		for item in self.childPanels:
			if hasattr(item, '_debug_paint'):
				continue
			rect = item.mapRectToParent(item.rect())
			painter.setPen(item.debugPen)
			painter.drawRect(rect.adjusted(1, 1, -1, -1))


class ValueStack(Stack, tag='value-stack'):
	presets = {
		Direction.Vertical:   {
			'title':   {
				'alignment':     Alignment(AlignmentFlag.CenterLeft),
				'matchingGroup': {
					'group':    'value-stack.text',
					'matchAll': True
				},
				'position':      DisplayPosition.Left,
				'size':          0.5,
			},
			'display': {
				'displayType': DisplayType.Text,
				'valueLabel':
				               {
					               'alignment':     Alignment(AlignmentFlag.CenterRight),
					               'matchingGroup': {
						               'group':    'value-stack.text',
						               'matchAll': True,
					               },
				               }
			}
		},
		Direction.Horizontal: {
			'title':   {
				'alignment':     Alignment(AlignmentFlag.Center),
				'matchingGroup': {'group': 'value-stack.text'},
				'position':      DisplayPosition.Top,
				'size':          0.2,
			},
			'display': {
				'displayType': DisplayType.Text,
				'valueLabel':
				               {
					               'alignment':     Alignment(AlignmentFlag.Center),
					               'matchingGroup': {
						               'group':    'value-stack.text',
						               'matchAll': True,
					               },
				               }
			}
		}
	}

	_defaultType = Realtime

	__defaults__ = {
		'defaultType': Realtime
	}

	def setAlignments(self):
		labelAlignment = self.labelAlignment
		valueAlignment = self.valueAlignment
		for item in self.childPanels:
			if (title := getattr(item, 'title', None)) is not None:
				title.setAlignment(labelAlignment)
			if (display := getattr(item, 'display', None)) is not None:
				if (valueLabel := getattr(display, 'valueTextBox', None)) is not None:
					valueLabel.setAlignment(valueAlignment)

	def extractExisting(
		self, state_: dict,
		existing_: List[Panel],
		itemType: Type[Panel] = Realtime
	) -> Realtime | None:
		for i, item in enumerate(existing_):
			if item.key == state_['key']:
				return existing_.pop(i)
		return None

	@StateProperty()
	def items(self) -> List[Dict[str, Dict | None] | CategoryItem]:
		items = []
		for item in Stack.items.fget(self):
			match item.state:
				case {'key': key, **state}:
					items.append({key: state} if state else key)
				case self.defaultType():
					items.append(item)
		return items

	def itemSetter(self, defaultType, existing, preset, value):
		defaultType = StackedItem.get_subclass(defaultType)
		stateKeys = set(defaultType.statefulItems)
		for index, item in enumerate(value):
			state = {}
			if isinstance(item, str) and re.match(r'(\w+\.)+?\w+?$', item):
				state['key'] = CategoryItem(item)
			elif isinstance(item, dict):
				firstKey, firstValue = item.popitem()
				if re.match(r'(\w+\.)+?\w+?$', firstKey) or firstValue is None:
					state['key'] = CategoryItem(firstKey)
				elif firstKey == 'type':
					pass

				if set(item) & stateKeys:
					state.update(item)
				elif isinstance(firstValue, dict) and set(firstValue) & stateKeys:
					state.update(firstValue)

			# case dict() if len((key:= list(item.items()))) == 1 and (key := key[0])[1] is None and re.match(r'(\w+\.)+?\w+?$', (key := key[0])):
			# 	state = DeepChainMap({'key': CategoryItem(key)}, preset).to_dict()
			# case {r'(\w+\.)+?\w+?$': dict(state)} if set(state) & set(self.statefulsItems):
			# 	key, state = item.popitem()
			# 	state = DeepChainMap(state, preset).to_dict()
			# 	state['key'] = key
			# case _:
			# 	log.warning(f'Unknown item type: {item}')
			# 	continue

			state = DeepChainMap(state, preset).to_dict()
			if (existingItem := self.extractExisting(state, existing)) is not None:
				existingItem.state = state
				item = existingItem
			else:
				item = defaultType(self, **state)
			if (geometry := getattr(item, 'geometry', None)) is not None:
				self.geometries[index] = geometry
			else:
				print(f'{item} has no geometry')

	@property
	def shared(self):
		return self.presets[self.direction]

	@StateProperty(key='labelAlignment', default=Alignment(vertical=AlignmentFlag.Center, horizontal=AlignmentFlag.Left), after=setAlignments, dependancies={'geometry'})
	def labelAlignment(self) -> Alignment | None:
		"""
		The alignment of the label.
		"""
		return getattr(self, '_labelAlignment', None) or ValueStack.labelAlignment.default(self)

	@labelAlignment.setter
	def labelAlignment(self, value: Alignment | None):
		self._labelAlignment = value

	@labelAlignment.decode
	def labelAlignment(self, value: str) -> Alignment:
		value = AlignmentFlag[value]
		return Alignment(vertical=AlignmentFlag.Center, horizontal=value)

	@labelAlignment.encode
	def labelAlignment(value: Alignment) -> str:
		if value is None:
			return ValueStack.labelAlignment.default(self).name
		return value.horizontal.name

	@StateProperty(key='valueAlignment', default=Alignment(vertical=AlignmentFlag.Center, horizontal=AlignmentFlag.Right), after=setAlignments, dependancies={'geometry'})
	def valueAlignment(self) -> Alignment | None:
		"""
		The alignment of the value.
		"""
		return getattr(self, '_valueAlignment', None) or ValueStack.valueAlignment.default(self)

	@valueAlignment.setter
	def valueAlignment(self, value: Alignment | None):
		self._valueAlignment = value

	@valueAlignment.decode
	def valueAlignment(self, value: str) -> Alignment:
		value = AlignmentFlag[value]
		return Alignment(vertical=AlignmentFlag.Center, horizontal=value)

	@valueAlignment.encode
	def valueAlignment(self, value: Alignment) -> str:
		if value is None:
			return ValueStack.valueAlignment.default(self).name
		return value.horizontal.name

import re
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property, partial
from typing import Any, Dict, List, Optional, Tuple, Type, Mapping

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from LevityDash import LevityDashboard
from LevityDash.lib.plugins.categories import CategoryItem, SomeValidKey
from LevityDash.lib.stateful import Stateful, StateProperty
from LevityDash.lib.ui import Color, UILogger as log
from LevityDash.lib.ui.frontends.PySide.Modules import NonInteractivePanel, Panel, Realtime
from LevityDash.lib.ui.frontends.PySide.utils import DebugPaint, DisplayType
from LevityDash.lib.ui.Geometry import (
	Alignment, AlignmentFlag, Dimension, Direction, DisplayPosition, Geometry, parseHeight, parseSize, parseWidth,
	Position, Size, size_float, size_px
)
from LevityDash.lib.utils import DeepChainMap, mostSimilarDict, sortDict
from WeatherUnits import Length, Percentage


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

		self.prep_init(kwargs=kwargs, stateful_parent=stack)
		self.add_defaults_to_state(kwargs)
		self.state = kwargs

	def updatePath(self):
		path = self.path()
		direction = self.direction

		stackSize = self.stack.size()
		stackSize = stackSize.width() if direction == Direction.Horizontal else stackSize.height()

		if self.size.relative:
			lineSize = float(self.size * stackSize)
		else:
			lineSize = float(self.size)

		start = -lineSize / 2
		stop = lineSize / 2

		if self.direction.isVertical:
			pos = float(self.position), stackSize / 2
			startX, startY = start, 0
			stopX, stopY = stop, 0
		else:
			pos = stackSize / 2, float(self.position)
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
		self.prep_init(kwargs=kwargs, stateful_parent=stack, stateful_key='dividers')
		self.add_defaults_to_state(kwargs)
		self.state = kwargs
		self.stack = stack

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
	_keepInFrame = True
	_index: Optional[int] = None

	__type_cache__ = {}

	statefulParent: 'Stack'
	parent: 'Stack'

	@property
	def index(self) -> int | None:
		return self._index

	@index.setter
	def index(self, value: int):
		self._index = value

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
		if size is None:
			return None
		if not isinstance(size, Dimension):
			size = size_px(size, self.parent.geometry, dimension=self.parent.direction.dimension)
			size = self.parent.primaryDimension.size(size, absolute=True)
		if size is not None:
			return size
		sizeRatio = self._sizeRatio
		if sizeRatio is not None:
			if self.parent.direction is Direction.Horizontal:
				sizeRatio = self.geometry.height * sizeRatio
			else:
				sizeRatio = self.parent.geometry.absoluteWidth * self.scene().viewScale.x / sizeRatio
			sizeRatio = self.parent.primaryDimension.size(sizeRatio)
		return sizeRatio

	@StateProperty(key='size-ratio', default=None, sortOrder=2)
	def _sizeRatio(self) -> float | None:
		return self.__sizeRatio

	@_sizeRatio.setter
	def _sizeRatio(self, value: float | None):
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

	@StateProperty(key='type', inheritFrom=Stateful.type)
	def type(self) -> str:
		pass

	@type.condition(method='get')
	def type(self, value: str) -> bool:
		return value != self.parent.defaultType.__tag__

	@classmethod
	def get_subclass(cls, sub_cls: Type[Stateful]) -> Type['StackedItem']:
		if issubclass(sub_cls, StackedItem):
			return sub_cls
		if (stacked_sub_cls := StackedItem.__type_cache__.get(sub_cls, None)) is None:
			cls.__type_cache__[sub_cls] = stacked_sub_cls = type(f'Stacked{sub_cls.__name__}', (sub_cls, StackedItem), {
				'type': StackedItem.type,
			})
		return stacked_sub_cls

	@property
	def combined_shared(self) -> Dict[str, Any]:
		return self.shared.new_child(self, child_map=self.parent.combined_preset).to_dict()

	@classmethod
	def representer(cls, dumper, data):
		exclude_data = data.combined_shared
		state = data.encodedState(exclude_value_map=exclude_data)
		match state:

			case {'key': key} if len(state) == 1:
				return dumper.represent_str(str(key))

			case {'key': key, **rest} if len(rest) >= 1:
				return dumper.represent_dict({key: rest})

			case {'type': _type} if len(state) == 1:
				return dumper.represent_str(_type)

			case {'type': _type, **rest} if len(rest) >= 1:
				return dumper.represent_dict({_type: rest})

			case _:
				pass

		result = super().representer(dumper, state)
		return result

	def _geometryManagerPositionChange(self, value: QPoint | QPointF) -> Tuple[bool, QPoint | QPointF]:
		originalValue = QPointF(value)
		pos = self.pos()
		value = self.sceneBoundingRect().translated(*(value - pos).toTuple()).center()
		if self.parent.direction is Direction.Horizontal:
			originalValue.setY(pos.y())
			value = value.x()
		else:
			originalValue.setX(pos.x())
			value = value.y()
		index = self.geometry.index

		newIndex, newPos = min(
      ((i, v) for i, v in enumerate(self.parent.itemPositions)), key=lambda i: abs(i[1] - value), default=(index,)
		)

		if newIndex == index or abs(newPos - value) > max(self.width() * .30, 20):
			return True, self.pos()

		self.setFlag(self.GraphicsItemFlag.ItemSendsGeometryChanges, False)
		self.parent.swap(index, newIndex)
		self.setFlag(self.GraphicsItemFlag.ItemSendsGeometryChanges, True)
		return True, self.geometry.absolutePosition().asQPointF()


class Spacer(NonInteractivePanel, StackedItem, tag='spacer'):
	__exclude__ = {
		'movable',
		'frozen',
		'locked'
	}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.setAcceptedMouseButtons(Qt.NoButton)
		self.setAcceptHoverEvents(False)
		self.setFlag(QGraphicsItem.ItemIsMovable, False)
		self.setFlag(QGraphicsItem.ItemIsSelectable, False)
		self.setFlag(QGraphicsItem.ItemIsFocusable, False)
		self.setFlag(self.GraphicsItemFlag.ItemHasNoContents)

	@property
	def key(self) -> str:
		return 'spacer'


@DebugPaint
class Stack(Panel, tag='stack'):
	spacing: Size.Height | Size.Width | float | int | Length
	size: Size.Height | Size.Width | float | int | Length
	direction: Direction
	orthogonalDirection: Direction
	geometries: Dict[int, Geometry]
	items: List[Panel]

	Item: Type[StackedItem] = StackedItem
	Spacer: Type[Spacer] = Spacer

	_direction: Direction = Direction.Vertical
	_defaultType: Type[Panel] = None
	_size: Size.Height | Size.Width | Length = None
	_minSize: Size.Height | Size.Width | Length = None
	_maxSize: Size.Height | Size.Width | Length = None
	_dividerProps: DividerProperties

	primaryDimension: DimensionSizePosition = DimensionSizePosition(Size.Height, Position.Y)
	orthogonalDimension: DimensionSizePosition = DimensionSizePosition(Size.Width, Position.X)

	presets: DeepChainMap[Direction, Dict[str, Dict]] = DeepChainMap(origin='stack', origin_map={
		Direction.Vertical:   {},
		Direction.Horizontal: {}
	})

	__defaults__ = {
		'defaultType': _defaultType,
	}

	__child_exclude__ = {
		'movable',
		'geometry'
	}

	def __init_subclass__(cls, **kwargs):
		super().__init_subclass__(**kwargs)

		# If the subclass has a 'presets' attribute, add the presets to the class's presets
		# with a new child of the super_presets.
		super_preset = next((i_presets for i in cls.__mro__[1:] if (i_presets := i.__dict__.get('presets', None)) is not None), None)

		if super_preset is None:
			super_preset = {
				Direction.Vertical:   {},
				Direction.Horizontal: {}
			}

		if not isinstance(super_preset, DeepChainMap):
			super_preset = DeepChainMap(super_preset)
		if (own_preset := cls.presets) is not super_preset:
			if isinstance(own_preset, DeepChainMap):
				own_preset = own_preset.to_dict()
			cls.presets = super_preset.new_child(origin=cls, child_map=own_preset)

	def __init__(self, *args, **kwargs):
		self._dividers: List[Tuple[Position, ...]] = []
		self.geometries = defaultdict(partial(Geometry, self))
		Panel.__init__(self, *args, **kwargs)

		self.scene().view.loadingFinished.connect(self.setGeometries)

	@cached_property
	def nonStackParent(self) -> Panel:
		up = self.parent
		while isinstance(up, Stack):
			up = up.parent
		return up

	def refresh(self):
		self.setGeometries()
		for group in (self._attrGroups or {}).values():
			group.adjustSizes(reason='refresh')

	@StateProperty(key='defaultType', sortOrder=0, default=Panel)
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
		if (subTag := getattr(value, 'subtag', None)) is not None and isinstance(subTag, str) and not value.__tag__.endswith(subTag):
			return f'{value.__tag__}.{subTag}'
		return getattr(value, '__tag__', 'group')

	@defaultType.decode
	def defaultType(value: str) -> Type[Panel] | None:
		return Stateful.findTag(value)

	@defaultType.condition
	def defaultType(self, value: Type[Panel]) -> bool:
		if not isinstance(value, type):
			return value is not None and value is not ...
		return getattr(value, '__tag__', ...) is not ...

	@property
	def itemPositions(self) -> List[float]:
		if self.direction is Direction.Vertical:
			getter = lambda g: g.surface.sceneBoundingRect().center().y()
		else:
			getter = lambda g: g.surface.sceneBoundingRect().center().x()
		return [getter(i) for i in sorted(self.geometries.values(), key=lambda i: i.index)]

	def setGeometries(self, manualSize: Size.Height | Size.Width | float | int | Length = None, exclude=None):
		if not self.geometries or self.state_is_loading:
			return  # no items

		self._dividers.clear()

		dimension = self.direction.dimension

		PrimarySize, PrimaryPosition = self.primaryDimension
		OrthogonalSize, OrthogonalPosition = self.orthogonalDimension

		geometries = list(self.geometries.values())

		fixedSizes = [f for i in geometries if (f := getattr(i.surface, 'fixedSize', None)) is not None]

		def getSize(item: Panel) -> PrimarySize:
			if self.direction == Direction.Vertical:
				return item.height(), item.width()
			return item.width(), item.height()

		absoluteSpacing = self.spacing_px

		padding = self.padding

		spacing = self.spacing
		if isinstance(spacing, Length):
			spacing = PrimarySize(size_px(spacing, self.geometry), absolute=True)

		own_size_px, own_ortho_size_px = getSize(self)
		totalFixeSizes = PrimarySize(sum([i.toRelativeF(own_size_px) for i in fixedSizes]), absolute=False)

		if manualSize is not None:
			cellSize = manualSize
		else:
			cellSize = self.cellSize

		if cellSize is not None and cellSize < 0:
			self.setGeometries(manualSize=PrimarySize(1, absolute=False))
			cellSize = getSize(max((i.boundingRect() for i in self._attrGroups['text'].items), key=lambda i: getSize(i)))
		length = len(self.geometries)
		if cellSize is None:
			breaks = length - 1
			spacingTotal = breaks * absoluteSpacing
			remainingSpace = padding.primarySpan - (float(spacingTotal) / own_size_px) - float(totalFixeSizes)
			cellSize = PrimarySize(remainingSpace / ((length - len(fixedSizes)) or remainingSpace), absolute=False)

		if self.minCellSize is not None:
			cellSize = max(cellSize, self.minCellSize)
		if self.maxCellSize is not None:
			cellSize = min(cellSize, self.meaxCellSize)

		if isinstance(cellSize, (Length, int, float)):
			size = size_px(cellSize, self.geometry, dimension)
			cellSize = PrimarySize(size, absolute=True)

		orthoOffset = OrthogonalPosition(0, absolute=False)  # This should always be 0 unless diagonal
		orthoPosition = OrthogonalPosition(0 + padding.orthogonalLeading, absolute=False)
		orthoLeading = OrthogonalPosition(0, absolute=False)
		orthoTrailing = OrthogonalPosition(1, absolute=False)

		if dividers := self.dividers:
			dividerSize = dividers.size
			if isinstance(dividerSize, Length) or dividerSize.absolute:
				dividerSize = size_float(dividerSize, self.geometry, dimension)

			dividerOffset = (1 - dividerSize) / 2

			dividerLeading = orthoLeading + dividerOffset
			dividerTrailing = orthoTrailing - dividerOffset
		else:
			dividerLeading = orthoLeading
			dividerTrailing = orthoTrailing

		orthoSize = OrthogonalSize(padding.orthogonalSpan, absolute=False)

		if cellSize.relative and spacing.absolute:
			spacing = spacing.toRelative(own_size_px)

		size = Size(cellSize, orthoSize, unsorted=True)

		defaultOffset = Position(PrimaryPosition(cellSize + spacing, absolute=cellSize.absolute), orthoOffset, unsorted=True)
		position = Position(PrimarySize(0 + padding.primaryLeading, absolute=cellSize.absolute), orthoPosition, unsorted=True)

		if size.width.absolute and position.x.relative:
			position.x = position.x.toAbsolute(own_size_px)
		elif size.width.relative and position.x.absolute:
			position.x = position.x.toRelative(own_size_px)

		if size.height.absolute and position.y.relative:
			position.y = position.y.toAbsolute(own_ortho_size_px)
		elif size.height.relative and position.y.absolute:
			position.y = position.y.toRelative(own_ortho_size_px)

		with self.action_pool:
			for index, geometry in enumerate(geometries):
				geometry.index = index
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

				if dividers and index < length - 1:
					if self._dividers:
						try:
							firstPoint, secondPoint = [i + offset for i in self._dividers[-1]]
						except RecursionError as e:
							firstPoint, secondPoint = self._dividers[-1]
					else:
						itemSize, _ = getSize(geometry)
						itemSize += padding.primaryLeading
						firstPoint = Position(PrimaryPosition(itemSize + (spacing / 2)), dividerLeading, unsorted=True)
						secondPoint = Position(PrimaryPosition(itemSize + (spacing / 2)), dividerTrailing, unsorted=True)
					self._dividers.append((firstPoint, secondPoint))

	def swap(self, first: int, second: int) -> None:
		"""Swap the positions of two items in the stack."""
		(
	    self.geometries[first],
	    self.geometries[first].index,
	    self.geometries[second],
	    self.geometries[second].index,
		) = (
	    self.geometries[second],
	    self.geometries[second].index,
	    self.geometries[first],
	    self.geometries[first].index,
		)
		self.geometries = {i: self.geometries[i] for i in sorted(self.geometries)}
		self.setGeometries()

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

	@property
	def _local_overrides(self) -> dict:
		return {}

	@StateProperty(after=setGeometries, sort=False, dependancies={..., 'size', 'spacing', 'padding', 'dividers', 'direction'})
	def items(self) -> List[StackedItem]:
		items = list(geometry.surface for geometry in self.geometries.values())
		return items

	@items.setter
	def items(self, value: List[CategoryItem]):
		existing = [item for item in self.childPanels]
		self.geometries.clear()
		preset = self.combined_preset
		defaultType = self.defaultType

		if not issubclass(defaultType, StackedItem):
			defaultType = type(self).Item.get_subclass(defaultType)

		if isinstance(preset, DeepChainMap):
			preset = preset.to_dict()

		self.itemSetter(defaultType, existing, preset, value)

		for item in existing:
			self.scene().removeItem(item)

	@items.encode
	def items(self, value: List[Panel]) -> List[CategoryItem]:
		return value

	def itemSetter(self, default_type, existing, preset, value):
		for index, item in enumerate(value):
			item_type = default_type

			# If the item is a string, assume that it's a key to be passed to the default type
			# along with the shared state and the preset for the direction.
			if isinstance(item, str):
				if item == 'spacer':
					item = Spacer(self)
				else:
					key = CategoryItem(item)
					state = DeepChainMap({'key': key}, preset, self.shared.to_dict()).to_dict()
					item = self.extractExisting(state, existing) or default_type(self, **state)

			elif isinstance(item, Mapping):
				# Determine the type of the item
				match item:
					case {'spacer': state} | {'type': 'spacer', **state}:
						item_type = Spacer

					# Check to see if the type is specified in the config
					case {'type': str(itemTypeStr), **state} if (state_specified_type := Stateful.findTag(itemTypeStr)) is not None:
						item_type = state_specified_type

					# Check to if the item in the format of {CategoryItem(key): state} and is contained in all_valid_keys
					case _:

						state = {}

						# Items can be in the format of:
						# Key first: {CategoryItem(key): state} or {CategoryItem(key): None, **state}
						# Type first: {type: state} or {type: None, **state}
						#
						# Because of this, the structure of the item must be determined before the state can be extracted.

						first_key, first_value = next(iter(item.items()))

						if first_key in {'spacer', ''}:
							item_type = Spacer

						# When the first key is the type
						elif (tag := Stateful.findTag(first_key)) is not None:
							item_type = tag

							# If the first value is None, then the first key is the type and the state is the rest of the item.
							if first_value is None and len(item) > 1:
								state['type'] = first_key
								item.pop(first_key)
								state.update(item)
							elif first_value is not None and len(item) == 1:
								state['type'] = first_key
								state.update(first_value)

						elif CategoryItem(first_key) in LevityDashboard.dispatcher.all_valid_keys:
							item_type = default_type

							# If the first value is None, then the first key is the key and the state is the rest of the item.
							if first_value is None and len(item) > 1:
								state['key'] = first_key
								item.pop(first_key)
								state.update(item)
							elif first_value is not None and len(item) == 1:
								state['key'] = first_key
								state.update(first_value)

						elif first_key in getattr(default_type, 'statefulKeys', {}):
							item_type = default_type
							state = item

						item_type = Stateful.findTag(item.get('type', default_type.__tag__)) or default_type

				if item_type is not Spacer:
					# Update the state with the shared state and the preset for the direction.
					# User-specified shared values will override the preset values.
					shared_state = self.shared.new_child(self, child_map=preset)

					# Swap the order of the maps so that the shared state is the first map.
					shared_state.maps[0], shared_state.maps[1] = shared_state.maps[1], shared_state.maps[0]

					state = shared_state.new_child(origin=self, child_map=state).to_dict()

				if (existingItem := self.extractExisting(state, existing)) is not None and isinstance(existingItem, item_type):
					existingItem.state = state
					item = existingItem
				else:
					# Ensure that the item type is a subclass of StackedItem
					if not issubclass(item_type, Spacer) and not issubclass(item_type, type(self).Item):
						item_type = type(self).Item.get_subclass(item_type)
					item = item_type(self, **state)
			else:
				log.warn(f'Invalid item state type {type(item)} for {item}.  Skipping...')
			if (geometry := getattr(item, 'geometry', None)) is not None:
				self.geometries[index] = geometry
				item.index = index
			else:
				log.debug(f'{item} has no geometry')

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

	@StateProperty(key='preset', sortOrder=0, dependancies={'direction'}, allowNone=True, default=None, after=setGeometries)
	def preset(self) -> Dict[str, Dict] | str | None:
		"""Values to be applied to each item of the stack.
		Can be a string or a dict.
		If a string, it must be a key in the `presets` dict."""
		return getattr(self, '_preset', None)

	@preset.setter
	def preset(self, value: Dict[str, Dict]):
		self._preset = value

	@property
	def combined_preset(self) -> Dict[str, Dict]:
		local_override = self._local_overrides
		default_preset = self.presets[self.direction]
		conf_preset = {}
		match self.preset:
			case None:
				conf_preset = {}
			case str(value) if value in self.presets:
				conf_preset = dict(self.presets[value].items())
			case dict(value):
				conf_preset = value
		return DeepChainMap(conf_preset, local_override, default_preset).to_dict()

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
		return size_px(self.cellSize, self.geometry, self.direction.dimension)

	@StateProperty(key='spacing', default=Size.Height(5, absolute=True), allowNone=False, after=setGeometries,
		dependancies={'geometry'}, sortOrder=3)
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

	padding = Panel.padding
	padding.after(setGeometries)

	@StateProperty(
		key='direction',
		default=Direction.Vertical,
		after=setGeometries,
		dependancies={'geometry'},
		allowNone=False,
		sortOrder=1,
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
		if change is self.GraphicsItemChange.ItemTransformHasChanged and any(i.surface.hasFixedSize for i in self.geometries.values()):
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

	def _debug_paint(self, painter: QPainter, *args, **kwargs):
		self._normal_paint(painter, *args, **kwargs)
		pen = painter.pen()
		pen.setColor(self.debugColor)
		painter.setPen(self.debugPen)
		for item in self.childPanels:
			if hasattr(item, '_debug_paint'):
				continue
			rect = item.mapRectToParent(item.rect())
			debug_pen = item.debugPen
			debug_pen.setDashPattern([3, 2])
			painter.setPen(debug_pen)
			painter.drawRect(rect)


class ValueStack(Stack, tag='value-stack'):

	"""
	value stacks are defined as such

	TODO: Extract subclass for a value stack that creates a list of Realtime.Text items from this class to
		allow for more value stack presets to be defined.

	type: value-stack
	items:
	- environment.light.irradiance.irradiance:
			title:
				text: Direct
	- environment.light.irradiance.diffuse:
			title:
				text: Diffuse
	- environment.light.irradiance.direct:
			title:
				text: Direct
	- environment.clouds.cover.high
	- environment.clouds.cover.low
	- spacer:
			size: 1.5 mm
	- environment.pressure.pressure
	- environment.pressure.surface:
			title:
				text: Sea Level

	items are to be in the format
	"""

	presets = {
		Direction.Vertical: {
			'title': {
				'matchingGroup': {
					'group': 'value-stack.title',
					'matchAll': True
				},
				'position': DisplayPosition.Left,
				'margins': {
					'left': 0,
					'right': 0.05,
					'top': 0.05,
					'bottom': 0.05,
				}

			},
			'display': {
				'valueLabel':
					{
						'alignment': Alignment(AlignmentFlag.CenterRight),
						'margins': {
							'top': 0.05,
							'bottom': 0.05,
							'left': 0.05,
							'right': 0,
						},
						'matchingGroup': {
							'group': 'value-stack.text',
							'matchAll': True,
						},
					}
			}
		},
		Direction.Horizontal: {
			'title': {
				'alignment': Alignment(AlignmentFlag.Center),
				'matchingGroup': {
					'group': 'value-stack.title',
					'matchAll': True
				},
				'position': DisplayPosition.Top,
			},
			'display': {
				'valueLabel':
					{
						'alignment': Alignment(AlignmentFlag.Center),
						'matchingGroup': {
							'group': 'value-stack.text',
							'matchAll': True,
						},
					}
			}
		}
	}

	_defaultType = Realtime.Text

	__defaults__ = {
		'defaultType': Realtime.Text,
	}

	def setAlignments(self):
		for item in self.childPanels:
			if (title := getattr(item, 'title', None)) is not None:
				title.setAlignment(self.labelAlignment)
			if (display := getattr(item, 'display', None)) is not None:
				if (valueLabel := getattr(display, 'valueTextBox', None)) is not None:
					valueLabel.setAlignment(self.valueAlignment)

	def extractExisting(
		self, state_: dict,
		existing_: List[Panel],
		itemType: Type[Panel] = Realtime
	) -> Realtime | None:
		for i, item in enumerate(existing_):
			if item.key == state_['key']:
				return existing_.pop(i)
		return None

	# @StateProperty()
	# def items(self) -> List[Dict[str, Dict | None] | CategoryItem]:
	# 	"""
	# 	Items must return a list rather than a dictionary since there can be multiple items with the same key or 'spacer' can be defined multiple times
	# 	Returns
	# 	-------
	#
	# 	"""
	# 	items = []
	# 	item_preset = self.combined_preset
	# 	for item in Stack.items.fget(self):
	# 		# use item.get_item_state and add a shared_state to get_item_state that is a child of the shared state
	# 		item_state = item.getItemState()
	#
	# 	return items

	@StateProperty(key='labelAlignment', after=setAlignments, dependancies={'geometry', 'direction'})
	def labelAlignment(self) -> Alignment | None:
		"""
		The alignment of the label.
		"""
		return self._labelAlignment

	@labelAlignment.item_default
	def labelAlignment(self) -> Alignment:
		match self.direction:
			case Direction.Vertical:
				return Alignment(vertical=AlignmentFlag.Center, horizontal=AlignmentFlag.Left)
			case Direction.Horizontal:
				return Alignment(vertical=AlignmentFlag.Center, horizontal=AlignmentFlag.Center)

	@labelAlignment.setter
	def labelAlignment(self, value: Alignment | None):
		self._labelAlignment = value

	@labelAlignment.decode
	def labelAlignment(self, value: str) -> Alignment:
		value = AlignmentFlag[value]
		return Alignment(vertical=AlignmentFlag.Center, horizontal=value)

	@labelAlignment.encode
	def labelAlignment(self, value: Alignment) -> str:
		if value is None:
			return ValueStack.labelAlignment.default(type(self)).name
		return value.horizontal.name

	@StateProperty(key='valueAlignment', after=setAlignments, dependancies={'geometry', 'direction'})
	def valueAlignment(self) -> Alignment | None:
		"""
		The alignment of the value.
		"""
		return self._valueAlignment

	@valueAlignment.item_default
	def valueAlignment(self) -> Alignment:
		match self.direction:
			case Direction.Vertical:
				return Alignment(vertical=AlignmentFlag.Center, horizontal=AlignmentFlag.Right)
			case Direction.Horizontal:
				return Alignment(vertical=AlignmentFlag.Center, horizontal=AlignmentFlag.Center)

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
			return ValueStack.valueAlignment.default(type(self)).name
		return value.horizontal.name

	@StateProperty(key='label-size', after=Stack.setGeometries, dependancies={'geometry', 'direction'})
	def labelSize(self) -> Size.Height | Size.Width | Length | Percentage:
		"""
		The size of the label.
		"""
		return self._labelSize

	@labelSize.setter
	def labelSize(self, value: Size.Height | Size.Width | Length | Percentage):
		self._labelSize = value

	@labelSize.decode
	def labelSize(self, value: str | int | float) -> Size.Height | Size.Width | Length | Percentage:

		return parseSize(value, None, dimension=self.direction.dimension)

	@labelSize.item_default
	def labelSize(self) -> Size.Height | Size.Width | Length | Percentage:
		match self.direction:
			case Direction.Vertical:
				return Percentage(0.5)
			case Direction.Horizontal:
				return Percentage(0.2)

	@property
	def label_size_ratio(self) -> float:
		match self.direction:
			case Direction.Vertical:
				ortho_size = self.rect().height()
				label_size_px = size_px(self.labelSize, ortho_size, Direction.Horizontal)
			case Direction.Horizontal:
				ortho_size = self.rect().width()
				label_size_px = size_px(self.labelSize, ortho_size, Direction.Vertical)
			case _:
				return 1.0
		return sorted((0, label_size_px / ortho_size, 1))[1]

	@property
	def _local_overrides(self) -> dict:
		return {
			'display': {
				'valueLabel': {
					'alignment': self.valueAlignment,
				}
			},
			'title': {
				'alignment': self.labelAlignment,
				'size': self.label_size_ratio
			}

		}

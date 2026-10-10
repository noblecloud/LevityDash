import re
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property, partial
from typing import Any, Dict, List, Optional, Tuple, Type, Mapping

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from LevityDash import LevityDashboard
from LevityDash.lib.plugins.categories import CategoryItem, SomeValidKey
from LevityDash.lib.stateful import Stateful, StateProperty
from LevityDash.lib.ui import Color, UILogger as log
from LevityDash.lib.ui.frontends.PySide.Modules import NonInteractivePanel, Panel, Realtime
from LevityDash.lib.ui.frontends.PySide.utils import DebugPaint, DisplayType
from LevityDash.lib.ui.Geometry import (
	Alignment, AlignmentFlag, Dimension, DimensionType, Direction, DisplayPosition, Geometry, parseHeight, parseSize, parseWidth,
	Position, Size, size_float, size_px
)
from LevityDash.lib.layout import flex as cssflex, grid as cssgrid, parse as cssparse
from LevityDash.lib.layout.types import Direction as CssDirection, Edge as CssEdge, Gap as CssGap, ItemAlign as CssItemAlign, Rect as CssRect
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
	_color: Color = Color.text
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
		default=Color.text,
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
	_color: Color = Color.text
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
		default=Color.text,
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


def _checkedKeys(value: Mapping | None, allowed: set[str], what: str) -> dict | None:
	"""A `flex:` or `grid:` mapping with its keys checked, so a typo is an error and not silence."""
	if value is None:
		return None
	if not isinstance(value, Mapping):
		raise ValueError(f'{what}: expected a mapping, got {value!r}')
	value = {str(k).casefold().replace('_', '-'): v for k, v in value.items()}
	if unknown := sorted(set(value) - allowed):
		raise ValueError(f'{what}: unknown key {unknown}; allowed: {sorted(allowed)}')
	return value


# One `flex:` mapping serves both roles, because a stack can be a flex item and a flex container
# at once. The two sets do not overlap: `align-self` is the item's, `align-items` the container's.
_FLEX_ITEM_KEYS = {'grow', 'shrink', 'basis', 'min', 'max', 'cross', 'align-self', 'order'}
_FLEX_STACK_KEYS = {'justify', 'align-items', 'wrap'}
_GRID_ITEM_KEYS = {'column', 'row', 'column-span', 'row-span', 'justify-self', 'align-self'}
_GRID_KEYS = {'columns', 'rows', 'auto-columns', 'auto-rows', 'auto-flow', 'dense', 'gap', 'justify-content', 'align-content', 'justify-items', 'align-items'}


class StackedItem(Stateful, tag=...):
	__size = None
	__sizeRatio = None
	__flex = None
	__grid = None
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

	@StateProperty(key='flex', default=None, sortOrder=2, allowNone=True)
	def flexProps(self) -> dict | None:
		"""CSS flex item options: `grow`, `shrink`, `basis`, `min`, `max`, `cross`, `align-self`, `order`.

		Any of them turns on the flex engine for the stack that holds this item.
		"""
		return self.__flex

	@flexProps.setter
	def flexProps(self, value: dict | None):
		self.__flex = _checkedKeys(value, _FLEX_ITEM_KEYS, 'flex')

	@StateProperty(key='grid', default=None, sortOrder=2, allowNone=True)
	def gridProps(self) -> dict | None:
		"""Where this item sits in a `grid` stack: `column`, `row`, `column-span`, `row-span`,
		`justify-self`, `align-self`. Lines count from 1."""
		return self.__grid

	@gridProps.setter
	def gridProps(self, value: dict | None):
		self.__grid = _checkedKeys(value, _GRID_ITEM_KEYS, 'grid')

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
			group.apply()

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

		if self.usesCssLayout:
			try:
				return self.setCssGeometries()
			except Exception as error:
				log.error(f'{self.name or type(self).__name__}: CSS layout failed ({error!r}); using the plain stack layout', exc_info=True)
				if isinstance(self, GridStack):
					return

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
			cellSize = PrimarySize(remainingSpace / max(length - len(fixedSizes), 1), absolute=False)

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

	# Section: CSS layout engine (lib/layout). Off unless a `flex:` key is present.
	@StateProperty(key='flex', default=None, after=setGeometries, allowNone=True, sortOrder=3)
	def flexProps(self) -> dict | None:
		"""Turns this stack into a CSS flex container: `justify`, `align-items`, `wrap`.
		It may also carry the item options (`grow`, `shrink`, ...) for when this stack is an item of another.

		A stack with no `flex:` on itself or on any item keeps the original sizing, so existing
		boards do not move. See docs/config/dashboard/layout.md.
		"""
		return getattr(self, '_flexProps', None)

	@flexProps.setter
	def flexProps(self, value: dict | None):
		self._flexProps = _checkedKeys(value, _FLEX_STACK_KEYS | _FLEX_ITEM_KEYS, 'flex')

	@property
	def usesCssLayout(self) -> bool:
		return any(key in (self.flexProps or ()) for key in _FLEX_STACK_KEYS) or any(
			getattr(geometry.surface, 'flexProps', None) is not None for geometry in self.geometries.values()
		)

	def cssPx(self, value, vertical: bool) -> float:
		"""A `.levity` length (`40%`, `12px`, `3mm`, `0.5`) as pixels along one axis of this stack."""
		dimension = DimensionType.height if vertical else DimensionType.width
		parsed = parseSize(value, None, dimension=dimension)
		if parsed is None:
			raise ValueError(f'{value!r} is not a size')
		return float(size_px(parsed, self.geometry, dimension))

	def cssGapPx(self) -> float:
		return float(self.spacing_px)

	def cssBox(self) -> tuple[float, float, float, float, float, float]:
		"""Own width and height, and the padding left, top, right, bottom, all in pixels."""
		width, height = float(self.geometry.absoluteWidth), float(self.geometry.absoluteHeight)
		padding = self.padding
		return width, height, padding.relativeLeft * width, padding.relativeTop * height, padding.relativeRight * width, padding.relativeBottom * height

	def cssFlexItem(self, item: Panel, vertical: bool, inner_cross: float) -> cssflex.FlexItem:
		"""One stack item as a `FlexItem`. An item with no size and no basis shares the rest, as a plain stack does."""
		props = getattr(item, 'flexProps', None) or {}
		size = getattr(item, '_fixedSize', None)
		px = lambda v, along_main=True: self.cssPx(v, vertical == along_main)
		content_main = 0.0
		basis_auto = str(props.get('basis', '')).casefold() in ('auto', 'content')
		if basis_auto:
			basis = None
			if (aspect := self.cssAspect(item)) is not None:
				content_main = inner_cross / aspect if vertical else inner_cross * aspect
		elif props.get('basis') is not None:
			basis = px(props['basis'])
		elif size is not None:
			basis = float(size_px(size, self.geometry, DimensionType.height if vertical else DimensionType.width))
		else:
			basis = None
		sized = basis is not None or basis_auto
		cross = props.get('cross')
		align = props.get('align-self')
		return cssflex.FlexItem(
			grow=float(props.get('grow', 0.0 if sized else 1.0)),
			shrink=float(props.get('shrink', 1.0)),
			basis=None if basis_auto else (0.0 if basis is None else basis),
			content_main=content_main,
			min_main=px(props['min']) if props.get('min') is not None else 0.0,
			max_main=px(props['max']) if props.get('max') is not None else cssflex.INF,
			cross=None if cross is None else px(cross, False),
			content_cross=inner_cross,
			align_self=CssItemAlign.auto if align is None else cssparse.parse_item_align(align).value,
			order=int(props.get('order', 0)),
		)

	def setCssGeometries(self):
		vertical = self.direction is Direction.Vertical
		width, height, left, top, right, bottom = self.cssBox()
		inner_w, inner_h = width - left - right, height - top - bottom
		if inner_w <= 0 or inner_h <= 0:
			return
		props = self.flexProps or {}
		gap = self.cssGapPx()
		container = cssflex.FlexContainer(
			direction=CssDirection.column if vertical else CssDirection.row,
			wrap=cssparse.parse_wrap(props.get('wrap', 'nowrap')),
			gap=CssGap(gap, gap),
			main=inner_h if vertical else inner_w,
			cross=inner_w if vertical else inner_h,
		)
		if (justify := props.get('justify')) is not None:
			container.justify_content = cssparse.parse_content_align(justify)
		if (align := props.get('align-items')) is not None:
			container.align_items = cssparse.parse_item_align(align)
		surfaces = [geometry.surface for geometry in self.geometries.values()]
		items = [self.cssFlexItem(surface, vertical, container.cross) for surface in surfaces]
		rects = cssflex.layout_flex(items, container)
		self.applyCssRects(rects, left, top, width, height)
		self.cssDividers(rects, left, top, width, height, columns=not vertical, rows=vertical)

	@staticmethod
	def cssAspect(item: Panel) -> float | None:
		"""Width over height of the widest text this item can show: the format hint at the item's own font.

		Never the live value, so the size does not move as the number changes. None when the item
		has no value text to measure (a container, a gauge, a value with no digits).
		"""
		try:
			textBox = item.display.valueTextBox.textBox
		except AttributeError:
			textBox = getattr(getattr(item, 'textBox', None), 'textBox', None) or getattr(item, 'textBox', None)
		if textBox is None:
			return None
		try:
			hint = textBox._formatHint or textBox.text
			metrics = QFontMetricsF(QFont(textBox._font))
			if not hint or metrics.height() <= 0:
				return None
			return metrics.horizontalAdvance(hint) / metrics.height()
		except Exception:  # noqa: BLE001 - sizing must never abort a layout
			return None

	def cssDividers(self, rects: list[CssRect], left: float, top: float, width: float, height: float, columns: bool = True, rows: bool = False):
		"""Dividers where two items meet: a line in the middle of the gap, as a plain stack draws them.

		`columns` draws between items side by side, `rows` between items one above the other. A line spans
		the stack's inner extent, shortened by the dividers' `size` as in a plain stack.
		"""
		dividers = self.dividers
		if not dividers or not dividers.enabled or len(rects) < 2:
			return
		size = dividers.size
		if isinstance(size, Length) or size.absolute:
			size = size_float(size, self.geometry, DimensionType.height)
		trim = (1 - float(size)) / 2
		inner_w, inner_h = width - left - self.cssBox()[4], height - top - self.cssBox()[5]
		eps = 0.5

		def edges(start, end):
			spans = sorted({(round(start(r), 1), round(end(r), 1)) for r in rects})
			found, reach = [], None
			for a, b in spans:
				if reach is not None and a >= reach - eps and a - reach < inner_w + inner_h:
					found.append((reach + a) / 2)
				reach = b if reach is None else max(reach, b)
			return sorted(set(round(x, 1) for x in found))

		if columns:
			for x in edges(lambda r: r.x, lambda r: r.x + r.width):
				ax, bx = (left + x) / width, (left + x) / width
				ya, yb = (top + inner_h * trim) / height, (top + inner_h * (1 - trim)) / height
				self._dividers.append((Position(Position.X(ax, absolute=False), Position.Y(ya, absolute=False), unsorted=True),
					Position(Position.X(bx, absolute=False), Position.Y(yb, absolute=False), unsorted=True)))
		if rows:
			for y in edges(lambda r: r.y, lambda r: r.y + r.height):
				ay = (top + y) / height
				xa, xb = (left + inner_w * trim) / width, (left + inner_w * (1 - trim)) / width
				self._dividers.append((Position(Position.X(xa, absolute=False), Position.Y(ay, absolute=False), unsorted=True),
					Position(Position.X(xb, absolute=False), Position.Y(ay, absolute=False), unsorted=True)))
		self.update()

	def applyCssRects(self, rects: list[CssRect], left: float, top: float, width: float, height: float):
		"""Give every item its rect (pixels inside the padding) as shares of this stack."""
		with self.action_pool:
			for index, (geometry, rect) in enumerate(zip(list(self.geometries.values()), rects)):
				geometry.index = index
				geometry.position = Position(
					Position.X((left + rect.x) / width, absolute=False),
					Position.Y((top + rect.y) / height, absolute=False),
					unsorted=True,
				)
				geometry.size = Size(
					Size.Width(rect.width / width, absolute=False),
					Size.Height(rect.height / height, absolute=False),
					unsorted=True,
				)
				geometry.updateSurface()


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

	@StateProperty(after=setGeometries, sort=False, dependencies={..., 'size', 'spacing', 'padding', 'dividers', 'direction'})
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

						# Identity is runtime scoping, not schema: `all_valid_keys`
						# holds base keys only, so a per-device key like
						# `indoor.humidity.humidity#bedroom` failed this test and
						# the row was silently dropped - it rendered as a bare
						# dash with a ••• value. Strip it, as every other schema
						# lookup does.
						elif CategoryItem(first_key).withoutIdentity in LevityDashboard.dispatcher.all_valid_keys:
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

				state = self._sizeFromGeometry(state)

				if (existingItem := self.extractExisting(state, existing)) is not None and isinstance(existingItem, item_type):
					existingItem.state = state
					item = existingItem
				else:
					# Ensure that the item type is a subclass of StackedItem
					if not issubclass(item_type, Spacer) and not issubclass(item_type, type(self).Item):
						item_type = type(self).Item.get_subclass(item_type)
					item = item_type(self, **state)
			else:
				log.warning(f'Invalid item state type {type(item)} for {item}.  Skipping...')
			if (geometry := getattr(item, 'geometry', None)) is not None:
				self.geometries[index] = geometry
				item.index = index
			else:
				log.debug(f'{item} has no geometry')

	def _sizeFromGeometry(self, state: dict) -> dict:
		"""Turn a child's `geometry:` into a `size:`, the one thing a stack honours.

		The stack lays every child out itself, so a child's own `geometry` was
		decoded and then overwritten by `setGeometries`: `geometry: {height: 30%}`
		in a vertical stack gave the child an equal share instead, with nothing in
		the log. Along the stack's direction that value now acts as `size:` (an
		explicit `size:` wins). The rest of it (`x`, `y`, the other dimension) has
		no meaning in a stack and is dropped with a warning.
		"""
		geometry = state.get('geometry')
		if geometry is None:
			return state
		state = {k: v for k, v in state.items() if k != 'geometry'}
		if isinstance(geometry, (tuple, list)) and len(geometry) == 4:
			geometry = dict(zip(('x', 'y', 'width', 'height'), geometry))
		if not isinstance(geometry, Mapping):
			return state
		primary = 'height' if self.direction is Direction.Vertical else 'width'
		if (size := geometry.get(primary)) is not None and state.get('size') is None:
			state['size'] = size
		ignored = [k for k in geometry if k not in (primary, 'fillParent')]
		if ignored:
			log.warning(
				f'{state.get("key") or state.get("type") or "item"} in {self.direction.name} stack {self.name!r}: '
				f'geometry {ignored} ignored; a stack sizes its children along {primary} with `size:`'
			)
		return state

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

	@StateProperty(key='preset', sortOrder=0, dependencies={'direction'}, allowNone=True, default=None, after=setGeometries)
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

	@StateProperty(key='item-size', default=None, after=setGeometries, dependencies={'geometry'}, decoder=_parseCellSize)
	def cellSize(self) -> Size.Height | Size.Width | Length | None:
		"""
		The size for each item in the list.
		"""
		return self._size

	@cellSize.setter
	def cellSize(self, value: Size.Height | Size.Width | Length | None):
		self._size = value

	@StateProperty(key='item-size-min', default=None, after=setGeometries, dependencies={'geometry'}, decoder=_parseCellSize)
	def minCellSize(self) -> Size.Height | Size.Width | Length | None:
		"""
		The minimum size for each item in the list.
		"""
		return self._minSize

	@minCellSize.setter
	def minCellSize(self, value: Size.Height | Size.Width | Length | None):
		self._minSize = value

	@StateProperty(key='item-size-max', default=None, after=setGeometries, dependencies={'geometry'}, decoder=_parseCellSize)
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
		dependencies={'geometry'}, sortOrder=3)
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
		dependencies={'geometry'},
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

	@StateProperty(key='labelAlignment', after=setAlignments, dependencies={'geometry', 'direction'})
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

	@StateProperty(key='valueAlignment', after=setAlignments, dependencies={'geometry', 'direction'})
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

	@StateProperty(key='label-size', after=Stack.setGeometries, dependencies={'geometry', 'direction'})
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


class GridStack(Stack, tag='grid'):
	"""A CSS grid: tracks, areas and gaps. Items are placed with `grid:` (`column`, `row`, spans).

	```yaml
	- type: grid
	  spacing: 8px
	  grid: {columns: [1fr, 2fr, 1fr], rows: [1fr, 1fr]}
	  items:
	    - type: realtime.text
	      key: environment.temperature.temperature
	      grid: {column: 1, row: 1, column-span: 2}
	```

	Uses `lib/layout/grid.py`. Always laid out by the engine; `spacing:` is the gap on both axes.
	"""

	@StateProperty(key='grid', default=None, after=Stack.setGeometries, allowNone=True, sortOrder=3)
	def gridProps(self) -> dict | None:
		"""`columns`, `rows` (track lists such as `[1fr, 200px]` or `repeat(auto-fit, minmax(150px, 1fr))`),
		`auto-columns`, `auto-rows`, `auto-flow` (row | column), `dense`, `gap`, `justify-content`,
		`align-content`, `justify-items`, `align-items`."""
		return getattr(self, '_gridProps', None)

	@gridProps.setter
	def gridProps(self, value: dict | None):
		self._gridProps = _checkedKeys(value, _GRID_KEYS | _GRID_ITEM_KEYS, 'grid')

	@property
	def usesCssLayout(self) -> bool:
		return True

	def _tracks(self, value, vertical: bool):
		if value is None:
			return []
		return cssgrid.parse_track_list(value, lambda number, unit: self.cssPx(f'{number}{unit}', vertical))

	def _trackSize(self, value, vertical: bool) -> cssgrid.TrackSize:
		if value is None:
			return cssgrid.TrackSize(cssgrid.Keyword.auto, cssgrid.Fr(1))
		(track,) = cssgrid.parse_track_list(value, lambda number, unit: self.cssPx(f'{number}{unit}', vertical))
		return track

	def setCssGeometries(self):
		width, height, left, top, right, bottom = self.cssBox()
		inner_w, inner_h = width - left - right, height - top - bottom
		if inner_w <= 0 or inner_h <= 0:
			return
		props = self.gridProps or {}
		gap = props.get('gap', None)
		if gap is None:
			gap_row = gap_column = self.cssGapPx()
		elif isinstance(gap, (list, tuple)):
			gap_row, gap_column = (self.cssPx(g, True) if i == 0 else self.cssPx(g, False) for i, g in enumerate(gap))
		else:
			gap_row, gap_column = self.cssPx(gap, True), self.cssPx(gap, False)
		container = cssgrid.GridContainer(
			columns=self._tracks(props.get('columns'), False),
			rows=self._tracks(props.get('rows'), True),
			auto_columns=self._trackSize(props.get('auto-columns'), False),
			auto_rows=self._trackSize(props.get('auto-rows'), True),
			auto_flow=str(props.get('auto-flow', 'row')),
			dense=bool(props.get('dense', False)),
			gap=CssGap(gap_row, gap_column),
			width=inner_w,
			height=inner_h,
		)
		for key, name in (('justify-content', 'justify_content'), ('align-content', 'align_content')):
			if props.get(key) is not None:
				setattr(container, name, cssparse.parse_content_align(props[key]))
		for key, name in (('justify-items', 'justify_items'), ('align-items', 'align_items')):
			if props.get(key) is not None:
				setattr(container, name, cssparse.parse_item_align(props[key]))
		# An item's natural height is a row of the explicit grid (or of an even split); its width follows the text's shape.
		columns = len(container.columns) or 1
		rows = len(container.rows) or -(-len(self.geometries) // columns)
		natural_h = inner_h / max(rows, 1)
		items = []
		for geometry in self.geometries.values():
			spec = getattr(geometry.surface, 'gridProps', None) or {}
			aspect = self.cssAspect(geometry.surface)
			items.append(cssgrid.GridItem(
				max_content=(0.0, 0.0) if aspect is None else (aspect * natural_h, natural_h),
				placement=cssgrid.Placement(
					column_start=spec.get('column'), column_span=int(spec.get('column-span', 1)),
					row_start=spec.get('row'), row_span=int(spec.get('row-span', 1)),
				),
				justify_self=CssItemAlign.auto if 'justify-self' not in spec else cssparse.parse_item_align(spec['justify-self']).value,
				align_self=CssItemAlign.auto if 'align-self' not in spec else cssparse.parse_item_align(spec['align-self']).value,
			))
		rects = cssgrid.layout_grid(items, container)
		self.applyCssRects(rects, left, top, width, height)
		self.cssDividers(rects, left, top, width, height, columns=True, rows=True)

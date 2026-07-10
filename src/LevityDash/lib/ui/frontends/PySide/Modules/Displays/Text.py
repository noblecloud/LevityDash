
from PySide6.QtCore import QObject, QPoint, QPointF, QRectF, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, Qt, QTransform, QGradient
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem
from datetime import datetime, timedelta
from dateutil.parser import parser
from enum import Enum
from functools import cached_property, lru_cache
from rich.repr import rich_repr
from typing import Any, Callable, List, Optional, TYPE_CHECKING, Union, get_type_hints, Set

import WeatherUnits as wu
from LevityDash.lib.plugins import Container
from LevityDash.lib.plugins.observation import TimeHash
from LevityDash.lib.ui import Color
from LevityDash.lib.ui.Geometry import Alignment, AlignmentFlag, Geometry, getDPI, Size
from LevityDash.lib.ui.Groups import SizeGroupItem
from LevityDash.lib.ui.fonts import defaultFont, FontWeight
from LevityDash.lib.ui.frontends.PySide.utils import addCrosshair, addRect, colorPalette, DebugPaint, addPath, move_shape_into_rect, rect_to_shape, add_corner_at_point
from LevityDash.lib.ui.icons import fa as FontAwesome, Icon
from LevityDash.lib.utils.shared import _Panel, ActionPool, ClosestMatchEnumMeta, defer, now, TextFilter, block_pools
from LevityDash.lib.log import debug as DEBUG

from LevityDash.lib.ui import UILogger as log
log = log.getChild(__name__)

if TYPE_CHECKING:
	from LevityDash.lib.ui.frontends.PySide.app import LevityScene
	from LevityDash.lib.ui.frontends.PySide.Modules.Panel import SizeGroup


class TextItemSignals(QObject):
	changed = Signal()
	transformed = Signal(QTransform)


class ScaleType(str, Enum, metaclass=ClosestMatchEnumMeta):
	fill = 'fill'
	auto = 'auto'
	font = 'font'
	string = 'string'


@DebugPaint
@rich_repr
class Text(QGraphicsPathItem):

	_format_value_func: Callable[[Any], str] = None

	_value: Container
	_parent: _Panel
	_textRect: QRectF = None

	__alignment: Alignment
	__modifier: Optional[dict]
	__defaultIcon = FontAwesome.getIcon('ellipsis', 'solid')
	__defaultText = '-'

	_defaultIconFromParent: Icon | None
	_defaultTextFromParent: str | None

	scaleSelection = min
	minimumDisplayHeight = wu.Length.Millimeter(10)
	baseLabelRelativeHeight = 0.3

	_fixedFontSize: int | float = 0
	_scaleType: ScaleType = ScaleType.auto
	_height: Size.Height | None = None
	_relativeTo: Geometry | None = None
	_height_px_cache: Optional[int] = None
	_color: Color = Color(colorPalette.windowText().color())
	_value: Container | str | int | float | datetime | timedelta | Icon | None = None

	_valueAccessor: Callable[[], Any] | None = None
	_textAccessor: Callable[[], str] | None = None
	_fontAccessor: Callable[[], QFont] | None = None

	_defaultIcon: Optional[Icon] = None
	_defaultText: Optional[str] = None

	enabledFilters: List[TextFilter]
	__enabledFilters: List[TextFilter]

	surface: Optional[QGraphicsItem]

	@cached_property
	def surface(self) -> QGraphicsItem:
		surface_type = get_type_hints(type(self)).get('surface', None)
		parent_item = self.parentItem()
		try:
			surface_type = surface_type.__args__
		except AttributeError:
			pass
		while parent_item is not None and not isinstance(parent_item, surface_type):
			parent_item = parent_item.parentItem()
		return parent_item

	@property
	def action_pool(self) -> ActionPool:
		try:
			return self.parent.action_pool
		except AttributeError:
			pass
		try:
			return self.surface.action_pool
		except AttributeError:
			pass

	if TYPE_CHECKING:
		from LevityDash.lib.ui.frontends.PySide.app import LevityScene
		def scene(self) -> LevityScene: ...

	# Section init
	def __init__(self, parent: _Panel,
		value: Optional[Any] = None,
		alignment: Union[Alignment, AlignmentFlag] = None,
		font: Union[QFont, str] = None,
		filters: Optional[List[str]] = None,
		modifier: Optional[dict] = None,
		color: QColor = None,
		**kwargs
	):
		self._font = None
		self.__enabledFilters = []
		self.__modifier = modifier or {}

		super(Text, self).__init__(parent=None)
		self.setPen(QPen(Qt.NoPen))
		self.signals = TextItemSignals()

		self.signals.transformed.connect(self.__transformSlot)

		self._parent = parent
		if isinstance(parent, QGraphicsItem):
			self.setParentItem(parent)
		if filters is None:
			filters = list()

		if alignment is None:
			alignment = Alignment(AlignmentFlag.Center)
		elif isinstance(alignment, AlignmentFlag):
			alignment = Alignment(alignment)
		self.__alignment = alignment

		self.setFont(font)
		self.setFillBrush(color)
		self.value = value
		self.setAlignment(alignment)
		self.updateTransform(reason='init')

		for _filter in filters:
			self.setFilter(_filter, True)

		if hasattr(self.parent, 'signals') and hasattr(self.parent.signals, 'resized'):
			self.parent.signals.resized.connect(self.asyncUpdateTransform)

	@property
	def is_loading(self) -> bool:
		try:
			return self.parent.is_loading
		except AttributeError:
			return self.topLevelItem().is_loading

	@property
	def state_is_loading(self) -> bool:
		if self.parent is None:
			return self.is_loading or False
		return self.is_loading or self.parent.state_is_loading

	def __rich_repr__(self):
		yield 'text', self.text
		if (textRect := getattr(self, '_textRect', None)) is not None:
			textRect = self.mapRectToScene(textRect)
			yield 'textRect', textRect
		yield 'limitRect', self.limitRect
		yield 'fontSize', self.font().pointSizeF(), 16.0
		yield 'fontWeight', FontWeight.fromQt(self._font.weight()), FontWeight.Normal
		yield 'font', self.font()
		yield 'transform', (self.transform().m11(), self.transform().m22())

	def setRelativeHeight(self, height: Size.Height, relativeTo: Geometry):
		self._height = height
		self._height_px_cache = None
		self._relativeTo = relativeTo
		self.updateTransform(updatePath=True, updateShared=True, reason='setRelativeHeight')

	def setAbsoluteHeight(self, height: Size.Height):
		self._height = height
		self._relativeTo = None
		self._height_px_cache = None
		self.updateTransform(updatePath=True, updateShared=True, reason='setAbsoluteHeight')

	@property
	def height(self) -> Size.Height | wu.Length | None:
		return self._height

	@property
	def height_px(self) -> float | None:
		if self._height_px_cache is not None:
			return self._height_px_cache
		height: Size.Height = self._height
		match height:
			case None:
				return None
			case Size.Height(absolute=True):
				self._height_px_cache = v = height.value
				return v
			case Size.Height(relative=True):
				if self._relativeTo is None:
					raise ValueError('RelativeTo is not set')
				return height.toAbsolute(self._relativeTo.absoluteHeight)
			case wu.Length(), _:
				dpi = getDPI(self.surface.scene().view.screen())
				value = float(height.inch) * dpi
				self._height_px_cache = value
				return value
			case _:
				return None

	@property
	def minimumFontSize(self) -> float:
		dpi = self.scene().view.physicalDpiX()
		return max(float(self.minimumDisplayHeight.inch*dpi), 5.0)

	@property
	def suggestedFontPixelSize(self) -> float:
		return round(max(self.height_limit, 5), 2)

	@property
	def fixedFontSize(self) -> float | int:
		return self._fixedFontSize

	@fixedFontSize.setter
	def fixedFontSize(self, size: float | int):
		self._fixedFontSize = size or 0.0
		if self._fixedFontSize:
			self._font.setPointSizeF(size)
		else:
			self._font.setPointSizeF(self.suggestedFontPixelSize)

	@property
	def fontSize(self) -> float | int:
		return self.fixedFontSize or self.suggestedFontPixelSize

	@property
	def align(self) -> Alignment:
		return self.__alignment

	@property
	def parent(self) -> _Panel:
		return self._parent

	def setAlignment(self, alignment: Alignment | AlignmentFlag):
		self.alignment = alignment

	def _setAlignment(self, alignment: Alignment):
		self.__alignment = alignment

	@property
	def alignment(self) -> Alignment:
		return self.__alignment

	@alignment.setter
	def alignment(self, value):
		if isinstance(value, AlignmentFlag):
			if value.isVertical:
				self.__alignment.vertical = value.asVertical
			if value.isHorizontal:
				self.__alignment.horizontal = value.asHorizontal
		else:
			if not isinstance(value, Alignment):
				if isinstance(value, AlignmentFlag):
					value = Alignment(value)
				elif isinstance(value, str):
					value = AlignmentFlag[value]
					value = Alignment(value)
				elif isinstance(value, dict):
					value = Alignment(**value)
				else:
					raise TypeError('Alignment must be of type Alignment or AlignmentFlag')
			self.__alignment = value
		self.updateTransform(reason='alignment-set')

	@property
	def enabledFilters(self) -> List[TextFilter]:
		return self.__enabledFilters

	@enabledFilters.setter
	def enabledFilters(self, value: List[TextFilter]):
		self.__enabledFilters = value

	def setFont(self, font: Union[QFont, str], update: bool = True):
		if font is None:
			font = QFont(defaultFont)
		elif isinstance(font, str):
			font = QFont(font)
		elif isinstance(font, QFont):
			font = QFont(font)
		else:
			font = QFont(font)
		self._font = font
		if self._value is not None and update:
			self.updateTransform(reason='setFont')

	def setFixedFontSize(self, size: float | int):
		self.fixedFontSize = size

	@property
	def _font(self):
		return self.__font

	@_font.setter
	def _font(self, value):
		self.__font = value

	def font(self, noIconFont: bool = False) -> QFont:
		font = QFont(self._font)
		font = QFont(icon.font) if (icon := self.icon) is not None and not noIconFont else font
		if g := getattr(self, '_sized', False):
			font.setPointSizeF(g.font_size_for(self))
		else:
			font.setPointSize(self.fontSize)
		return font

	def setFontFamily(self, family: str, update: bool=True):
		self._font.setFamily(family)
		if update: self.updateTransform(reason='setFontFamily')

	def setFontWeight(self, weight: int, update: bool=True):
		self._font.setWeight(weight)
		if weight != 50:
			self._font: QFont
		if update: self.updateTransform(reason='setFontWeight')

	def setFontAccessor(self, accessor: Callable):
		self._fontAccessor = accessor

	@property
	def hasDynamicFontFamily(self) -> bool:
		return self._fontAccessor is not type(self)._fontAccessor

	@property
	def limitRect(self) -> QRectF:
		"""
		The limitRect is the area in which the text is allowed to be drawn.
		Typically, this is the parent's marginRect, but it can be overridden.

		Must NOT depend on this item's own transform. mapRectFromItem divides
		by the item's current scale, so reading limitRect while a scale is
		applied distorts it and corrupts the fit (this was the resize/refresh
		regression vs. main). The item is a direct child of its parent, so
		translating the parent's marginRect by -pos gives it in this item's
		coordinate space at identity scale.
		"""
		return self.parent.marginRect.translated(-self.pos())

	@property
	def sceneLimitRect(self) -> QRectF:
		return self.mapRectToScene(self.limitRect)

	@property
	def unmapped_limit_rect(self) -> QRectF:
		return self.parent.marginRect

	@property
	def height_limit(self) -> float:
		return self.parent.marginRect.height()

	@property
	def containingRect(self) -> QRectF:
		return self.mapRectFromItem(self.parent, self.parent.rect())

	@property
	def size_group(self) -> Optional['SizeGroup']:
		return getattr(self, '_sized', None)

	@Slot(QRectF)
	def asyncUpdateTransform(self, rect: QRectF):
		# The parent resized; the group's fit is stale. Invalidate it, then
		# re-apply this item - updateTransform pulls a fresh fit (which recomputes
		# the whole group once). Sibling items re-apply through their own
		# parent-resized connections.
		if (group := self.size_group) is not None:
			group.mark_dirty()
		self.updateTransform(updatePath=True, updateShared=False, reason='asyncUpdateTransform')

	@Slot(QTransform)
	def __transformSlot(self, t: QTransform):
		self.setTransform(t)

	# Section Transform
	@defer(pool_attr='action_pool')
	def updateTransform(self, rect: QRectF = None, updateShared: bool = True, updatePath: bool = True, reason: str = None, *args):
		transform = QTransform()
		self.setTransform(transform)

		if group := getattr(self, '_sized', None):
			log.verbose(f'Updating transform for {self.value} with reason: {reason}')

		if updatePath:
			self._update_path(update_others=updateShared)
			self.setTransform(transform)

		limitRect = self.limitRect

		if (height := self.height_px) is not None:
			center = limitRect.center()
			limitRect.setHeight(height)
			limitRect.moveCenter(center)

		rect = self._textRect or self._update_path()
		self.setTransformOriginPoint(0, 0)
		# thread the one (height-adjusted) limitRect through both helpers so
		# position and scale are computed against the same rect
		x, y = self.getTextPosition(limitRect).toTuple()
		fit = None
		if (group := getattr(self, '_sized', None)) is not None:
			group: 'SizeGroup'
			fit = group.fit_for(self)
			# baseline alignment: share the group's scene-y (computed at identity
			# here, since the transform is reset - same hygiene as limitRect)
			if fit.baseline_y is not None:
				y = self.mapFromScene(QPointF(0, fit.baseline_y)).y()
		transform.translate(x, y)
		if not self._fixedFontSize:
			scale = fit.scale if fit is not None else self.getTextScale(rect, limitRect)
			transform.scale(scale, scale)

		if DEBUG:
			font = self.font()
			if not self.isIcon:
				tool_tip_text = [
					'font:',
					f'  family: {font.family()}',
					f'  size: {font.pointSizeF():.2f}',
					'transform:',
				]
			else:
				tool_tip_text = [
					'font:',
					f'  family: {font.family()}',
					f'  size: {font.pointSizeF():.2f}',
					f'  icon: {self.icon.name}',
					'transform:',
				]

			if transform.isScaling():
				tool_tip_text.append(f'  scale: {transform.m11():.2f}')
			if transform.isRotating():
				tool_tip_text.append(f'  rotation: {transform.rotation():.2f}')
			if transform.isTranslating():
				tool_tip_text.append(f'  translate:\n    x: {transform.dx():.2f}\n    y: {transform.dy():.2f}')
			if tool_tip_text[-1] == 'transform:':
				tool_tip_text.append('  none')
			if (group := locals().get('group', None)) is not None and fit is not None:
				group: 'SizeGroup'
				group_name = f'{getattr(group.parent, "__tag__", "?")}.{group.key}'
				tool_tip_text.extend((
					f'group: {group_name} ({len(group.items)})',
					f'  scale: {fit.scale:.2f}',
					f'  font_size: {fit.font_size:.2f}')
				)
			self.setToolTip('\n'.join(tool_tip_text))

		self.setTransform(transform)

	def find_character_bounding_rect(
		self,
		index: int = None,
		font: QFont = None,
		font_metrics: QFontMetricsF = None,
		string: str = None,
	) -> QRectF:

		string = string or self.text
		if len(string) <= 1:
			return self.path().boundingRect()

		if index is None:
			h_align = self.alignment.horizontal
			text_len = len(self.text)
			if h_align.isLeft:
				index = 0
			elif h_align.isRight:
				index = text_len - 1
			elif h_align.isCenter:
				if text_len == 2:
					return self.path().boundingRect()
				index = text_len / 2 if (text_len % 2 == 0) else text_len // 2
			else:
				raise ValueError(f'Invalid alignment: {self.alignment.horizontal}')

		font = font or self.font()
		font_metrics = font_metrics or QFontMetricsF(font)

		if isinstance(index, float):
			index = int(index)
			character = string[index:index + 1]
		else:
			index = int(index)
			character = string[index]

		text_rect = self.path().boundingRect()

		left_text, right_text = string[:index], string[index + len(character):]

		bounding_rect = font_metrics.boundingRect(string)
		bounding_rect.moveCenter(text_rect.center())

		left_width = font_metrics.horizontalAdvance(left_text)

		char_rect = font_metrics.boundingRectChar(character)
		char_rect.moveCenter(text_rect.center())
		char_rect.moveLeft(text_rect.left() + left_width)

		return char_rect

	def setScenePosition(self, position: QPointF):
		self.setPos(self.mapFromScene(position))

	def getTextScale(self, textRect: QRectF = None, limitRect: QRectF = None) -> float:
		# Pure: never mutates the transform. limitRect is transform-independent,
		# so no reset is needed; leaving the transform alone means computing one
		# item's scale (e.g. during a group's shared-size pass) can't corrupt
		# another item's transform.
		textRect = textRect or self._textRect or self._update_path(update_others=False)
		limitRect = limitRect if limitRect is not None else self.limitRect

		width = (textRect.width()) or 1
		height = (textRect.height()) or 1

		rotation = abs(self.rotation() or self.parent.rotation())
		if rotation < 45:
			wScale = limitRect.width()/width
			hScale = limitRect.height()/height
		else:
			wScale = limitRect.width()/height
			hScale = limitRect.height()/width
		return round(self.scaleSelection(wScale, hScale), 4)

	def getTextPosition(self, limitRect: QRectF = None) -> QPointF:
		# Pure: takes the caller's limitRect (e.g. the height-adjusted one from
		# updateTransform) and never touches the transform.
		limitRect = limitRect if limitRect is not None else self.limitRect
		m = QPointF(*self.align.multipliersAlt)
		x, y = limitRect.topLeft().toTuple()
		x += m.x()*limitRect.width()
		y += m.y()*limitRect.height()
		return QPointF(x, y)

	def getTextScenePosition(self) -> QPointF:
		t = self.transform()
		self.resetTransform()
		limitRect = self.mapRectToScene(self.limitRect)
		m = QPointF(*self.align.multipliersAlt)
		x, y = limitRect.topLeft().toTuple()
		x += m.x()*limitRect.width()
		y += m.y()*limitRect.height()
		self.setTransform(t)
		return QPointF(x, y)

	def scenePath(self) -> QPainterPath:
		return self.mapToScene(self.path())

	def getRelativeTextPosition(self, item: QGraphicsItem) -> QPointF:
		pos = self.getTextPosition()
		return self.mapToItem(item, pos)

	@lru_cache(maxsize=1)
	def overlap_shape(self, reach: float) -> QPainterPath:
		rect = self.containingRect
		rect.adjusted(-reach, -reach, reach, reach)
		return rect_to_shape(rect)

	def scene_overlap_shape(self, reach: float) -> QPainterPath:
		return self.mapToScene(self.overlap_shape(reach))

	def get_neighbors(self, reach: int, from_items: Set['Text'] = None, exclude: Set['Text'] = None) -> Set['Text']:
		if from_items is None and (size_group := getattr(self, '_sized', None)) is not None:
			size_group: 'SizeGroup'
			from_items = set(size_group.items)

		neighbors = set()

		if exclude is None:
			exclude = set()

		exclude.add(self)

		own_shape = self.scene_overlap_shape(reach)
		from_items = sorted(from_items, key=lambda item: abs(item.scenePos().manhattanLength() - self.scenePos().manhattanLength()))

		# return {item for item in from_items if item.scene_overlap_shape(reach).intersects(own_shape)}

		# first_collision = next((item for item in from_items if item.scene_overlap_shape(reach).intersects(own_shape)), None)
		first_collision, index = next(
			(
				(item, i) for i, item in enumerate(from_items)
				if item not in exclude
				and item.scene_overlap_shape(reach).intersects(own_shape)
			),
			(None, None)
		)

		if first_collision is None:
			return neighbors

		neighbors.add(first_collision)
		from_items = from_items[index:]
		neighbors |= first_collision.get_neighbors(reach, from_items, exclude)
		return neighbors

		own_shape = own_shape.united(first_collision.scene_overlap_shape(reach))

		while from_items:
			item = from_items.pop(0)
			if item.scene_overlap_shape(reach).intersects(own_shape):
				own_shape = own_shape.united(item.scene_overlap_shape(reach))
				neighbors.add(item)

		return neighbors

	def refresh(self):
		# refresh() is the value-arrival path (a container update calls it), so
		# the displayed text may have changed: rebuild this item's path with
		# updatePath=True - otherwise a late-arriving value never replaces the
		# '...' placeholder. If grouped, re-fit the whole group afterwards so
		# the shared size/baseline pick up the new text.
		self.updateTransform(reason='refresh', updatePath=True, updateShared=False)
		if (group := getattr(self, '_sized', None)) is not None:
			group.apply()
		# value = getattr(self.value, 'value', self.value)
		# if isinstance(value, wu.Time) and userConfig.getOrSet('Display', 'liveUpdateTimedeltas', True, userConfig.getboolean):
		# 	refreshTask = getattr(self, 'refreshTask', None)
		# 	if refreshTask is not None:
		# 		refreshTask.cancel()
			# TODO: change this to properly use abs once WeatherUnits has it implemented
			# if wu.Time.Minute(abs(value.minute)) < wu.Time.Minute(1):
			# 	self.refreshTask = loop.call_later(1, self.refresh)
			# elif wu.Time.Hour(abs(value.hour)) < wu.Time.Hour(1):
			# 	self.refreshTask = loop.call_later(60, self.refresh)

	def _debug_paint(self, painter: QPainter, option, widget):
		if self.path().isEmpty():
			return self._normal_paint(painter, option, widget)
		size = 10
		debug_colors = self._debug_paint_alt_colors
		# addRect(painter, self.find_character_bounding_rect(), color=QColor(Qt.yellow), label_text=f'char_rect: {self.text}')
		if (dbug_shap := getattr(self, '_debug_paint_shape', None)) is not None:
			c = QColor(self._debug_paint_color)
			c.setAlphaF(.3)
			# addRect(painter, dbug_shap.boundingRect(), color=c, label_text='fmt_hint_text_path')
			addPath(painter, dbug_shap, fill=c, color=c, weight=3)
		if (tr := getattr(self, '_textRect', None)) is not None:
			label_text = 'text_rect'
			if (fmt_rect := getattr(self, 'fmt_rect_hint', None)) is not None:
				if fmt_rect == tr:
					label_text = 'fmt_rect == text_rect'
					addRect(painter, fmt_rect.adjusted(-2, -2, 2, 2), color=debug_colors[1])
				else:
					addRect(painter, fmt_rect, color=debug_colors[2], label_text='fmt_rect')
			addRect(painter, tr, color=debug_colors[1], label_text=label_text)

		addRect(painter, self.limitRect, color=debug_colors[3], label_text='limit_rect')
		self._normal_paint(painter, option, widget)
		addCrosshair(painter, size=size, pos=QPoint(0, 0), weight=1, color=self._debug_paint_color)
		add_corner_at_point(painter, self._text_pos, color=debug_colors[1])

		# addCrosshair(painter, size=size, pos=self.path().boundingRect().center(), weight=2, color=debug_colors[2])

	@property
	def physicalDisplaySize(self) -> tuple[wu.Length.Centimeter, wu.Length.Centimeter]:
		window = self.scene().views()[0]
		# t = self.worldTransform()
		rect = self.path().boundingRect()
		physicalHeight = wu.Length.Inch(rect.height()/window.physicalDpiY()).cm
		physicalWidth = wu.Length.Inch(rect.width()/window.physicalDpiX()).cm
		return physicalWidth, physicalHeight

	def setFillBrush(self, value: QBrush):
		if value is None:
			value = QBrush(Color.text.QColor)
		self.setBrush(value)

	@property
	def fill_brush(self) -> QBrush:
		return self.brush()

	@fill_brush.setter
	def fill_brush(self, value: QBrush):
		self.setFillBrush(value)

	def estimateTextSize(self, font: QFont | float | int) -> tuple[float, float]:
		"""
		Estimates the height and width of a string provided a font
		:rtype: float, float
		:param font:
		:return: height and width of text
		"""
		if isinstance(font, (float, int)):
			font = QFont(self.font())
			font.setPointSizeF(font)
		p = QPainterPath()
		p.addText(QPoint(0, 0), font, self.text)
		rect = p.boundingRect()
		return rect.width(), rect.height()

	def setFilter(self, filter: str, value: bool = None):
		rawString = str(self.text)
		if value is None:
			value = not filter in self.enabledFilters
		if value:
			self.enabledFilters.add(filter)
		else:
			self.enabledFilters.discard(filter)
		# if rawString == self.text:
		# 	self.enabledFilters.discard(filter)
		# 	self.log.warning(f'Filter {filter[1:]} is not applicable to "{rawString}"')
		self._update_path()

	@property
	def modifiers(self):
		return self.__modifier

	@modifiers.setter
	def modifiers(self, value):
		if value is None:
			self.__modifier.clear()
			return
		self.__modifier = value

	def setTextAccessor(self, accessor: Callable[[], Any] | None):
		self._textAccessor = accessor
		if accessor is not None:
			self._value = None
		self.updateText()

	@property
	def hasDynamicText(self) -> bool:
		# !Note: Note the same as .hasDynamicValue
		return self._textAccessor is not None and self._value is None

	@cached_property
	def _defaultIconFromParent(self) -> Icon | None:
		return getattr(self.parentItem(), 'defaultIcon', None)

	@cached_property
	def _defaultTextFromParent(self) -> str | None:
		return getattr(self.parentItem(), 'defaultText', None)

	@property
	def default(self) -> str | Icon:
		return (self._defaultTextFromParent or
		        self._defaultIconFromParent or
		        self._defaultText or
		        self._defaultIcon or
		        self.__defaultText or
		        self.__defaultIcon)

	def set_formatting_func(self, func: Callable[[Any], str]):
		self._format_value_func = func

	@property
	def text(self) -> str | None:
		value = self.value if (func := self._textAccessor) is None else func()
		if value is None:
			return None

		text = self._format_value_func(value) if self._format_value_func is not None else str(value)

		for filterFunc in self.enabledFilters:
			text = filterFunc(text)
		return text

	@text.setter
	def text(self, value):
		self.value = value

	@property
	def value(self) -> Container | str | int | float | datetime | timedelta | Icon | None:
		if self._valueAccessor is not None:
			try:
				return self._valueAccessor()
			except Exception as e:
				self.log.error(f'Error getting value from accessor: {e}')

		if self._value is None:
			return self.default
		if isinstance(self._value, (str, int, float, datetime, timedelta, Icon)):
			value = self._value
		else:
			value = self._value.value
			if self.__modifier:
				# if self.__modifier['type'] == 'attribute' and hasattr(value, f'@{self.__modifier["key"]}'):
				# 	value = getattr(value, f'@{self.__modifier["key"]}')
				if time := self.__modifier.get('atTime', None):
					value = value.source.source[value.key]
					if time == 'today':
						time = now()
						time = time.replace(hour=0, minute=0, second=0, microsecond=0)
					elif time == 'tomorrow':
						time = now()
						time = time.replace(hour=0, minute=0, second=0, microsecond=0)
						time += timedelta(days=1)
					elif time == 'yesterday':
						time = now()
						time = time.replace(hour=0, minute=0, second=0, microsecond=0)
						time -= timedelta(days=1)
					else:
						time = parser.parse(time)
					value = value.getFromTime(time, timehash=TimeHash.Minutely)

		return value

	@value.setter
	def value(self, value):
		if str(value) != self.text:
			self._value = value
			self.updateTransform(reason='value-set', updatePath=True, updateShared=True)

	@property
	def icon(self) -> None | Icon:
		value = self.value
		value = subValue if (subValue := getattr(value, 'value', None)) is not None else value
		if value is None and self.text is None and self._defaultText is None:
			return self._defaultIcon or self.__defaultIcon
		return icon if isinstance(icon := value, Icon) and self._textAccessor is None else None

	@property
	def isIcon(self) -> bool:
		value = self.icon
		return (value is not self.__defaultIcon or self.text is None) and isinstance(value, Icon)

	def setValueAccessor(self, accessor: Callable[[], Any] | None):
		self._valueAccessor = accessor
		if accessor is not None:
			self._value = None
		self.updateTransform(reason='setValueAccessor')

	@property
	def hasDynamicValue(self) -> bool:
		return (self._valueAccessor is not None and self._textAccessor is not None) and self._value is None

	@property
	def hasStaticValue(self) -> bool:
		return (self._valueAccessor is None and self._textAccessor is None) and self._value is not None

	@property
	def allow_dynamic_value(self) -> bool:
		return getattr(self, '_value', None) is None

	@property
	def textScaleType(self) -> ScaleType:
		return self._scaleType

	@textScaleType.setter
	def textScaleType(self, value: ScaleType):
		if value != self._scaleType:
			self._scaleType = value
			self.updateTransform(reason='textScaleType')

	def setScaleType(self, value: ScaleType):
		self._scaleType = value
		self.updateTransform(reason='setScaleType')

	def _update_path(self, /, update_others: bool = False) -> QRectF:
		self.resetTransform()
		font = self.font()
		fm = QFontMetricsF(font)

		text = self.text if self.icon is None else str(self.icon)

		path = QPainterPath()  # The actual path of the text
		path.setFillRule(Qt.WindingFill)

		fmt_hint_text_path = QPainterPath()  # The path of the text used to calculate the size of the text
		fmt_hint_text_path.setFillRule(Qt.WindingFill)

		path_size_hint = QPainterPath()
		path_size_hint.setFillRule(Qt.WindingFill)  # The path of the text used to calculate the fixed height of the text based on scale type

		limit_rect = self.limitRect  # The area in which the text is allowed to be drawn

		font_height = fm.height()

		fmt_hint_rect = fm.tightBoundingRect(fmt_hint_text := getattr(self, '_formatHint', None) or text)
		fmt_hint_rect |= fm.tightBoundingRect(text)

		fmt_hint_bearing = QPointF(fm.leftBearing(fmt_hint_text[0] if fmt_hint_text else ' '), 0)

		text_rect = fm.tightBoundingRect(text)
		text_bearing = QPointF(fm.leftBearing(text[0] if text else ' '), 0)

		pipe_rect = fm.tightBoundingRect('|')
		pipe_bearing = QPointF(fm.leftBearing('|'), 0)

		scaleType = self._scaleType

		if scaleType is ScaleType.auto:
			if fmt_hint_text != text:
				scaleType = ScaleType.string
			elif pipe_rect.isEmpty():
				scaleType = ScaleType.font

		# fmt_hint_rect.moveCenter(QPoint(0, fm.strikeOutPos()))
		# text_rect.moveCenter(QPoint(0, fm.strikeOutPos()))

		align = self.alignment

		match align.horizontal:
			case AlignmentFlag.Left:
				fmt_hint_rect.moveLeft(0)
				text_rect.moveLeft(fmt_hint_rect.left())
				# path_size_hint.translate(fmt_hint_rect.left() - path_size_hint.boundingRect().left(), 0)
			case AlignmentFlag.Right:
				fmt_hint_rect.moveRight(0)
				text_rect.moveRight(fmt_hint_rect.right())
				# path_size_hint.translate(fmt_hint_rect.right() - path_size_hint.boundingRect().right(), 0)
			case AlignmentFlag.HorizontalCenter:
				fmt_hint_rect.moveCenter(QPoint(0, fmt_hint_rect.center().y()))
				text_rect.moveCenter(QPoint(fmt_hint_rect.center().x(), text_rect.center().y()))
				# path_size_hint.translate(fmt_hint_rect.center().x() - path_size_hint.boundingRect().center().x(), 0)

		match align.vertical:
			case AlignmentFlag.Top:
				fmt_hint_rect.moveTop(0)
				top_diff = fmt_hint_rect.top() - text_rect.top()
				text_rect.moveTop(fmt_hint_rect.top())
				# path_size_hint.translate(0, top_diff)
			case AlignmentFlag.Bottom:
				fmt_hint_rect.moveBottom(0)
				text_rect.moveBottom(fmt_hint_rect.bottom())
				# path_size_hint.translate(0, fmt_hint_rect.bottom() - path_size_hint.boundingRect().bottom())
			case AlignmentFlag.VerticalCenter:
				# fmt_hint_rect.moveCenter(QPoint(fmt_hint_rect.center().x(), fmt_hint_rect.center().y() - y_diff))
				fmt_hint_rect.moveCenter(QPoint(fmt_hint_rect.center().x(), 0))
				# fmt_hint_rect.moveCenter(QPoint(fmt_hint_rect.center().x(), fmt
				# fmt_hint_rect.moveCenter(QPoint(fmt_hint_rect.center().x(), -strikeout_pos_y))
				# fmt_hint_rect.moveCenter(QPoint(fmt_hint_rect.center().x(), -(fm.ascent() - fm.xHeight())))
				# fmt_hint_rect.moveCenter(QPoint(0, -fm.strikeOutPos()))
				text_rect.moveCenter(QPoint(text_rect.center().x(), fmt_hint_rect.center().y()))
				# path_size_hint.translate(0, fmt_hint_rect.center().y() - path_size_hint.boundingRect().center().y())

		self._text_pos = text_pos = text_rect.bottomLeft() - text_bearing
		self._fmt_text_pos = fmt_text_pos = fmt_hint_rect.bottomLeft() - fmt_hint_bearing

		# Move offset the text position for the center to be at the strikeout position
		text_pos.setY(text_pos.y() - (text_rect.height() / 2 - fm.strikeOutPos()))
		fmt_text_pos.setY(fmt_text_pos.y() - (fmt_hint_rect.height() / 2 - fm.strikeOutPos()))

		# Draw the value and format hint text
		fmt_hint_text_path.addText(fmt_text_pos, font, fmt_hint_text)
		path.addText(text_pos, font, text)

		# Determine the scale type and add the path to the size hint path
		match scaleType:

			# Use the size of the format hint text as the size of the text
			case ScaleType.string if text != fmt_hint_text:
				path_size_hint.addPath(fmt_hint_text_path)

			case ScaleType.auto:
				if self.isIcon:
					# Use average of capHeight and xHeight as the height of the text
					height = (fm.capHeight() + fm.xHeight()) / 2
					path_size_hint.addRect(QRectF(*fmt_hint_rect.bottomLeft().toTuple(), fmt_hint_rect.width(), -height))
				else:
					path_size_hint.addText(QPointF(fmt_hint_rect.center().x(), fmt_text_pos.y()), font, '|')

			# Use the size of the font as the size of the text
			case ScaleType.font:
				path_size_hint.moveTo(QPointF(fmt_hint_rect.center().x(), text_pos.y()) - QPointF(0, fm.capHeight()))
				path_size_hint.lineTo(QPointF(fmt_hint_rect.center().x(), text_pos.y()) + QPointF(0, fm.descent()))

			case ScaleType.fill:
				if self.isIcon:
					path_size_hint.addRect(QRectF(*fmt_hint_rect.bottomLeft().toTuple(), fmt_hint_rect.width(), -(fm.capHeight() + fm.xHeight())/2))
				else:
					path_size_hint.moveTo(QPointF(fmt_hint_rect.center().x(), text_pos.y()) - QPointF(0, fmt_hint_rect.bottom()))
					path_size_hint.lineTo(QPointF(fmt_hint_rect.center().x(), text_pos.y()) + QPointF(0, fmt_hint_rect.top()))
			case _:
				pass

		# # Add strikeout line to the size hint path
		# path_size_hint.moveTo(QPointF(fmt_hint_rect.left(), fmt_text_pos.y() - fm.strikeOutPos()))
		# path_size_hint.lineTo(QPointF(fmt_hint_rect.right(), fmt_text_pos.y() - fm.strikeOutPos()))
		#
		# # Add capHeight line to the size hint path
		# path_size_hint.moveTo(QPointF(fmt_hint_rect.left(), fmt_text_pos.y() - fm.capHeight()))
		# path_size_hint.lineTo(QPointF(fmt_hint_rect.right(), fmt_text_pos.y() - fm.capHeight()))
		#
		# # Add decent line to the size hint path
		# path_size_hint.moveTo(QPointF(fmt_hint_rect.left(), fmt_text_pos.y() + fm.descent()))
		# path_size_hint.lineTo(QPointF(fmt_hint_rect.right(), fmt_text_pos.y() + fm.descent()))

		fmt_hint_text_path.addPath(path_size_hint)

		fmt_hint_rect |= path_size_hint.boundingRect()

		# if scaleType is ScaleType.fill:
		# 	reach = 10
		# 	if align.vertical is AlignmentFlag.VerticalCenter:
		# 		y = limit_rect.center().y()
		# 		if not y - reach < fmt_hint_rect.center().y() < y + reach:
		# 			y_diff = fmt_hint_rect.center().y() - y
		# 			fmt_hint_rect.translate(0, y_diff)
		# 			path.translate(0, y_diff)
		# 			fmt_hint_text_path.translate(0, y_diff)

		self._shapePath = fmt_hint_text_path

		size_hint_rect = fmt_hint_text_path.boundingRect()
		self.fmt_rect_hint = fmt_hint_rect
		self._debug_paint_shape = fmt_hint_text_path

		# rotation = self.rotation() or self.parent.rotation()
		newTextRect = size_hint_rect #if not abs(rotation) else QTransform().rotate(rotation).map(pathSizeHint).boundingRect()

		self._textRect = newTextRect
		self._sizeHintRect = newTextRect
		self._fmt_rect = fmt_hint_rect
		self.setPath(path)

		if update_others and (group := getattr(self, '_sized', None)) is not None:
			group: 'SizeGroup'
			# this item's text/size changed; the group's shared fit is stale.
			# Mark it dirty so the next fit pull recomputes for all members.
			group.mark_dirty()

		return newTextRect

	def updateText(self):
		self.updateTransform(updatePath=True, updateShared=True, reason='updateText')

	_shapePath: QPainterPath = QPainterPath()

	def shape(self) -> QPainterPath:
		return self._shapePath


class TextHelper(Text):
	"""
	This class does not have its own stored value, instead it is provided a value by the parent Text item.
	Example: Displaying the parent text item's unit
	"""

	def __init__(self, parent, reference: Text, font: QFont = None, alignment: Alignment = None, enabledFilters: set = None, *args, **kwargs):
		self.reference = reference
		super().__init__(parent, '', font, alignment, enabledFilters, *args, **kwargs)

	@property
	def value(self):
		return getattr(self.reference.value, '@unit', '')

	@value.setter
	def value(self, value):
		pass

	def __dir__(self):
		return set(super().__dir__()) - set(dir(QGraphicsItem))

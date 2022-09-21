import asyncio
import re
from collections import defaultdict
from functools import cached_property, partial, reduce
from operator import or_
from pathlib import Path
from pprint import pprint
from typing import (
	Any, Callable, ClassVar, Dict, ForwardRef, List, NamedTuple, Optional, overload, Set, Sized, Tuple, TYPE_CHECKING,
	TypeAlias, TypeVar, Union
)
from uuid import UUID, uuid4

from math import inf, prod
from PySide2.QtCore import (
	QByteArray, QMargins, QMimeData, QPoint, QPointF, QRect, QRectF, QSize, QSizeF, Qt, QThread, QTimer, Slot
)
from PySide2.QtGui import QBrush, QColor, QDrag, QFocusEvent, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide2.QtWidgets import (
	QApplication, QFileDialog, QGraphicsItem, QGraphicsItemGroup, QGraphicsPathItem, QGraphicsSceneDragDropEvent,
	QGraphicsSceneMouseEvent, QStyleOptionGraphicsItem
)
from qasync import asyncSlot
from rich.repr import auto

from LevityDash.lib.config import userConfig
from LevityDash.lib.EasyPath import EasyPathFile
from LevityDash.lib.log import debug
from LevityDash.lib.stateful import DefaultGroup, Stateful, StateProperty
from LevityDash.lib.ui import UILogger as log
from LevityDash.lib.ui.colors import Color
from LevityDash.lib.ui.Geometry import (
	AlignmentFlag, Dimension, Edge, Geometry, LocationFlag, Margins, Padding, parseSize, polygon_area, Position, Size,
	size_px
)
from LevityDash.lib.utils import ExecThread
from LevityDash.lib.utils.shared import (
	_Panel, boolFilter, clearCacheAttr, disconnectSignal, getItemsWithType, hasState, Numeric, SimilarValue
)
from WeatherUnits import Length
from .Handles import Handle, HandleGroup
from .Handles.Resize import ResizeHandles
from .Menus import BaseContextMenu
from ..utils import colorPalette, GeometryManaged, GeometryManager, GraphicsItemSignals, itemLoader, selectionPen

if TYPE_CHECKING:
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text

loop = asyncio.get_running_loop()


class Border(QGraphicsPathItem, Stateful, tag=...):
	_offset: Size.Height = Size.Height(0, absolute=True)

	edges: LocationFlag
	size: Size
	weight: float

	def __init__(self, parent: 'Panel', *args, **kwargs):
		super().__init__()
		self.parent = parent
		self.setParentItem(parent)
		self.setVisible(False)
		self.setEnabled(False)
		kwargs = self.prep_init(kwargs)
		self.state = kwargs

	@asyncSlot()
	async def parentResized(self, *args):
		self.updatePath()

	def updatePath(self) -> None:
		rect = self.parent.rect()
		if o := self.offset_px:
			rect.adjust(-o, -o, o, o)
		path = self.path()
		path.clear()
		size = self.size
		edges = self.edges
		if edges == LocationFlag.Edges:
			path.addRect(rect)
		elif edges == LocationFlag.Center:
			pass
		else:
			if edges & LocationFlag.Vertical:
				top = rect.top()
				bottom = rect.bottom()
				if size < 1:
					diff = (rect.height() - rect.height()*float(size))/2
					top += diff
					bottom -= diff
				if edges & LocationFlag.Left:
					path.moveTo(rect.left(), top)
					path.lineTo(rect.left(), bottom)
				if edges & LocationFlag.Right:
					path.moveTo(rect.right(), top)
					path.lineTo(rect.right(), bottom)

			if edges & LocationFlag.Horizontal:
				left = rect.left()
				right = rect.right()
				if size < 1:
					diff = (rect.width() - rect.width()*float(size))/2
					left += diff
					right -= diff
				if edges & LocationFlag.Top:
					path.moveTo(left, rect.top())
					path.lineTo(right, rect.top())
				if edges & LocationFlag.Bottom:
					path.moveTo(left, rect.bottom())
					path.lineTo(right, rect.bottom())
		self.setPath(path)
		self.setEnabled(path.elementCount() > 0)

	def updatePen(self) -> None:
		pen = self.pen()
		weight = self.weight
		color = self.color
		pen.setWidthF(weight)
		pen.setColor(color.QColor)
		self.setPen(pen)

	@StateProperty(default=LocationFlag.Edges, allowNone=False, after=updatePath)
	def edges(self) -> LocationFlag:
		return self._edges

	@edges.setter
	def edges(self, value: LocationFlag):
		self._edges = value

	@edges.decode
	def edges(self, value: str | int) -> LocationFlag:
		if isinstance(value, str):
			if value.casefold().startswith('all'):
				return LocationFlag.Edges
			elif value.casefold() == 'none':
				return LocationFlag.Center
			location = []
			if 'left' in value.casefold():
				location.append(LocationFlag.Left)
			if 'right' in value.casefold():
				location.append(LocationFlag.Right)
			if 'top' in value.casefold():
				location.append(LocationFlag.Top)
			if 'bottom' in value.casefold():
				location.append(LocationFlag.Bottom)
			if len(location) in {0, 4}:
				return LocationFlag.Edges
			return LocationFlag(sum(location))
		return LocationFlag(value)

	@edges.encode
	def edges(self, value: LocationFlag) -> str:
		if value & LocationFlag.Edges == LocationFlag.Edges:
			return 'all'
		name = value.name
		if name is None:
			return ', '.join(str(x.name).lower() for x in LocationFlag.edges() if value & x)
		return name.lower()

	@StateProperty(default=Dimension(0, absolute=True), after=updatePath)
	def offset(self) -> Dimension | Length:
		return self._offset

	@offset.setter
	def offset(self, value: Dimension | Length):
		self._offset = value

	@offset.decode
	def offset(self, value: str | int) -> float:
		return parseSize(value, 0.0)

	@property
	def offset_px(self) -> float:
		return size_px(self.offset, self.parent.geometry)

	@StateProperty(default=Size.Height(1, absolute=False), allowNone=False, after=updatePath)
	def size(self) -> Size.Height | Size.Width:
		return self._size

	@size.setter
	def size(self, value: Size.Height | Size.Width):
		self._size = value

	@size.decode
	def size(self, value: str | int) -> Size.Height | Size.Width:
		return self.parseSize(value, Size.Height(1, relative=True))

	@size.encode
	def size(self, value: Size.Height | Size.Width) -> str:
		return str(value)

	def parseSize(self, value: str | float | int, default) -> Size.Height | Size.Width:
		match value:
			case str(value):
				unit = ''.join(re.findall(r'[^\d\.\,]+', value)).strip(' ')
				match unit:
					case 'pt' | 'px':
						return Size.Height(float(value.strip(unit)), absolute=True)
					case '%':
						return Size.Height(float(value.strip(unit))/100, relative=True)
					case _:
						try:
							value = float(value.strip(unit))
							return Size.Height(value)
						except ValueError:
							return default
			case float(value) | int(value):
				return Size.Height(value)
			case _:
				log.error(f'{value} is not a valid value for labelHeight.  Using default value of {default} for now.')
				return default

	@StateProperty(default=1.0, allowNone=False, after=updatePen)
	def weight(self) -> float:
		return getattr(self, '_weight', None)

	@weight.setter
	def weight(self, value: float):
		self._weight = value

	@weight.decode
	def weight(self, value: str | int) -> float:
		return float(value)

	@weight.encode
	def weight(self, value: float) -> float:
		return round(value, 2)

	@StateProperty(default=DefaultGroup(Color('#ffffff'), colorPalette.windowText().color(), '#ffffff', 'ffffff'), allowNone=False, after=updatePen)
	def color(self) -> Color:
		return getattr(self, '_color', None)

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
					log.error(f'{value} is not a valid value for Color.  Using default value of #ffffff for now.')
					return Color('#ffffff')
			case QColor():
				value: QColor
				return Color(value.toRgb().toTuple())
			case _:
				log.error(f'{value} is not a valid value for Color.  Using default value of #ffffff for now.')
				return Color('#ffffff')

	@StateProperty(default=False, allowNone=False)
	def enabled(self) -> bool:
		return self.isEnabled() and self.isVisible()

	@enabled.setter
	def enabled(self, value: bool):
		self.setEnabled(value)
		self.setVisible(value)

	@StateProperty(key='opacity', default=1.0)
	def _opacity(self) -> float:
		return self.opacity()

	@_opacity.setter
	def _opacity(self, value: float):
		self.setOpacity(value)

	@_opacity.decode
	def _opacity(self, value: str | int) -> float:
		if isinstance(value, int) and value > 1:
			value /= 256
		return sorted([float(value), 0.0, 1.0])[1]

# @enabled.condition
# def enabled(self) -> bool:
# 	return not self.isEnabled()


class SizeGroup:
	items: Set['Text']
	parent: _Panel
	key: str

	locked: bool = False
	_lastSize: float = 0
	_alignments: Dict[AlignmentFlag, float]


	class ItemData(NamedTuple):
		item: 'Text'
		pos: QPointF

		def __hash__(self):
			return hash(self.item)


	itemsToAdjust: Set[ItemData]

	def __new__(cls, *args, **kwargs):
		matchAll = kwargs.pop('matchAll', False)
		if matchAll:
			cls = MatchAllSizeGroup
		return super().__new__(cls)

	def __init__(self, parent: 'Panel', key: str, items: Set['Text'] = None, matchAll: bool = False):
		self.updateTask = None
		self.key = key
		self.items = items or set()
		self.itemsToAdjust = set()
		self.parent = parent
		self._alignments = defaultdict(float)
		self.adjustSizes(reason='init')

		QApplication.instance().resizeFinished.connect(self.adjustSizes)

	def adjustSizes(self, exclude: Set['Text'] = None, reason=None):
		# items = self.similarItems(similarTo) if similarTo is not None else self.items
		# items = [i.text for i in self.items]
		if self.locked or len(self.items) < 2:
			return
		self.locked = True
		for group in self.sizes.values():
			for item in group:
				if item is not exclude:
					item.updateTransform(updatePath=False)
		self.locked = False

	def addItem(self, item: 'Text'):
		self.items.add(item)
		item._sized = self
		loop.call_later(.5, partial(self.adjustSizes, item, reason='addItem'))

	def removeItem(self, item: 'Text'):
		self.items.remove(item)
		item._sized = None
		self.adjustSizes(reason='remove')

	def sharedFontSize(self, item) -> int:
		sizes: List[int] = list(self.sizes)
		if len(sizes) == 0:
			clearCacheAttr(self, 'sizes')
			sizes = list(self.sizes)
		if len(sizes) == 1:
			return sizes[0]
		itemHeight = item.limitRect.height()
		return min(sizes, key=lambda x: abs(x - itemHeight))

	def sharedSize(self, v):
		s = min((item.getTextScale() for item in self.simlilarItems(v)), default=1)
		if not self.locked and abs(s - self._lastSize) > 0.01:
			self._lastSize = s
			self.__dict__.pop('sizes', None)
			loop.call_later(.5, partial(self.adjustSizes, v, reason='shared-size-change'))
		return s

	def testSimilar(self, rect: QRect | QRectF, other: 'Text') -> bool:
		other = other.parent.sceneBoundingRect()
		diff = (other.size() - rect.size())
		area = 10
		margins = QMargins(area, area, area, area)
		return abs(diff.height()) < area and rect.marginsAdded(margins).intersects(other.marginsAdded(margins))

	def simlilarItems(self, item: 'Text'):
		ownSize = item.parent.sceneBoundingRect()
		return {x for x in self.items if self.testSimilar(ownSize, x)}

	@cached_property
	def sizes(self) -> Dict[int, set['Text']]:
		items = set(self.items)
		groups = defaultdict(set)
		while items:
			randomItem = items.pop()
			group = self.simlilarItems(randomItem)
			items -= group
			height = max(sum(i.limitRect.height() for i in group) / len(group), 10)
			groups[round(height / 10) * 10] |= group
		return dict(groups)

	def clearSizes(self):
		self.__dict__.pop('sizes', None)

	def sharedY(self, item: 'Text') -> float:
		alignedItems = self.getSimilarAlignedItems(item)
		y = sum((i.pos.y() for i in alignedItems)) / (len(alignedItems) or 1)
		return y

	def getSimilarAlignedItems(self, item: 'Text') -> Set[ItemData]:
		position = item.getTextScenePosition()
		y = position.y()
		x = position.x()
		tolerance = item.limitRect.height()*0.2
		alignment = item.alignment.vertical
		alignedItems = {SizeGroup.ItemData(i, p) for i in self.items if i.alignment.vertical & alignment and abs((p := i.getTextScenePosition()).y() - y) < tolerance}
		return alignedItems


class MatchAllSizeGroup(SizeGroup):

	def simlilarItems(self, item: 'Text'):
		return self.items


PanelType = ForwardRef('Panel', is_class=True, module='Panel')
Panel: TypeAlias = TypeVar('Panel', bound=PanelType)


@auto
class Panel(_Panel, Stateful, tag='group'):
	collisionThreshold: ClassVar[float] = 0.5
	onlyAddChildrenOnRelease: ClassVar[bool] = False
	_acceptsChildren: ClassVar[bool] = True
	savable: ClassVar[bool] = True
	_keepInFrame: ClassVar[bool] = True
	acceptsWheelEvents: ClassVar[bool] = False
	__exclude__: ClassVar[Set[str]] = set()
	__match_args__ = ('geometry',)
	deletable: ClassVar[bool] = True

	signals: GraphicsItemSignals
	filePath: Optional[EasyPathFile]
	_childIsMoving: bool
	_attrGroups: None | Dict[str, SizeGroup] = None

	__groups__: Dict[str, 'Panel'] = {}

	__defaults__ = {
		'resizable': True,
		'movable':   True,
		'frozen':    False,
		'locked':    False,
		'margins': (0, 0, 0, 0)
	}

	# section Panel init
	def __init__(self, parent: _Panel, *args, **kwargs):
		# !setting the parent through the QGraphicsItem __init__ causes early
		# !isinstance checks to fail, so we do it manually later
		super(Panel, self).__init__()
		self._parent = parent
		self._init_defaults_()
		if debug:
			self.debugColor = Color.random(min=50, max=200).QColor
			self.debugColor.setAlpha(200)
			self.debugPen = QPen(self.debugColor)
			brush = QBrush(self.debugColor)
			self.debugPen.setBrush(brush)

		self.setParentItem(parent)
		kwargs = Stateful.prep_init(self, kwargs)
		self._init_args_(*args, **kwargs)
		self.previousParent = self.parent
		self.setFlag(self.ItemClipsChildrenToShape, False)
		self.setFlag(self.ItemClipsToShape, False)

	def _init_args_(self, *args, **kwargs) -> None:
		self.setAcceptedMouseButtons(Qt.AllButtons if kwargs.get('clickable', None) or kwargs.get('intractable', True) else Qt.NoButton)
		self.state = kwargs

	def _init_defaults_(self):
		self._childIsMoving = False
		self._contextMenuOpen = False
		self.uuidShort = self.uuid.hex[-4:]
		self.__hold = False
		self.signals = GraphicsItemSignals()
		self._fillParent = False
		self.filePath = None
		self._locked = False
		self.startingParent = None
		self.previousParent = None
		self.maxRect = None
		self._frozen = False
		self._name = None

		self.resizeHandles.setEnabled(True)

		self.hideTimer = QTimer(interval=1000*5, singleShot=True, timeout=self.hideHandles)

		self.setAcceptHoverEvents(True)
		self.setAcceptDrops(True)
		self.setFlag(QGraphicsItem.ItemIsSelectable)
		self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
		self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, False)
		self.setFlag(QGraphicsItem.ItemIsFocusable)

		self.setBrush(Qt.NoBrush)
		self.setPen(QColor(Qt.transparent))
		self.setFlag(QGraphicsItem.ItemStopsClickFocusPropagation)
		self.setFlag(QGraphicsItem.ItemStopsFocusHandling)

	def __eq__(self, other):
		if isinstance(other, Panel):
			return self.uuid == other.uuid
		return False

	@cached_property
	def uuid(self) -> UUID:
		return uuid4()

	def __hash__(self):
		return hash(self.uuid)

	@classmethod
	def validate(cls, item: dict, context=None):
		context = context or {}
		if (parent := context.get('parent', type)) is not type:
			if isinstance(parent, GeometryManager):
				return True
		geometry = Geometry.validate(item.get('geometry', {'fillParent': True}))
		return geometry

	@property
	def childIsMoving(self):
		return self._childIsMoving

	@childIsMoving.setter
	def childIsMoving(self, value):
		if self._childIsMoving != value:
			self._childIsMoving = value

	def debugBreak(self):
		state = self.state
		print(pprint(self.state))

	def isValid(self) -> bool:
		return self.rect().isValid()

	def size(self) -> QSizeF:
		return self.rect().size()

	@property
	def name(self):
		if self._name is None:
			if hasattr(self, 'title'):
				title = self.title
				if hasattr(title, 'text'):
					title = title.text
				if isinstance(title, Callable):
					title = title()
				self._name = str(title)
				return self._name
			if hasattr(self, 'text'):
				name = self.text
				if isinstance(name, Callable):
					name = name()
				self._name = str(name)
				return self._name

			if self.childPanels:
				# find the largest child with a 'text' attribute
				textAttrs = [child for child in self.childItems() if hasattr(child, 'text')]
				if textAttrs:
					textAttrs.sort(key=lambda child: child.geometry.size, reverse=True)
					self._name = textAttrs[0].text
					return self._name
				# find the largest panel with a linkedValue
				linkedValues = [child for child in self.childItems() if hasattr(child, 'linkedValue')]
			else:
				self._name = f'{self.__class__.__name__}-0x{self.uuidShort}'
				return self._name

	@name.setter
	def name(self, name):
		self._name = name

	def hideHandles(self):
		self.clearFocus()

	def setSize(self, *args):
		if len(args) == 1 and isinstance(args[0], QSizeF):
			size = args[0]
		elif len(args) == 2:
			size = QSizeF(*args)
		else:
			raise ValueError('Invalid arguments')
		self.setRect(self.rect().adjusted(0, 0, size.width(), size.height()))

	@property
	def acceptsChildren(self) -> bool:
		return self._acceptsChildren

	@acceptsChildren.setter
	def acceptsChildren(self, value: bool):
		self._acceptsChildren = value

	def __rich_repr__(self, **kwargs):
		# Section .repr
		if name := self.stateName is not None:
			yield 'name', name
		yield 'rect', Size(*self.rect().size().toTuple(), absolute=True)
		if getattr(self, '_geometry', None):
			yield 'geometry', self.geometry
			yield 'position', self.geometry.position
			yield 'size', self.geometry.size
		yield 'hierarchy', self.hierarchyString
		yield from Stateful.__rich_repr__(self, exclude={'geometry', 'name'})

	@property
	def snapping(self) -> bool:
		return self.geometry.snapping

	@snapping.setter
	def snapping(self, value):
		pass

	def updateSizePosition(self, recursive: bool = False):
		# if self.geometry.size.snapping:
		# 	self.setRect(self.geometry.rect())
		# if self.geometry.size:
		# 	w = self.sizeRatio.width * self.parent.containingRect.width()
		# 	h = self.sizeRatio.height * self.parent.containingRect.height()
		# 	self.setRect(QRectF(0, 0, w, h))
		#
		# if self.geometry.position.snapping:
		# 	self.setPos(self.geometry.pos())
		# elif self.positionRatio:
		# 	y = self.positionRatio.x * self.parent.containingRect.height()
		# 	x = self.positionRatio.y * self.parent.containingRect.width()
		# 	self.setPos(QPointF(x, y))
		# QGraphicsRectItem.setRect(self, self.geometry.rect())
		# QGraphicsRectItem.setPos(self, self.geometry.pos())
		self.signals.resized.emit(self.geometry.absoluteRect())
		if recursive:
			items = [item for item in self.childItems() if isinstance(item, Panel)]
			for item in items:
				item.updateSizePosition()

	def updateRatios(self):
		rect = self.parent.containingRect
		width = max(1, rect.width())
		height = max(1, rect.height())

		if self.geometry.relative:
			self.geometry.size.width = self.rect().width()/width
			self.geometry.size.height = self.rect().height()/height
			self.geometry.position.x = self.pos().x()/width
			self.geometry.position.y = self.pos().y()/height
		else:
			pass

	@cached_property
	def resizeHandles(self):
		clearCacheAttr(self, 'allHandles')
		handles = ResizeHandles(self)
		return handles

	@cached_property
	def marginHandles(self):
		clearCacheAttr(self, 'allHandles')
		from .Handles.MarginHandles import MarginHandles
		if existing := next((handle for handle in self.allHandles if isinstance(handle, MarginHandles)), None):
			return existing
		handles: MarginHandles = MarginHandles(self)
		# handles.signals.action.connect(self.refreshMargins)
		return handles

	@cached_property
	def allHandles(self):
		return [handleGroup for handleGroup in self.childItems() if isinstance(handleGroup, (Handle, HandleGroup))]

	@StateProperty(default=Geometry(width=1, height=1, x=0, y=0), match=True, allowNone=False)
	def geometry(self) -> Geometry:
		return self._geometry

	@geometry.setter
	def geometry(self, geometry):
		self._geometry = geometry

	@geometry.decode
	def geometry(self, value: dict | None) -> dict:
		match value:
			case None:
				return {'surface': self}
			case dict():
				return {'surface': self, **value}
			case tuple():
				x, y, w, h = value
				return dict(surface=self, x=x, y=y, width=w, height=h)
			case _:
				raise ValueError('Invalid geometry', value)

	@geometry.encode
	def geometry(self, value: Geometry) -> dict:
		return value.state

	@geometry.factory
	def geometry(self) -> Geometry:
		return Geometry(surface=self)

	@geometry.after
	def geometry(self):
		self.geometry.updateSurface()

	@geometry.condition(method='get')
	def geometry(self) -> bool:
		return not isinstance(self.parent, GeometryManager)

	@geometry.score
	def geometry(self, value) -> float:
		g: Geometry = self.geometry
		if isinstance(value, dict):
			value = Geometry(**value)
		g.scoreSimilarity(value)

	@StateProperty(default=Margins.default(), allowNone=False, dependencies={'geometry'}, decoder=Margins.decode)
	def margins(self) -> Margins:
		return self._margins

	@margins.setter
	def margins(self, value: Margins):
		value.surface = self
		self._margins = value

	@margins.factory
	def margins(self) -> Margins:
		return Margins(self, 0.1, 0.1, 0.1, 0.1)

	@margins.after
	def margins(self):
		clearCacheAttr(self, 'marginRect')

	@StateProperty(
		key='padding',
		default=Padding.default(),
		dependancies={'geometry'},
		sortOrder=3,
		decoder=Padding.decode
	)
	def padding(self) -> Padding:
		"""
		The padding around the panel.
		"""
		return self._padding

	@padding.setter
	def padding(self, value: Padding):
		value.surface = self
		self._padding = value

	@padding.factory
	def padding(self) -> Padding:
		return Padding(self)

	@StateProperty(key='border', default=Stateful, allowNone=False, dependencies={'geometry'})
	def borderProp(self) -> Border:
		return self._border

	@borderProp.setter
	def borderProp(self, value: Border):
		self._border = value

	@borderProp.factory
	def borderProp(self) -> Border:
		return Border(self)

	@borderProp.condition(method='get')
	def borderProp(self) -> bool:
		return self.borderProp.enabled

	@cached_property
	def localGroup(self) -> 'Panel':
		if (up := self.parentItem()) is None:
			return self
		elif self.__tag__ is not ...:
			return self
		return up.localGroup

	@cached_property
	def parentLocalGroup(self) -> Panel | None:
		parent = self.localGroup.parentItem()
		if parent is None:
			return None
		return parent.localGroup

	@property
	def hierarchy(self) -> List['Panel']:
		if (parent := self.parentItem()) is None:
			return [self]

		while parentHierarchy := getattr(parent, 'hierarchy', None) is None and isinstance(parent, QGraphicsItem):
			parent = parent.parentItem()

		if parentHierarchy is None:
			return [self]

		return parent.hierarchy + [self]

	@property
	def hierarchyString(self) -> str:
		hierarchy = []
		for i in self.hierarchy:
			if (name := i.stateName) is not None:
				hierarchy.append(name)
			elif i.__tag__ is ...:
				if hierarchy and hierarchy[-1] != '...':
					hierarchy.append('...')
			else:
				hierarchy.append(i.__tag__)

		return ' -> '.join(reversed(hierarchy))

	@cached_property
	def attrGroups(self) -> Dict[str, SizeGroup]:
		return {}

	def getTaggedGroup(self, tag: str) -> 'Panel':
		x = self
		while (t := getattr(x, '__tag__', None)) != tag and t is not None:
			try:
				x = x.parentItem()
			except AttributeError:
				break
		return x

	def getNamedGroup(self, name: str) -> 'Panel':
		if (namedGroup := Panel.__groups__.get(name, None)) is None:
			namedGroup = next((group for group in self.hierarchy if group.stateName == name), None)
			if namedGroup is None:
				return self.localGroup
			Panel.__groups__[name] = namedGroup
		return namedGroup

	def getAttrGroup(self, group: str | _Panel, matchAll: bool = False) -> SizeGroup:
		kwargs = {}
		match group.split('.') if isinstance(group, str) else group:
			case 'local', str(key):
				group = self.localGroup
			case 'global', str(key):
				group = self.scene().base
			case 'parent', str(key):
				group = (self.parentLocalGroup or self.localGroup)
			case 'group', str(key):
				group = self.getTaggedGroup('group')
			case str(tag), str(key):
				group = self.getTaggedGroup(tag)
			case [str(named)] if '@' in named:
				key, group = named.split('@')
				kwargs['tag'] = group
				group = self.getNamedGroup(group)
			case _:
				raise ValueError(f'invalid group {group}')

		attrGroups = group.attrGroups
		if (attrGroup := attrGroups.get(key, None)) is None:
			attrGroups[key] = attrGroup = SizeGroup(parent=group, key=key, matchAll=matchAll)
		return attrGroup

	@property
	def titledName(self) -> str | None:
		title = getattr(self, 'title', None)
		if title is None:
			return None
		if isinstance(title, str):
			return title
		if titleText := getattr(title, 'textBox', None):
			return str(titleText.text)
		if titleText := getattr(title, 'text', None):
			return str(titleText)
		return None

	@StateProperty(key='name', default=None, sortOrder=0)
	def stateName(self) -> str | None:
		if name := getattr(self, '_stateName', None):
			return name
		return title if (title := self.titledName) not in {'', 'Na', 'None', '. . .', '⋯'} else None

	@stateName.setter
	def stateName(self, value: str):
		existing = getattr(self, '_stateName', None)
		self._stateName = value
		if existing != value:
			Panel.__groups__.pop(existing, None)
		Panel.__groups__[value] = self

	@stateName.condition(method='get')
	def stateName(self) -> bool:
		return getattr(self, '_stateName', None) is not None

	def show(self):
		self.updateFromGeometry()
		# if not all(self.rect().size().toTuple()):
		# 	self.setRect(self.geometry.rect())
		# 	self.setPos(self.gridItem.pos())
		super(Panel, self).show()

	def scene(self) -> 'LevityScene':
		return super(Panel, self).scene()

	@StateProperty(
		sort=True,
		sortKey=lambda x: x.geometry.sortValue,
		default=DefaultGroup(None, []),
		dependencies={'geometry', 'margins'},
		sortOrder=-1,
	)
	def items(self) -> List['Panel']:
		return [child for child in self.childItems() if isinstance(child, _Panel) and hasState(child)]

	@items.setter
	def items(self, value: List[dict]):
		self.geometry.updateSurface()
		existing = self.items
		itemLoader(self, value, existing=existing)

	@items.condition(method='get')
	def items(owner: 'Panel') -> bool:
		return owner.hasChildren

	@items.condition(method={'get', 'set'})
	def items(value: List['Panel']) -> bool:
		if isinstance(value, Sized):
			return len(value) > 0
		return False

	def addItem(self, item: dict | _Panel, position: Position | QPoint | Tuple[float | int, float | int] = None):
		if isinstance(item, dict):
			item = itemLoader(self, [item])[0]
		else:
			item.setParentItem(self)
		item.updateSizePosition()
		item.geometry.relative = True

		# For whatever reason this prevents the item from jumping to the top left corner
		# when the item is first moved
		if position is not None:
			position = Position(position)
		else:
			position = item.geometry.position
		rect = item.rect()
		rect.moveTo(position.asQPointF())
		item.geometry.setGeometry(rect)

	@property
	def initArgs(self):
		return self.__initAgs__

	@cached_property
	def contextMenu(self):
		menu = BaseContextMenu(self)
		return menu

	def contextMenuEvent(self, event):
		if self.canFocus and self.hasFocus():
			event.accept()
		else:
			event.ignore()
			return
		self.contextMenu.position = event.pos()
		self.setSelected(True)
		self.contextMenu.exec_(event.screenPos())
		self.setFocus(Qt.MouseFocusReason)
		self.setSelected(True)

	def underMouse(self):
		return self.scene().underMouse()

	def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent):
		if self.acceptsChildren:
			if {*event.mimeData().formats()} & {'text/plain', 'text/yaml', 'text/x-yaml', 'application/x-yaml', 'application/yaml'}:
				event.acceptProposedAction()
				return
		event.ignore()
		super().dragEnterEvent(event)

	def dragMoveEvent(self, event: QGraphicsSceneDragDropEvent):
		super(Panel, self).dragMoveEvent(event)

	def dragLeaveEvent(self, event: QGraphicsSceneDragDropEvent):
		self.clearFocus()
		super(Panel, self).dragLeaveEvent(event)

	def dropEvent(self, event: QGraphicsSceneDragDropEvent):
		fmt = {*event.mimeData().formats()} & {'text/plain', 'text/yaml', 'text/x-yaml', 'application/x-yaml', 'application/yaml'}
		invalidFormats = []
		loader = type(self).__loader__
		for fmt in fmt:
			data = event.mimeData().data(fmt)
			try:
				data = data.data().decode('utf-8')
				data = loader(data).get_data()
				break
			except Exception as e:
				invalidFormats.append((fmt, data, e))
		else:
			raise ValueError('Invalid data', invalidFormats)

		self.addItem(data, position=Position(event.pos()))

	def clone(self):
		item = self
		state = item.state
		stateString = self.__dumper__(state)
		info = QMimeData()
		if hasattr(item, 'text'):
			info.setText(str(item.text))
		else:
			info.setText(repr(item))
		info.setData('text/yaml', QByteArray(stateString.encode('utf-8')))
		drag = QDrag(self.scene().views()[0].parent())
		drag.setPixmap(item.pix)
		drag.setHotSpot(item.rect().center().toPoint())
		# drag.setParent(child)
		drag.setMimeData(info)

	def groupItems(self):
		items = self.scene().selectedItems()
		parent = self.findCommonAncestor(*items)

		# combine all the rects
		rect = reduce(or_, (item.mapRectToScene(item.rect()) for item in items))
		rect = parent.mapRectFromScene(rect)
		newParent = Panel(parent=parent)
		newParent.geometry.setGeometry(rect)
		newRects = [i.mapRectToItem(newParent, i.rect()) for i in items]
		self.scene().clearSelection()
		for item, rect in zip(items, newRects):
			item.setParentItem(newParent)
			item.geometry.setGeometry(rect)
			item.update()

		newParent.setFocus(Qt.MouseFocusReason)

	def findCommonAncestor(self, *items) -> 'Panel':
		item = self.parentItem() or self.scene().base()
		while not all(item.isAncestorOf(i) for i in items):
			item = item.parentItem() or item.scene().base()
		return item

	def focusInEvent(self, event: QFocusEvent) -> None:
		if QApplication.queryKeyboardModifiers() & Qt.ShiftModifier or len(self.scene().selectedItems()) > 1:
			pass
		else:
			self.refreshHandles()
		super(Panel, self).focusInEvent(event)

	def refreshHandles(self):
		for handleGroup in self.allHandles:
			if handleGroup.isEnabled() and handleGroup.surface is self:
				handleGroup.show()
				handleGroup.updatePosition(self.rect())
				handleGroup.setZValue(self.zValue() + 1000)
			else:
				handleGroup.hide()

	def focusOutEvent(self, event: QFocusEvent) -> None:
		for handleGroup in self.allHandles:
			handleGroup.hide()
			handleGroup.setZValue(self.zValue() + 100)
		if QApplication.queryKeyboardModifiers() & Qt.ShiftModifier or len(self.scene().selectedItems()) > 1:
			pass
		else:
			self.setSelected(False)
		super(Panel, self).focusOutEvent(event)

	def stackOnTop(self, *above, recursive: bool = False):
		maxZ = max([item.z for item in above], default=0)
		if recursive:
			if parentFunc := getattr(self.parentItem(), 'stackOnTop', None):
				parentFunc(recursive=True)
		siblings = getattr(self.parentItem(), 'childPanels', [])
		for z, sibling in enumerate(sorted(filter(lambda x: x is not self and x.z >= maxZ, siblings), key=lambda x: x.z)):
			sibling.z = z
		self.z = len(siblings)

	def stackBelow(self, recursive: bool = False):
		if recursive:
			if parentFunc := getattr(self.parentItem(), 'stackBelow', None):
				parentFunc(recursive=True)
		siblings = getattr(self.parentItem(), 'childPanels', [])
		for z, sibling in enumerate(sorted(filter(lambda x: x is not self and x.z < self.z, siblings), key=lambda x: x.z)):
			sibling.z = z
		self.z = 0

	@property
	def z(self):
		return self.zValue()

	@z.setter
	def z(self, value):
		self.setZValue(value)

	@property
	def level(self):
		return getattr(self.parentItem(), 'level', -1) + 1

	def moveToTop(self):
		items = self.scene().items()
		if items:
			highestZValue = max([item.zValue() for item in items])
			self.setZValue(highestZValue + 1)

	@property
	def neighbors(self):
		n = 10
		rect = self.boundingRect()
		rect.adjust(-n, -n, n, n)
		rect = self.mapToScene(rect).boundingRect()
		path = QPainterPath()
		path.addRect(rect)
		neighbors = [item for item in self.parent.childPanels if item is not self and item.sceneShape().intersects(path)]

		return neighbors

	def childHasFocus(self):
		return any(item.hasFocus() or item.childHasFocus() for item in self.childPanels)

	def siblingHasFocus(self):
		return self.parent.childHasFocus()

	def mousePressEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		self.hideTimer.stop()
		if mouseEvent.buttons() == Qt.LeftButton | Qt.RightButton:
			mouseEvent.setButtons(Qt.LeftButton)
			mouseEvent.setButton(Qt.LeftButton)
			return self.mousePressEvent(mouseEvent)
		elif mouseEvent.button() == Qt.RightButton and mouseEvent.buttons() ^ Qt.RightButton:
			mouseEvent.accept()
			return super(Panel, self).mousePressEvent(mouseEvent)
		elif mouseEvent.button() == Qt.MouseButton.LeftButton:
			if (self.scene().focusItem() is self.apparentParent
			    or self.parent is self.scene().base
			    or self.hasFocus()
			    or self.siblingHasFocus()) and self.canFocus:
				if bool(mouseEvent.modifiers() & Qt.KeyboardModifier.ShiftModifier):
					self.setSelected(not self.isSelected())
				else:
					self.scene().clearSelection()
					self.setSelected(True)
				mouseEvent.accept()
				self.setFocus(Qt.FocusReason.MouseFocusReason)
				self.stackOnTop(recursive=True)
				self.startingParent = self.parent
				if self.maxRect is None:
					self.maxRect = self.rect().size()
			else:
				mouseEvent.ignore()

	@property
	def canFocus(self) -> bool:
		parentIsFrozen = isinstance(self.parent, Panel) and self.parent.frozen
		return bool(int(self.flags() & QGraphicsItem.ItemIsFocusable)) and not parentIsFrozen

	def hold(self):
		self.setFlag(QGraphicsItem.ItemIsMovable, False)
		self.__hold = True

	def release(self):
		self.setFlag(QGraphicsItem.ItemIsMovable, True)
		self.__hold = False

	def mouseMoveEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		if self.__hold:
			return
		filledParent = self.rect().size().toSize() == self.parent.rect().size().toSize()
		if (filledParent or self.parent.hasFocus()) and isinstance(self.parent, (QGraphicsItemGroup, Panel)):
			mouseEvent.ignore()
			self.parent.mouseMoveEvent(mouseEvent)
		if not self.movable and isinstance(self.parent, Panel) and self.parent.movable and self.parent.childHasFocus() and self.parent is not self.scene():
			mouseEvent.ignore()
			self.parent.mouseMoveEvent(mouseEvent)
			self.parent.setFocus(Qt.FocusReason.MouseFocusReason)
		else:
			if hasattr(self.parent, 'childIsMoving'):
				self.parent.childIsMoving = True
			return super(Panel, self).mouseMoveEvent(mouseEvent)

	def mouseReleaseEvent(self, mouseEvent: QGraphicsSceneMouseEvent) -> None:
		# self.hideTimer.start()
		if wasMoving := getattr(self.parent, 'childIsMoving', False):
			self.parent.childIsMoving = False

			if wasMoving:
				releaseParents = [item for item in self.scene().items(mouseEvent.scenePos())
					if item is not self
					   and not item.isAncestorOf(self)
					   and self.parent is not item
					   and isinstance(item, Panel)
					   and item.onlyAddChildrenOnRelease]

				sorted(releaseParents, key=lambda item: item.zValue(), reverse=True)
				if releaseParents:
					releaseParent = releaseParents[0]
					self.setParentItem(releaseParent)
					self.updateFromGeometry()
		if self.scene().focusItem() is not self:
			self.setFocus(Qt.FocusReason.MouseFocusReason)
		if QApplication.queryKeyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
			pass
		else:
			super().mouseReleaseEvent(mouseEvent)
		self.previousParent = None
		self.maxRect = None
		self.startingParent = self.parent

	def mouseDoubleClickEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		if not self.parent in [self.scene(), self.scene().base]:
			self._fillParent = not self._fillParent
			if self._fillParent:
				self.fillParent()
			else:
				self.geometry.updateSurface()

	def fillParent(self, setGeometry: bool = False):
		if self.parent is None:
			log.warn('No parent to fill')
			return QRect(0, 0, 0, 0)
		area = self.parent.fillArea(self)
		if area:
			rect = area[0]
			pos = rect.topLeft()
			rect.moveTo(0, 0)
			self.setRect(rect)
			self.setPos(pos)
			if setGeometry:
				self.geometry.setAbsolutePosition(pos)
				self.geometry.setAbsoluteRect(rect)

	def fillArea(self, *exclude) -> List[QRectF]:
		spots = []
		mappedVisibleArea = self.mapFromScene(self.visibleArea(*exclude))
		polygons = mappedVisibleArea.toFillPolygons()
		for spot in polygons:
			rect = spot.boundingRect()
			if rect.width() > 20 and rect.height() > 20:
				spots.append(rect)
		spots.sort(key=lambda x: x.width()*x.height(), reverse=True)
		return spots

	def findNewParent(self, position: QPointF):
		items = self.scene().items(position)
		items = getItemsWithType(items, Panel)
		items = [item for item in items if item is not self and item.acceptDrops()]
		items.sort(key=lambda item: item.zValue(), reverse=True)
		if items:
			return items[0]
		else:
			return None

	def similarEdges(self, other: 'Panel', rect: QRectF = None, singleEdge: LocationFlag = None):
		if singleEdge is None:
			edges = LocationFlag.edges()
		else:
			edges = [singleEdge]

		if rect is None:
			rect = self.rect()

		otherRect = self.parent.mapRectFromScene(other.sceneRect())

		matchedEdges = []
		for edge in edges:
			e = edge.fromRect(rect)
			for oEdge in [i for i in LocationFlag.edges() if i.sharesDirection(edge)]:
				o = oEdge.fromRect(otherRect)
				distance = abs(o - e)
				if distance <= 10:
					eX = Edge(self, edge, e)
					oX = Edge(other, oEdge, o)
					s = SimilarValue(eX, oX, distance)
					matchedEdges.append(s)
		matchedEdges.sort(key=lambda x: x.differance)
		return matchedEdges

	@property
	def marginRect(self) -> QRectF:
		rect = getattr(self, 'contentsRect', self.rect())
		margins = rect.marginsRemoved(self.margins.asQMarginF())
		return margins

	# def shape(self):
	# 	path = QPainterPath()
	# 	path.addRect(self.rect())
	# 	if self.hasFocus() and self.resizeHandles.isEnabled():
	# 		for handle in self.resizeHandles.childItems():
	# 			path += self.mapFromItem(handle, handle.shape())
	# 	return path.simplified()

	@cached_property
	def _focusedBoundingRect(self) -> QRectF:
		path = self.clipPath()
		for handle in self.resizeHandles.childItems():
			path += self.mapFromItem(handle, handle.shape())
		return path.boundingRect()

	def boundingRect(self) -> QRectF:
		if self.hasFocus() and self.resizeHandles.isEnabled():
			return self._focusedBoundingRect
		return super().boundingRect()

	def grandChildren(self) -> list['Panel']:
		if self._frozen:
			return [self]
		children = [i.grandChildren() for i in self.childPanels]
		# flatten children list
		children = [i for j in children for i in j]
		children.insert(0, self)
		return children

	def visibleArea(self, *exclude: 'Panel') -> QRectF:
		children = self.childPanels
		path = self.sceneShape()
		for child in children:
			if child.hasFocus() or child in exclude or not child.isVisible() or not child.isEnabled():
				continue
			path -= child.sceneShape()
		return path

	def setHighlighted(self, highlighted: bool):
		self._childIsMoving = highlighted

	# section itemChange

	def _handleParentChangeFromPositionChange(self, shape: QPainterPath, area: float):
		siblings = []
		areas = []
		collidingItems = [i for i in self.scene().items(shape) if
		                  i is not self and
		                  isinstance(i, Panel) and
		                  not self.isAncestorOf(i) and
		                  i.acceptsChildren and
		                  not i.onlyAddChildrenOnRelease and
		                  not i._frozen]

		for item in collidingItems:
			itemShape = shape.intersected(item.visibleArea())
			overlap = round(polygon_area(itemShape) / area, 5)
			if item.isUnderMouse():
				overlap *= 1.5
			if overlap:
				siblings.append(item)
				areas.append(overlap)

		collisions = [(item, area) for item, area in zip(siblings, areas) if item.acceptsChildren and area > item.collisionThreshold]
		collisions.sort(key=lambda x: (x[0].zValue(), x[1]), reverse=True)

		if collisions and any([i[1] for i in collisions]):
			p = self.parent
			newParent = collisions[0][0]
			if newParent is not p:
				p.setHighlighted(False)
				p.update()
				newParent.setHighlighted(True)
				self.setParentItem(newParent)
				newParent.update()

	def _handleKeepInFrame(self, area: float, value: QPoint | QPointF):
		intersection = self.parent.shape().intersected(self.shape().translated(*value.toTuple()))
		overlap = prod(intersection.boundingRect().size().toTuple()) / area
		if overlap >= 0.75:
			frame = self.parent.rect()
			maxX = frame.width() - min(self.rect().width(), frame.width())
			maxY = frame.height() - min(self.rect().height(), frame.height())

			x = min(max(value.x(), 0), maxX)
			y = min(max(value.y(), 0), maxY)
			value.setX(x)
			value.setY(y)

	def _handleItemSpecificPositionChange(self, value: QPoint | QPointF) -> Tuple[bool, QPoint | QPointF]:
		return False, value

	def _handlePositionChange(self, value: QPointF | QPoint) -> QPointF | QPoint:
		if isinstance(self, GeometryManaged):
			override, value, = self._geometryManagerPositionChange(value)
			if override:
				return value

		area = polygon_area(self.shape())
		diff = value - self.pos()

		rect = self.rect()
		rect.moveTo(value)

		value = self._handleEdgeSnapping(value, rect)

		translated = self.sceneShape().translated(*diff.toTuple())

		if self.startingParent is not self.parent:
			translated = self.parent.mapFromItem(self.startingParent, translated)

		self._handleParentChangeFromPositionChange(translated, area)

		# else:
		# 	collisions = [i for i in collisions if i[0] is not self.scene().base]
		# 	if collisions:
		#
		#
		# 		# 	# collisionItem = self.mapFromParent(collisions[0].shape()).boundingRect()
		# 		collisionItem = collisions[0][0].shape().boundingRect()
		# 		# if self.startingParent is not self.parent:
		#
		# 			# collisionItem = collisions[0][0].mapRectToScene(collisionItem)
		# 		# collisionItem = collisions[0][0].mapToScene(collisionItem).boundingRect()
		#
		#
		# 		# innerRect = QRectF(collisionItem)
		# 		panel = collisions.pop(0)
		# 		# n = 20
		# 		# innerRect.adjust(n, n, -n, -n)
		# 		# if innerRect.contains(value):
		# 		# 	# panel.resizeHandles.show()
		# 		# 	collisions = False
		# 		# 	self.setParentItem(panel)
		# 		# 	break
		#
		# 		x, y = value.x(), value.y()
		#
		# 		shape = shape.boundingRect()
		#
		# 		f = [abs(collisionItem.top() - shape.center().y()), abs(collisionItem.bottom() - shape.center().y()), abs(collisionItem.left() - shape.center().x()), abs(collisionItem.right() - shape.center().x())]
		# 		closestEdge = min(f)
		# 		if closestEdge == abs(collisionItem.top() - shape.center().y()):
		# 			y = collisionItem.top() - shape.height()
		# 			if y < 0:
		# 				y = collisionItem.bottom()
		# 		elif closestEdge == abs(collisionItem.bottom() - shape.center().y()):
		# 			y = collisionItem.bottom()
		# 			if y + shape.height() > self.parent.containingRect.height():
		# 				y = collisionItem.top() - shape.height()
		# 		elif closestEdge == abs(collisionItem.left() - shape.center().x()):
		# 			x = collisionItem.left() - shape.width()
		# 			if x < 0:
		# 				x = collisionItem.right()
		# 		elif closestEdge == abs(collisionItem.right() - shape.center().x()):
		# 			x = collisionItem.right()
		# 		value = QPointF(x, y)
		# else:
		#
		# 	self.indicator.colors = Qt.green
		# 	if self.parentItem() is not self.scene().base:
		# 		self.setParentItem(self.scene().base)

		if self.startingParent is not None and self.startingParent is not self.parent:
			destination = self.parent
			start = self.startingParent
			value = destination.mapFromItem(start, value)

		if self._keepInFrame:
			self._handleKeepInFrame(area, value)

		self._geometry.setPos(value)
		return value

	def _handleEdgeSnapping(self, value, rect):
		similarEdges = [item for sublist in [self.similarEdges(n, rect=rect) for n in self.neighbors] for item in sublist]
		for s in similarEdges:
			loc = s.value.location
			oLoc = s.otherValue.location
			snapValue = s.otherValue.pix
			if loc.isRight:
				rect.moveRight(snapValue)
			elif loc.isLeft:
				rect.moveLeft(snapValue)
			elif loc.isTop:
				rect.moveTop(snapValue)
			elif loc.isBottom:
				rect.moveBottom(snapValue)
		if similarEdges:
			value = rect.topLeft()
		return value

	def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
		if change == QGraphicsItem.ItemSceneHasChanged:
			clearCacheAttr(value, 'panels')

		elif change == QGraphicsItem.ItemPositionChange:
			if QApplication.mouseButtons() & Qt.LeftButton and self.isSelected() and not self.focusProxy():
				value = self._handlePositionChange(value)

		# section Child Added
		elif change == QGraphicsItem.ItemChildAddedChange:
			# Whenever a Panel is added
			if (resizedFunc := getattr(value, 'parentResized', None)) is not None:
				self.signals.resized.connect(resizedFunc)
				if isinstance(value, Panel):
					clearCacheAttr(self, 'childPanels')
					self.signals.childAdded.emit()

			# Whenever Handles are added
			elif isinstance(value, HandleGroup):
				clearCacheAttr(self, 'allHandles')
			elif isinstance(value, Handle):
				self.signals.resized.connect(value.updatePosition)

		# section Child Removed
		elif change == QGraphicsItem.ItemChildRemovedChange:
			# Removing Panel
			if (resizedFunc := getattr(value, 'parentResized', None)) is not None:
				disconnectSignal(self.signals.resized, resizedFunc)
				if isinstance(value, Panel):
					clearCacheAttr(self, 'childPanels')
					self.signals.childRemoved.emit()

			# Removing Handle
			elif isinstance(value, HandleGroup):
				clearCacheAttr(self, 'allHandles')
				disconnectSignal(self.signals.resized, value.updatePosition)
				disconnectSignal(value.signals.action, self.updateFromGeometry)
			elif isinstance(value, Handle):
				disconnectSignal(self.signals.resized, value.updatePosition)

		# section Parent Changed
		elif change == QGraphicsItem.ItemParentChange:
			clearCacheAttr(self, 'localGroup', 'parentLocalGroup')
			if value != self.parent and None not in (value, self.previousParent):
				if self.geometry.size.relative and value is not None:
					g = self.geometry.absoluteSize()/value.geometry.absoluteSize()
					self.geometry.setRelativeSize(g)
				self.previousParent = self.parent
			self.parent = value

		elif change == QGraphicsItem.ItemParentHasChanged:
			if hasattr(self.previousParent, 'childIsMoving'):
				self.previousParent.childIsMoving = False
			self.parent = value
			self.stackOnTop()

			if hasattr(value, 'childIsMoving') and QApplication.mouseButtons() & Qt.LeftButton:
				value.childIsMoving = True

			if value is not None:
				self.signals.parentChanged.emit()

		return super(Panel, self).itemChange(change, value)

	@property
	def parent(self) -> Union['Panel', 'LevityScene']:
		if (parent := getattr(self, '_parent', None)) is None:
			parent = self.parentItem() or self.scene()
			self._parent = parent
		return parent

	@parent.setter
	def parent(self, value: Union['Panel', 'LevityScene']):
		if getattr(self, '_parent', None) is not value:
			self._parent = value

	@property
	def apparentParent(self) -> 'Panel':
		p = self.parentItem()
		while p is not None and isinstance(p, NonInteractivePanel):
			p = p.parentItem()
		return p

	def updateFromGeometry(self):
		self.setRect(self.geometry.absoluteRect())
		self.setPos(self.geometry.absolutePosition().asQPointF())

	def setGeometry(self, rect: Optional[QRectF], position: Optional[QPointF]):
		if rect is not None:
			self.geometry.setAbsoluteRect(rect)
			if self.geometry.size.snapping or self.geometry.size.relative:
				rect = self.geometry.absoluteRect()
			self.setRect(rect)
		if position is not None:
			self.geometry.setAbsolutePosition(position)
			if self.geometry.position.snapping or self.geometry.position.relative:
				position = self.geometry.absolutePosition()
			self.setPos(position)

	@overload
	def setRect(self, pos: 'Position', size: 'Size'): ...

	@overload
	def setRect(self, args: tuple[Numeric, Numeric, Numeric, Numeric]): ...

	def setRect(self, rect: QRectF | QRect) -> bool:
		emit = self.rect().size() != rect.size()
		super(Panel, self).setRect(rect)
		if emit:
			clearCacheAttr(self, 'marginRect', '_focusedBoundingRect')
			self.signals.resized.emit(rect)
		return emit

	def updateRect(self, parentRect: QRectF = None):
		self.setRect(self.geometry.absoluteRect())

	def setMovable(self, value: bool = None):
		if value is None:
			value = not self.movable
		self.movable = value

	@StateProperty(default=True, allowNone=False)
	def movable(self) -> bool:
		return bool(self.flags() & QGraphicsItem.ItemIsMovable)

	@movable.setter
	def movable(self, value: bool):
		self.setFlag(QGraphicsItem.ItemIsMovable, boolFilter(value))

	@movable.condition
	def movable(self) -> bool:
		return not getattr(self.parent, 'frozen', False)

	@movable.condition
	def movable(self) -> bool:
		return not self.frozen or not self.locked

	def setResizable(self, value: bool = None):
		if value is None:
			value = not self.resizable
		self.resizable = value

	@StateProperty(default=True)
	def resizable(self) -> bool:
		return self.resizeHandles.isEnabled()

	@resizable.setter
	def resizable(self, value):
		self.resizeHandles.setEnabled(boolFilter(value))

	@resizable.condition
	def resizable(self) -> bool:
		return not getattr(self.parent, 'frozen', False)

	@resizable.condition
	def resizable(self) -> bool:
		return not self.frozen or not self.locked

	def setClipping(self, value: bool = None):
		if value is None:
			value = not self.clipping
		self.clipping = value

	@property
	def clipping(self) -> bool:
		return bool(self.flags() & QGraphicsItem.ItemClipsChildrenToShape)

	@clipping.setter
	def clipping(self, value: bool):
		self.setFlag(QGraphicsItem.ItemClipsChildrenToShape, boolFilter(value))

	def setKeepInFrame(self, value: bool = None):
		if value is None:
			value = not self._keepInFrame
		self._keepInFrame = value

	@property
	def keepInFrame(self) -> bool:
		return self._keepInFrame

	@keepInFrame.setter
	def keepInFrame(self, value: bool):
		self._keepInFrame = value
		self.updateFromGeometry()

	def sceneShape(self):
		# for panel in self.childPanels:
		# 	shape = shape.subtracted(panel.mappedShape())
		return self.mapToScene(self.shape())

	def sceneRect(self):
		return self.mapRectToScene(self.rect())

	def sceneShapePunched(self):
		return self.sceneShape() - self.childrenShape()

	def childrenShape(self):
		path = QPainterPath()
		for panel in self.childPanels:
			path += panel.sceneShape()
		return path

	def mappedShape(self) -> QPainterPath:
		return self.mapToParent(self.shape())

	def shouldShowGrid(self) -> bool:
		return any([self.isSelected(), *[panel.hasFocus() for panel in self.childPanels]]) and self.childPanels

	@property
	def isEmpty(self):
		return len([childPanel for childPanel in self.childPanels if not childPanel.isEmpty]) == 0

	# section paint
	def paint(self, painter, option, widget):
		# if debug:
		# 	pen = painter.pen()
		# 	brush = painter.brush()
		# 	painter.setPen(self.debugPen)
		# 	painter.setBrush(self.debugColor)
		# 	painter.drawRect(self.rect())
		# 	painter.setPen(pen)
		# 	painter.setBrush(brush)
		if self.isSelected() or self.isEmpty or self.childIsMoving:
			painter.setPen(selectionPen)
			painter.setBrush(Qt.NoBrush)
			painter.drawRect(self.rect())
			return

		super().paint(painter, option, widget)

	@cached_property
	def sharedFontSize(self):
		labels = [x for x in self.childPanels if hasattr(x, 'text')]
		if False:
			return sum([x.fontSize for x in labels])/len(labels)
		return min([x.fontSize for x in labels])

	@Slot(QPointF, QSizeF, QRectF, 'parentResized')
	def parentResized(self, arg: Union[QPointF, QSizeF, QRectF]):
		if isinstance(arg, (QRect, QRectF, QSize, QSizeF)):
			self.geometry.updateSurface(arg)

	@property
	def containingRect(self):
		return self.rect()

	@property
	def globalTransform(self):
		return self.scene().views()[0].viewportTransform()

	@property
	def pix(self) -> QPixmap:
		pix = QPixmap(self.containingRect.size().toSize())
		pix.fill(Qt.transparent)
		painter = QPainter(pix)
		pix.initPainter(painter)
		painter.setRenderHint(QPainter.Antialiasing)
		opt = QStyleOptionGraphicsItem()
		self.paint(painter, opt, None)
		for child in self.childItems():
			child.paint(painter, opt, None)
		return pix

	def recursivePaint(self, painter: QPainter):
		t = QTransform.fromTranslate(*self.scenePos().toPoint().toTuple())
		painter.setTransform(t)
		self.paint(painter, QStyleOptionGraphicsItem(), None)
		for child in self.childItems():
			if hasattr(child, 'collapse'):
				continue
			if hasattr(child, 'recursivePaint'):
				child.recursivePaint(painter)
			else:
				child.paint(painter, QStyleOptionGraphicsItem(), None)

	def height(self):
		return self.rect().height()

	def width(self):
		return self.rect().width()

	@StateProperty(default=False)
	def locked(self) -> bool:
		return self._locked

	@locked.setter
	def locked(self, value):
		if value != self._locked:
			self.setFlag(QGraphicsItem.ItemIsMovable, not value)
			self.setFlag(QGraphicsItem.ItemStopsClickFocusPropagation, not value)
			for handle in self.allHandles:
				if not value and self.isSelected():
					handle.setVisible(not value)
				handle.setEnabled(not value)
				handle.update()
		self._locked = value
		self.update()

	@locked.condition
	def locked(self) -> bool:
		return not getattr(self.parent, 'frozen', False)

	def setLocked(self, value: bool = None):
		if value is None:
			value = not self._locked
		self.locked = value

	@StateProperty(default=False)
	def frozen(self) -> bool:
		return self._frozen

	@frozen.setter
	def frozen(self, value: bool):
		self.freeze(value)

	def freeze(self, value: bool = None):
		if self._frozen == value:
			return
		if value is None:
			value = not self._frozen
		self._frozen = value
		for child in self.childPanels:
			child.setLocked(value)
		# self.setHandlesChildEvents(value)
		# self.setFiltersChildEvents(value)
		self.setFlag(QGraphicsItem.ItemStopsClickFocusPropagation, value)
		self.setFlag(QGraphicsItem.ItemStopsFocusHandling, value)
		# self.setHandlesChildEvents(value)
		self.setAcceptDrops(not value)

	@cached_property
	def childPanels(self) -> List['Panel']:
		items = [child for child in self.childItems() if isinstance(child, Panel)]
		items.sort(key=lambda x: (x.pos().y(), x.pos().x()))
		return items

	@property
	def hasChildren(self) -> bool:
		return len(self.items) > 0 and getattr(self, 'includeChildrenInState', True)

	def _save(self, path: Path = None, fileName: str = None):
		raise log.warning('Single panel save not implemented')

	def _saveAs(self):
		path = userConfig.userPath.joinpath('saves', 'panels')

		path = path.joinpath(self.__class__.__name__)
		dialog = QFileDialog(self.parentWidget(), 'Save Dashboard As...', str(path))
		dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
		dialog.setNameFilter("Dashboard Files (*.levity)")
		dialog.setViewMode(QFileDialog.ViewMode.Detail)
		if dialog.exec_():
			fileName = Path(dialog.selectedFiles()[0])
			path = fileName.parent
			fileName = dialog.selectedFiles()[0].split('/')[-1]
			self._save(path, fileName)

	def save(self):
		if self.filePath is not None:
			self._save(*self.filePath.asTuple)
		else:
			self._saveAs()

	def delete(self):
		for item in self.childItems():
			if hasattr(item, 'delete'):
				item.delete()
			else:
				item.setParentItem(None)
				self.scene().removeItem(item)
		if self.scene() is not None:
			self.scene().removeItem(self)

	def wheelEvent(self, event) -> None:
		if self.acceptsWheelEvents:
			event.accept()
		else:
			event.ignore()
		super(Panel, self).wheelEvent(event)

	def editMargins(self, toggle: bool = True):
		self.parent.clearFocus()
		self.parent.parent.clearFocus()

		self.marginHandles.scene().clearFocus()
		self.marginHandles.setEnabled(True)
		self.marginHandles.show()
		self.marginHandles.updatePosition(self.marginRect)
		self.marginHandles.setFocus()

	def clear(self):
		items = [child for child in self.childPanels]
		for item in items:
			self.scene().removeItem(item)

	def doFuncInThread(self, func, *args, **kwargs):
		self.thread = QThread()
		self.exec_thread = ExecThread()

		self.exec_thread.args = args
		self.exec_thread.kwargs = kwargs
		self.exec_thread.func = func
		self.exec_thread.moveToThread(self.thread)
		self.thread.started.connect(self.exec_thread.run)
		self.exec_thread.finished.connect(self.thread.quit)
		self.thread.start()


class NonInteractivePanel(Panel):

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.setFlag(self.ItemIsMovable, False)
		self.setFlag(self.ItemIsSelectable, False)
		self.setFlag(self.ItemIsFocusable, False)
		self.setAcceptedMouseButtons(Qt.NoButton)
		self.setAcceptDrops(False)
		self.setHandlesChildEvents(False)
		self.setFiltersChildEvents(False)
		self.setAcceptTouchEvents(False)
		self.setFlag(self.ItemHasNoContents)

	def mousePressEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		mouseEvent.ignore()
		return

	def mouseMoveEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		mouseEvent.ignore()
		return

	def mouseReleaseEvent(self, mouseEvent):
		mouseEvent.ignore()
		return


class PanelFromFile:

	def __new__(cls, parent: Panel, filePath: Path, position: QPointF = None):
		raise NotImplementedError


__all__ = ['Panel', 'NonInteractivePanel', 'PanelFromFile']

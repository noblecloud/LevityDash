from dataclasses import asdict, is_dataclass
from enum import Enum
from functools import lru_cache
from importlib import reload

from qasync import QApplication
from time import process_time
from types import SimpleNamespace

from PySide2.QtCore import QLineF, QObject, QPoint, QPointF, QRectF, QSize, QSizeF, Qt, QTimer, Signal, QEvent
from PySide2.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QTransform, QPixmap, QImage, QBrush
from PySide2.QtWidgets import QGraphicsScene, QGraphicsDropShadowEffect, QGraphicsSceneMouseEvent, QGraphicsPixmapItem, QGraphicsEffect, QGraphicsItem
from typing import Callable, Union, List, ClassVar, Optional
from yaml import SafeDumper, Dumper

from LevityDash.lib.utils import ClosestMatchEnumMeta, getItemsWithType, utilLog
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.utils import Unset, levenshtein, Position, Size

from LevityDash.lib.ui.Geometry import Geometry
from LevityDash.lib.stateful import Stateful
from LevityDash.lib.log import debug
from LevityDash.lib.ui.colors import randomColor


def objectRepresentor(dumper, obj):
	if hasattr(obj, 'representer'):
		return obj.representer(dumper, obj)
	if hasattr(obj, '__serialize__'):
		return obj.__serialize__(dumper, obj)
	if hasattr(obj, 'toDict'):
		return dumper.represent_dict(obj.toDict())
	elif hasattr(obj, 'toJSON'):
		return dumper.represent_dict(obj.toJSON())
	elif hasattr(obj, 'state'):
		return dumper.represent_dict(obj.state.items())
	elif isinstance(obj, Enum):
		return dumper.represent_scalar(u'tag:yaml.org,2002:str', obj.name)
	if is_dataclass(obj):
		return dumper.represent_dict(asdict(obj))
	return dumper.represent_scalar(u'tag:yaml.org,2002:str', str(obj))


itemCount = 0
itemSkip = 3


def loadGraphs(parent, items, parentItems, **kwargs):
	global itemCount

	from LevityDash.lib.ui.frontends.PySide.Modules import GraphPanel
	existing = [i for i in parentItems if isinstance(i, GraphPanel)]
	newItems = []
	while items:
		item = items.pop(0)
		if not GraphPanel.validate(item):
			utilLog.error('Invalid state for graph:', item)
		ns = SimpleNamespace(**item)

		match existing:
			case [graph]:
				existing.remove(graph)
				graph.state = item
			case [GraphPanel(geometry=ns.geometry) as graph, *existing]:
				existing.remove(graph)
				graph.state = item
			case []:
				item = GraphPanel(parent=parent, **item, cacheInitArgs=True)
				newItems.append(item)
			case [*_]:
				graph = sorted(existing, key=lambda g: (g.geometry.scoreSimilarity(ns.geometry), abs(len(ns.figures) - len(g.figures))))[0]
				existing.remove(graph)

		itemCount += 1
		if itemCount%itemSkip == 0:
			QApplication.processEvents()
	for i in existing:
		i.scene().removeItem(i)
	return newItems


def loadRealtime(parent, items, parentItems, **kwargs):
	global itemCount

	from LevityDash.lib.ui.frontends.PySide.Modules import Realtime
	existing: [Realtime] = [i for i in parentItems if isinstance(i, Realtime)]
	newItems = []
	pop = getattr(type(items), 'popitem', None) or getattr(type(items), 'pop', Unset)
	while items:
		item = pop(items)
		# if not Realtime.validate(item):
		# 	utilLog.error('Invalid state for existingItem:', item)
		# ns = SimpleNamespace(**item)
		if not Realtime.validate(item):
			utilLog.error('Invalid state for existingItem:', item)
		item['key'] = CategoryItem(item['key'])
		ns = SimpleNamespace(**item)
		match existing:
			case []:
				item = Realtime(parent=parent, **item, cacheInitArgs=True)
				newItems.append(item)
			case [existingItem]:
				existing.remove(existingItem)
				existingItem.state = item
			case [Realtime(key=ns.key, geometry=ns.geometry) as existingItem, *_]:
				existing.remove(existingItem)
				existingItem.state = item
			case [*_]:
				existingItem = sorted(existing, key=lambda g: (g.geometry.scoreSimilarity(ns.geometry), levenshtein(str(ns.key), str(g.key))))[0]
				existing.remove(existingItem)
				existingItem.state = item
			case _:
				print('fail')
		itemCount += 1
		if itemCount%itemSkip == 0:
			QApplication.processEvents()
	for i in existing:
		i.scene().removeItem(i)
	return newItems


def loadClock(parent, items, parentItems, **kwargs):
	global itemCount

	from LevityDash.lib.ui.frontends.PySide.Modules import Clock
	existing = [i for i in parentItems if isinstance(i, Clock)]
	newItems = []
	while items:
		item = items.pop(0)
		if not Clock.validate(item):
			utilLog.error('Invalid state for clock:', item)
		ns = SimpleNamespace(**item)
		match existing:
			case [clock]:
				clock.state = item
				existing.remove(clock)
			case [Clock(geometry=ns.geometry) as clock, *existing]:
				clock.state = item
				existing.remove(clock)
			case []:
				item = Clock(parent=parent, **item)
				newItems.append(item)
			case [*_]:
				clock = sorted(existing, key=lambda g: (g.geometry.scoreSimilarity(ns.geometry), levenshtein(ns.format, g.format)))[0]
				existing.remove(clock)
		itemCount += 1
		if itemCount%itemSkip == 0:
			QApplication.processEvents()
	for i in existing:
		i.scene().removeItem(i)
	return newItems


def loadPanels(parent, items, parentItems, **kwargs) -> List[Stateful]:
	global itemCount

	from LevityDash.lib.ui.frontends.PySide.Modules import Panel
	existing = [i for i in parentItems if type(i) is Panel]
	newItems = []
	while items:
		item = items.pop(0)
		if not Panel.validate(item):
			utilLog.error('Invalid state for panel:', item)
		ns = SimpleNamespace(**item)
		match existing:
			case [panel]:
				existing.remove(panel)
				panel.state = item
			case [Panel(geometry=ns.geometry) as panel, *_]:
				existing.remove(panel)
				panel.state = item
			case []:
				item = Panel(parent=parent, **item, cacheInitArgs=True)
				newItems.append(item)
			case [*_]:
				panel = sorted(existing, key=lambda g: g.geometry.scoreSimilarity(ns.geometry))[0]
				existing.remove(panel)
		itemCount += 1
		if itemCount%itemSkip == 0:
			QApplication.processEvents()
	for i in existing:
		i.scene().removeItem(i)

	return newItems


def loadLabels(parent, items, parentItems, **kwargs):
	global itemCount

	from LevityDash.lib.ui.frontends.PySide.Modules import EditableLabel
	parentItems = parentItems or getattr(parent, 'items', [])
	existing = [i for i in parentItems if isinstance(i, EditableLabel)]
	newItems = []
	while items:
		item = items.pop(0)
		if not EditableLabel.validate(item):
			utilLog.error('Invalid state for label:', item)
			continue
		ns = SimpleNamespace(**item)
		match existing:
			case [label]:
				existing.remove(label)
				label.state = item
			case [EditableLabel(text=ns.text, geometry=ns.geometry) as label, *_]:
				existing.remove(label)
				label.state = item
			case [EditableLabel(geometry=ns.geometry) as label, *_]:
				existing.remove(label)
				label.state = item
			case [EditableLabel(text=ns.text) as label, *_]:
				existing.remove(label)
				label.state = item
			case []:
				item = EditableLabel(parent=parent, **item)
				newItems.append(item)
			case [*_]:
				label = sorted(existing, key=lambda g: (g.geometry.scoreSimilarity(ns.geometry)))[0]
				existing.remove(label)
		itemCount += 1
		if itemCount%itemSkip == 0:
			QApplication.processEvents()
	for i in existing:
		i.scene().removeItem(i)
	return newItems


def loadMoon(parent, items, parentItems, **kwargs):
	global itemCount

	from LevityDash.lib.ui.frontends.PySide.Modules import Moon
	existing = [i for i in parentItems if isinstance(i, Moon)]
	newItems = []
	while items:
		item = items.pop(0)
		ns = SimpleNamespace(**item)
		match existing:
			case [moon]:
				existing.remove(moon)
				moon.state = item
			case [Moon(geometry=ns.geometry) as moon, *_]:
				existing.remove(moon)
				moon.state = item
			case []:
				item = Moon(parent=parent, **item)
				newItems.append(item)
			case [*_]:
				moon = sorted(existing, key=lambda g: g.geometry.scoreSimilarity(ns.geometry))[0]
				existing.remove(moon)
				moon.state = item
		itemCount += 1
		if itemCount%itemSkip == 0:
			QApplication.processEvents()
	for i in existing:
		i.scene().removeItem(i)
	return newItems


def itemLoader(parent, unsortedItems: list[dict], existing: list = None, **kwargs):
	if not unsortedItems:
		return
	if existing is None:
		existing = []

	sortedItems = dict()

	for i in unsortedItems:
		_type = i.get('type', Unset)
		if _type is Unset:
			if 'key' in i:
				_type = 'realtime.text'
			else:
				_type = 'group'
			i['type'] = _type
		_type = _type.split('.')[0]
		if _type not in sortedItems:
			sortedItems[_type] = []
		sortedItems[_type].append(i)

	newItems = []

	for _type, group in sortedItems.items():
		match _type:
			case 'graph':
				items = loadGraphs(parent, group, existing, **kwargs)
			case 'realtime':
				items = loadRealtime(parent, group, existing, **kwargs)
			case 'clock':
				items = loadClock(parent, group, existing, **kwargs)
			case 'group':
				items = loadPanels(parent, group, existing, **kwargs)
			case 'text' | 'label':
				items = loadLabels(parent, group, existing, **kwargs)
			case 'moon':
				items = loadMoon(parent, group, existing, **kwargs)
			case _:
				items = []
		newItems.extend(items)

	return newItems


def hasState(obj):
	return 'state' in dir(obj) and hasattr(obj, 'savable') and obj.savable


def findSizePosition(*args, **kwargs):
	if 'size' in kwargs and kwargs['size'] is not None:
		pass
	elif 'width' in kwargs and 'height' in kwargs:
		width, height = kwargs['width'], kwargs['height']
		if width is not None and height is not None:
			kwargs['size'] = QSizeF(kwargs.pop('width'), kwargs.pop('height'))
	else:
		kwargs['size'] = None
	if 'position' in kwargs and kwargs['position'] is not None:
		pass
	elif 'x' in kwargs and 'y' in kwargs:
		x, y = kwargs['x'], kwargs['y']
		if x is not None and y is not None:
			kwargs['position'] = QPointF(kwargs.pop('x'), kwargs.pop('y'))
	else:
		kwargs['position'] = None

	position = getItemsWithType(args, kwargs, Position)
	size = getItemsWithType(args, kwargs, QSize, QSizeF)
	geometry = getItemsWithType(args, kwargs, Geometry)

	if kwargs['size'] is None and size:
		kwargs['size'] = size.pop(0)
	if kwargs['position'] is None and position:
		if len(position) == 2:
			kwargs['position'] = position
	if kwargs.get('geometry', None) is None and geometry:
		kwargs['geometry'] = geometry.pop(0)
	if kwargs['size'] is None:
		kwargs.pop('size')
	if kwargs['position'] is None:
		kwargs.pop('position')
	if 'geometry' in kwargs and kwargs['geometry'] is None:
		kwargs.pop('geometry')
	return kwargs


def modifyTransformValues(
	transform: QTransform,
	xTranslate: float = None,
	yTranslate: float = None,
	xScale: float = None,
	yScale: float = None,
	xRotate: float = None,
	yRotate: float = None
):
	"""Modifies the values of a QTransform inplace and also returns the modified transformation.
	All values are optional and if not specified will not be modified.

	Note: This function does not increase or decrease the transform parameters, it sets them.

	Parameters
	----------
		transform: QTransform
			The transform to modify
		xTranslate: float
			The x translation value
		yTranslate: float
			The y translation value
		xScale: float
			The x scale value
		yScale: float
			The y scale value
		xRotate: float
			The x rotation value
		yRotate: float
			The y rotation value

	Returns
	-------
		QTransform
			The modified transformation
	"""

	if xTranslate is None:
		xTranslate = transform.dx()
	if yTranslate is None:
		yTranslate = transform.dy()
	if xScale is None:
		xScale = transform.m11()
	if yScale is None:
		yScale = transform.m22()
	if xRotate is None:
		xRotate = transform.m12()
	if yRotate is None:
		yRotate = transform.m21()
	transform.setMatrix(xScale, xRotate, 0, yRotate, yScale, 0, xTranslate, yTranslate, 1)
	return transform


def estimateTextFontSize(font: QFont, string: str, maxWidth: Union[float, int], maxHeight: Union[float, int], resize: bool = True) -> tuple[QRectF, QFont]:
	font = QFont(font)
	p = QPainterPath()
	p.addText(QtCore.QPoint(0, 0), font, string)
	rect = p.boundingRect()
	rect = estimateTextSize(font, string)
	while resize and (rect.width() > maxWidth or rect.width() > maxHeight):
		size = font.pixelSize()
		if font.pixelSize() < 10:
			break
		font.setPixelSize(size - 3)
		rect = estimateTextSize(font, string)
	return rect, font


def estimateTextSize(font: QFont, string: str) -> QRectF:
	p = QPainterPath()
	p.addText(QPoint(0, 0), font, string)
	return p.boundingRect()


class DisplayType(str, Enum, metaclass=ClosestMatchEnumMeta):
	Text = 'text'
	Gauge = 'gauge'
	Graph = 'graph'
	LinePlot = 'plot'
	BarGraph = 'bargraph'
	WindVein = 'windVein'
	Custom = 'custom'


class GraphicsItemSignals(QObject):
	"""
	A QObject that emits signals for the GraphicsItem.
	"""
	#: Signal emitted when the item is preferredSource.
	selected = Signal()
	#: Signal emitted when the item is deselected.
	deselected = Signal()
	#: Signal emitted when the item is resized.
	resized = Signal(QRectF)
	#: Signal emitted when the item is deleted.
	deleted = Signal()
	#: Signal emitted when a child item is added.
	childAdded = Signal()
	#: Signal emitted when a child item is removed.
	childRemoved = Signal()
	#: Signal emitted when the visibility changes.
	visibility = Signal(bool)
	#: Signal emitted when the parent is changed.
	parentChanged = Signal()
	#: Signal emitted when the item is transformed.
	transformChanged = Signal(QTransform)
	#: Signal emitted when the item is clicked.
	clicked = Signal(QGraphicsSceneMouseEvent)


class mouseTimer(QTimer):
	_startPosition: QPointF
	_position: QPointF
	_timeout: Callable

	def __init__(self, timeout: Callable, interval: int = 500, singleShot: bool = True):
		self._timeout = timeout
		super(mouseTimer, self).__init__(interval=interval, timeout=self._T, singleShot=singleShot)

	def _T(self):
		self._timeout()

	def start(self, position: QPointF, *args):
		self._startPosition = position
		self._position = position
		super().start(*args)

	def updatePosition(self, position: QPointF):
		self._position = position

	def stop(self) -> None:
		self._startPosition = None
		self._position = None
		super().stop()

	@property
	def position(self):
		return self._position


class mouseHoldTimer(mouseTimer):

	def __init__(self, *args, holdArea: QRectF = None, **kwargs):
		if holdArea is None:
			holdArea = QRectF(0, 0, 10, 10)
		self._holdArea = holdArea
		super(mouseHoldTimer, self).__init__(*args, **kwargs)

	def start(self, position: QPointF):
		super(mouseHoldTimer, self).start(position)
		self._holdArea.moveCenter(self._startPosition)

	def updatePosition(self, position: QPointF):
		super(mouseHoldTimer, self).updatePosition(position)
		if not self._holdArea.contains(self._position):
			self.stop()

	def _T(self):
		if self._holdArea.contains(self._startPosition):
			super(mouseHoldTimer, self)._T()


def addCrosshair(painter: QPainter, color: QColor = Qt.red, size: int | float = 2.5, weight=1, pos: QPointF = QPointF(0, 0)):
	"""
	Decorator that adds a crosshair paint function
	"""
	pen = QPen(color, weight)
	# pen.setCosmetic(Fa)
	painter.setPen(pen)
	verticalLine = QLineF(-size, 0, size, 0)
	verticalLine.translate(pos)
	horizontalLine = QLineF(0, -size, 0, size)
	horizontalLine.translate(pos)
	painter.drawLine(verticalLine)
	painter.drawLine(horizontalLine)


def addRect(painter: QPainter, rect: QRectF, color: QColor = Qt.red, fill: QColor = Qt.transparent, offset: float | int = 0):
	pen = QPen(color or Qt.white)
	brush = QBrush(fill or Qt.transparent)
	pen.setCosmetic(True)
	painter.setPen(pen)
	painter.setBrush(brush)
	painter.drawRect(rect.adjusted(-offset, -offset, offset, offset))

def addCrosshairDecorator(func: Callable, **dkwargs) -> Callable:
	"""
	A decorator that adds a crosshair to the item.
	"""

	def wrapper(self, *args, **kwargs):
		func(self, *args, **kwargs)
		painter: QPainter = args[0] or kwargs.get('painter')
		addCrosshair(painter, **dkwargs)

	return wrapper


from PySide2.QtGui import QPalette

colorPalette = QPalette()
colorPalette.setColor(QPalette.Window, QColor(0, 0, 0))
colorPalette.setColor(QPalette.Base, QColor(0, 0, 0))
colorPalette.setColor(QPalette.Background, QColor(0, 0, 0))

colorPalette.setColor(QPalette.WindowText, QColor(255, 255, 255))
colorPalette.setColor(QPalette.ButtonText, QColor(255, 255, 255))

selectionPen = QPen(QColor(colorPalette.windowText().color()), 1)
selectionPen.setDashPattern([5, 5])
debugPen = QPen(colorPalette.windowText().color(), 1)
debugPen.setCosmetic(True)

gridColor = colorPalette.windowText().color()
gridColor.setAlpha(128)
gridPen = QPen(gridColor, 1)
gridPen.setDashPattern([4, 4])

SafeDumper.add_multi_representer(object, objectRepresentor)
Dumper.add_multi_representer(object, objectRepresentor)

__all__ = ('DisplayType', 'GraphicsItemSignals', 'addCrosshair', 'estimateTextFontSize', 'estimateTextSize',
'findSizePosition', 'getItemsWithType', 'hasState',
'itemLoader', 'modifyTransformValues', 'mouseHoldTimer', 'mouseTimer', 'objectRepresentor',
'colorPalette', 'selectionPen', 'debugPen', 'gridColor', 'gridPen')

useCache = False


class DebugSwitch(type(QObject)):
	def __new__(cls, name, bases, attrs):
		if '_debug_paint' in attrs and debug:
			attrs['_debug_paint_color'] = QColor(randomColor())
			attrs['_normal_paint'] = attrs.get('paint', None) or next(base.paint for base in bases if hasattr(base, 'paint'))
			attrs['paint'] = attrs['_debug_paint']
		return super().__new__(cls, name, bases, attrs)


def DebugPaint(cls):
	if debug and not utilLog.VERBOSITY - 5:
		e = None
		try:
			cls._normal_paint = cls.paint
		except AttributeError as e:
			print(f'{cls} has no paint function')
		try:
			cls.paint = cls._debug_paint
			cls._debug_paint_color = QColor(randomColor())
		except AttributeError as e:
			print(f'{cls} has no _debug_paint function')
		if e:
			raise e
	return cls


class EffectPainter(QPainter):

	def __init__(self, *args, **kwargs):
		super(EffectPainter, self).__init__(*args, **kwargs)
		self.setRenderHint(QPainter.Antialiasing)
		self.setRenderHint(QPainter.SmoothPixmapTransform)
		self.setRenderHint(QPainter.TextAntialiasing)


def getAllParents(item: QGraphicsItem, filter: Callable[[QGraphicsItem], bool] | None = None) -> List[QGraphicsItem]:
	parents = []
	while item is not None:
		if filter is None or filter(item):
			parents.append(item)
		item = item.parentItem()
	return parents


def itemClipsChildren(item: QGraphicsItem) -> bool:
	return bool(item.flags() & QGraphicsItem.ItemClipsChildrenToShape)


class SoftShadow(QGraphicsDropShadowEffect):

	def __init__(self, owner=None, *args, **kwargs):
		super(SoftShadow, self).__init__(*args, **kwargs)
		self.owner = owner
		self.setOffset(0.0)
		if hasattr(owner, 'text'):
			self.setBlurRadius(20)
		else:
			self.setBlurRadius(60)
		self.setColor(Qt.black)


# def sourceChanged(self, flags: PySide2.QtWidgets.QGraphicsEffect.ChangeFlags) -> None:
# 	print(int(PySide2.QtWidgets.QGraphicsEffect.SourceInvalidated & flags))
# 	super().sourceChanged(flags)

# def event(self, event: QEvent) -> bool:
# 	super(SoftShadow, self).event(event)

# def update(self):
# 	if self.__owner:
# 		return
# 	super(SoftShadow, self).update()


class CachedSoftShadow(SoftShadow):
	transformAmount: ClassVar[int] = 0
	__parent__ = SoftShadow
	owner: QGraphicsPixmapItem

	def __new__(cls, *args, **kwargs):
		if not kwargs.get('useCache', useCache):
			return super(SoftShadow, cls).__new__(cls, *args, **kwargs)
		return QGraphicsDropShadowEffect.__new__(CachedSoftShadow, *args, **kwargs)

	def __init__(self, owner=None, *args, **kwargs):
		self.cache = None
		self.owner = owner
		super(CachedSoftShadow, self).__init__(owner, *args, **kwargs)

	def sourcePixmap(self, system: Qt.CoordinateSystem = ..., offset: Optional[QPoint] = ..., mode: QGraphicsDropShadowEffect.PixmapPadMode = ...) -> QPixmap:
		system = Qt.CoordinateSystem.LogicalCoordinates
		mode = QGraphicsDropShadowEffect.NoPad
		return super(CachedSoftShadow, self).sourcePixmap(system=system, mode=mode)

	# 	dynamic.sourcePixmap(self, system, offset, mode)
	#

	# def drawSource(self, painter: QPainter) -> None:
	# 	super(CachedSoftShadow, self).drawSource(painter)

	# def draw(self, painter):
	# 	try:
	# 		# painter.save()
	# 		# painter.resetTransform()
	# 		reload(dynamic)
	# 		# super(CachedSoftShadow, self).draw(painter)
	# 		# 		# rect = self.boundingRectFor(self.__owner.figure.boundingRect()).toRect()
	# 		# 		ownerRect = self.owner.boundingRect()
	# 		dynamic.draw(self, self.owner, painter)
	# 		# painter.restore()
	# 	except Exception as e:
	# 		pass

	#
	# 			# painter.resetTransform()
	# 			# pos = painter.transform().dx(), painter.transform().dy()
	# 			# painter.setTransform(QTransform.fromTranslate(*pos))
	# 			# rect = self.cache.rect()
	# 			# rect = painter.transform().inverted()[0].mapRect(rect)
	# 			# painter.setTransform(QTransform.fromScale(t.m11(), t.m22()))
	# 			# string = f'x: {t.dx():.5g}, y: {t.dy():.5g}, scale: {t.m11():.5g}, {t.m22():.5g}'
	# 			# painter.translate(-t.dx()/tc.m11()*painter.transform().m11() + 30, 0)
	# 			# rect = painter.worldTransform().inverted()[0].mapRect(rect)
	#
	# 			# painter.translate(-self.__owner.figure.sceneBoundingRect().x(), 0)
	# 			dynamic.paintFromCacheFunc(self, ownerRect, self.__owner, painter)
	# 		else:
	# 			# if qApp.mouseButtons():
	# 			# 	self.drawSource(painter)
	# 			# 	return
	# 			super(SoftShadow, self).draw(painter)
	# 	except Exception as e:
	# 		split = e.args[0]
	# 		message = f'{process_time():>7.5g}s: {e.__class__.__name__}: \nr{split}'
	# 		print(message)
	# 		return

	def invalidate(self):
		self.cache = None
		self.update()
		self.owner.update()

# def boundingRect(self) -> QRectF:
# 	return dynamic.boundingRect(self)

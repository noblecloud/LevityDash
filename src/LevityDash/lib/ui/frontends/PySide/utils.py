from dataclasses import asdict, is_dataclass
from enum import Enum
from PySide2.QtCore import QLineF, QObject, QPoint, QPointF, QRectF, QSize, QSizeF, Qt, QTimer, Signal
from PySide2.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QTransform
from PySide2.QtWidgets import QGraphicsScene
from typing import Callable, Union
from yaml import SafeDumper

from LevityDash.lib.utils import ClosestMatchEnumMeta, getItemsWithType


def itemLoader(parent, item: dict):
	from LevityDash.lib.ui.frontends.PySide.Modules import Realtime, Clock, Panel, GraphPanel, EditableLabel, Moon
	item['parent'] = parent
	itemType = item.pop('type', None)
	if itemType is None:
		if 'key' in item:
			itemType = 'realtime.text'
		else:
			itemType = 'panel'
	if itemType.startswith('realtime'):
		if '.' in itemType:
			item['displayType'] = itemType.split('.')[1]
		else:
			item['displayType'] = 'numeric'
		if Realtime.validate(item):
			return Realtime(**item)
	elif itemType == 'clock':
		if Clock.validate(item):
			return Clock(**item)
	elif itemType in ('panel', 'group'):
		if Panel.validate(item):
			return Panel(**item)
	elif itemType == 'graph':
		if GraphPanel.validate(item):
			return GraphPanel(**item)
	elif itemType in ('text', 'editablelabel'):
		if EditableLabel.validate(item):
			return EditableLabel(**item)
	elif itemType == 'moon':
		if Moon.validate(item):
			return Moon(**item)
	return None


def objectRepresentor(dumper, obj):
	if hasattr(obj, '__serialize__'):
		return obj.__serialize__(dumper, obj)
	if hasattr(obj, 'representer'):
		return obj.representer(dumper, obj)
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


def hasState(obj):
	return hasattr(obj, 'state') and hasattr(obj, 'savable') and obj.savable


def findScene(*args, **kwargs):
	if 'scene' in kwargs and isinstance(kwargs['scene'], QGraphicsScene):
		return kwargs
	parent = kwargs.get('parent', None)
	if parent is not None:
		if hasattr(parent, 'scene'):
			kwargs['scene'] = parent.scene()
			return kwargs
		elif isinstance(parent, QGraphicsScene):
			kwargs['scene'] = parent
			return kwargs
	args = getItemsWithType(args, kwargs, QGraphicsScene)
	if args:
		kwargs['scene'] = args.pop(0)
	return kwargs


def findSizePosition(*args, **kwargs):
	from LevityDash.lib.utils.geometry import Position, Size
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
	from LevityDash.lib.Geometry import Geometry
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


def findGrid(*args, **kwargs):
	from LevityDash.lib.Grid import Grid
	args = {arg.grid if hasattr(arg, 'grid') else arg for arg in args if isinstance(arg, Grid) or hasattr(arg, 'grid')}
	kwargsSet = {arg.grid if hasattr(arg, 'grid') else arg for arg in kwargs.values() if isinstance(arg, Grid) or hasattr(arg, 'grid')}
	args = list(args.union(kwargsSet))

	assigned = [grid for grid in args if grid.surface is not None]
	unassigned = [grid for grid in args if grid.surface is None]
	if 'grid' not in kwargs:
		if assigned:
			kwargs['grid'] = assigned.pop(0)
		elif unassigned:
			kwargs['grid'] = unassigned.pop(0)
		else:
			kwargs['grid'] = None
	if unassigned:
		if 'subGrid' not in kwargs:
			kwargs['subGrid'] = unassigned.pop(0)
		else:
			kwargs['subGrid'] = None
	return kwargs


def findGridItem(*args, **kwargs):
	from LevityDash.lib.Grid import GridItem
	if 'gridItem' in kwargs:
		return kwargs
	args = {arg.gridItem if hasattr(arg, 'gridItem') else arg for arg in args if isinstance(arg, GridItem) or hasattr(arg, 'gridItem')}
	kwargsSet = {arg.gridItem if hasattr(arg, 'gridItem') else arg for arg in kwargs.values() if isinstance(arg, GridItem) or hasattr(arg, 'gridItem')}
	args = list(args.union(kwargsSet))

	if args:
		kwargs['gridItem'] = args.pop(0)
	return kwargs


def modifyTransformValues(transform: QTransform, xTranslate: float = None, yTranslate: float = None, xScale: float = None, yScale: float = None, xRotate: float = None, yRotate: float = None):
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


def addBoundingRectDecorator(func: Callable, color: QColor = None, width: float = 1) -> Callable:
	"""
	A decorator that adds a bounding box to the item.
	"""

	def wrapper(self, *args, **kwargs):
		func(self, *args, **kwargs)
		painter: QPainter = args[0] or kwargs.get('painter')
		pen = QPen(color or Qt.white, width)
		pen.setCosmetic(True)
		painter.setPen(pen)
		painter.setBrush(Qt.NoBrush)
		painter.drawRect(self.boundingRect())

	return wrapper


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

__all__ = ('DisplayType', 'GraphicsItemSignals', 'addCrosshair', 'estimateTextFontSize', 'estimateTextSize',
'findGrid', 'findGridItem', 'findScene', 'findSizePosition', 'getItemsWithType', 'hasState',
'itemLoader', 'modifyTransformValues', 'mouseHoldTimer', 'mouseTimer', 'objectRepresentor',
'colorPalette', 'selectionPen', 'debugPen', 'gridColor', 'gridPen')

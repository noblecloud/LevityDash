import asyncio
from datetime import timedelta
from functools import cached_property

from json import dumps
from PySide2.QtCore import QByteArray, QMimeData, Qt, QTimer, Slot
from PySide2.QtGui import QDrag, QFocusEvent, QFont, QPainter, QPixmap, QTransform
from PySide2.QtWidgets import QGraphicsItem, QGraphicsSceneMouseEvent, QStyleOptionGraphicsItem
from typing import Union
from WeatherUnits.time.time import Second

from LevityDash.lib.Geometry.Grid import Grid
from LevityDash.lib.ui.frontends.PySide.Modules.Label import NonInteractiveLabel as Label, TitleLabel

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.dispatcher import MonitoredKey, MultiSourceContainer, PlaceholderSignal, ValueDirectory
from LevityDash.lib.ui.fonts import weatherGlyph
from LevityDash.lib.ui.frontends.PySide.utils import DisplayType, mouseHoldTimer
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import TextHelper
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Resize import MeasurementUnitSplitter, ResizeHandle, TitleValueSplitter
from LevityDash.lib.ui.frontends.PySide.Modules.Menus import RealtimeContextMenu
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.utils.geometry import Alignment, AlignmentFlag, DisplayPosition
from LevityDash.lib.utils.shared import clamp, disconnectSignal, Now, TitleCamelCase
from LevityDash.lib.log import LevityGUILog as guiLog
from LevityDash.lib.utils.data import JsonEncoder

log = guiLog.getChild(__name__)

displayDefault = {'displayType': DisplayType.Text, 'geometry': {'absolute': False, 'position': {'x': 0, 'y': 0.2}, 'size': {'width': 1.0, 'height': 0.8}}}


def buildDisplay(parent, displayType: Union[str, DisplayType], kwargs: dict = {}):
	if len(kwargs) == 0:
		kwargs = displayDefault
	if isinstance(displayType, str):
		displayType = DisplayType(displayType)
	if isinstance(kwargs, str):
		kwargs = {}
	if displayType == DisplayType.Text:
		return DisplayLabel(parent=parent, **kwargs)
	if displayType == DisplayType.Gauge:
		return DisplayGauge(parent=parent, **kwargs)


class Realtime(Panel):
	_includeChildrenInState = False

	def __init__(self, parent: Panel, **kwargs):
		super(Realtime, self).__init__(parent=parent, **kwargs)
		self.buildTitle(kwargs.get('title', {}))
		self.geometry.updateSurface()
		self._valueLink = None
		self._placeholder = None
		self._key = None
		self.display = buildDisplay(self, kwargs.get('displayType', 'text'), kwargs.get('display', {}))
		if 'value' in kwargs:
			value = kwargs.pop('value')
			if isinstance(value, MultiSourceContainer):
				self.valueLink = value
			else:
				self.value = value
		else:
			self.key = kwargs.get([k for k in ['key', 'valueLink', 'value', 'placeholder'] if k in kwargs].pop())
		self.display.setFlag(self.display.ItemIsSelectable, False)

		self.contentStaleTimer = QTimer()

		self.setAcceptHoverEvents(True)
		self.setAcceptDrops(True)
		if isinstance(kwargs.get('title', None), bool):
			kwargs['title'] = {'visible': kwargs['title']}
		self.splitter = TitleValueSplitter(surface=self, title=self.title, value=self.display, **kwargs.get('title', {}))
		self.splitter.hide()
		self.setFlag(self.ItemIsSelectable, True)
		self.title.setFlag(self.display.ItemIsSelectable, False)

		self.display: DisplayLabel
		self.display.valueTextBox.marginHandles.surfaceProxy = self
		self.display.unitTextBox.marginHandles.surfaceProxy = self
		self.display.unitTextBox.resizeHandles.surfaceProxy = self
		self.timeOffsetLabel.setEnabled(False)

	def __repr__(self):
		return f'<Realtime: {self.key.name}>'

	def buildTitle(self, kwargs):
		# if isinstance(kwargs, bool):
		# 	kwargs = {'visible': kwargs}
		self.title = TitleLabel(self)

	def hideTitle(self):
		self.splitter.hideTitle()

	def showTitle(self):
		self.splitter.showTitle()

	def toggleTitle(self):
		self.splitter.toggleTitle()

	def dragEnterEvent(self, event):
		event.accept()

	def dropEvent(self, event):
		if event.mimeData().hasFormat('text/plain'):
			self.key = event.mimeData().text()
			event.accept()

	@cached_property
	def grid(self) -> None:
		return Grid(self, rows=12, columns=12, static=True)

	@cached_property
	def contextMenu(self):
		return RealtimeContextMenu(self)

	@cached_property
	def timeOffsetLabel(self):
		return TimeOffsetLabel(self)

	@property
	def key(self):
		return self._key

	@key.setter
	def key(self, value):
		if isinstance(value, str):
			value = CategoryItem(value)
		self._key = value
		value = ValueDirectory.request(self, value)
		if isinstance(value, PlaceholderSignal):
			self.placeholder = value
			self.valueLink = None
		elif isinstance(value, MultiSourceContainer):
			self.valueLink = value
			self.placeholder = None

	@property
	def valueLink(self) -> 'MultiSourceContainer':
		return self._valueLink

	@valueLink.setter
	def valueLink(self, value):
		if self._valueLink is not None and value != self._valueLink:
			self._valueLink.valueChanged.disconnect(self.updateSlot)
		elif self._valueLink is None and value is not None:
			if isinstance(value, MultiSourceContainer):
				self._key = value.key
				value = value.value
			self._valueLink = value

			self._valueLink.source.publisher.connectChannel(self.key, self.updateSlot)
			if value.metadata['type'] == 'icon' and value.metadata['iconType'] == 'glyph':
				fontName = value.metadata['glyphFont']
				if fontName == 'WeatherIcons':
					self.display.valueTextBox.textBox.setFont(weatherGlyph)
			if hasattr(self, 'display'):
				self.display.value = self._valueLink
			if self.title.isEnabled() and self.title.allowDynamicUpdate():
				if isinstance(self._valueLink, MultiSourceContainer):
					title = self._valueLink.defaultContainer.value['title']
				else:
					title = self._valueLink.value['title']
				self.title.setText(title)
			self.lastUpdate = asyncio.get_event_loop().time()
			self.display.splitter.updateUnitDisplay()
			self.__updateTimeOffsetLabel()

			self.display.refresh()
			self.setToolTip(f'{value.source.name} @ {value.value.timestamp:%I:%M%p}')

	@property
	def placeholder(self):
		return self._placeholder

	@placeholder.setter
	def placeholder(self, value):
		if isinstance(value, PlaceholderSignal):
			self.display.value = "⋯"
			value.signal.connect(self.listenForKey)
		elif self._placeholder is not None and value is None:
			self._placeholder.signal.disconnect(self.listenForKey)
		self._placeholder = value

	@Slot(MonitoredKey)
	def listenForKey(self, value):
		if value.key == self.placeholder.key and value.value.now:
			self.valueLink = value.value
			disconnectSignal(self.placeholder.signal, self.listenForKey)
			value.requesters.remove(self)
		elif self.placeholder.key in value.key and value.value.now:
			self.valueLink = value.value
			disconnectSignal(self.placeholder.signal, self.listenForKey)
			value.requesters.remove(self)

	def setSubscription(self, value):
		self.valueLink = value

	def adjustContentStaleTimer(self):
		now = asyncio.get_event_loop().time()
		last = self.lastUpdate
		self.updateFreqency = now - last

		def resumeRegularInterval():
			self.contentStaleTimer.stop()
			falloff = self.updateFreqency*0.1
			self.contentStaleTimer.setInterval(1000*falloff)
			self.contentStaleTimer.timeout.disconnect(resumeRegularInterval)
			self.contentStaleTimer.timeout.connect(self.contentStaled)
			self.contentStaleTimer.start()

		self.contentStaleTimer.timeout.connect(resumeRegularInterval)
		self.contentStaleTimer.setInterval(1000*(self.updateFreqency + 15))
		self.contentStaleTimer.start()

	@Slot()
	def updateSlot(self):
		self.__updateTimeOffsetLabel()
		self.setOpacity(1)
		self.display.refresh()
		self.adjustContentStaleTimer()
		try:
			self.setToolTip(f'{self.valueLink.source.name} @ {self.valueLink.value.timestamp:%-I:%M%p}')
		except AttributeError:
			pass

	def __updateTimeOffsetLabel(self):
		if self.valueLink.forecastOnly:
			# if abs(offset := Now() - self.value.timestamp) > timedelta(hours=5):
			# 	self.timeOffsetLabel.setEnabled(True)
			self.timeOffsetLabel.setEnabled(False)
		elif self.value.isValid and abs(offset := Now() - self.value.timestamp) > timedelta(minutes=15):
			self.timeOffsetLabel.setEnabled(True)
		else:
			self.timeOffsetLabel.setEnabled(False)

	def contentStaled(self):
		self.timeOffsetLabel.setEnabled(True)
		opacity = self.opacity()
		self.setOpacity(clamp(opacity - 0.1, 0.6, 1))
		self.update()

	@property
	def value(self):
		return self.display.value

	@value.setter
	def value(self, value):
		self.display.value = value

	def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
		if self.splitter.isUnderMouse():
			event.ignore()
			return
		super(Realtime, self).mouseDoubleClickEvent(event)

	def mousePressEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		if item := self.focusProxy():
			if not item.isUnderMouse():
				if isinstance(item, ResizeHandle):
					item.parent.hide()
				else:
					item.hide()
				self.setFocusProxy(None)
				self.setFocus(Qt.MouseFocusReason)
		if self.display.displayProperties.unitPosition == 'floating' and self.display.unitTextBox.isAncestorOf(self.scene().itemAt(mouseEvent.scenePos(), QTransform())):
			self.display.unitTextBox.setFocus(Qt.MouseFocusReason)
			self.display.unitTextBox.mousePressEvent(mouseEvent)
			self.setFocusProxy(self.display.unitTextBox)
			return
		super().mousePressEvent(mouseEvent)

	# if mouseEvent.isAccepted():
	# 	item = self.scene().itemAt(mouseEvent.scenePos(), self.transform())
	# 	if isinstance(item, ResizeHandle):
	# 		self.setFocusProxy(item)
	# 		# item.mousePressEvent(mouseEvent)
	# 	elif self.focusProxy():
	# 		if not self.focusProxy().isUnderMouse():
	# # 			self.focusProxy().hide()
	# # 			self.setFocusProxy(None)
	# # 			self.setFocus(Qt.MouseFocusReason)

	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
		if self.focusProxy():
			self.focusProxy().mouseMoveEvent(event)
			return
		super(Realtime, self).mouseMoveEvent(event)

	def focusInEvent(self, event: QFocusEvent):
		if self.display.splitter.isEnabled():
			self.display.splitter.show()
		if self.display.displayProperties.unitPosition == 'floating':
			self.display.unitTextBox.resizeHandles.show()
		super(Realtime, self).focusInEvent(event)

	def focusOutEvent(self, event: QFocusEvent):
		self.display.splitter.hide()
		self.display.valueTextBox.marginHandles.hide()
		self.display.unitTextBox.marginHandles.hide()
		super(Realtime, self).focusOutEvent(event)

	def changeSource(self, newSource):
		if self._valueLink is not None:
			self._valueLink.valueChanged.disconnect(self.updateSlot)
		self.valueLink.preferredSource = newSource
		self._valueLink.valueChanged.connect(self.updateSlot)
		self.valueLink = self.valueLink

	@property
	def name(self):
		return f'{str(self.key.name)@TitleCamelCase}-0x{self.uuidShort.upper()}'

	@classmethod
	def validate(cls, item: dict):
		panelValidation = super(Realtime, cls).validate(item)
		key = 'key' in item and item['key']
		return panelValidation and key

	# def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent):
	# 	self.setScale(1.1)
	# 	self.setTransformOriginPoint(self.boundingRect().center())
	# 	super(Realtime, self).hoverEnterEvent(event)
	#
	# def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent):
	# 	self.setScale(1)
	# 	super(Realtime, self).hoverLeaveEvent(event)
	#
	# def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent):
	# 	# tilt the item towards the mouse with QTransform sheering
	# 	transform = QTransform()
	# 	tPoint = event.pos()# - self.boundingRect().center()
	# 	x = event.pos().x() / self.width() - 0.5
	# 	y = event.pos().y() / self.height() - 0.5
	# 	x *= -0.001
	# 	y *= 0.001
	# 	y = 0
	# 	# if x > 0:
	# 	# 	tPoint.setX(self.width())
	# 	# else:
	# 	# 	tPoint.setX(0)
	# 	self.setTransformOriginPoint(tPoint)
	# 	print(f'\r{x:0.4f}, {y:0.4f}', end='')
	# 	# transform.setMatrix(1, 0, x, 0, 1, y, 0, 0, 1)
	# 	# self.setTransform(transform)
	#
	# def wheelEvent(self, event: QGraphicsSceneWheelEvent) -> None:
	# 	value = event.delta() / 1200000
	# 	transform = QTransform()
	# 	if event.orientation() != 1:
	# 		transform.setMatrix(1 - value*100, 0, value, 0, 1, 0, 0, 0, 1)
	# 	else:
	# 		transform.setMatrix(1, 0, 0, 0, 1, value, 0, 0, 1)
	# 	self.setTransform(transform, True)

	@property
	def state(self):
		display = self.display.state
		state = {
			'type': f'realtime.{display.pop("displayType") if isinstance(display, dict) else display}',
			'key':  str(self.key)
		}
		if isinstance(display, dict):
			state['display'] = display
		titleState = self.splitter.state
		if len(titleState) == 1 and 'visible' in titleState:
			titleState = titleState['visible']
		state['title'] = titleState
		if state['title'] is True:
			del state['title']
		superState = super(Realtime, self).state
		state.update({k: v for k, v in superState.items() if k not in state})
		state.pop('childItems', None)
		return state

	@state.setter
	def state(self, state):
		self.key = state.pop('key', None) or self.key
		displayState = state.pop('display', None)
		if displayState:
			displayType = displayState.pop('displayType', None)
			if 'value' in displayState:
				valueState = displayState.pop('value')
				valueState.pop('text', None)
				self.display.valueTextBox.state = valueState
			if 'unit' in displayState:
				unitState = displayState.pop('unit')
				unitState.pop('text', None)
				self.display.unitTextBox.state = unitState
			self.display.displayProperties.state = displayState
		if 'title' in state:
			self.splitter.state = state.pop('title')
		self.geometry = state.pop('geometry', None) or self.geometry

	def __del__(self):
		self._valueLink.source.publisher.disconnectChannel(self.key, self.updateSlot)
		log.debug(f'{self.name} deleted')
		super(Realtime, self).__del__()


class TimeOffsetLabel(Label):
	def __init__(self, parent, *args, **kwargs):
		kwargs['geometry'] = {'x': 0.7, 'y': 0.85, 'width': 0.3, 'height': 0.15, 'relative': True}
		super(TimeOffsetLabel, self).__init__(parent, alignment=AlignmentFlag.BottomRight, *args, **kwargs)

	def refresh(self):
		if not self.isEnabled():
			return
		offset = Now() - self.parent.value.timestamp
		value = Second(offset.total_seconds()).autoAny
		value.precision = 0
		if value > 0:
			self.text = f'{value.str} ago'
		else:
			self.text = f'in {value.str.strip("-")}'

	def setEnabled(self, enabled: bool) -> None:
		super(TimeOffsetLabel, self).setEnabled(enabled)
		if enabled:
			self.show()
			# connectSignal(baseClock.minute, self.refresh)
			self.refresh()
		else:
			self.hide()
# disconnectSignal(baseClock.minute, self.refresh)


class LockedRealtime(Realtime):
	savable = False

	def __init__(self, *args, **kwargs):
		kwargs['showTitle'] = True
		kwargs['margins'] = {'left': 0, 'right': 0, 'top': 0, 'bottom': 0}
		super(LockedRealtime, self).__init__(*args, **kwargs)
		self.clickHoldTimer = mouseHoldTimer(self.startPickup, interval=1000)
		self.freeze()
		self.locked = True
		self.setZValue(self.parent.zValue() + 100)

	def mousePressEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		self.clickHoldTimer.start(mouseEvent.scenePos())
		mouseEvent.accept()

	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
		self.clickHoldTimer.updatePosition(event.scenePos())
		event.accept()

	def mouseReleaseEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		self.clickHoldTimer.stop()
		mouseEvent.accept()

	def startPickup(self):
		item = self
		state = item.state
		state['class'] = 'Realtime'
		stateString = str(dumps(state, cls=JsonEncoder))
		info = QMimeData()
		if hasattr(item, 'text'):
			info.setText(str(item.text))
		else:
			info.setText(str(item))
		info.setData('application/panel-valueLink', QByteArray(stateString.encode('utf-8')))
		drag = QDrag(self.scene().views()[0])
		drag.setPixmap(item.pix)
		drag.setHotSpot(item.rect().center().toPoint())
		# drag.setParent(child)
		drag.setMimeData(info)
		self.parent.collapse()
		self.parent.startHideTimer(.5)
		drag.start()

	# currentThread: QThread = self.scene().views()[0].thread().currentThread()

	# asyncio.get_running_loop().run_in_executor(None, drag.start, Qt.CopyAction)

	@property
	def state(self):
		return {
			'key': self.key
		}

	@property
	def pix(self) -> QPixmap:
		rect = self.rect()
		rect = self.globalTransform.mapRect(rect)
		pix = QPixmap(rect.size().toSize())
		pix.fill(Qt.transparent)
		painter = QPainter(pix)
		painter.translate(rect.center().toPoint())
		# painter.setTransform(self.transform())
		# painter.setWorldTransform(self.globalTransform)
		painter.setRenderHint(QPainter.Antialiasing)
		opt = QStyleOptionGraphicsItem(15)
		opt.rect.setRect(*rect.toRect().getCoords())
		opt.exposedRect.setRect(*rect.toRect().getCoords())
		# opt.exposedRect = self.containingRect
		# opt.rect = self.containingRect
		self.paint(painter, opt, None)
		textBox = self.display.valueTextBox.textBox
		textRect = textBox.boundingRect()
		scale = min(rect.width()/textRect.width(), rect.height()/textRect.height())
		painter.scale(scale, scale)
		textBox.paint(painter, opt, None)
		return pix


# class PropertyTypeVar(TypeVar):
# 	pass


class MeasurementDisplayProperties:
	__slots__ = ('__label', '__maxLength', '__precision', '__forcePrecision', '__unitSpacer', '__unitPosition', '__suffix',
	'__decorator', '__shorten', '__decimalSeparator', '__radixPoint', '__valueMargins', '__unitMargins', '__dict__')

	Label: 'DisplayLabel'
	maxLength: int
	precision: int
	forcePrecision: bool
	unitSpacer: str
	unitPosition: DisplayPosition
	suffix: str
	decorator: str
	shorten: bool
	decimalSeparator: str
	radixPoint: str

	"""
	Properties for how a label should display its value.  It is assumed that the value is a WeatherUnit Measurement.
	Attributes that are unset will provide the default value for the Measurement as specified WeatherUnit config.

	Attributes
	----------
	maxLength : int, optional
		The maximum length of the label.  If the value is longer than this, it will be truncated.
	precision : int, optional
		The number of decimal places to display.  If the value is a float, it will be rounded to this number of decimal places.
	unitSpacer : str, optional
		The string to use between the value and the unit.
	unitDisplayPosition : UnitDisplayPosition, default='Auto'
		How the unit should be displayed.
	suffix : str, optional
		The string to use as the suffix.
	decorator : str, optional
		The string to use to 'decorate' the unit
			Example: 'º' is used to decorate temperature values
	shorten : bool, optional
		If True, if the value is longer than the allowed length and there are no decimal places to round, the value will be
		displayed in the next order of magnitude.
			Example: '1024m' becomes '1.0km'
	decimalSeparator : str, optional
		The string to use as the decimal separator.  If not specified, the default is the decimal separator for the current locale.
	radixPoint : str, optional
		The string to use as the radix point (character between the values integer and float).  If not specified, the default 
		is the radix point for the current locale.
	"""

	def __init__(self, label: 'DisplayLabel' = None,
		maxLength: int = None,
		precision: int = None,
		unitSpacer: str = None,
		unitPosition: DisplayPosition = None,
		suffix: str = None,
		decorator: str = None,
		shorten: bool = None,
		decimalSeparator: str = None,
		radixPoint: str = None,
		valueUnitRatio: float = None,
		splitDirection=None,
		**kwargs
	):
		self.label = label
		self.maxLength = maxLength
		self.precision = precision
		self.unitSpacer = unitSpacer
		self.unitPosition = unitPosition
		self.suffix = suffix
		self.decorator = decorator
		self.shorten = shorten
		self.decimalSeparator = decimalSeparator
		self.radixPoint = radixPoint
		self.valueUnitRatio = valueUnitRatio or kwargs.get('ratio', None)
		self.splitDirection = splitDirection
		if 'unit' in kwargs:
			unitDict = kwargs['unit']
			position = unitDict.pop('position', None)
			if position is not None and self.__unitPosition is None:
				self.unitPosition = position
			hide = None
			if 'hide' in unitDict:
				hide = unitDict.pop('hide')
			elif 'show' in unitDict:
				hide = not unitDict.pop('show')
			elif 'visible' in unitDict:
				hide = not unitDict.pop('visible')
			if hide:
				self.unitPosition = DisplayPosition.Hidden

	@property
	def label(self):
		return self.__label

	@label.setter
	def label(self, value):
		self.__label = value

	@property
	def __isValid(self) -> bool:
		return self.__label.value is not None and hasattr(self.__label.value, '@unit')

	@property
	def hasUnit(self) -> bool:
		if self.__label.value is not None and hasattr(self.__label.value, '@unit'):
			unit = self.__label.value['@unit']
			return unit is not None or len(unit) == 0
		return False

	@property
	def maxLength(self) -> int:
		if self.__maxLength is None and self.__isValid:
			return self.__label.value['@max']
		return self.__maxLength

	@maxLength.setter
	def maxLength(self, value: int):
		self.__maxLength = value

	@property
	def precision(self) -> int:
		if self.__precision is None and self.__isValid:
			return self.__label.value['@precision']
		return self.__precision

	@precision.setter
	def precision(self, value: int):
		self.__precision = value

	@property
	def unitSpacer(self) -> str:
		if self.__unitSpacer is None and self.__isValid:
			return self.__label.value['@unitSpacer']
		return self.__unitSpacer

	@unitSpacer.setter
	def unitSpacer(self, value: str):
		self.__unitSpacer = value

	@property
	def unitPosition(self) -> DisplayPosition:
		if self.__unitPosition is None:
			if self.__isValid:
				if self.__label.value['@showUnit']:
					unitText = self.__label.value['@unit']
					if len(unitText) > 2:
						return DisplayPosition.Auto
					elif len(unitText) == 0:
						return DisplayPosition.Hidden
					return DisplayPosition.Inline
				return DisplayPosition.Hidden
			return DisplayPosition.Hidden
		return self.__unitPosition

	@unitPosition.setter
	def unitPosition(self, value: DisplayPosition):
		if isinstance(value, str):
			value = DisplayPosition[value]
		self.__unitPosition = value

	@property
	def suffix(self) -> str:
		if self.__suffix is None and self.__isValid:
			return self.__label.value['@suffix']
		return self.__suffix

	@suffix.setter
	def suffix(self, value: str):
		self.__suffix = value

	@property
	def decorator(self) -> str:
		if self.__decorator is None and self.__isValid:
			return self.__label.value['@decorator']
		return self.__decorator

	@decorator.setter
	def decorator(self, value: str):
		self.__decorator = value

	@property
	def shorten(self) -> bool:
		if self.__shorten is None and self.__isValid:
			return self.__label.value['@shorten']
		return self.__shorten

	@shorten.setter
	def shorten(self, value: bool):
		self.__shorten = value

	@property
	def decimalSeparator(self) -> str:
		if self.__decimalSeparator is None and self.__isValid:
			return self.__label.value['@decimalSeparator']

		return self.__decimalSeparator

	@decimalSeparator.setter
	def decimalSeparator(self, value: str):
		self.__decimalSeparator = value

	@property
	def radixPoint(self) -> str:
		if self.__radixPoint is None and self.__isValid:
			return self.__label.value['@radixPoint']
		return self.__radixPoint

	@radixPoint.setter
	def radixPoint(self, value: str):
		self.__radixPoint = value

	@property
	def valueUnitRatio(self) -> float:
		if self.__isValid:
			return self.__valueUnitRatio
		return 1.0

	@valueUnitRatio.setter
	def valueUnitRatio(self, value):
		if value is None:
			self.__valueUnitRatio = value
		else:
			self.__valueUnitRatio = clamp(value, 0.1, 0.9)

	@property
	def splitDirection(self):
		return self.__splitDirection

	@splitDirection.setter
	def splitDirection(self, value):
		self.__splitDirection = value

	def toDict(self) -> dict:
		attrs = {
			'maxLength':        self.__maxLength,
			'precision':        self.__precision,
			'unitSpacer':       self.__unitSpacer,
			'unitPosition':     self.__unitPosition.value if self.__unitPosition is not None else None,
			'suffix':           self.__suffix,
			'decorator':        self.__decorator,
			'shorten':          self.__shorten,
			'decimalSeparator': self.__decimalSeparator,
			'radixPoint':       self.__radixPoint,
			'valueUnitRatio':   self.__valueUnitRatio,
			'splitDirection':   self.__splitDirection.value if self.__splitDirection is not None else None
		}
		return {k: v for k, v in attrs.items() if v is not None}

	def toPropertyOptions(self):
		pass

	def __getstate__(self):
		return self.toDict()

	def __setstate__(self, state):
		self.__init__(label=self.__label, **state)


def withoutUnit(self):
	return self.value['@withoutUnit']


class DisplayLabel(Panel):
	def __init__(self, displayProperties: MeasurementDisplayProperties = None, *args, **kwargs):
		kwargs.pop('childItems', None)
		self.text = ""
		super().__init__(*args, **kwargs)
		self.displayType = DisplayType.Text
		self.setMovable(False)
		self.setResizable(False)
		self.displayProperties = MeasurementDisplayProperties(self, **(displayProperties or {}), **kwargs)

		unitDisplay = kwargs.get('unit', {})
		valueDisplay = kwargs.get('value', {})

		self.valueTextBox = Label(self, clickable=False, **valueDisplay)
		self.valueTextBox.locked = True
		self.valueTextBox.movable = False
		self.valueTextBox.resizable = False

		self.unitTextBox = UnitLabel(self, self.valueTextBox, clickable=False, **unitDisplay)
		self.unitTextBox.locked = True
		self.unitTextBox.movable = False
		self.unitTextBox.resizable = False

		self.splitter = MeasurementUnitSplitter(surface=self, value=self.valueTextBox, unit=self.unitTextBox)
		self.setFlag(QGraphicsItem.ItemIsMovable, False)
		self.setFlag(QGraphicsItem.ItemIsSelectable, False)
		self.setFlag(QGraphicsItem.ItemIsFocusable, False)
		self.setAcceptDrops(False)

	# self.setHandlesChildEvents(True)
	# self.a.setAlignment(Qt.AlignCenter)
	# self.a.setZValue(1000)

	# modifiers = AttributeEditor(self.parent, IntAttribute(value, 'max', -1, 1, 6))
	# modifiers.setVisible(True)

	def setUnitPosition(self, value: DisplayPosition):
		self.displayProperties.unitPosition = value
		self.splitter.updateUnitDisplay()

	def contextMenuEvent(self, event):
		event.ignore()
		return

	@property
	def value(self):
		return self.valueTextBox.textBox.value

	@value.setter
	def value(self, value):
		self.valueTextBox.textBox.value = value
		self.unitTextBox.textBox.refresh()
		self.splitter.updateUnitDisplay()

	# @cached_property
	# def valueTextBox(self):
	# 	a = Label(self, clickable=False)
	# 	a.locked = True
	# 	a.movable = False
	# 	a.resizable = False
	# 	a.setAlignment(AlignmentFlag.VerticalCenter | AlignmentFlag.HorizontalCenter)
	# 	return a

	# @cached_property
	# def unitTextBox(self):
	# 	a = UnitLabel(self, self.valueTextBox, clickable=False)
	# 	a.locked = True
	# 	a.movable = False
	# 	a.resizable = False
	# 	a.setAlignment(AlignmentFlag.Top | AlignmentFlag.HorizontalCenter)

	# return a

	def mouseDoubleClickEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		mouseEvent.ignore()
		return

	def refresh(self):
		# self.a.setHtml(f'<div style="text-align: center; top: 50%;">{str(self.text)}</div>')
		if self.displayProperties.hasUnit and self.displayProperties.unitPosition != DisplayPosition.Inline:
			self.valueTextBox.textBox.setCustomFilterFunction(True)
		else:
			self.valueTextBox.textBox.setCustomFilterFunction(False)

		self.valueTextBox.textBox.refresh()

	def setRect(self, *args):
		super().setRect(*args)

	# self.valueTextBox.setPos(self.rect().topLeft())
	# self.a.adjustSize()
	# self.a.setTextWidth(self.rect().width())

	# self.a.setTextWidth(self.rect().width())
	# self.a.adjustSize

	def hideUnit(self):
		self.displayProperties.unitPosition = DisplayPosition.Hidden
		self.splitter.updateUnitDisplay()

	def showUnit(self):
		self.displayProperties.unitPosition = DisplayPosition.Auto
		self.splitter.updateUnitDisplay()

	def toggleUnit(self):
		if self.displayProperties.unitPosition == DisplayPosition.Hidden:
			self.showUnit()
		else:
			self.hideUnit()

	@property
	def state(self):
		state = {
			'displayType': self.displayType,
		}
		state.update(self.displayProperties.toDict())
		valueState = {}
		if self.valueTextBox.textBox.alignment != AlignmentFlag.Center:
			valueState['alignment'] = self.valueTextBox.textBox.alignment
		if len(self.valueTextBox.textBox.enabledFilters):
			valueState['filters'] = tuple(self.valueTextBox.textBox.enabledFilters)
		if not self.valueTextBox.margins.isDefault():
			valueState['margins'] = self.valueTextBox.margins
		if self.valueTextBox.modifiers:
			valueState['modifiers'] = self.valueTextBox.modifiers
		if valueState:
			state['value'] = valueState

		if self.unitTextBox.isVisible():
			unitState = {}
			if self.unitTextBox.textBox.alignment != AlignmentFlag.Center:
				unitState['alignment'] = self.unitTextBox.textBox.alignment.__getstate__()
			if self.unitTextBox.textBox.enabledFilters:
				unitState['filters'] = tuple(self.unitTextBox.textBox.enabledFilters)
			if not self.unitTextBox.margins.isDefault():
				unitState['margins'] = self.unitTextBox.margins
			if unitState:
				if 'unitPosition' in state:
					unitState['position'] = state.pop('unitPosition')
				state['unit'] = unitState
		else:
			state.pop('valueUnitRatio', None)
		if len(state) == 1 and 'displayType' in state:
			return state['displayType']
		return state


class UnitLabel(Label):
	def __init__(self, parent: Union['Panel', 'LevityScene'],
		reference: Label,
		alignment: Alignment = None,
		filters: list[str] = None,
		font: QFont = None,
		*args, **kwargs):
		self.reference = reference
		super().__init__(parent=parent, alignment=alignment, filters=filters, font=font, *args, **kwargs)
		self.setResizable(False)
		self.setMovable(False)

	@property
	def isEmpty(self):
		return False

	@cached_property
	def textBox(self):
		box = TextHelper(self, self.reference.textBox)
		box.setParentItem(self)
		return box

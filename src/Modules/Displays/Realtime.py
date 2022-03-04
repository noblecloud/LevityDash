from PySide2.QtGui import QColor, QPainter, QRegion, QTextBlockFormat, QTransform

from src.Modules.Handles.Figure import MarginHandles
from src.Modules.Displays.Text import Text
from src.catagories import ValueWrapper
from src import logging
from functools import cached_property

from json import loads
from PySide2.QtCore import QRectF, Qt, QTimer, Signal, Slot
from PySide2.QtWidgets import QGraphicsBlurEffect, QGraphicsSceneHoverEvent, QGraphicsSceneMouseEvent, QGraphicsTextItem, QStyleOptionGraphicsItem, QWidget

from src.dispatcher import endpoints, MergedValue, MonitoredKey, PlaceholderSignal
from src.Grid import Grid
from src.Modules.Handles.Resize import Splitter
from src.Modules import hook, Panel
from src.Modules.Menus import RealtimeContextMenu
from src.utils import addCrosshair, disconnectSignal, DisplayType, Subscription
from src.Modules.Label import EditableLabel, Label, TitleLabel

log = logging.getLogger(__name__)

displayDefault = {'displayType': DisplayType.Numeric, 'geometry': {'absolute': False, 'position': {'x': 0, 'y': 0.2}, 'size': {'width': 1.0, 'height': 0.8}}}


def buildDisplay(parent, kwargs):
	if len(kwargs) == 0:
		kwargs = displayDefault
	displayType = kwargs.pop('displayType', DisplayType.Numeric)
	if displayType == DisplayType.Numeric:
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
		self.display = buildDisplay(self, kwargs.get('display', {}))
		self.key = kwargs.get([k for k in ['key', 'valueLink', 'placeholder'] if k in kwargs].pop())
		self.display.setFlag(self.display.ItemIsSelectable, False)

		self.contentStaleTimer = QTimer()
		self.contentStaleTimer.setInterval(1000 * 60 * 30)
		self.contentStaleTimer.timeout.connect(self.contentStaled)
		self.contentStaleTimer.start()

		self.setAcceptHoverEvents(True)
		self.setAcceptDrops(True)
		self.splitter = Splitter(surface=self, splitType='horizontal', ratio=0.2, primary=self.title, secondary=self.display)
		self.splitter.hide()
		self._titleRatio = self.splitter.ratio
		self.setFlag(self.ItemIsSelectable, True)
		self.title.setFlag(self.display.ItemIsSelectable, False)
		if kwargs.get('showTitle', True):
			self.showTitle()
		else:
			self.hideTitle()

	def buildTitle(self, kwargs):
		if not hasattr(self, 'title'):
			self.title = TitleLabel(self, **kwargs)

	def hideTitle(self):
		self._titleRatio = self.splitter.ratio
		self.title.hide()
		self.title.setEnabled(False)
		self.splitter.ratio = 0
		self.splitter.setGeometries()

	def showTitle(self):
		self.splitter.ratio = self._titleRatio
		self.title.setEnabled(True)
		self.title.show()
		self.title.updateFromGeometry()

	def toggleTitle(self):
		if self.title.isEnabled():
			self.hideTitle()
		else:
			self.showTitle()

	@cached_property
	def grid(self) -> None:
		return Grid(self, rows=12, columns=12, static=True)

	@cached_property
	def contextMenu(self):
		return RealtimeContextMenu(self)

	@property
	def key(self):
		return self._key

	@key.setter
	def key(self, value):
		self._key = value
		value = endpoints.request(self, value)
		if isinstance(value, PlaceholderSignal):
			self.placeholder = value
			self.valueLink = None
		elif isinstance(value, MergedValue):
			self.valueLink = value
			self.placeholder = None

	@property
	def valueLink(self) -> 'MergedValue':
		return self._valueLink

	@valueLink.setter
	def valueLink(self, value):
		if self._valueLink is not None and value != self._valueLink:
			self._valueLink.valueChanged.disconnect(self.updateSlot)
		elif self._valueLink is None and value is not None:
			self._valueLink = value
			self._valueLink.valueChanged.connect(self.updateSlot)
			if hasattr(self, 'display'):
				self.display.value = self._valueLink
			if self.title.isEnabled() and self.title.allowDynamicUpdate():
				self.title.setText(self._valueLink.title)

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
		if value.key == self.placeholder.key:
			self.valueLink = value.value
			disconnectSignal(self.placeholder.signal, self.listenForKey)
			value.requesters.remove(self)

	def setSubscription(self, value):
		self.valueLink = value

	@Slot(ValueWrapper)
	def updateSlot(self, value):
		print(f"{self.key} updated to {value.value}")
		self.contentStaleTimer.start()
		self.display.refresh()

	def contentStaled(self):
		effect = QGraphicsBlurEffect()
		effect.setBlurRadius(10)
		# self.setGraphicsEffect(effect)
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

	def changeSource(self, newSource):
		if self._valueLink is not None:
			self._valueLink.valueChanged.disconnect(self.updateSlot)
		self.valueLink.preferredSource = newSource
		self._valueLink.valueChanged.connect(self.updateSlot)
		self.valueLink = self.valueLink

	@property
	def state(self):
		state = super(Realtime, self).state
		state.pop('childItems', None)
		state['display'] = self.display
		state['title'] = self.title
		state['showTitle'] = self.title.isEnabled()
		state['key'] = self.key
		return state


class DisplayLabel(Panel):
	def __init__(self, value: MergedValue = None, *args, **kwargs):
		kwargs.pop('childItems', None)
		self.text = ""
		super().__init__(*args, **kwargs)
		self.displayType = DisplayType.Numeric
		self.setMovable(False)
		self.value = value

		# self.textBox.setDefaultTextColor(Qt.white)
		self.marginHandles = MarginHandles(self)
		self.marginHandles.signals.action.connect(self.textBox.updateTransform)

	# self.a.setAlignment(Qt.AlignCenter)
	# self.a.setZValue(1000)

	# modifier = AttributeEditor(self.parent, IntAttribute(value, 'max', -1, 1, 6))
	# modifier.setVisible(True)

	@property
	def value(self):
		return self.textBox.value

	@value.setter
	def value(self, value):
		self.textBox.value = value

	@cached_property
	def textBox(self):
		a = Text(self, value=str(self.text))
		a.setParentItem(self)
		return a

	def mouseDoubleClickEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		mouseEvent.ignore()
		return

	def refresh(self):
		# self.a.setHtml(f'<div style="text-align: center; top: 50%;">{str(self.text)}</div>')
		self.textBox.refresh()

	def setRect(self, *args):
		super().setRect(*args)
		# self.textBox.setPos(self.rect().topLeft())
		# self.a.adjustSize()
		# self.a.setTextWidth(self.rect().width())
		self.textBox.updateTransform()

	# self.a.setTextWidth(self.rect().width())
	# self.a.adjustSize

	@property
	def state(self):
		state = {'displayType': self.displayType}
		state.update(super().state)
		state.pop('childItems', None)
		return state

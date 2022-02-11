from src import logging
from functools import cached_property

from json import loads
from PySide2.QtCore import QTimer, Slot
from PySide2.QtWidgets import QGraphicsBlurEffect, QGraphicsSceneMouseEvent

from src.merger import MergedValue
from src.Grid import Grid
from src.Modules.AttributeEditor import AttributeEditor, IntAttribute
from src import selectionPen
from src.Modules.Handles.Figure import MarginHandles
from src.Modules.Handles.Resize import Splitter
from src.Modules import hook, Panel
from src.Modules.Menus import RealtimeContextMenu
from src.utils import DisplayType, Subscription
from src.Modules.Label import EditableLabel, Label, TitleLabel

log = logging.getLogger(__name__)


def buildDisplay(kwargs):
	displayType = kwargs.pop('displayType', DisplayType.Numeric)
	if displayType == DisplayType.Numeric:
		return DisplayLabel(**kwargs)


class Realtime(Panel):
	_includeChildrenInState = False

	def __init__(self, parent: Panel, **kwargs):
		super(Realtime, self).__init__(parent=parent, **kwargs)
		self.buildTitle(kwargs.get('title', {}))
		self.geometry.updateSurface()
		self._valueLink = None
		valueLink = kwargs.get('valueLink', None)
		self.valueLink = valueLink
		display = kwargs.get('display', None)
		if display is None:
			display = {'displayType': DisplayType.Numeric, 'geometry': {'absolute': False, 'position': {'x': 0, 'y': 0.2}, 'size': {'width': 1.0, 'height': 0.8}}}
		display['parent'] = self
		display['value'] = valueLink
		self.display = buildDisplay(display)
		self.display.setFlag(self.display.ItemIsSelectable, False)

		self.contentStaleTimer = QTimer()
		self.contentStaleTimer.setInterval(1000 * 60 * 15)
		self.contentStaleTimer.timeout.connect(self.contentStaled)
		self.setAcceptHoverEvents(True)
		# if self.grid is not None:
		# 	delattr(self, 'grid')

		# self.resizeHandles.mapValues()
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

	def paint(self, painter, option, widget):
		super().paint(painter, option, widget)

	# if self.hasFocus() or self.childHasFocus():
	# 	painter.setPen(selectionPen)
	# 	splitterPosition = self.splitter.position
	# 	if self.splitter.location.isVertical:
	# 		painter.drawLine(splitterPosition.x(), 0, splitterPosition.x(), self.height())
	# 	else:
	# 		painter.drawLine(0, splitterPosition.y(), self.width(), splitterPosition.y())

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
	def valueLink(self) -> 'MergedValue':
		return self._valueLink

	@valueLink.setter
	def valueLink(self, value):
		if not value:
			log.warn(f'No valueLink set for {self.name}')
			return
		if self._valueLink is not None and value != self._valueLink:
			self._valueLink.valueChanged.disconnect(self.updateSlot)
		self._valueLink = value
		self._valueLink.valueChanged.connect(self.updateSlot)
		if hasattr(self, 'display'):
			self.display.value = self._valueLink
		if self.title.isEnabled() and self.title.allowDynamicUpdate():
			self.title.setText(self._valueLink.title)

	def setSubscription(self, value):
		self.valueLink = value

	@Slot(dict)
	def updateSlot(self, value):
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
		self.valueLink.selected = newSource
		self._valueLink.valueChanged.connect(self.updateSlot)
		self.valueLink = self.valueLink

	@property
	def state(self):
		state = super(Realtime, self).state
		state.pop('childItems', None)
		state['display'] = self.display
		state['title'] = self.title
		state['showTitle'] = self.title.isEnabled()
		state['valueLink'] = self.valueLink.toDict()

		return state


class DisplayLabel(Label):
	def __init__(self, value: MergedValue, *args, **kwargs):
		kwargs.pop('childItems', None)
		super().__init__(*args, **kwargs)
		self.displayType = DisplayType.Numeric
		self.setMovable(False)
		self.value = value

	# self.marginAdjusters.setVisible(True)
	# modifier = AttributeEditor(self.parent, IntAttribute(value, 'max', -1, 1, 6))
	# modifier.setVisible(True)

	def mouseDoubleClickEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		mouseEvent.ignore()
		return

	@property
	def value(self):
		return self.text

	@value.setter
	def value(self, value):
		self.text = value

	@property
	def state(self):
		state = {'displayType': self.displayType}
		state.update(super().state)
		state.pop('childItems', None)
		return state

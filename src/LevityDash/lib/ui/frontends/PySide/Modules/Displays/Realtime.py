from asyncio import get_event_loop, gather, get_running_loop, Task
from abc import abstractmethod
from datetime import timedelta
from functools import cached_property, partial

from PySide2.QtCore import QByteArray, QMimeData, Qt, QTimer, Slot
from PySide2.QtGui import QDrag, QFocusEvent, QFont, QPainter, QPixmap, QTransform
from PySide2.QtWidgets import QGraphicsItem, QGraphicsSceneMouseEvent, QStyleOptionGraphicsItem
from typing import Any, Iterable, Type, Dict

from qasync import asyncSlot, QApplication

from LevityDash.lib.config import DATETIME_NO_ZERO_CHAR
from WeatherUnits.time_.time import Second

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins import Plugin, Plugins, Container
from LevityDash.lib.plugins.plugin import AnySource, SomePlugin
from LevityDash.lib.plugins.dispatcher import MultiSourceContainer, ValueDirectory
from LevityDash.lib.ui.fonts import weatherGlyph
from LevityDash.lib.ui.frontends.PySide.utils import DisplayType, mouseHoldTimer
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import TextHelper
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import NonInteractiveLabel as Label, TitleLabel
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Resize import MeasurementUnitSplitter, ResizeHandle, TitleValueSplitter
from LevityDash.lib.ui.frontends.PySide.Modules.Menus import RealtimeContextMenu
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.utils.geometry import Alignment, AlignmentFlag, DisplayPosition, LocationFlag, Size
from LevityDash.lib.utils.shared import clamp, disconnectSignal, Now, TitleCamelCase, Unset, OrUnset, connectSignal
from LevityDash.lib.stateful import StateProperty, Stateful, DefaultGroup
from LevityDash.lib.plugins.observation import RealtimeSource

from ... import UILogger as guiLog

log = guiLog.getChild(__name__)

loop = get_running_loop()


class Display(Panel, tag=...):
	__exclude__ = {'items', 'geometry', 'locked', 'frozen', 'movable', 'resizable', 'text'}

	__defaults__ = {
		'displayType': DisplayType.Text,
		'geometry':    {'x': 0, 'y': 0.2, 'width': 1.0, 'height': 0.8},
		'movable':     False,
		'resizable':   False,
		'locked':      True,
	}

	@property
	@abstractmethod
	def type(self) -> DisplayType: ...

	@classmethod
	def default(cls):
		return super().default()


class InvalidSource(Exception):
	pass


# Section Realtime
class Realtime(Panel, tag='realtime'):
	_preferredSourceName: str
	_acceptsChildren = False
	key: CategoryItem
	_source: Plugin | SomePlugin
	_container: Container
	_key: CategoryItem

	__exclude__ = {'items'}

	__match_args__ = ('key',)

	__defaults__ = {
		'resizable': True,
		'movable':   True,
		'frozen':    False,
		'locked':    False,
	}

	__exclude__ = {'items'}

	@property
	def subtag(self) -> str:
		return self.display.displayType.value

	def __init__(self, parent: Panel, **kwargs):
		self.__connectedContainer: Container | None = None
		self.__pendingActions: Dict[int, Task] = {}
		super(Realtime, self).__init__(parent=parent, **kwargs)
		self.lastUpdate = None
		self.display.valueTextBox.marginHandles.surfaceProxy = self
		self.display.unitTextBox.marginHandles.surfaceProxy = self
		self.display.unitTextBox.resizeHandles.surfaceProxy = self
		self.timeOffsetLabel.setEnabled(False)
		self.scene().view.loadingFinished.connect(self.onLoadFinished)

	@asyncSlot()
	async def onLoadFinished(self):
		if not self.__pendingActions:
			return
		await gather(*self.__pendingActions)

	def _init_defaults_(self):
		super()._init_defaults_()
		self.contentStaleTimer = QTimer(singleShot=True)
		self.setFlag(self.ItemIsSelectable, True)
		self.setAcceptHoverEvents(not True)
		self.setAcceptDrops(True)
		self._container = None
		self._placeholder = None
		self._source = AnySource

	def _init_args_(self, *args, **kwargs):
		displayType = kwargs.pop('type', 'realtime.text')
		display = kwargs.pop('display')
		display['displayType'] = DisplayType[displayType.split('.')[-1]]
		kwargs['display'] = display
		super(Realtime, self)._init_args_(*args, **kwargs)

	def __repr__(self):
		return f'Realtime(key={self.key.name}, display={self.display.displayType.value})'

	def __rich_repr__(self):
		yield 'value', self.container
		yield from super().__rich_repr__()

	def __str__(self):
		return f'Realtime.{self.display.displayType.name}: {self.key.name}'

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
	def title(self):
		return TitleLabel(self)

	@cached_property
	def contextMenu(self):
		return RealtimeContextMenu(self)

	@cached_property
	def timeOffsetLabel(self):
		return TimeOffsetLabel(self)

	@StateProperty(sortOrder=0, match=True, dependencies={'display', 'title', 'forecast'})
	def key(self) -> CategoryItem:
		return getattr(self, '_key', None)

	@key.setter
	def key(self, value):
		if isinstance(value, str):
			value = CategoryItem(value)
		if value == getattr(self, '_key', None):
			return
		self._key = value
		self.container = ValueDirectory.getContainer(value)

	@StateProperty(default=AnySource, dependencies={'key', 'display', 'title', 'forecast'}, values=Plugins.plugins)
	def source(self) -> Plugin | SomePlugin:
		return getattr(self, '_source', AnySource)

	@source.setter
	def source(self, value: Plugin):
		self._source = value or AnySource

	@source.after
	def source(self):
		return

	@source.encode
	def source(value: Plugin) -> str:
		return getattr(value, 'name', 'any')

	@source.decode
	def source(self, value: str) -> Plugin | SomePlugin:
		source = Plugins.get(value, AnySource)
		self._preferredSourceName = value
		if source is None:
			log.info(f'{value} is not a valid source or the plugin is not Loaded')
		return source

	@StateProperty(default=False)
	def forecast(self) -> bool:
		return getattr(self, '_forecast', False)

	@forecast.setter
	def forecast(self, value: bool):
		self._forecast = value
		if self.container is not None:
			self.container = ValueDirectory.getContainer(self.key)

	@property
	def currentSource(self) -> Plugin | None:
		if self.__connectedContainer is not None:
			return self.__connectedContainer.source

	@StateProperty(allowNone=False, default=Stateful)
	def display(self) -> Display:
		return self._display

	@display.setter
	def display(self, value):
		self._display = value

	@display.decode
	def display(self, value) -> Panel:
		if isinstance(value, dict):
			return DisplayLabel(parent=self, **value)

	@StateProperty(key='title', sortOrder=1, allowNone=False, default=Stateful)
	def splitter(self) -> TitleValueSplitter:
		return self._splitter

	@splitter.setter
	def splitter(self, value: TitleValueSplitter):
		self._splitter = value
		value.hide()

	@splitter.decode
	def splitter(self, value: dict | bool | float | str) -> TitleValueSplitter:
		match value:
			case bool(value):
				value = {'visible': value}
			case float(value):
				value = {'ratio': value}
			case str(value):
				value = {'text': value}
			case _:
				pass
		return TitleValueSplitter(surface=self, title=self.title, value=self.display, **value)

	@cached_property
	def __requestAttempts(self) -> int:
		return 0

	@property
	def container(self) -> 'MultiSourceContainer':
		return self._container

	@container.setter
	def container(self, container: 'MultiSourceContainer'):
		# Always accept the container unless it is the same as the current one or is None.
		# The rest of the long will be handled by the subscriber and unless the key changes,
		# the container will not be changed.
		if self._container == container or container is None:
			return

		realtimePossible = any(
			not metadata.get('timeseriesOnly', False)
				for plugin in ValueDirectory.plugins
				if (metadata := plugin.schema.getExact(self.key, silent=True)) is not None
				   and any(isinstance(obs, RealtimeSource) for obs in plugin.observations)
		)
		self._container = container
		trueRealtimePreferred = False  # This is a placeholder for a future option.

		async def setupScheduledCheck():
			raise NotImplementedError

		async def startConnecting():
			if not self.forecast:
				firstAttemptContainer: Container = self.container.getRealtimeContainer(self.source, realtimePossible)
			else:
				firstAttemptContainer: Container = self.container.getDaily(self.source)

			if firstAttemptContainer is None:
				# If no realtime provided the MultiSourceContainer to notify when new realtime
				# sources are available.  For now accept anything that is available.
				# It can be assumed from here forward that the MultiSourceContainer will
				# have a realtime source available.
				if not self.forecast:
					container.getPreferredSourceContainer(self, AnySource, firstRealtimeContainerAvailable())
				else:
					container.getDailyContainer(self, AnySource, firstRealtimeContainerAvailable())
			else:
				loop.create_task(firstRealtimeContainerAvailable())

		async def firstRealtimeContainerAvailable():
			# This should only be called once!
			if not self.forecast:
				anyRealtimeContainer = self.container.getRealtimeContainer(self.source, realtimePossible) or self.container.getRealtimeContainer(self.source, False)
			else:
				anyRealtimeContainer = self.container.getDaily(self.source)

			# Not picky about the source, so just try to connect to anything
			self.connectRealtime(anyRealtimeContainer)

			if self.source is not AnySource and anyRealtimeContainer.source is self.source:
				# Correct source found on first attempt, and it's already connected!
				if not anyRealtimeContainer.isRealtime and not anyRealtimeContainer.isRealtimeApproximate:
					# The source is correct, but it isn't true real value has not been added yet.
					# have the container notify when it is.  This is currently not exactly necessary, since
					# the container is already listening for any changes to the container.  However, it's
					# eventually a 'connect to any true realtime source' will be implemented, and it will be
					# necessary then.

					if not self.forecast:
						def requirementCheck(sources: Iterable['Observation']):
							return any(isinstance(obs, RealtimeSource) for obs in sources)
					else:
						def requirementCheck(sources: Iterable['Observation']):
							return any(isinstance(obs, TimeseriesSource) and obs.period >= timedelta(days=0.8) for obs in sources)

					connect = partial(self.connectRealtime, anyRealtimeContainer)
					anyRealtimeContainer.notifyOnRequirementsMet(self, requirementCheck, connect)

			elif (self.source is AnySource
			      and not self.forecast
			      and realtimePossible
			      and anyRealtimeContainer.isRealtimeApproximate):
				# A true real time source is possible and better than what is
				# currently connected.
				container.getTrueRealtimeContainer(self, AnySource, approximateRealtimeOnLastAttempt())

			elif self.forecast and self.source != anyRealtimeContainer.source:
				# There's a preferred source, but this ain't it...ask the MultiSourceContainer
				# to notify when the preferred source is available.
				container.getPreferredSourceContainer(self, self.source, notPreferredSourceOnLastAttempt())

		# This should be called when a source is specified or changed
		async def notPreferredSourceOnLastAttempt():
			if not self.forecast:
				preferredSourceContainer = self.container.getRealtimeContainer(self.source)
			else:
				preferredSourceContainer = self.container.getDaily(self.source)

			# This should never happen
			if preferredSourceContainer is None:
				raise Exception(f'{self.source} is not a valid source or the plugin is not Loaded')

			# This should also never happen
			if preferredSourceContainer.source is not self.source:
				container.getPreferredSourceContainer(self, self.source, notPreferredSourceOnLastAttempt())
				return

			# If the preferred source does not have a realtime value
			if not self.forecast and not preferredSourceContainer.isRealtime:
				# However, the source plugin's schema says it never will
				if preferredSourceContainer.isRealtimeApproximate:
					self.connectRealtime(preferredSourceContainer)
					return

				# For now, it's better than the current connection
				if not self.__connectedContainer.isRealtime:
					self.connectRealtime(preferredSourceContainer)

				def requirementCheck(sources: Iterable['Observation']):
					return any(isinstance(obs, RealtimeSource) for obs in sources)

				# We have the correct source, but a realtime value has not been received yet
				preferredSourceContainer.notifyOnRequirementsMet(self, requirementCheck, wasPreferredSourceButNotTrueRealtime())

		# This should be called when any source will be accepted
		async def approximateRealtimeOnLastAttempt():
			# ask for containers again, but only those with true realtime sources
			trueRealtimeContainer = self.container.getRealtimeContainer(AnySource, strict=True)

			# Still no true realtime sources check if any of the loaded plugins
			# have a realtime source according to their respective schemas
			# This should never happen though.
			if trueRealtimeContainer is None:
				raise Exception(f'No true realtime source found for {self.source}')

			# # "I'll fuckin' do it again! guh-HYuK"
			# if realtimePossible:
			# 	if self.__requestAttempts < 10:
			# 		self.__requestAttempts += 1
			# 		container.getPreferredSourceContainer(self.source, firstRealtimeContainerAvailable())
			# 	else:
			# 		# TODO: Implement a time scheduled check and disconnect from MultiSourceContainer
			# 		pass
			#
			# # Accept a realtime approximate source and connect to it if not already
			# loop.create_task(self.connectToAny())

			# If the preferred source does not have a realtime value
			if trueRealtimeContainer.isRealtimeApproximate:
				# However, the source plugin's schema says it never will
				if trueRealtimeContainer.isTimeSeriesOnly:
					self.connectRealtime(trueRealtimeContainer)

				# For now, it's better than the current connection
				if not self.__connectedContainer.isRealtime:
					self.connectRealtime(trueRealtimeContainer)

				def requirementCheck(sources: Iterable['Observation']):
					return any(isinstance(obs, RealtimeSource) for obs in sources)

				# We have the correct source, but a realtime value has not been received yet
				trueRealtimeContainer.notifyOnRequirementsMet(requirementCheck, approximateRealtimeOnLastAttempt())
				return

			# Everything checks out, connect to the realtime source
			self.connectRealtime(trueRealtimeContainer)

		async def wasPreferredSourceButNotTrueRealtime():
			preferredTrueRealtimeContainer = self.container.getRealtimeContainer(self.source, strict=True)
			self.connectRealtime(preferredTrueRealtimeContainer)

		loop.create_task(startConnecting())

	def connectRealtime(self, container: Container):
		if self.__connectedContainer is container:
			return True
		try:
			disconnected = self.disconnectRealtime()
		except ValueError:
			disconnected = True
		if not disconnected:
			raise ValueError('Failed to disconnect from existing timeseries')

		connected = container.channel.connectSlot(self.updateSlot)
		if connected:
			self.__connectedContainer = container
			log.debug(f'Realtime {self.key.name} connected to {self.__connectedContainer!r}')
		else:
			log.warning(f'Realtime {self.key.name} failed to connect to {container}')
			return

		# The logic for after a connection is made
		if container.metadata['type'] == 'icon' and container.metadata['iconType'] == 'glyph':
			fontName = container.metadata['glyphFont']
			if fontName == 'WeatherIcons':
				self.display.valueTextBox.textBox.setFont(weatherGlyph)
		if self.title.isEnabled() and self.title.allowDynamicUpdate():
			title = container.value['title']
			self.title.setText(title)
		self.lastUpdate = get_event_loop().time()
		self.display.splitter.updateUnitDisplay()
		self.__updateTimeOffsetLabel()

		self.display.refresh()
		self.updateToolTip()
		return connected

	def disconnectRealtime(self) -> bool:
		if self.__connectedContainer is not None:
			disconnected = self.__connectedContainer.source.publisher.disconnectChannel(self._key, self.updateSlot)
			if disconnected:
				log.debug(f'Realtime {self.key.name} disconnected from {self.__connectedContainer}')
				self.__connectedContainer = None
			else:
				log.warning(f'Realtime {self.key.name} failed to disconnect from {self.__connectedContainer}')
			return disconnected
		raise ValueError('No timeseries connected')

	@asyncSlot(MultiSourceContainer)
	async def testSlot(self, container: MultiSourceContainer):
		if isinstance(container, MultiSourceContainer):
			self.container = container
			ValueDirectory.getChannel(self.key).disconnectSlot(self.testSlot)

	def adjustContentStaleTimer(self):
		now = get_event_loop().time()
		last = self.lastUpdate or get_event_loop().time()
		self.updateFreqency = now - last

		def resumeRegularInterval():
			self.contentStaleTimer.stop()
			falloff = self.updateFreqency*0.1
			self.contentStaleTimer.setInterval(1000*falloff)
			self.contentStaleTimer.timeout.disconnect(resumeRegularInterval)
			self.contentStaleTimer.start()

		self.contentStaleTimer.setInterval(1000*(self.updateFreqency + 15))
		self.contentStaleTimer.start()

	@asyncSlot()
	async def updateSlot(self, *args):
		self.__updateTimeOffsetLabel()
		self.setOpacity(1)
		self.display.refresh()
		self.adjustContentStaleTimer()

	def updateToolTip(self):
		try:
			container = self.__connectedContainer
			if container.isDailyOnly:
				self.setToolTip(f'{self.currentSource.name} {self.value.timestamp:%{DATETIME_NO_ZERO_CHAR}m/%{DATETIME_NO_ZERO_CHAR}d}')
			else:
				self.setToolTip(f'{self.currentSource.name} @ {container.now.timestamp:%{DATETIME_NO_ZERO_CHAR}I:%M%p}')

		except AttributeError:
			pass

	def __updateTimeOffsetLabel(self):
		# TODO: fix this
		return
		if self.container.timeseriesOnly:
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

	def changeSource(self, newSource: Plugin):
		self.source = newSource

	@property
	def name(self):
		return f'{str(self._key.name)@TitleCamelCase}-0x{self.uuidShort.upper()}'

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

	def __del__(self):
		self._container.source.publisher.disconnectChannel(self.key, self.updateSlot)
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
			self.text = f'{value:unit=False} {type(value).pluralUnit} ago'
		else:
			self.text = f'in {value: format:{"{value}"}, type: g} {type(value).pluralUnit}'

	def setEnabled(self, enabled: bool) -> None:
		super(TimeOffsetLabel, self).setEnabled(enabled)
		if enabled:
			self.show()
			connectSignal(qApp.instance().clock.minute, self.refresh)
			self.refresh()
		else:
			self.hide()
			disconnectSignal(qApp.instance().clock.minute, self.refresh)


class LockedRealtime(Realtime):
	savable = False
	deletable = False

	__defaults__ = {
		'geometry':  {'x': 0, 'y': 0, 'width': '100px', 'height': '100px'},
		'movable':   False,
		'resizable': False,
		'locked':    True,
	}

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
		state = {'key': str(item.key)}
		info = QMimeData()
		info.state = state
		info.setText(str(item.key))
		info.setData('text/plain', QByteArray(str(item.key).encode('utf-8')))
		drag = QDrag(self.scene().views()[0])
		drag.setPixmap(item.pix)
		drag.setHotSpot(item.rect().center().toPoint())
		# drag.setParent(child)
		drag.setMimeData(info)
		self.parent.collapse()
		self.parent.startHideTimer(.5)
		drag.start()

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


class MeasurementDisplayProperties(Stateful):
	# __slots__ = ('__label', '__maxLength', '__precision', '__forcePrecision', '__unitSpacer', '__unitPosition', '__suffix',
	# '__decorator', '__shorten', '__decimalSeparator', '__radixPoint', '__valueMargins', '__unitMargins', '__dict__')

	Label: 'DisplayLabel'
	maxLength: int
	precision: int
	forcePrecision: bool
	unitSpacer: str
	unitPosition: DisplayPosition
	unit: Type[Measurement] | None
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

	def __init__(self, label: 'DisplayLabel', **kwargs):
		kwargs = self.prep_init(kwargs)
		self.label = label
		self.state = kwargs
		if 'unit' in kwargs:
			unitDict = kwargs['unit']
			position = unitDict.pop('position', Unset)
			if position is not Unset and self.__unitPosition is Unset:
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

	def __copy__(self):
		return MeasurementDisplayProperties(self.label, **self.state)

	@property
	def label(self):
		return self.__label

	@label.setter
	def label(self, value):
		self.__label = value

	@property
	def __isValid(self) -> bool:
		return self.measurement is not None

	@StateProperty(key='unit-string', default=Unset, allowNone=False)
	def unit_string(self) -> str:
		if self.__unit is Unset:
			return getattr(self.measurement, 'unit', '')
		return self.__unit

	@unit_string.setter
	def unit_string(self, value):
		self.__unit = value

	@unit_string.condition
	def unit_string(self, value):
		return value != getattr(self.measurement, 'unit', value)

	@property
	def hasUnit(self) -> bool:
		if self.__label.value is not None and hasattr(self.__label.value, '@unit'):
			unit = self.__label.value['@unit']
			return unit is not None or len(unit) == 0
		return False

	@StateProperty(default=Unset, allowNone=False)
	def maxLength(self) -> int:
		if self.__maxLength is Unset and self.__isValid:
			return self.__label.value['@max']
		return self.__maxLength

	@maxLength.condition
	def maxLength(self) -> bool:
		return getattr(self, '__maxLength', Unset) is not Unset

	@maxLength.setter
	def maxLength(self, value: int):
		self.__maxLength = value

	@StateProperty(default=Unset, allowNone=False)
	def precision(self) -> int:
		if self.__precision is Unset and self.__isValid:
			return self.__label.value['@precision']
		return self.__precision

	@precision.setter
	def precision(self, value: int):
		self.__precision = value

	@precision.condition
	def precision(self) -> bool:
		return getattr(self, '__precision', Unset) is not Unset

	@StateProperty(default=Unset, allowNone=False)
	def unitSpacer(self) -> str:
		if self.__unitSpacer is Unset and self.__isValid:
			return self.__label.value['@unitSpacer']
		return self.__unitSpacer

	@unitSpacer.setter
	def unitSpacer(self, value: str):
		self.__unitSpacer = value

	@unitSpacer.condition
	def unitSpacer(self) -> bool:
		return getattr(self, '__unitSpacer', Unset) is not Unset

	@StateProperty(default=DisplayPosition.Auto, allowNone=False, singleVal=True)
	def unitPosition(self) -> DisplayPosition:
		if self.__unitPosition == DisplayPosition.Auto:
			if self.__isValid:
				if self.__label.value['@showUnit']:
					unitText = f'{self.__label.value.value:format: {"{unit}"}}'
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
		if hasattr(self.label, 'splitter'):
			self.label.splitter.updateUnitDisplay()

	@unitPosition.decode
	def unitPosition(self, value: str) -> DisplayPosition:
		return DisplayPosition[value]

	@unitPosition.condition
	def unitPosition(self) -> bool:
		return getattr(self, '__unitPosition', Unset) is not Unset

	@StateProperty(default=Unset, allowNone=False)
	def suffix(self) -> str:
		if self.__suffix is Unset and self.__isValid:
			return self.__label.value['@suffix']
		return self.__suffix

	@suffix.setter
	def suffix(self, value: str):
		self.__suffix = value

	@suffix.condition
	def suffix(self) -> bool:
		return getattr(self, '__suffix', Unset) is not Unset

	@StateProperty(default=Unset, allowNone=False)
	def decorator(self) -> str:
		if self.__decorator is Unset and self.__isValid:
			return self.__label.value['@decorator']
		return self.__decorator

	@decorator.setter
	def decorator(self, value: str):
		self.__decorator = value

	@decorator.condition
	def decorator(self) -> bool:
		return getattr(self, '__decorator', Unset) is not Unset

	@StateProperty(default=Unset, allowNone=False)
	def shorten(self) -> bool:
		if self.__shorten is Unset and self.__isValid:
			return self.__label.value['@shorten']
		return self.__shorten

	@shorten.setter
	def shorten(self, value: bool):
		self.__shorten = value

	@shorten.condition
	def shorten(self) -> bool:
		return getattr(self, '__shorten', Unset) is not Unset

	# ! This is broken
	@StateProperty(default=Unset, allowNone=False)
	def decimalSeparator(self) -> str:
		# if self.__decimalSeparator is None and self.__isValid:
		# 	return self.__label.value['@decimalSeparator']
		return self.__decimalSeparator

	@decimalSeparator.setter
	def decimalSeparator(self, value: str):
		self.__decimalSeparator = value

	@decimalSeparator.condition
	def decimalSeparator(self) -> bool:
		return getattr(self, '__decimalSeparator', Unset) is not Unset

	@StateProperty(default=Unset, allowNone=False)
	def radixPoint(self) -> str:
		# if self.__radixPoint is None and self.__isValid:
		# 	return self.__label.value['@radixPoint']
		return self.__radixPoint

	@radixPoint.setter
	def radixPoint(self, value: str):
		self.__radixPoint = value

	@radixPoint.condition
	def radixPoint(self) -> bool:
		return getattr(self, '__radixPoint', Unset) is not Unset

	@StateProperty(key='unitSize', default=0.2, singleVal=True, allowNone=False)
	def valueUnitRatio(self) -> Size.Height:
		if self.__isValid:
			return self.__valueUnitRatio
		return Size.Height(1.0, relative=True)

	@valueUnitRatio.setter
	def valueUnitRatio(self, value: Size.Height):
		if value is None:
			self.__valueUnitRatio = value
		else:
			if value.relative:
				value = clamp(value, 0.1, 0.9)
			self.__valueUnitRatio = value

	@valueUnitRatio.decode
	def valueUnitRatio(value: str | int | float) -> Size.Height:
		return Size.Height(value)

	@valueUnitRatio.condition
	def valueUnitRatio(self):
		return self.unitPosition != DisplayPosition.Hidden and self.unitPosition != DisplayPosition.Floating

	@StateProperty(key='format', default=None, allowNone=True)
	def formatString(self) -> str | None:
		try:
			return self.__format
		except AttributeError:
			return None

	@formatString.setter
	def formatString(self, value: str):
		self.__format = value

	def format(self, value: Measurement) -> str:
		if self.formatString is not None and isinstance(value, Measurement):
			return f'{value: format:{self.formatString}}'
		elif value is None:
			return "⋯"
		return str(value)

	@property
	def measurement(self) -> Measurement | datetime | None:
		value = self.localGroup.value
		if isinstance(value, ObservationValue):
			value = value.value
		# if isinstance(value, Measurement):
		# 	pass
		# elif isinstance(value, datetime):
		# 	return value
		# if not isinstance(value, Measurement):
		# 	pass
		if (convertTo := self.convertTo) is not None and value is not None:
			try:
				value = convertTo(value)
			except Exception as e:
				log.warning(f'Could not convert {value} to {convertTo}', exc_info=e)
		if hash((value, type(value))) != self.__measurementHash:
			self.__measurementHash = hash((value, type(value)))
			list(i.textBox.refresh() for i in self.childItems() if isinstance(i, UnitLabel))
		return value

	@property
	def text(self) -> str:
		measurement = self.measurement
		if isinstance(measurement, Measurement):
			if (formatString := self.formatString) is not None and measurement is not None:
				if isinstance(formatString, dict):
					formatString = f'{", ".join(f"{k}: {value}" for k, value in formatString.items())}'
				return f'{measurement:{formatString}}'
			elif measurement is None:
				return "⋯"
			elif self.unitPosition != DisplayPosition.Inline:
				return measurement.withoutUnit
			return str(measurement).strip()
		elif isinstance(measurement, datetime):
			formatString = self.formatString or '%H:%M:%S'
			return f'{measurement:{formatString}}'.lower()
		elif measurement is None:
			return "⋯"
		return str(measurement).strip()

	@StateProperty(default=None)
	def convertTo(self) -> Type[Measurement] | None:
		try:
			return self.__convertTo
		except AttributeError:
			return None

	@convertTo.setter
	def convertTo(self, value: Type[Measurement] | None):
		self.__convertTo = value

	@convertTo.decode
	def convertTo(self, value: str) -> Type[Measurement] | Type[timedelta]:
		match value:
			case 'relative-time' | 'relative-date' | 'relative-timestamp':
				return Second
			case _:
				return autoMeasurement(value)

	@convertTo.encode
	def convertTo(self, value: Type[Measurement]) -> str | None:
		# TODO: Add support for writing 'relative-time' and 'relative-date'
		match value:
			case type() if issubclass(value, Measurement):
				return value.unit or value.id
			case Measurement():
				return type(value).unit or type(value).id
			case timedelta():
				return 'relative-timestamp'
			case _:
				return None

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

	def __iter__(self):
		return iter(self.toDict())


def withoutUnit(self):
	return self.value['@withoutUnit']


class UnitLabel(Label, tag=...):
	deletable = False

	__exclude__ = {'items', 'geometry', 'locked', 'frozen', 'movable', 'resizable', 'text'}

	def __init__(self, parent: Panel,
		reference: Label,
		alignment: Alignment = None,
		filters: list[str] = None,
		font: QFont = None,
		*args, **kwargs):
		self.reference = reference
		super().__init__(parent=parent, alignment=alignment, filters=filters, font=font, *args, **kwargs)
		self.setResizable(False)
		self.setMovable(False)

	@StateProperty
	def text(self) -> str:
		pass

	@text.condition
	def text(self, value: str):
		return value != getattr(self.referenceValue, '@unit', Unset) << OrUnset >> getattr(self.referenceValue, 'unit', None)

	@property
	def referenceValue(self) -> Any:
		return self.parent.value

	@property
	def isEmpty(self):
		return False

	@cached_property
	def textBox(self):
		box = TextHelper(self, self.reference.textBox)
		box.setParentItem(self)
		return box


class DisplayLabel(Display):
	deletable = False

	def __init__(self, *args, **kwargs):
		self.text = "⋯"
		super().__init__(*args, **kwargs)
		self.displayType = DisplayType.Text

		self.splitter = MeasurementUnitSplitter(surface=self, value=self.valueTextBox, unit=self.unitTextBox)
		self.setFlag(QGraphicsItem.ItemIsSelectable, False)
		self.setFlag(QGraphicsItem.ItemIsFocusable, False)
		self.setAcceptDrops(False)
		self.value = "⋯"

	def setUnitPosition(self, value: DisplayPosition):
		self.displayProperties.unitPosition = value

	def contextMenuEvent(self, event):
		event.ignore()
		return

	@StateProperty(key='value', sortOrder=0, allowNone=False, default=Stateful)
	def valueTextBox(self) -> Label:
		return self._valueTextBox

	@valueTextBox.setter
	def valueTextBox(self, value: Label):
		self._valueTextBox = value

	@valueTextBox.decode
	def valueTextBox(self, value: dict) -> Label:
		return Label(self, clickable=False, **value)

	@StateProperty(key='unit', allowNone=False, default=Stateful)
	def unitTextBox(self) -> UnitLabel:
		return self._unitTextBox

	@unitTextBox.setter
	def unitTextBox(self, value: UnitLabel):
		self._unitTextBox = value

	@unitTextBox.decode
	def unitTextBox(self, value: dict) -> UnitLabel:
		return UnitLabel(self, self.valueTextBox, clickable=False, **value)

	@StateProperty(unwrap=True, allowNone=False, default=Stateful)
	def displayProperties(self) -> MeasurementDisplayProperties:
		return self._displayProperties

	@displayProperties.setter
	def displayProperties(self, value: MeasurementDisplayProperties):
		self._displayProperties = value

	@displayProperties.decode
	def displayProperties(self, value: dict | float | str) -> MeasurementDisplayProperties:
		match value:
			case float(value):
				value = {'valueUnitRatio': value}
			case str(value):
				value = {'unitPosition': DisplayPosition[value]}
			case _:
				pass
		return MeasurementDisplayProperties(self, **value)

	@property
	def type(self):
		return self.displayProperties.displayType

	@property
	def value(self):
		return self.valueTextBox.textBox.value

	@value.setter
	def value(self, value):
		self.valueTextBox.textBox.value = value
		self.unitTextBox.textBox.refresh()
		self.splitter.updateUnitDisplay()

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

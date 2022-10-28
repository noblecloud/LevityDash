from asyncio import get_event_loop, gather, get_running_loop, Task
from abc import abstractmethod
from datetime import timedelta, datetime
from functools import cached_property, partial
from numbers import Number
from typing import Iterable, Type, Dict

from PySide2.QtCore import QByteArray, QMimeData, Qt, QThread, QTimer, QRectF
from PySide2.QtGui import QDrag, QFocusEvent, QFont, QPainter, QPixmap, QTransform
from PySide2.QtWidgets import QGraphicsItem, QGraphicsSceneMouseEvent, QStyleOptionGraphicsItem
from qasync import asyncSlot, QApplication

from LevityDash import LevityDashboard
from LevityDash.lib.config import DATETIME_NO_ZERO_CHAR
from LevityDash.lib.ui.icons import fa as FontAwesome, getIcon, Icon
from WeatherUnits.time_.time import Second
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins import Plugin, Plugins, Container
from LevityDash.lib.plugins.plugin import AnySource, SomePlugin
from LevityDash.lib.plugins.dispatcher import MultiSourceContainer, ValueDirectory
from LevityDash.lib.ui.fonts import FontWeight
from LevityDash.lib.ui.frontends.PySide import UILogger as guiLog
from LevityDash.lib.ui.frontends.PySide.utils import DisplayType, mouseHoldTimer
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import NonInteractiveLabel as Label, TitleLabel
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Resize import ResizeHandle
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Splitters import TitleValueSplitter, MeasurementUnitSplitter
from LevityDash.lib.ui.frontends.PySide.Modules.Menus import RealtimeContextMenu
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.ui.Geometry import (
	getDPI, Size, LocationFlag, AlignmentFlag, DisplayPosition, parseSize,
	RelativeFloat, size_px
)
from LevityDash.lib.utils.shared import (disconnectSignal, Now, TitleCamelCase, Unset, connectSignal,
                                         clearCacheAttr)
from LevityDash.lib.stateful import StateProperty, Stateful
from LevityDash.lib.plugins.observation import RealtimeSource, ObservationValue, TimeseriesSource
from WeatherUnits import Measurement, auto as autoMeasurement, Length

qApp: QApplication

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


class RealtimeTitle(TitleLabel):
	parent: 'Realtime'

	__defaults__ = {}


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

	# Section Realtime
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
		yield 'title', self.title
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
		title = RealtimeTitle(self, stateKey=TitleValueSplitter.title)
		return title

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
		container = LevityDashboard.get_container(value)

		if self.title.allowDynamicUpdate():
			self.title.textBox.setTextAccessor(lambda: container.title)
			if not self.title.isEnabled():
				self.title.textBox.setTextAccessor(None)
		self.title.textBox.refresh()
		self.container = container

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
		source = LevityDashboard.plugins.get(value, AnySource)
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
			self.container = LevityDashboard.get_container(self.key)

	@property
	def currentSource(self) -> Plugin | None:
		if self.__connectedContainer is not None:
			return self.__connectedContainer.source

	@StateProperty(allowNone=False, default=Stateful, link=Display)
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
	def splitter(self, value: dict | bool | float | str) -> dict:
		match value:
			case bool(value):
				value = {'visible': value}
			case float(value):
				value = {'ratio': value}
			case str(value):
				value = {'text': value}
			case _:
				pass
		return value

	@splitter.factory
	def splitter(self) -> TitleValueSplitter:
		return TitleValueSplitter(surface=self, title=self.title, value=self.display)

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
				for plugin in LevityDashboard.plugins.enabled_plugins
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
			log.verbose(f'Realtime {self.key.name} connected to {self.__connectedContainer!r}', verbosity=1)
		else:
			log.warning(f'Realtime {self.key.name} failed to connect to {container}')
			return

		# The logic for after a connection is made
		if container.metadata['type'] == 'icon' and container.metadata['iconType'] == 'glyph':
			self.display.valueTextBox.textBox.setTextAccessor(None)
		if self.title.isEnabled() and self.title.allowDynamicUpdate():
			self.title.textBox.setTextAccessor(lambda: container.value['title'])
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
			LevityDashboard.get_channel(self.key).disconnectSlot(self.testSlot)

	def adjustContentStaleTimer(self):
		if QThread.currentThread() is QApplication.instance().thread():
			loop.call_soon_threadsafe(self.adjustContentStaleTimer)
			return

		self.__updateTimeOffsetLabel()
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
		self.setOpacity(1)
		self.display.refresh()
		self.updateToolTip()
		loop.call_soon_threadsafe(self.adjustContentStaleTimer)

	def updateToolTip(self):
		try:
			container = self.__connectedContainer
			name = self.currentSource.name
			if not container.isRealtime:
				if (s := getattr(self.value, 'source', None)) is not None and (n := getattr(s, 'name', None)) is not None:
					name += f': {n}'
			if container.isDailyOnly:
				self.setToolTip(f'{name} {self.value.timestamp:%{DATETIME_NO_ZERO_CHAR}m/%{DATETIME_NO_ZERO_CHAR}d}')
			else:
				self.setToolTip(f'{name} @ {container.now.timestamp:%{DATETIME_NO_ZERO_CHAR}I:%M%p}')

		except AttributeError:
			self.setToolTip('')

	def __updateTimeOffsetLabel(self):
		value = self.value
		if self.__connectedContainer.isDailyOnly:
			self.timeOffsetLabel.setEnabled(False)
		elif value.isValid and abs(Now() - value.timestamp) > (timedelta(minutes=15) if isinstance(value.source, RealtimeSource) else value.source.period):
			self.timeOffsetLabel.setEnabled(True)
		else:
			self.timeOffsetLabel.setEnabled(False)

	def contentStaled(self):
		self.timeOffsetLabel.setEnabled(True)
		self.setOpacity(sorted((self.opacity() - 0.1, 0.6, 1))[0])
		self.update()

	@property
	def value(self) -> ObservationValue | None:
		if self.__connectedContainer is None:
			return None
		try:
			return self.__connectedContainer.value
		except AttributeError:
			return None

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
		# self.display.valueTextBox.marginHandles.hide()
		# self.display.unitTextBox.marginHandles.hide()
		super(Realtime, self).focusOutEvent(event)

	def changeSource(self, newSource: Plugin):
		self.source = newSource

	@property
	def name(self):
		return f'{str(self._key.name)@TitleCamelCase}-0x{self.uuidShort.upper()}'

	@classmethod
	def validate(cls, item: dict, context=None):
		panelValidation = super(Realtime, cls).validate(item, context)
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
	_connected: bool = False

	def __init__(self, parent, *args, **kwargs):
		kwargs['geometry'] = {'x': 0.7, 'y': 0.85, 'width': 0.3, 'height': 0.15, 'relative': True}
		super(TimeOffsetLabel, self).__init__(parent, alignment=AlignmentFlag.BottomRight, *args, **kwargs)

	def refresh(self):
		if not self.isEnabled():
			return
		offset = Now() - self.parent.value.timestamp
		value = Second(offset.total_seconds()).auto
		value.precision = 0
		if value > 0:
			self.text = f'{value:unit=False} {type(value).pluralUnit} ago'
		else:
			self.text = f'in {value: format:{"{value}"}, type: g} {type(value).pluralUnit}'

	def setEnabled(self, enabled: bool) -> None:
		super(TimeOffsetLabel, self).setEnabled(enabled)
		if enabled:
			self.show()
			self.connectSignal()
			self.refresh()
		else:
			self.hide()
			self.disconnectSignal()

	def connectSignal(self):
		if not self._connected:
			connectSignal(qApp.instance().clock.minute, self.refresh)
			self._connected = True

	def disconnectSignal(self):
		if self._connected:
			disconnectSignal(qApp.instance().clock.minute, self.refresh)
			self._connected = False


class LockedRealtime(Realtime):
	savable = False
	deletable = False

	__defaults__ = {
		'geometry':  {'x': 0, 'y': 0, 'width': '100px', 'height': '100px'},
		'movable':   False,
		'resizable': False,
		'locked':    True,
	}

	# Section LockedRealtime
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
	__measurementHash: int = 0
	__valueUnitRatio: Size.Height = Size.Height(0.2, relative=True)
	_floatingOffset = Size.Height(5, absolute=True)

	"""
	Properties for how a label should display its value.  It is assumed that the value is a WeatherUnit Measurement.
	Attributes that are unset will provide the default value for the Measurement as specified WeatherUnit config.

	Example Config
	--------------
	root:
		maxLength: 2
		precision: 1
		unit: 'F'
		format: '{value}{decorator}'
		unitPosition: 'inline'
		shorten: False
		convertTo: 'Fahrenheit'
		unitSize: 20%
	"""

	label: 'DisplayLabel'
	maxLength: int
	precision: int
	unitPosition: DisplayPosition
	unit_string: str | None
	shorten: bool

	# Section MeasurementDisplayProperties
	"""
	Parameters
	----------
	maxLength : int, optional
		The maximum length of the label.  If the value is longer than this, it will be truncated.
	precision : int, optional
		The number of decimal places to display.  If the value is a float, it will be rounded to this number of decimal places.
	unitDisplayPosition : UnitDisplayPosition, default='Auto'
		How the unit should be displayed.
	shorten : bool, optional
		If True, if the value is longer than the allowed length and there are no decimal places to round, the value will be
		displayed in the next order of magnitude.
			Example: '1024m' becomes '1.0km'
	"""

	def _afterSetState(self):

		self.updateSplitter()

	def updateSplitter(self):
		try:
			self.splitter.updateUnitDisplay()
		except AttributeError:
			pass

	def updateLabels(self):
		if self.__isValid:
			self.valueTextBox.textBox.refresh()
			if self.hasUnit:
				self.unitTextBox.textBox.refresh()

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
		return self.unit_string is not Unset and self.unit_string

	@StateProperty(default=Unset, allowNone=False)
	def maxLength(self) -> int:
		if self.__maxLength is Unset and self.__isValid:
			return getattr(self.measurement, 'max', Unset)
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
			return getattr(self.measurement, 'precision', Unset)
		return self.__precision

	@precision.setter
	def precision(self, value: int):
		self.__precision = value

	@precision.condition(method={'get'})
	def precision(self) -> bool:
		return getattr(self, '__precision', Unset) is not Unset

	@StateProperty(default=LocationFlag.Horizontal, allowNone=False)
	def splitDirection(self) -> LocationFlag:
		return self.__splitDirection

	@splitDirection.setter
	def splitDirection(self, value: LocationFlag):
		self.__splitDirection = value

	@splitDirection.decode
	def splitDirection(self, value: str) -> LocationFlag:
		return LocationFlag[value]

	@cached_property
	def titleSplitter(self) -> TitleValueSplitter | None:
		return self.localGroup.splitter

	@property
	def titleSplitDirection(self) -> LocationFlag:
		if (titleSplitter := getattr(self, 'titleSplitter', None)) is not None:
			return titleSplitter.location
		return LocationFlag.Horizontal

	@property
	def unitPosition(self) -> DisplayPosition:
		if self.__isValid and self.hasUnit:
			if self._unitPosition == DisplayPosition.Auto:
				if getattr(self.measurement, 'showUnit', False):
					if self.titleSplitDirection == LocationFlag.Horizontal:
						unitText = f'{self.measurement:format: {"{unit}"}}'
						if len(unitText) > 2:
							return DisplayPosition.Auto
						elif len(unitText) == 0:
							return DisplayPosition.Hidden
						return DisplayPosition.Inline
					else:
						return DisplayPosition.Inline
				return DisplayPosition.Hidden
			return self._unitPosition
		return DisplayPosition.Hidden

	@unitPosition.setter
	def unitPosition(self, value: DisplayPosition):
		self._unitPosition = value

	@StateProperty(key='unitPosition', default=DisplayPosition.Auto, allowNone=False, after=updateSplitter)
	def _unitPosition(self) -> DisplayPosition:
		return self.__unitPosition

	@_unitPosition.setter
	def _unitPosition(self, value: DisplayPosition):
		self.__unitPosition = value

	@_unitPosition.decode
	def _unitPosition(self, value: str) -> DisplayPosition:
		return DisplayPosition[value]

	@StateProperty(default=Unset, allowNone=False)
	def shorten(self) -> bool:
		if self.__shorten is Unset and self.__isValid:
			return getattr(self.measurement, 'shorten', Unset)
		return self.__shorten

	@shorten.setter
	def shorten(self, value: bool):
		self.__shorten = value

	@shorten.condition
	def shorten(self) -> bool:
		return self.__shorten is not Unset

	@StateProperty(key='unitSize', default=__valueUnitRatio, allowNone=True)
	def _unitSize(self) -> Size.Height:
		return self.__valueUnitRatio

	@_unitSize.setter
	def _unitSize(self, value: Size.Height):
		self.__valueUnitRatio = value

	@_unitSize.decode
	def _unitSize(self, value: str | int | float | Length) -> Size.Height:
		value = parseSize(value, Size.Height(0.2, relative=True))
		if isinstance(value, Length):
			value = Size.Height(value)
		return value

	@_unitSize.encode
	def _unitSize(self, value: Size.Height) -> str:
		return str(value)

	@_unitSize.condition
	def _unitSize(self):
		return self.unitPosition != DisplayPosition.Hidden \
		       and self.unitPosition != DisplayPosition.Floating \
		       and self.unitSize is not None

	@property
	def valueUnitRatio(self) -> Size.Height:
		if self.__isValid:
			value = self.__valueUnitRatio
			if not isinstance(value, RelativeFloat):
				value = value.toRelative(self.geometry.absoluteHeight)
			return value
		return Size.Height(0.0, relative=True)

	@valueUnitRatio.setter
	def valueUnitRatio(self, value: Size.Height):
		existing = self.__valueUnitRatio
		if isinstance(existing, RelativeFloat):
			pass
		elif existing.isPhysicalMeasurement and isinstance(value, RelativeFloat):
			value = Length.Inch(value.toAbsoluteF(self.geometry) / getDPI())
			value = type(existing)(value)
		elif existing.absolute and isinstance(value, RelativeFloat):
			value = value.toAbsolute(self.geometry)
		self.__valueUnitRatio = value

	@property
	def unitSize(self) -> Size.Height | None:
		value = self.__valueUnitRatio
		if value is MeasurementDisplayProperties._unitSize.default(type(self)):
			return None
		return value

	@property
	def unitSize_px(self) -> float | None:
		if u := self.unitSize:
			return u.toAbsoluteF(self.geometry.absoluteHeight)

	@property
	def relativeUnitSize(self) -> Size.Height | None:
		value = self.__valueUnitRatio
		if value is MeasurementDisplayProperties.valueUnitRatio.default(type(self)):
			return None
		if not isinstance(value, RelativeFloat):
			value = value.toRelative(self.geometry.absoluteHeight)
		return value

	@StateProperty(key='floating-offset', default=_floatingOffset)
	def floatingOffset(self) -> Size.Height | Length:
		return self._floatingOffset

	@floatingOffset.setter
	def floatingOffset(self, value: Size.Height | Length):
		self._floatingOffset = value
		if isinstance(value, RelativeFloat):
			value.relativeTo = self.parent

	@floatingOffset.decode
	def floatingOffset(self, value: str | int | float | Number) -> Size.Height | Length:
		return parseSize(value, DisplayLabel.floatingOffset.default)

	@property
	def floatingOffset_px(self) -> float:
		return size_px(self.floatingOffset, self.geometry)

	@StateProperty(key='format', default=None, allowNone=True)
	def formatString(self) -> str | None:
		try:
			return self.__format
		except AttributeError:
			return None

	@formatString.setter
	def formatString(self, value: str):
		self.__format = value

	@StateProperty(key='format-hint', default=None, allowNone=True, after=updateLabels)
	def formatHint(self) -> str | None:
		return getattr(self.valueTextBox.textBox, '_formatHint', None)

	@formatHint.setter
	def formatHint(self, value: str):
		self.valueTextBox.textBox._formatHint = value

	def format(self, value: Measurement) -> str:
		formatString = self.formatString
		if formatString is not None:
			if isinstance(value, Measurement):
				formatString = f'format:{formatString}'
			elif isinstance(value, datetime):
				other_ = '%-' if DATETIME_NO_ZERO_CHAR == '#' else '%#'
				formatString = formatString.replace(other_, f'%{DATETIME_NO_ZERO_CHAR}')
			return value.__format__(formatString)
		elif value is None:
			return "⋯"
		return str(value)

	@property
	def measurement(self) -> Measurement | datetime | None:
		value = self.localGroup.value
		if isinstance(value, ObservationValue):
			value = value.value
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
	def icon(self) -> Icon | None:
		value = self.localGroup.value
		if isinstance(value, ObservationValue) and value.isIcon:
			value = value.icon
		else:
			return None
		icon = getIcon(value)
		return icon

	@property
	def text(self) -> str | None:
		measurement = self.measurement
		if isinstance(measurement, Measurement):
			if (precision := self.precision) is not Unset and measurement.precision != precision:
				measurement.precision = precision
			if (formatString := self.formatString) is not None and measurement is not None:
				if isinstance(formatString, dict):
					formatString = f'{", ".join(f"{k}: {value}" for k, value in formatString.items())}'
				return f'{measurement:{formatString}}'
			elif measurement is None:
				return None
			elif self.unitPosition != DisplayPosition.Inline:
				return measurement.withoutUnit
			return str(measurement).strip()
		elif isinstance(measurement, datetime):
			formatString = self.formatString or '%H:%M:%S'
			other_ = '%-' if DATETIME_NO_ZERO_CHAR == '#' else '%#'
			formatString = formatString.replace(other_, f'%{DATETIME_NO_ZERO_CHAR}')
			try:
				return f'{measurement:{formatString}}'.lower()
			except ValueError:
				print(f'Invalid format string: {formatString}')
				return f'{measurement:%H:%M:%S}'.lower()
		elif measurement is None:
			return None
		if (not measurement) and self.nullValue is not None:
			return self.nullValue
		return str(measurement).strip() or self.nullValue

	@StateProperty(key='null', default=None, after=updateLabels)
	def nullValue(self) -> str | None:
		return getattr(self, '__null', None)

	@nullValue.setter
	def nullValue(self, value: str | None):
		self.__null = value

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


def withoutUnit(self):
	return self.value['@withoutUnit']


class UnitLabel(Label, tag=...):
	deletable = False

	__exclude__ = {'items', 'geometry', 'locked', 'frozen', 'movable', 'resizable', 'text'}

	# Section UnitLabel
	def __init__(self, parent: Panel,
		properties: Label,
		*args, **kwargs):
		self.displayProperties = properties
		super().__init__(parent=parent, *args, **kwargs)
		self.textBox.setTextAccessor(self.unitText)

	def unitText(self) -> str:
		value = self.localGroup.value
		if isinstance(value, ObservationValue):
			value = value.value
		return getattr(value, 'unit', '')

	# @property
	# def marginRect(self) -> QRectF:
	# 	return super().marginRect()

	@property
	def isEmpty(self):
		return False


class DisplayLabel(Display, MeasurementDisplayProperties):
	"""
  display:
    unitSize: 0.9
    valueLabel:
      alignment: center
      margins: 0%, 0%, 0%, 0%
    unitLabel:
      alignment: top
      margins:
        top: 0%
        right: 10px
        bottom: 0%
        left: 0%
	"""

	__exclude__ = {'items', 'geometry', 'locked', 'frozen', 'movable', 'resizable', 'text'}

	deletable = False

	class ValueLabel(Label, tag=..., defaultIcon=FontAwesome.getIcon('ellipsis', 'solid')):

		__defaults__ = {
			'weight': FontWeight.Regular,
		}

		__exclude__ = {..., 'format-hint'}

		@property
		def marginRect(self) -> QRectF:
			rect = Label.marginRect.fget(self)
			if p := self.parent:
				if (u := p.displayProperties.unitSize_px) and p.displayProperties.unitPosition is DisplayPosition.FloatUnder:
					r = QRectF(rect)
					rr = self.rect()
					r.setBottom(rr.bottom() - u - p.displayProperties.floatingOffset_px)
					return r
			return rect


		@property
		def unitSpace(self) -> QRectF:
			textRect = self.textBox.sceneBoundingRect()
			labelRect = self.mapRectFromScene(textRect)
			ownRect = self.rect()
			ownRect.setTop(labelRect.bottom() + self.parent.floatingOffset_px)
			return ownRect


	# Section DisplayLabel
	def __init__(self, *args, **kwargs):
		self.displayProperties = self
		super().__init__(*args, **kwargs)
		self.displayType = DisplayType.Text
		self.setFlag(QGraphicsItem.ItemIsSelectable, False)
		self.setFlag(QGraphicsItem.ItemIsFocusable, False)
		self.setAcceptDrops(False)

	def _init_args_(self, *args, **kwargs) -> None:
		# self._valueTextBox = Label(self)
		# self._unitTextBox = UnitLabel(self, self._valueTextBox)
		super()._init_args_(*args, **kwargs)
		self.splitter = MeasurementUnitSplitter(surface=self, value=self.valueTextBox, unit=self.unitTextBox)

	def setUnitPosition(self, value: DisplayPosition):
		self.displayProperties.unitPosition = value
		if isinstance(value, str):
			value = DisplayPosition[value]
		if not isinstance(value, DisplayPosition):
			raise TypeError('titlePosition must be a DisplayPosition')
		if value.casefold() in {'left', 'right'}:
			self.splitter.location = LocationFlag.Vertical
			clearCacheAttr(self.splitter, 'cursor')
			self.splitter.resetPath()
		try:
			self.splitter.setGeometries()
		except Exception as e:
			pass
		self.refresh()

	def contextMenuEvent(self, event):
		event.ignore()
		return

	@StateProperty(key='valueLabel', sortOrder=0, allowNone=False, default=Stateful, dependancies={'geometry'})
	def valueTextBox(self) -> Label:
		return self._valueTextBox

	@valueTextBox.setter
	def valueTextBox(self, value: Label):
		self._valueTextBox = value

	@valueTextBox.factory
	def valueTextBox(self) -> ValueLabel:
		label = DisplayLabel.ValueLabel(self)
		label.textBox.setValueAccessor(lambda: self.parent.value)
		label.textBox.setTextAccessor(lambda: self.displayProperties.text)
		return label

	@StateProperty(key='unitLabel', allowNone=False, default=Stateful, dependancies={'geometry', 'value'})
	def unitTextBox(self) -> UnitLabel:
		return self._unitTextBox

	@unitTextBox.setter
	def unitTextBox(self, value: UnitLabel):
		self._unitTextBox = value

	@unitTextBox.factory
	def unitTextBox(self) -> UnitLabel:
		label = UnitLabel(self, self.valueTextBox)
		return label

	@property
	def type(self):
		return self.displayProperties.displayType

	@property
	def value(self) -> ObservationValue | None:
		return self.parent.value

	def mouseDoubleClickEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
		mouseEvent.ignore()
		return

	def refresh(self):
		# self.a.setHtml(f'<div style="text-align: center; top: 50%;">{str(self.text)}</div>')
		if self.displayProperties.hasUnit:
			if self.displayProperties.unitPosition is DisplayPosition.FloatUnder:
				self.splitter.fitUnitUnder()

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

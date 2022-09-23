import asyncio
import mimetypes
import os
import platform
import webbrowser
from collections import namedtuple
from datetime import datetime, timedelta
from email.generator import Generator
from email.message import EmailMessage
from functools import cached_property, partial
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict
from zipfile import ZipFile

import PySide2
import sys
from PySide2 import QtGui
from PySide2.QtCore import (
	QByteArray, QEvent, QMimeData, QObject, QRect, QRectF, QSize, Qt, QTimer, QUrl, Signal
)
from PySide2.QtGui import (
	QCursor, QDesktopServices, QDrag, QPainter, QPainterPath, QPixmapCache, QScreen, QShowEvent,
	QSurfaceFormat, QTransform
)
from PySide2.QtWidgets import (
	QAction, QApplication, QGraphicsItem, QGraphicsRectItem, QGraphicsScene,
	QGraphicsView, QMainWindow, QMenu, QMenuBar, QOpenGLWidget
)
from time import perf_counter, time

from LevityDash.lib.plugins.dispatcher import ValueDirectory as pluginManager
from LevityDash.lib.ui.frontends.PySide.utils import (
	colorPalette, RendererScene
)
from WeatherUnits import Length
from . import qtLogger as guiLog
from ...Geometry import AbsoluteFloat, DimensionType, findScreen, getDPI, LocationFlag, parseSize, RelativeFloat, Size
from ....config import userConfig
from ....plugins.categories import CategoryAtom, CategoryItem
from ....utils import BusyContext, clearCacheAttr, joinCase

app: QApplication = QApplication.instance()

ACTIVITY_EVENTS = {QEvent.KeyPress, QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseMove, QEvent.GraphicsSceneMouseMove, QEvent.GraphicsSceneMouseRelease, QEvent.GraphicsSceneMousePress, QEvent.InputMethod,
                   QEvent.InputMethodQuery}

loop = asyncio.get_running_loop()

app.setQuitOnLastWindowClosed(True)
guiLog.info('Loading Qt GUI')


class FocusStack(list):

	def __init__(self, scene: QGraphicsScene):
		super().__init__([scene.base])

	def stepIn(self, item: QGraphicsItem):
		self.append(item)

	def stepOut(self):
		if len(self) > 2:
			self.pop()

	def getCurrent(self):
		return self[-1]

	def getPrevious(self):
		return self[-2]

	def focusAllowed(self, item: QGraphicsItem):
		parent = item.parentItem()
		if not parent in self[-2:]:
			return False
		return parent in self or any(i in self for i in parent.childItems())


ViewScale = namedtuple('ViewScale', 'x y')


# Section Scene
class LevityScene(RendererScene):
	preventCollisions = False
	editingMode = False
	frozen: bool
	focusStack: FocusStack
	view: QGraphicsView

	# Section .init
	def __init__(self, *args, **kwargs):
		self.__view = args[0]
		self.time = time()
		super(LevityScene, self).__init__(*args, **kwargs)
		self.setSceneRect(QRectF(0, 0, self.__view.width(), self.__view.height()))
		from LevityDash.lib.ui.frontends.PySide.Modules import CentralPanel
		self.base = CentralPanel(self)
		self.staticGrid = False
		clearCacheAttr(self, 'geometry')
		self.setBackgroundBrush(Qt.transparent)
		self.busyBlocker = QGraphicsRectItem(self.sceneRect())
		self.busyBlocker.setVisible(False)
		self.addItem(self.busyBlocker)

	def addBusyBlocker(self):
		self.busyBlocker.setZValue(100)
		self.busyBlocker.setVisible(False)
		self.busyBlocker.setBrush(Qt.white)
		self.busyBlocker.setOpacity(0.5)
		self.busyBlocker.setFlag(QGraphicsItem.ItemIsMovable, False)
		self.busyBlocker.setFlag(QGraphicsItem.ItemIsSelectable, False)
		self.busyBlocker.setFlag(QGraphicsItem.ItemIsFocusable, False)
		self.busyBlocker.setFlag(QGraphicsItem.ItemIsPanel)
		self.busyBlocker.setFlag(QGraphicsItem.ItemStopsFocusHandling)
		BusyContext.blocker = self.busyBlocker

	@property
	def view(self) -> 'LevitySceneView':
		return self.__view

	@property
	def viewScale(self) -> ViewScale:
		return ViewScale(self.view.transform().m11(), self.view.transform().m22())

	def stamp(self, *exclude, excludeChildren=True, excludeParent=False):
		e = list(exclude)
		path = QPainterPath()
		if excludeChildren:
			e += [i for j in [i.grandChildren() for i in exclude] for i in j]
		if excludeParent:
			e += [i.parent for i in exclude]
		e = [self.base, self.apiDrawer, *e]
		for child in self.panels:
			if child in e:
				continue
			path += child.sceneShape()
		return path

	def setHighlighted(self, value):
		pass

	def hasCursor(self):
		return True

	def childHasFocus(self):
		return self.base.hasFocus()

	@cached_property
	def panels(self):
		from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
		return [i for i in self.items() if isinstance(i, Panel)]

	@cached_property
	def geometry(self):
		from LevityDash.lib.ui.Geometry import StaticGeometry
		return StaticGeometry(surface=self, position=(0, 0), absolute=True, snapping=False, updateSurface=False)

	@cached_property
	def window(self):
		return app.activeWindow()

	def rect(self):
		return self.sceneRect()

	@property
	def marginRect(self) -> QRectF | QRect:
		return self.sceneRect()

	def size(self):
		return self.sceneRect().size()

	@property
	def frozen(self):
		return False

	@property
	def containingRect(self):
		return self.gridRect()

	def zValue(self):
		return -1

	@property
	def clicked(self):
		return QApplication.instance().mouseButtons() == Qt.LeftButton


class MenuBar(QMenuBar):

	def __init__(self, *args, **kwargs):
		super(MenuBar, self).__init__(*args, **kwargs)

	def showEvent(self, event: QShowEvent) -> None:
		super(MenuBar, self).showEvent(event)
		self.update()
		for menu in self.findChildren(QMenu):
			menu.adjustSize()

	def mouseMoveEvent(self, arg__1: PySide2.QtGui.QMouseEvent) -> None:
		super().mouseMoveEvent(arg__1)
		self.parent().mouseMoveEvent(arg__1)


# Section View
class LevitySceneView(QGraphicsView):
	resizeFinished = Signal()
	loadingFinished = Signal()
	__lastKey = (None, None)

	def __init__(self, *args, **kwargs):
		self.status = 'Initializing'
		self.lastEventTime = perf_counter()
		super(LevitySceneView, self).__init__(*args, **kwargs)
		opengl = userConfig.getOrSet('QtOptions', 'openGL', True, userConfig.getboolean)
		QApplication.instance().resizeFinished = self.resizeFinished

		antialiasing = userConfig.getOrSet('QtOptions', 'antialiasing', True, getter=userConfig.getboolean)
		if opengl:
			viewport = QOpenGLWidget(self)
			if antialiasing:
				antialiasingSamples = int(userConfig.getOrSet('QtOptions', 'antialiasingSamples', 8, getter=userConfig.getint))
				frmt = QSurfaceFormat()
				frmt.setRenderableType(QSurfaceFormat.OpenGL)
				frmt.setSamples(antialiasingSamples)
				viewport.setFormat(frmt)
			self.setViewport(viewport)
		else:
			self.setRenderHint(QPainter.Antialiasing, antialiasing)
			self.setRenderHint(QPainter.SmoothPixmapTransform, antialiasing)
			self.setRenderHint(QPainter.TextAntialiasing, antialiasing)
		self.viewport().setPalette(colorPalette)
		self.maxTextureSize = userConfig.getOrSet('QtOptions', 'maxTextureSize', '20mb', getter=userConfig.configToFileSize)
		guiLog.debug(f'Max texture size set to {self.maxTextureSize / 1000:.0f}KB')
		self.pixmapCacheSize = int(userConfig.getOrSet('QtOptions', 'pixmapCacheSize', '200mb', getter=userConfig.configToFileSize) / 1024)
		QPixmapCache.setCacheLimit(self.pixmapCacheSize)
		guiLog.debug(f'Pixmap cache size set to {self.pixmapCacheSize}KB')

		self.noActivityTimer = QTimer(self)
		self.noActivityTimer.setSingleShot(True)
		self.noActivityTimer.timeout.connect(self.noActivity)
		self.noActivityTimer.setInterval(15000)
		self.setGeometry(0, 0, *self.window().size().toTuple())
		self.graphicsScene = LevityScene(self)
		self.setScene(self.graphicsScene)
		self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
		self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
		self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
		self.setBackgroundBrush(Qt.black)
		self.setStyleSheet('QGraphicsView { border: 0px; }')

		self.setRenderHints(QPainter.HighQualityAntialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)

	def deviceTransform(self) -> QTransform:
		devicePixelRatio = self.devicePixelRatioF()
		return QTransform.fromScale(devicePixelRatio, devicePixelRatio)

	def postInit(self):
		app.primaryScreenChanged.connect(self.__screenChange)
		self.base = self.graphicsScene.base
		self.resizeDone = QTimer(interval=300, singleShot=True, timeout=self.resizeDoneEvent)
		self.installEventFilter(self)
		self.graphicsScene.installEventFilter(self)
		loop.call_soon(self.load)

	def eventFilter(self, obj, event):
		if event.type() in ACTIVITY_EVENTS:
			self.noActivityTimer.start()
			self.setCursor(Qt.ArrowCursor)
		if event.type() == QEvent.KeyPress:
			if event.key() == Qt.Key_R:
				pos = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
				items = self.graphicsScene.items(pos)
				for item in items:
					if hasattr(item, 'refresh'):
						item.refresh()
			shiftHeld = event.modifiers() & Qt.ShiftModifier
			if event.key() == Qt.Key_Down:
				if getattr(self.graphicsScene.focusItem(), 'movable', False):
					moveAmount = 1 if shiftHeld else 0.1
					self.graphicsScene.focusItem().moveBy(0, moveAmount)
			elif event.key() == Qt.Key_Up:
				if getattr(self.graphicsScene.focusItem(), 'movable', False):
					moveAmount = -1 if shiftHeld else -0.1
					self.graphicsScene.focusItem().moveBy(0, moveAmount)
			elif event.key() == Qt.Key_Left:
				if getattr(self.graphicsScene.focusItem(), 'movable', False):
					moveAmount = -1 if shiftHeld else -0.1
					self.graphicsScene.focusItem().moveBy(moveAmount, 0)
			elif event.key() == Qt.Key_Right:
				if getattr(self.graphicsScene.focusItem(), 'movable', False):
					moveAmount = 1 if shiftHeld else 0.1
					self.graphicsScene.focusItem().moveBy(moveAmount, 0)
			elif event.key() == Qt.Key_Escape:
				if self.graphicsScene.focusItem():
					self.graphicsScene.clearFocus()
					self.graphicsScene.clearSelection()
			self.__lastKey = event.key(), loop.time()
		return super(LevitySceneView, self).eventFilter(obj, event)

	def resizeDoneEvent(self):
		self.resetTransform()
		self.graphicsScene.invalidate(self.graphicsScene.sceneRect())
		self.graphicsScene.update()
		self.resizeFinished.emit()
		rect = self.viewport().rect()
		self.setSceneRect(rect)
		self.scene().setSceneRect(rect)
		self.graphicsScene.base.geometry.updateSurface()

	def load(self):
		self.graphicsScene.base.loadDefault()

	@property
	def dpi(self):
		return getDPI(app.activeWindow().screen()) or 96

	def __screenChange(self):
		self.resizeDone.start()

	def resizeEvent(self, event):
		super(LevitySceneView, self).resizeEvent(event)
		self.fitInView(self.base, Qt.AspectRatioMode.KeepAspectRatio)
		self.graphicsScene.busyBlocker.setRect(self.sceneRect())
		self.resizeDone.start()
		self.parent().menuBarHoverArea.size.setWidth(self.width())
		self.parent().menuBarHoverArea.update()
		self.parent().bar.setGeometry(0, 0, self.width(), self.parent().bar.height())

	def noActivity(self):
		self.graphicsScene.clearSelection()
		self.graphicsScene.clearFocus()
		self.setCursor(Qt.BlankCursor)


class PluginsMenu(QMenu):

	def __init__(self, parent):
		super(PluginsMenu, self).__init__(parent)
		self.setTitle('Plugins')
		# self.setIcon(QIcon.fromTheme('preferences-plugin'))
		# self.setToolTipsVisible(True)
		# self.setToolTip('Plugins')
		# refresh = QAction(text='Refresh', triggered=self.refresh)
		# refresh.setCheckable(False)
		# self.addAction(refresh)
		self.buildItems()

	def buildItems(self):
		from LevityDash.lib.plugins import Plugins as pluginManager
		for plugin in pluginManager:
			action = QAction(plugin.name, self)
			action.setCheckable(True)
			action.setChecked(plugin.running)
			action.plugin = plugin
			action.togglePlugin = partial(self.togglePlugin, plugin)
			action.toggled.connect(action.togglePlugin)
			self.addAction(action)

	def refresh_toggles(self):
		for action in self.actions():
			action.setChecked(action.plugin.running)

	@staticmethod
	def togglePlugin(plugin, enabled):
		if enabled:
			plugin.start()
		else:
			plugin.stop()


class InsertMenu(QMenu):
	existing = Dict[CategoryItem, QMenu | QAction]
	source = pluginManager

	def __init__(self, parent):
		super(InsertMenu, self).__init__(parent)
		self.noItems = self.addAction('No items')
		self.noItemsBelow = self.addAction('')
		self.noItems.setEnabled(False)
		self.noItemsBelow.setEnabled(False)
		self.noItemsBelow.setVisible(False)
		self.existing = {}
		self.setTitle('Items')
		self.buildItems()
		self.aboutToShow.connect(self.buildItems)


	def buildItems(self):
		items = sorted(pluginManager.containers(), key=lambda x: str(x.key))
		if items:
			self.noItems.setText('Item key will be')
			self.noItemsBelow.setText('copied to clipboard')
			self.noItemsBelow.setVisible(True)
			skel = CategoryItem.keysToDict([i.key for i in items], extendedKeys=True)
			self.buildLevel(skel, self)
		else:
			self.noItems.setText('No items')
			self.noItemsBelow.setText('')
			self.noItemsBelow.setVisible(False)

	def clearSubMenu(self, menu):
		try:
			menu.hovered_item.refresh_text()
		except AttributeError:
			pass

	def handleMenuHovered(self, action):
		try:
			self.hovered_item.refresh_text()
		except AttributeError:
			pass

		try:
			action.hoverAction()
		except AttributeError:
			pass

		self.hovered_item = action

	def buildLevel(self, level: Dict[CategoryAtom, CategoryItem], menu: QMenu = None):
		menu = menu or self
		if isinstance(level, dict):
			for name, subLevel in level.items():
				if isinstance(subLevel, dict):
					if (subMenu := self.existing.get(name, None)) is None:
						self.existing[name] = subMenu = menu.addMenu(joinCase(name.name, itemFilter=str.title))
						# subMenu.setFont(QFont('monospace', self.font().pointSize()))
						# subMenu.hovered.connect(lambda: self.clearSubMenu(subMenu))
						subMenu.setToolTipsVisible(True)
						subMenu.hovered.connect(self.handleMenuHovered)
					self.buildLevel(subLevel, subMenu)
				elif subLevel not in self.existing:
					self.existing[subLevel] = action = InsertItemAction(menu, key=subLevel)
					menu.addAction(action)
					try:
						action.refresh_text()
					except AttributeError:
						pass
		else:
			if (action := self.existing.get(level, None)) is None:
				self.existing[level] = action = InsertItemAction(menu, key=level)
				menu.addAction(action)
			try:
				action.refresh_text()
			except AttributeError:
				pass
		menu.adjustSize()

	def refresh(self):
		self.buildItems()


class InsertItemAction(QAction):

	def __init__(self, parent, key):
		super(InsertItemAction, self).__init__(parent)
		self.key = key
		self.container = pluginManager.getContainer(key)
		self.name = joinCase(key[-1].name, itemFilter=str.title)
		self.setToolTip(f'Copy key \'{str(key)}\' to clipboard')
		self.setStatusTip(self.toolTip())
		self.triggered.connect(self.toClipboard)
		# self.hovered.connect(self.hoverAction)

	def toClipboard(self):
		clip = QApplication.clipboard()
		clip.setText(str(self.key))

	def hoverAction(self):
		self.setText(str(self.key))

	def refresh_text(self):
		# length = self.parent().width() // self.parent().fontMetrics().averageCharWidth()
		# reminder = length - len(f'{self.name}: ')
		# text = f'{self.name}: {self.value_str.ljust(reminder, "-")}'
		text = f'{self.name}: {self.value_str}'
		self.setText(text)

	@property
	def value_str(self) -> str:
		if not self.container.isRealtime:
			return str(self.container.nowFromTimeseries)
		return str(self.container.realtime)

	def insert(self):
		info = QMimeData()
		info.setText(str(self.key))
		info.setData('text/plain', QByteArray(str(self.key).encode('utf-8')))
		drag = QDrag(self.parent())
		drag.setMimeData(info)
		drag.exec_(Qt.CopyAction)


class LevityMainWindow(QMainWindow):

	def __init__(self, *args, **kwargs):
		super(LevityMainWindow, self).__init__(*args, **kwargs)
		self.setWindowTitle('LevityDash')

		self.__init_ui__()
		view = LevitySceneView(self)
		self.setCentralWidget(view)
		style = '''
					QMenuBar {
						background-color: #2e2e2e;
						padding: 5px;
						color: #fafafa;
					}
					QMenuBar::item {
						padding: 3px 10px;
						margin: 5px;
						background-color: #2e2e2e;
						color: #fafafa;
					}
					QMenuBar::item:selected {
						background-color: #6e6e6e;
						color: #fafafa;
						border-radius: 2.5px;
					}
					QMenuBar::item:disabled {
						background-color: #2e2e2e;
						color: #aaaaaa;
					}
					QMenu {
						background-color: #2e2e2e;
						color: #fafafa;
						padding: 2.5px;
						border: 1px solid #5e5e5e;
						border-radius: 5px;
					}
					QMenu::item {
						padding: 2.5px 5px;
						margin: 1px;
						background-color: #2e2e2e;
						color: #fafafa;
					}
					QMenu::item:selected {
						background-color: #6e6e6e;
						color: #fafafa;
						border-radius: 2.5px;
					}
					QMenu::item:disabled {
						background-color: #2e2e2e;
						color: #aaaaaa;
					}
					QToolTip {
						background-color: #2e2e2e;
						color: #fafafa;
						padding: 2.5px;
						border-width: 1px;
						border-color: #5e5e5e;
						border-style: solid;
						border-radius: 10px;
						font-size: 18px;
						background-clip: border-radius;
					}
					'''
		if platform.system() == 'Darwin':
			style += '''
					QMenu::item::unchecked {
						padding-left: -0.8em;
						margin-left: 0px;
					}
					QMenu::item::checked {
						padding-left: 0px;
						margin-left: 0px;
					}'''
		app.setStyleSheet(style)
		view.postInit()

		from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Various import HoverArea
		self.menuBarHoverArea = HoverArea(
			view.graphicsScene.base,
			size=10,
			rect=QRect(0, 0, self.width(), 50),
			enterAction=self.menuBarHover,
			exitAction=self.menuBarLeave,
			alignment=LocationFlag.Bottom,
			position=LocationFlag.TopLeft,
			ignoredEdges=LocationFlag.Top,
			delay=userConfig.getOrSet('MenuBar', 'delay', 0.3, userConfig.getfloat)
		)
		self.menuBarHoverArea.setEnabled(False)
		if platform.system() != 'Darwin':
			menubar = MenuBar(self)
			self.__menubarHeight = self.menuBar().height() * 2
			self.bar = menubar
			self.setMenuWidget(menubar)
			self.updateMenuBar()
		else:
			self.bar = self.menuBar()

		self.buildMenu()

		self.show()

	def menuBarHover(self):
		self.bar.setFixedHeight(self.bar.sizeHint().height())
		self.menuBarHoverArea.setPos(0, self.__menubarHeight)

	def menuBarLeave(self):
		self.bar.setFixedHeight(0)
		self.menuBarHoverArea.setPos(0, 0)

	def __init_ui__(self):
		envFullscreen = os.getenv('LEVITY_FULLSCREEN', None)
		configFullscreen = userConfig.getOrSet('Display', 'fullscreen', False, getter=userConfig.getboolean)
		if envFullscreen is None:
			fullscreen = configFullscreen
		else:
			try:
				fullscreen = bool(int(envFullscreen))
			except ValueError:
				fullscreen = False

		g = self.geometry()
		screen: QScreen = findScreen()
		guiLog.debug(f'Using screen {screen!r}')
		screenGeometry = screen.geometry()
		width = parseSize(userConfig.getOrSet('Display', 'width', '80%'), 0.8, dimension=DimensionType.width)
		height = parseSize(userConfig.getOrSet('Display', 'height', '80%'), 0.8)

		dpi = getDPI(screen)
		sizeX = screenGeometry.width()
		sizeY = screenGeometry.height()
		physicalSizeX = Length.Inch(sizeX / dpi)
		physicalSizeY = Length.Inch(sizeY / dpi)
		guiLog.debug(f'Screen size: {sizeX}px x {sizeY}px ({physicalSizeX:.3} x {physicalSizeY:.3}) {dpi=:g}')

		match width:
			case AbsoluteFloat() as w:
				width = min(w, screenGeometry.width())
			case RelativeFloat() as w:
				width = min(w * screen.availableSize().width(), screen.availableSize().width())
			case Length() as w:
				w = float(w.inch)
				width = min(w * dpi, screenGeometry.size().width())
			case _:
				width = screen.availableSize().width() * 0.8

		match height:
			case Size.Height(h, absolute=True):
				height = min(h, screenGeometry.height())
			case Size.Height(h, relative=True):
				height = min(h * screen.availableSize().height(), screen.availableSize().height())
			case Length() as h:
				h = float(h.inch)
				height = min(h * dpi, screenGeometry.size().height())
			case _:
				height = screen.availableSize().height() * 0.8

		g.setSize(QSize(round(width), round(height)))
		g.moveCenter(screen.availableGeometry().center())
		self.setGeometry(g)

		similarity = (g.width() / screen.availableSize().width() + g.height() / screen.availableSize().height()) / 2

		if fullscreen or '--fullscreen' in sys.argv or similarity > 0.95:
			self.showFullScreen()

	def buildMenu(self):
		menubar = self.bar
		fileMenu = menubar.addMenu('&File')

		if platform.system() == 'Darwin':
			macOSConfig = QAction('&config', self)
			macOSConfig.setStatusTip('Open the config folder')
			macOSConfig.triggered.connect(self.openConfigFolder)
			fileMenu.addAction(macOSConfig)

		save = QAction('&Save', self)
		save.setShortcut('Ctrl+S')
		save.setStatusTip('Save the current dashboard')
		save.triggered.connect(self.centralWidget().graphicsScene.base.save)

		saveAs = QAction('&Save As', self)
		saveAs.setShortcut('Ctrl+Shift+S')
		saveAs.setStatusTip('Save the current dashboard as a new file')
		saveAs.triggered.connect(self.centralWidget().graphicsScene.base.saveAs)

		setAsDefault = QAction('Set Default', self)
		setAsDefault.setStatusTip('Set the current dashboard as the default dashboard')
		setAsDefault.triggered.connect(self.centralWidget().graphicsScene.base.setDefault)

		load = QAction('&Open', self)
		load.setShortcut('Ctrl+L')
		load.setStatusTip('Load a dashboard')
		load.triggered.connect(self.centralWidget().graphicsScene.base.load)

		reload = QAction('Reload', self)
		reload.setShortcut('Ctrl+R')
		reload.setStatusTip('Reload the current dashboard')
		reload.triggered.connect(self.centralWidget().graphicsScene.base.reload)

		refresh = QAction('Refresh', self)
		refresh.setShortcut('Ctrl+Alt+R')
		refresh.setStatusTip('Refresh the current dashboard')
		refresh.triggered.connect(self.centralWidget().graphicsScene.update())

		printState = QAction('Print State', self)
		printState.setShortcut('Ctrl+P')
		printState.setStatusTip('Print the current state of the dashboard')
		printState.triggered.connect(self.centralWidget().graphicsScene.base.contextMenu.printState)

		fullscreen = QAction('&Fullscreen', self)
		fullscreen.setShortcut('Ctrl+F')
		fullscreen.setStatusTip('Toggle fullscreen')
		fullscreen.triggered.connect(self.toggleFullScreen)

		from LevityDash.lib.ui.frontends.PySide.Modules.Menus import DashboardTemplates

		fileConfigAction = QAction('Open Config Folder', self)
		fileConfigAction.setStatusTip('Open the config folder')
		fileConfigAction.setShortcut('Alt+C')
		fileConfigAction.triggered.connect(self.openConfigFolder)

		clear = QAction('Clear', self)
		clear.setStatusTip('Clear the current dashboard')
		clear.setShortcut('Ctrl+Alt+C')
		clear.triggered.connect(self.centralWidget().graphicsScene.base.clear)

		quitAct = QAction('Quit', self)
		quitAct.setStatusTip('Quit the application')
		quitAct.setShortcut('Ctrl+Q')
		quitAct.triggered.connect(QApplication.instance().quit)

		fileMenu.addAction(save)
		fileMenu.addAction(saveAs)
		fileMenu.addAction(load)
		fileMenu.addMenu(DashboardTemplates(self))
		fileMenu.addSeparator()
		fileMenu.addAction(fullscreen)
		fileMenu.addAction(fileConfigAction)
		fileMenu.addAction(quitAct)

		dashboardMenu = menubar.addMenu("Dashboard")
		dashboardMenu.addAction(setAsDefault)
		dashboardMenu.addAction(reload)
		dashboardMenu.addAction(refresh)
		dashboardMenu.addAction(clear)
		dashboardMenu.addAction(printState)

		plugins = PluginsMenu(self)
		self.bar.addMenu(plugins)

		insertMenu = InsertMenu(self)
		self.bar.addMenu(insertMenu)

		logsMenu = menubar.addMenu('&Logs')

		openLogAction = QAction('Open Log', self)
		openLogAction.setStatusTip('Open the current log file')
		openLogAction.triggered.connect(self.openLogFile)
		logsMenu.addAction(openLogAction)

		fileLogAction = QAction('Open Log Folder', self)
		fileLogAction.setStatusTip('Open the log folder')
		fileLogAction.setShortcut('Alt+L')
		fileLogAction.triggered.connect(self.openLogFolder)
		logsMenu.addAction(fileLogAction)

		submitLogsMenu = QMenu('Submit Logs', self)
		submitLogsMenu.setStatusTip('Submit the logs to the developer')
		showLogBundle = QAction('Create Zip Bundle', self)
		showLogBundle.setStatusTip('Create a zipfile containing the logs')
		showLogBundle.triggered.connect(lambda: self.submitLogs('openFolder'))
		submitLogsMenu.addAction(showLogBundle)

		submitLogs = QAction('Email logs', self)
		submitLogs.setStatusTip('Create an email containing the logs to send to the developer')
		submitLogs.triggered.connect(lambda: self.submitLogs('email'))
		submitLogsMenu.addAction(submitLogs)
		logsMenu.addMenu(submitLogsMenu)

		raiseException = QAction('Test Raise Exception', self)
		raiseException.setStatusTip('Test raising an exception for log capture')
		raiseException.triggered.connect(lambda: exec('raise Exception("Raised Test Exception")'))
		logsMenu.addAction(raiseException)

	def toggleFullScreen(self):
		if self.isFullScreen():
			self.showNormal()
		else:
			self.showFullScreen()

	def openConfigFolder(self):
		from LevityDash import __dirs__
		QDesktopServices.openUrl(QUrl.fromLocalFile(Path(__dirs__.user_config_dir).as_posix()))

	def openLogFile(self):
		guiLog.openLog()

	def openLogFolder(self):
		from LevityDash import __dirs__
		QDesktopServices.openUrl(QUrl.fromLocalFile(Path(__dirs__.user_log_dir).as_posix()))

	def submitLogs(self, sendType=None):
		if sendType is None:
			sendType = 'openFolder'
		from LevityDash import __dirs__
		logDir = Path(__dirs__.user_log_dir)

		def writeFiles(zipFile, path, relativeTo: Path = None):
			if relativeTo is None:
				relativeTo = path
			for file in path.iterdir():
				if file.is_dir():
					writeFiles(zipFile, file, relativeTo)
				else:
					zipFile.write(file, file.relative_to(relativeTo))

		tempDir = Path(__dirs__.user_cache_dir)
		tempDir.mkdir(exist_ok=True, parents=True)

		email = EmailMessage()
		email['Subject'] = 'Levity Dashboard Logs'
		email['To'] = 'logs@levitydash.app'

		zipFilePath = tempDir.joinpath('logs.zip')
		if zipFilePath.exists():
			zipFilePath.unlink()
		with ZipFile(zipFilePath, 'x') as zip:
			writeFiles(zip, logDir)

		if sendType == 'openFolder':
			webbrowser.open(zipFilePath.parent.as_uri())
			return

		_ctype, encoding = mimetypes.guess_type(zipFilePath.as_posix())
		if _ctype is None or encoding is not None:
			_ctype = 'application/octet-stream'
		maintype, subtype = _ctype.split('/', 1)

		with open(zipFilePath, 'rb') as zipFile:
			email.add_attachment(zipFile.read(), maintype=maintype, subtype=subtype, filename='logs.zip')

		with NamedTemporaryFile(mode='w', suffix='.eml') as f:
			gen = Generator(f)
			gen.flatten(email)
			webbrowser.open(Path(f.name).as_uri())

	def changeEvent(self, event: QEvent):
		super().changeEvent(event)
		if event.type() == QEvent.WindowStateChange and (platform.system() != 'Darwin'):
			self.updateMenuBar()

	def updateMenuBar(self):
		if (hba := getattr(self, 'menuBarHoverArea', None)) is not None:
			hba.size.setWidth(self.width())
			hba.update()
			menubar = self.bar
			view = self.centralWidget()
			if self.windowState() & Qt.WindowFullScreen:
				self.setMenuWidget(menubar)
				menubar.setParent(view)
				hba.setEnabled(True)
				self.menuBarLeave()
			else:
				self.setMenuWidget(menubar)
				menubar.setParent(self)
				self.menuBarHover()
				hba.setEnabled(False)


class ClockSignals(QObject):
	second = Signal(int)
	minute = Signal(int)
	hour = Signal(int)
	sync = Signal()

	syncInterval = timedelta(minutes=5)

	def __new__(cls):
		if not hasattr(cls, '_instance'):
			cls._instance = super().__new__(cls)
		return cls._instance

	def __init__(self):
		super().__init__()
		self.__init_timers_()

	def __init_timers_(self):
		self.__secondTimer = QTimer()
		self.__secondTimer.setTimerType(Qt.PreciseTimer)
		self.__secondTimer.setInterval(1000)
		self.__secondTimer.timeout.connect(self.__emitSecond)

		self.__minuteTimer = QTimer()
		self.__minuteTimer.setInterval(60000)
		self.__minuteTimer.timeout.connect(self.__emitMinute)
		self.__hourTimer = QTimer()
		self.__hourTimer.setInterval(3600000)
		self.__hourTimer.timeout.connect(self.__emitHour)

		self.__syncTimers()

		# Ensures that the timers are synced to the current time every six hours
		self.__syncTimer = QTimer()
		self.__syncTimer.timeout.connect(self.__syncTimers)
		self.__syncTimer.setInterval(1000 * 60 * 5)
		self.__syncTimer.setTimerType(Qt.VeryCoarseTimer)
		self.__syncTimer.setSingleShot(False)
		self.__syncTimer.start()

	def __startSeconds(self):
		self.__emitSecond()
		self.__secondTimer.setSingleShot(False)
		self.__secondTimer.start()
		guiLog.verbose('Second timer started', verbosity=4)

	def __startMinutes(self):
		self.__emitMinute()
		self.__minuteTimer.setSingleShot(False)
		self.__minuteTimer.start()
		guiLog.verbose('Minute timer started', verbosity=4)

	def __startHours(self):
		self.__emitHour()
		self.__hourTimer.setSingleShot(False)
		self.__hourTimer.start()
		guiLog.verbose('Hour timer started', verbosity=4)

	def __emitSecond(self):
		# now = datetime.now()
		# diff = now.replace(second=now.second + 1, microsecond=0) - now
		self.second.emit(datetime.now().second)

	def __emitMinute(self):
		minute = datetime.now().minute
		guiLog.verbose(f'Minute timer emitted with value {minute}', verbosity=5)
		self.minute.emit(minute)

	def __emitHour(self):
		hour = datetime.now().hour
		guiLog.verbose(f'Hour timer emitted with value {hour}', verbosity=5)
		self.hour.emit(hour)

	def __syncTimers(self):
		"""Synchronizes the timers to the current time."""
		guiLog.verbose(f'Syncing timers', verbosity=2)

		self.sync.emit()

		self.__secondTimer.stop()
		self.__minuteTimer.stop()
		self.__hourTimer.stop()

		now = datetime.now()

		# Offset the timers by 500ms to ensure that refresh actions happen after the time change
		# otherwise, the time will be announced
		timerOffset = 500

		timeToNextSecond = round((now.replace(second=now.second, microsecond=0) + timedelta(seconds=1) - now).total_seconds() * 1000)
		self.__secondTimer.singleShot(timeToNextSecond + timerOffset, self.__startSeconds)

		timeToNextMinute = round((now.replace(minute=now.minute, second=0, microsecond=0) + timedelta(minutes=1) - now).total_seconds() * 1000)
		guiLog.verbose(f'Time to next minute: {timeToNextMinute / 1000} seconds', verbosity=5)
		self.__minuteTimer.singleShot(timeToNextMinute + timerOffset, self.__startMinutes)

		timeToNextHour = round((now.replace(hour=now.hour, minute=0, second=0, microsecond=0) + timedelta(hours=1) - now).total_seconds() * 1000)
		guiLog.verbose(f'Time to next hour: {timeToNextHour / 1000} seconds', verbosity=5)
		self.__hourTimer.singleShot(timeToNextHour + timerOffset, self.__startHours)


app.clock = ClockSignals()

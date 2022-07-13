import asyncio
import mimetypes
import os
import platform
import webbrowser
from collections import namedtuple
from datetime import timedelta, datetime
from email.generator import Generator
from email.message import EmailMessage
from functools import cached_property

import PySide2
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZipFile

from PySide2.QtCore import QRectF, Signal, QTimer, Qt, QRect, QEvent, QObject, QPoint, QPointF, QSize, QUrl
from PySide2.QtGui import QPainterPath, QMouseEvent, QPainter, QCursor, QIcon, QPixmapCache, QPixmap, QImage, QTransform, QSurfaceFormat, QScreen, QDesktopServices, QShowEvent
from PySide2.QtWidgets import (QApplication, QGraphicsScene, QGraphicsItem, QGraphicsPathItem, QGraphicsView, QMenu,
                               QAction, QMainWindow, QToolTip, QStyle, QStyleOptionGraphicsItem, QOpenGLWidget, QGraphicsEffect, QGraphicsPixmapItem, QGraphicsRectItem, QMenuBar)

from WeatherUnits import Length

from LevityDash.lib.plugins.dispatcher import ValueDirectory as pluginManager

from LevityDash.lib.ui.frontends.PySide.utils import colorPalette, SoftShadow, EffectPainter, itemClipsChildren, getAllParents
from ....config import userConfig
from . import qtLogger as guiLog

from ....utils import clearCacheAttr, LocationFlag, Unset, parseSize, Size, DimensionType, BusyContext
from time import time, perf_counter

app: QApplication = QApplication.instance()

ACTIVITY_EVENTS = {QEvent.KeyPress, QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseMove, QEvent.GraphicsSceneMouseMove, QEvent.GraphicsSceneMouseRelease, QEvent.GraphicsSceneMousePress, QEvent.InputMethod,
	QEvent.InputMethodQuery}

loop = asyncio.get_running_loop()

app.setQuitOnLastWindowClosed(True)

print('-------------------------------')
print('Loading Qt GUI...')
print('-------------------------------')


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
class LevityScene(QGraphicsScene):
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
		return StaticGeometry(self, position=(0, 0), absolute=True, snapping=False, updateSurface=False)

	@cached_property
	def window(self):
		return app.activeWindow()

	def rect(self):
		return self.sceneRect()

	def size(self):
		return self.sceneRect().size()

	@property
	def frozen(self):
		return False

	def mousePressEvent(self, event: QMouseEvent):
		super(LevityScene, self).mousePressEvent(event)

	def mouseReleaseEvent(self, event):
		super(LevityScene, self).mouseReleaseEvent(event)

	@property
	def containingRect(self):
		return self.gridRect()

	def zValue(self):
		return -1

	@property
	def clicked(self):
		return QApplication.instance().mouseButtons() == Qt.LeftButton

	def renderItem(self, item: QGraphicsItem, dispose: bool = False) -> QPixmap:
		rect = self.view.deviceTransform().mapRect(item.boundingRect())
		raster = QImage(rect.size().toSize(), QImage.Format_ARGB32)
		raster.setDevicePixelRatio(self.view.devicePixelRatio())
		raster.fill(Qt.transparent)
		painter = EffectPainter(raster)
		pos = item.pos()
		renderingPosition = QPointF(10000, 10000)
		item.setPos(renderingPosition - item.scenePos())
		painter.setBackgroundMode(Qt.TransparentMode)
		if wasClipped := item.isClipped():
			clippingParents = getAllParents(item, filter=itemClipsChildren)
			list(map(lambda i: i.setFlag(QGraphicsItem.ItemClipsChildrenToShape, False), clippingParents))
		self.render(painter, rect, QRectF(renderingPosition, rect.size()))
		if dispose:
			painter.end()
			self.removeItem(item)
			return QPixmap.fromImage(raster)
		item.setPos(pos)
		painter.end()
		if wasClipped:
			list(map(lambda i: i.setFlag(QGraphicsItem.ItemClipsChildrenToShape, True), clippingParents))
		return QPixmap.fromImage(raster)

	def bakeEffects(self, item: QGraphicsItem | QPixmap, *effects: QGraphicsEffect) -> QPixmap:
		# Convert the item to a GraphicsPixmapItem
		if not isinstance(item, QGraphicsItem):
			item = QGraphicsPixmapItem(item)

		# Add the item to the scene
		if item.scene() is not self:
			self.addItem(item)

		# Apply only the first effect and bake the pixmap
		if effects:
			effect, *effects = effects
			if not issubclass(effect, QGraphicsEffect):
				guiLog.error('Effect must be a QGraphicsEffect for baking')
				return item
			initVars = effect.__init__.__code__.co_varnames
			if 'owner' in initVars:
				effect = effect(owner=item)
			else:
				effect = effect()
			item.setGraphicsEffect(effect)
		item = self.renderItem(item, dispose=True)

		# If there are still effects, recursively bake them
		if effects:
			item = self.bakeEffects(item, *effects)

		return item


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

	def __init__(self, *args, **kwargs):
		self.status = 'Initializing'
		self.lastEventTime = perf_counter()
		super(LevitySceneView, self).__init__(*args, **kwargs)
		opengl = userConfig.getOrSet('QtOptions', 'openGL', True, userConfig.getboolean)

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
		guiLog.debug(f'Max texture size set to {self.maxTextureSize/1000:.0f}KB')
		self.pixmapCacheSize = int(userConfig.getOrSet('QtOptions', 'pixmapCacheSize', '200mb', getter=userConfig.configToFileSize)/1024)
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

	def deviceTransform(self) -> QTransform:
		devicePixelRatio = self.devicePixelRatioF()
		return QTransform.fromScale(devicePixelRatio, devicePixelRatio)

	def postInit(self):
		app.primaryScreenChanged.connect(self.__screenChange)
		ratio = self.height()/self.width()
		size = 1000
		rect = QRect(0, 0, size, size*ratio)
		self.graphicsScene.base.setRect(rect)
		self.sceneRect = rect
		self.graphicsScene.setSceneRect(rect)
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
				self.graphicsScene.clearFocus()
				self.graphicsScene.clearSelection()
		# elif event.type() == QEvent.GraphicsSceneMousePress:
		# 	SoftShadow.disable(delay=400)
		# elif event.type() == QEvent.GraphicsSceneMouseRelease:
		# 	SoftShadow.enable()
		return super(LevitySceneView, self).eventFilter(obj, event)

	def resizeDoneEvent(self):
		self.graphicsScene.invalidate(self.graphicsScene.sceneRect())
		self.graphicsScene.update()
		self.resizeFinished.emit()

	def focusInEvent(self, *args):
		super(LevitySceneView, self).focusInEvent(*args)
		print('focusInEvent')

	def load(self):
		self.status = 'Loading'
		with BusyContext(pluginManager) as context:
			self.graphicsScene.base.loadDefault()
			self.graphicsScene.clearSelection()
			self.status = 'Ready'
		self.loadingFinished.emit()

	@property
	def dpi(self):
		if app.activeWindow():
			return app.activeWindow().screen().logicalDotsPerInch()
		return 96

	def __screenChange(self):
		self.resizeDone.start()

	def resizeEvent(self, event):
		super(LevitySceneView, self).resizeEvent(event)
		self.fitInView(self.base)
		self.graphicsScene.busyBlocker.setRect(self.sceneRect)
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
			action.setChecked(plugin.enabled())
			# action.toggled.connect(plugin.setEnabled)
			self.addAction(action)

	def show(self):
		from LevityDash.lib.plugins import Plugins as pluginManager
		for action in self.actions():
			plugin = action.text()
			action.setChecked(pluginManager.get(plugin).enabled())

	def update(self):
		for action in self.actions():
			plugin = action.text()
			action.setChecked(plugin.enabled())


class InsertMenu(QMenu):
	existing = set()

	def __init__(self, parent):
		super(InsertMenu, self).__init__(parent)
		self.setTitle('Items')
		self.buildItems()
		self.aboutToShow.connect(self.buildItems)

	def showEvent(self, event) -> None:
		self.buildItems()
		super(InsertMenu, self).showEvent(event)

	def buildItems(self):
		self.clear()
		items = sorted(pluginManager.containers(), key=lambda x: str(x.key))
		if items:
			for item in items:
				action = InsertItemAction(self, key=item.key)
				self.addAction(action)
		else:
			refresh = QAction('Refresh', self)
			refresh.triggered.connect(self.refresh)
			self.addAction(refresh)

	def refresh(self):
		self.buildItems()


class InsertItemAction(QAction):

	def __init__(self, parent, key):
		super(InsertItemAction, self).__init__(parent)
		self.key = key
		self.setText(str(key))
		self.triggered.connect(self.insert)

	def insert(self):
		value = self.parent().pluginManager[self.key]
		print(repr(value))


class LevityMainWindow(QMainWindow):

	def __init__(self, *args, **kwargs):
		super(LevityMainWindow, self).__init__(*args, **kwargs)
		self.setWindowTitle('LevityDash')

		# if width < 1:
		# 	width = width * self.screen.width()
		# if height < 1:
		# 	height = height * self.screen.height()
		# rect = QRect(0, 0, 800, 600)
		# rect.setSize(self.screen().size() * 0.8)
		# rect.moveCenter(self.screen().availableGeometry().center())
		# self.setGeometry(rect)
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
		self.menuBarHoverArea = HoverArea(view.graphicsScene.base,
			size=10,
			rect=QRect(0, 0, self.width(), 50),
			enterAction=self.menuBarHover,
			exitAction=self.menuBarLeave,
			alignment=LocationFlag.Bottom,
			position=LocationFlag.TopLeft,
			ignoredEdges=LocationFlag.Top
		)

		if platform.system() != 'Darwin':
			menubar = MenuBar(self)
			self.__menubarHeight = self.menuBar().height()*2
			menubar.setParent(view)
			self.bar = menubar
			self.setMenuWidget(menubar)
			self.bar.setParent(view)
			self.menuBarHoverArea.setEnabled(True)
		else:
			self.menuBarHoverArea.setEnabled(False)
			self.bar = self.menuBar()

		self.buildMenu()

		self.__init_ui__()

	def focusOutEvent(self, event):
		super(LevityMainWindow, self).focusOutEvent(event)
		print('focus out')

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

		def findScreen():
			screens = app.screens()
			display = userConfig['Display'].get('display', 'smallest')
			match display:
				case 'smallest':
					return min(screens, key=lambda s: s.size().width()*s.size().height())
				case 'largest':
					return max(screens, key=lambda s: s.size().width()*s.size().height())
				case 'primary' | 'main' | 'default':
					return app.primaryScreen()
				case 'current' | 'active':
					return app.screenAt(QCursor.pos())
				case str(i) if i.isdigit():
					return screens[min(int(i), len(screens))]
				case _:
					if len(screens) == 1:
						return screens[0]
					for screen in screens:
						# if the screen is the primary screen, skip it
						if app.primaryScreen() == screen:
							continue
						# if the screen is taller than it is wide, skip it
						if screen.size().height() > screen.size().width():
							continue
			return screen

		g = self.geometry()
		screen: QScreen = findScreen()
		screenGeometry = screen.geometry()
		width = parseSize(userConfig.getOrSet('Display', 'width', '80%'), 0.8, dimension=DimensionType.width)
		height = parseSize(userConfig.getOrSet('Display', 'height', '80%'), 0.8)

		match width:
			case Size.Width(w, absolute=True):
				width = min(w, screenGeometry.width())
			case Size.Width(w, relative=True):
				width = min(w*screen.availableSize().width(), screen.availableSize().width())
			case Length() as w:
				w = float(w.inch)
				xDPI = screen.physicalDotsPerInchX()
				width = min(w*xDPI, screen.availableSize().width())
			case _:
				width = screen.availableSize().width()*0.8

		match height:
			case Size.Height(h, absolute=True):
				height = min(h, screenGeometry.height())
			case Size.Height(h, relative=True):
				height = min(h*screen.availableSize().height(), screen.availableSize().height())
			case Length() as h:
				h = float(h.inch)
				yDPI = screen.physicalDotsPerInchY()
				height = min(h*yDPI, screen.availableSize().height())
			case _:
				height = screen.availableSize().height()*0.8

		g.setSize(QSize(round(width), round(height)))
		g.moveCenter(screen.availableGeometry().center())
		self.setGeometry(g)

		if fullscreen:
			self.showFullScreen()

		self.show()

		if '--fullscreen' in sys.argv:
			self.showFullScreen()

	def buildMenu(self):
		menubar = self.bar
		fileMenu = menubar.addMenu('&File')

		if platform.system() == 'Darwin':
			self.setUnifiedTitleAndToolBarOnMac(True)
			macOSConfig = QAction('&config', self)
			macOSConfig.setStatusTip('Open the config folder')
			macOSConfig.triggered.connect(self.openConfigFolder)
			fileMenu.addAction(macOSConfig)

		plugins = PluginsMenu(self)
		self.bar.addMenu(plugins)

		insertMenu = InsertMenu(self)
		self.bar.addMenu(insertMenu)

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

		fileMenu.addAction(save)
		fileMenu.addAction(saveAs)
		fileMenu.addAction(setAsDefault)

		load = QAction('&Load', self)
		load.setShortcut('Ctrl+L')
		load.setStatusTip('Load a dashboard')
		load.triggered.connect(self.centralWidget().graphicsScene.base.load)
		fileMenu.addAction(load)

		reload = QAction('Reload', self)
		reload.setShortcut('Ctrl+R')
		reload.setStatusTip('Reload the current dashboard')
		reload.triggered.connect(self.centralWidget().graphicsScene.base.reload)

		refresh = QAction('Refresh', self)
		refresh.setShortcut('Ctrl+Alt+R')
		refresh.setStatusTip('Refresh the current dashboard')
		refresh.triggered.connect(self.centralWidget().graphicsScene.update())
		fileMenu.addAction(refresh)

		fullscreen = QAction('&Fullscreen', self)
		fullscreen.setShortcut('Ctrl+F')
		fullscreen.setStatusTip('Toggle fullscreen')
		fullscreen.triggered.connect(self.toggleFullScreen)
		fileMenu.addAction(fullscreen)

		from LevityDash.lib.ui.frontends.PySide.Modules.Menus import DashboardTemplates
		fileMenu.addMenu(DashboardTemplates(self))

		fileMenu.addSeparator()

		fileConfigAction = QAction('Open Config Folder', self)
		fileConfigAction.setStatusTip('Open the config folder')
		fileConfigAction.setShortcut('Alt+C')
		fileConfigAction.triggered.connect(self.openConfigFolder)
		fileMenu.addAction(fileConfigAction)

		clear = QAction('Clear Dashboard', self)
		clear.setStatusTip('Clear the current dashboard')
		clear.setShortcut('Ctrl+Alt+C')
		clear.triggered.connect(self.centralWidget().graphicsScene.base.clear)

		fileMenu.addAction(clear)

		quitAct = QAction('Quit', self)
		quitAct.setStatusTip('Quit the application')
		quitAct.setShortcut('Ctrl+Q')
		quitAct.triggered.connect(QApplication.instance().quit)
		fileMenu.addAction(quitAct)

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
			self.menuBarHoverArea.setEnabled(True)
			self.menuBarHoverArea.size.setWidth(self.width())
			self.menuBarHoverArea.update()
			self.menuBarLeave()


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
		self.__syncTimer.setInterval(1000*60*5)
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

		self.sync.emit()

		self.__secondTimer.stop()
		self.__minuteTimer.stop()
		self.__hourTimer.stop()

		now = datetime.now()

		# Offset the timers by 10ms to ensure that the timers are synced to the current time
		# otherwise, the time will be announced
		timerOffset = 10

		timeToNextSecond = round((now.replace(second=now.second, microsecond=0) + timedelta(seconds=1) - now).total_seconds()*1000)
		self.__secondTimer.singleShot(timeToNextSecond + timerOffset, self.__startSeconds)

		timeToNextMinute = round((now.replace(minute=now.minute, second=0, microsecond=0) + timedelta(minutes=1) - now).total_seconds()*1000)
		guiLog.verbose(f'Time to next minute: {timeToNextMinute/1000} seconds', verbosity=5)
		self.__minuteTimer.singleShot(timeToNextMinute + timerOffset, self.__startMinutes)

		timeToNextHour = round((now.replace(hour=now.hour, minute=0, second=0, microsecond=0) + timedelta(hours=1) - now).total_seconds()*1000)
		guiLog.verbose(f'Time to next hour: {timeToNextHour/1000} seconds', verbosity=5)
		self.__hourTimer.singleShot(timeToNextHour + timerOffset, self.__startHours)


app.clock = ClockSignals()

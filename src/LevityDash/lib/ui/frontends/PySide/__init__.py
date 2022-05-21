import asyncio
import mimetypes
import platform
import sys
import webbrowser
from email.generator import Generator
from email.message import EmailMessage
from pathlib import Path
from functools import cached_property
from tempfile import TemporaryFile, NamedTemporaryFile
from zipfile import ZipFile

from qasync import QApplication
from PySide2.QtCore import QEvent, QRect, QRectF, Qt, QTimer, Signal
from PySide2.QtGui import QIcon, QMouseEvent, QPainter, QPainterPath, QCursor
from PySide2.QtWidgets import (QGraphicsItem, QGraphicsPathItem, QGraphicsScene, QGraphicsView,
                               QMainWindow, QMenu, QAction)

from LevityDash.lib.config import userConfig
from LevityDash.lib.utils import clearCacheAttr, LocationFlag
from LevityDash.lib.ui.frontends.PySide.utils import *
from LevityDash.lib.log import LevityGUILog as guiLog

from time import time

app: QApplication = QApplication.instance()
app.setPalette(colorPalette)

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


class LevityScene(QGraphicsScene):
	columnWidth = 100
	rowHeight = 100
	_gridRect: QRectF = None
	gridSignal = Signal('GridSize')
	preventCollisions = False
	editingMode = False
	frozen: bool
	neverReleaseChildren: bool
	focusStack: FocusStack

	def __init__(self, *args, **kwargs):
		self.time = time()
		super(LevityScene, self).__init__(*args, **kwargs)
		from .Modules.CentralPanel import CentralPanel
		self.base = CentralPanel(self)
		self.editingModeTimer = QTimer(interval=3*1000, timeout=self.hideLines)
		from LevityDash.lib.Geometry.Grid import Grid
		self.grid = Grid(self, static=False, overflow=False)
		self.staticGrid = False
		clearCacheAttr(self, 'geometry')
		self.setBackgroundBrush(QApplication.instance().palette().window().color())

	def addVisualAids(self):
		self.addItem(self.visualAidRed)
		pen = self.visualAidRed.pen()
		pen.setColor(Qt.red)
		pen.setWidth(3)
		self.visualAidRed.setPen(pen)
		self.visualAidRed.setZValue(80)
		color = pen.color()
		color.setAlpha(100)
		self.visualAidRed.setBrush(color)
		self.visualAidPurple = QGraphicsPathItem()
		self.visualAidPurple.setZValue(99)
		self.addItem(self.visualAidPurple)
		pen = self.visualAidPurple.pen()
		pen.setColor(Qt.darkMagenta)
		pen.setWidth(9)
		self.visualAidPurple.setPen(pen)
		self.visualAidPurple.setBrush(Qt.NoBrush)

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
		from LevityDash.lib.Geometry import StaticGeometry
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

	@property
	def neverReleaseChildren(self):
		return False

	# def setSceneRect(self, rect: QRectF):
	# 	super(LevityScene, self).setSceneRect(rect)
	# self.base.parentResized(rect)

	def hideLines(self, hide: bool = True):
		self.editingMode = not hide
		# self.apiDrawer.handle.setVisible(not hide)
		self.update()
		# for item in self.views():
		# 	item.updateSceneRect(item.rect())
		if self.base.staticGrid:
			self.base.adjusters.setVisible(not hide)

	def mousePressEvent(self, event: QMouseEvent):
		self.hideLines(False)
		super(LevityScene, self).mousePressEvent(event)

	# def mouseMoveEvent(self, event):
	# 	# if event.button == Qt.LeftButton:
	# 	# 	self.editingModeTimer.start()
	# 	# event.ignore()
	# 	super(LevityScene, self).mouseMoveEvent(event)

	def mouseReleaseEvent(self, event):
		self.editingModeTimer.start()
		super(LevityScene, self).mouseReleaseEvent(event)

	def gridRect(self):
		if self._gridRect is None:
			if self.views():
				return self.views()[0].rect()
			return self.sceneRect()
		else:
			return self._gridRect

	def setGridRect(self, rect: QRectF):
		self._gridRect = rect

	@property
	def containingRect(self):
		return self.gridRect()

	def zValue(self):
		return -1

	@property
	def clicked(self):
		return QApplication.instance().mouseButtons() == Qt.LeftButton


class LevitySceneView(QGraphicsView):
	resizeFinished = Signal()

	def __init__(self, *args, **kwargs):
		super(LevitySceneView, self).__init__(*args, **kwargs)
		self.noActivityTimer = QTimer(self)
		self.noActivityTimer.setSingleShot(True)
		self.noActivityTimer.timeout.connect(self.noActivity)
		self.noActivityTimer.setInterval(15000)
		# self.setLayout(QVBoxLayout(self))
		# self.layout().setContentsMargins(1, 1, 1, 1)
		# self.layout().setSpacing(0)
		# self.layout().setAlignment(Qt.AlignTop)

		# self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
		# self.graphicsView = QGraphicsView(self)
		# self.layout().addWidget(self.graphicsView)
		# self.graphicsView.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
		self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
		self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
		self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
		self.graphicsScene = LevityScene(self)
		self.setScene(self.graphicsScene)
		self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
		self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
		self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

	# rect = self.graphicsScene.base.rect()
	# # self.graphicsView.fitInView(rect)
	# self.graphicsScene.setSceneRect(rect)

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

	def eventFilter(self, obj, event):
		if event.type() in {QEvent.KeyPress, QEvent.MouseButtonPress, QEvent.MouseMove, QEvent.GraphicsSceneMouseMove, QEvent.GraphicsSceneMousePress, QEvent.InputMethod, QEvent.InputMethodQuery}:
			self.noActivityTimer.start()
			self.setCursor(Qt.ArrowCursor)
		if event.type() == QEvent.KeyPress:
			if event.key() == Qt.Key_R:
				pos = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
				items = self.graphicsScene.items(pos)
				for item in items:
					if hasattr(item, 'refresh'):
						item.refresh()
			if event.key() == Qt.Key_Down:
				if getattr(self.graphicsScene.focusItem(), 'movable', False):
					self.graphicsScene.focusItem().moveBy(0, 1)
			elif event.key() == Qt.Key_Up:
				if getattr(self.graphicsScene.focusItem(), 'movable', False):
					self.graphicsScene.focusItem().moveBy(0, -1)
			elif event.key() == Qt.Key_Left:
				if getattr(self.graphicsScene.focusItem(), 'movable', False):
					self.graphicsScene.focusItem().moveBy(-1, 0)
			elif event.key() == Qt.Key_Right:
				if getattr(self.graphicsScene.focusItem(), 'movable', False):
					self.graphicsScene.focusItem().moveBy(1, 0)
		# 	yamlStr = yaml.safe_dump(item, default_flow_style=False)
		# 	print(yamlStr)
		# load
		return super(LevitySceneView, self).eventFilter(obj, event)

	def resizeDoneEvent(self):
		self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
		self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
		self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
		self.graphicsScene.update()
		self.resizeFinished.emit()

	def load(self):
		self.graphicsScene.base.load()
		self.graphicsScene.clearSelection()

	@property
	def dpi(self):
		if app.activeWindow():
			return app.activeWindow().screen().logicalDotsPerInch()
		return 96

	def __screenChange(self):
		pass

	def resizeEvent(self, event):
		self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
		self.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
		self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
		# if any(int(i) % 10 == 0 for i in event.size().toTuple()):
		# 	self.base.setRect(rect)
		# 	self.setSceneRect(rect)

		super(LevitySceneView, self).resizeEvent(event)
		self.fitInView(self.base)
		self.resizeDone.start()

	def noActivity(self):
		self.graphicsScene.clearSelection()
		self.graphicsScene.clearFocus()
		self.setCursor(Qt.BlankCursor)


class PluginsMenu(QMenu):

	def __init__(self, parent):
		super(PluginsMenu, self).__init__(parent)
		self.setTitle('Plugins')
		self.setIcon(QIcon.fromTheme('preferences-plugin'))
		self.setToolTipsVisible(True)
		self.setToolTip('Plugins')
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


class LevityMainWindow(QMainWindow):

	def __init__(self, *args, **kwargs):
		super(LevityMainWindow, self).__init__(*args, **kwargs)
		self.setWindowTitle('LevityDash')
		view = LevitySceneView(self)
		view.setGeometry(self.geometry())
		self.setCentralWidget(view)
		style = '''
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
					'''
		if platform.system() == 'Darwin':
			style += '''
					QMenu::item::unchecked {
						padding-left: -12px;
						margin-left: 0px;
					}
					QMenu::item::checked {
						padding-left: 0px;
						margin-left: 0px;
					}'''
		app.setStyleSheet(style)
		# view.setVisible(False)
		self.setStyleSheet("selection-color: transparent; border-color: transparent; border-style: Solid; border-width: 0px;")
		view.postInit()

		from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Various import HoverArea
		self.menuBarHoverArea = HoverArea(view.graphicsScene.base,
			size=10,
			rect=QRect(0, 0, self.width(), 5),
			visible=False,
			enterAction=self.menuBarHover,
			exitAction=self.menuBarLeave,
			alignment=LocationFlag.Bottom,
			position=LocationFlag.TopLeft,
			ignoredEdges=LocationFlag.Top
		)
		self.menuBarHoverArea.setEnabled(False)
		self.buildMenu()

		self.__init_ui__()

	def menuBarHover(self):
		self.menuBar().show()

	def menuBarLeave(self):
		self.menuBar().hide()

	def __init_ui__(self):
		self.centralWidget().load()

		def findScreen():
			screens = app.screens()
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
		screen = findScreen()
		screen = screen.geometry()
		g.setWidth(screen.width()*0.8)
		g.setHeight(screen.height()*0.8)
		g.moveCenter(screen.center())

		self.setGeometry(g)
		self.show()

		if '--fullscreen' in sys.argv:
			self.showFullScreen()

	def buildMenu(self):
		menubar = self.menuBar()
		fileMenu = menubar.addMenu('&File')

		if platform.system() == 'Darwin':
			self.setUnifiedTitleAndToolBarOnMac(True)
			macOSConfig = QAction('&config', self)
			macOSConfig.setStatusTip('Open the config folder')
			macOSConfig.triggered.connect(self.openConfigFolder)
			fileMenu.addAction(macOSConfig)

		# plugins = PluginsMenu(self)
		# self.menuBar().addMenu(plugins)

		save = QAction('&Save', self)
		save.setShortcut('Ctrl+S')
		save.setStatusTip('Save the current dashboard')
		save.triggered.connect(self.centralWidget().graphicsScene.base.save)

		saveAs = QAction('Save &As', self)
		saveAs.setShortcut('Ctrl+Shift+S')
		saveAs.setStatusTip('Save the current dashboard as a new file')
		saveAs.triggered.connect(self.centralWidget().graphicsScene.base.saveAs)

		fileMenu.addAction(save)
		fileMenu.addAction(saveAs)

		load = QAction('&Load', self)
		load.setShortcut('Ctrl+L')
		load.setStatusTip('Load a dashboard')
		load.triggered.connect(self.centralWidget().graphicsScene.base.load)

		fileMenu.addAction(load)

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

	def toggleFullScreen(self):
		if self.isFullScreen():
			self.showNormal()
		else:
			self.showFullScreen()

	def show(self):
		super(LevityMainWindow, self).show()
		if userConfig['Display'].getboolean('fullscreen'):
			asyncio.get_event_loop().call_later(10, self.showFullScreen)

	def openConfigFolder(self):
		from LevityDash import __dirs__
		webbrowser.open(Path(__dirs__.user_config_dir).as_uri())

	def openLogFile(self):
		guiLog.openLog()

	def openLogFolder(self):
		from LevityDash import __dirs__
		webbrowser.open(Path(__dirs__.user_log_dir).as_uri())

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
		if event.type() == QEvent.WindowStateChange \
			and (platform.system() != 'Darwin' or not app.testAttribute(Qt.AA_DontUseNativeMenuBar)):
			if self.windowState() & Qt.WindowFullScreen:
				self.menuBarHoverArea.setEnabled(True)
				self.menuBarHoverArea.size.setWidth(self.width())
				self.menuBarHoverArea.update()
				self.menuBar().move(0, self.menuBar().height())
			else:
				self.menuBar().move(0, -self.menuBar().height())
				self.menuBarHoverArea.setEnabled(False)
				self.menuBarHoverArea.update()


__all__ = ['LevityMainWindow']

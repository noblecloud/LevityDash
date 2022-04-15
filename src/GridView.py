from time import time

from src import app, logging
from functools import cached_property

from PySide2.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide2.QtGui import QIcon, QMouseEvent, QPainter, QPainterPath, QTransform, QWheelEvent, QWindow
from PySide2.QtWidgets import (QApplication, QGraphicsItem, QGraphicsPathItem, QGraphicsScene, QGraphicsView,
                               QMainWindow, QOpenGLWidget,
                               QSizePolicy,
                               QVBoxLayout, QWidget)

__all__ = []

from src.utils import _Panel, ActionTimer, cachedUnless, clearCacheAttr

log = logging.getLogger(__name__)


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


class GridScene(QGraphicsScene):
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
		super(GridScene, self).__init__(*args, **kwargs)
		from src.Modules.CentralPanel import CentralPanel
		# QGraphicsScene.setSceneRect(self, self.window.rect())
		self.base = CentralPanel(self)
		self.editingModeTimer = QTimer(interval=3*1000, timeout=self.hideLines)
		from src.Grid import Grid
		self.grid = Grid(self, static=False, overflow=False)
		self.staticGrid = False
		clearCacheAttr(self, 'geometry')
		self.focusStack = FocusStack(self)

		self.visualAidRed = QGraphicsPathItem()
		self.addVisualAids()
		from src.Modules.Drawer import PanelDrawer

		# self.apiDrawer = PanelDrawer(self, self.base)
		# self.apiDrawer.close()
		# self.setBackgroundBrush(Qt.red)
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
		from src.Modules.Panel import Panel
		return [i for i in self.items() if isinstance(i, Panel)]

	@cached_property
	def geometry(self):
		from src.Grid.Geometry import StaticGeometry
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
	# 	super(GridScene, self).setSceneRect(rect)
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
		super(GridScene, self).mousePressEvent(event)

	# def mouseMoveEvent(self, event):
	# 	# if event.button == Qt.LeftButton:
	# 	# 	self.editingModeTimer.start()
	# 	# event.ignore()
	# 	super(GridScene, self).mouseMoveEvent(event)

	def mouseReleaseEvent(self, event):
		self.editingModeTimer.start()
		super(GridScene, self).mouseReleaseEvent(event)

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

# def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
# 	super(GridScene, self).drawForeground(painter, rect)
# 	fpsTimer()
# 	end = time()
# 	print(f'\r{1/(end - self.time):.3f}fps', end='')
# 	self.time = end


# import platform
# if platform.system() == 'Darwin':
windowClass = QOpenGLWidget


# else:
# windowClass = QWidget


# fpsTimer = ActionTimer('resize')


class GridView(QGraphicsView):
	resizeFinshed = Signal()

	def __init__(self, *args, **kwargs):
		super(GridView, self).__init__(*args, **kwargs)
		# self.setLayout(QVBoxLayout(self))
		# self.layout().setContentsMargins(1, 1, 1, 1)
		# self.layout().setSpacing(0)
		# self.layout().setAlignment(Qt.AlignTop)

		# self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
		# self.graphicsView = QGraphicsView(self)
		# self.layout().addWidget(self.graphicsView)
		# self.graphicsView.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
		self.setRenderHint(QPainter.HighQualityAntialiasing)
		self.graphicsScene = GridScene(self)
		self.setScene(self.graphicsScene)
		self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
		self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
		self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

		# rect = self.graphicsScene.base.rect()
		# # self.graphicsView.fitInView(rect)
		# self.graphicsScene.setSceneRect(rect)
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

	def eventFilter(self, obj, event):
		if event.type() == QEvent.KeyPress:
			# save
			if event.key() == Qt.Key_S and event.modifiers() == Qt.ControlModifier:
				self.base.save()
			# load
			elif event.key() == Qt.Key_L and event.modifiers() == Qt.ControlModifier:
				self.base.load()
		return super(GridView, self).eventFilter(obj, event)

	def resizeDoneEvent(self):
		self.setRenderHint(QPainter.HighQualityAntialiasing, True)
		self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
		self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
		self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
		self.graphicsScene.update()
		self.resizeFinshed.emit()

	# rect = self.rect()
	# self.fitInView(rect)
	# self.graphicsScene.setSceneRect(rect)
	# self.base.setRect(rect)

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

	# rect = self.graphicsScenecsScene.base.sceneRect()
	# self.graphicsSceneView.fitInView(rect)

	def toggleFullScreen(self):
		if self.isFullScreen():
			self.showNormal()
		else:
			self.showFullScreen()

	def resizeEvent(self, event):
		self.setRenderHint(QPainter.HighQualityAntialiasing, False)
		self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
		self.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
		self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
		# if any(int(i) % 10 == 0 for i in event.size().toTuple()):
		# 	self.base.setRect(rect)
		# 	self.setSceneRect(rect)

		super(GridView, self).resizeEvent(event)
		self.fitInView(self.base)
		self.resizeDone.start()

# 	finish = time()
# 	# print(f'\rResize took {finish - start:.6f} seconds', end ='')

# def show(self):
# 	rect = self.graphicsScene.base.rect()
# 	super(GridView, self).show()
# 	self.graphicsView.fitInView(rect)

# def scroll(self, dx: int, dy: int) -> None:
# 	return None

# def eventFilter(self, obj, event: QEvent):
# 	if event.type() == QEvent.KeyPress:
# 		log.debug(Qt.Key(event.key()).name.decode())
# 		if event.key() == Qt.Key_F or event.key() == Qt.Key_F11:
# 			self.toggleFullScreen()
# 			return True
# 		elif event.key() == Qt.Key_Q:
# 			QApplication.instance().quit()
# 		elif event.key() == Qt.Key_R:
# 			self.graphicsScene.base.load()
# 		elif event.key() == Qt.Key_Control:
# 			self.graphicsView.parentWidget().setCursor(Qt.CursorShape.OpenHandCursor)
# 	elif event.type() == QEvent.KeyRelease:
# 		if event.key() == Qt.Key_Control:
# 			self.graphicsView.parentWidget().setCursor(Qt.CursorShape.ArrowCursor)
#
# 	return super(GridView, self).eventFilter(obj, event)


class TestWindow(GridView):

	def __init__(self, panel: _Panel = None):
		super(TestWindow, self).__init__()
		if panel:
			panel.setParent(self.graphicsScene.base)

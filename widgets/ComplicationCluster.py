import logging
from typing import Iterable, Union

from PySide2.QtGui import QColor, QDragLeaveEvent, QDropEvent, QMouseEvent, QPainter
from PySide2.QtCore import QSize, Qt, QTimer
from PySide2.QtWidgets import QWidget
from WeatherUnits.base import Measurement

from ui.ComplicationCluster_UI import Ui_ComplicationGroup
from src.utils import goToNewYork, Position
from src.colors import randomColor
from widgets.ComplicationArray import ClusterGrid
from widgets.grip import Gripper
from widgets.Proto import ComplicationPrototype
from widgets.Complication import Complication

log = logging.getLogger(__name__)


class ComplicationCluster(Ui_ComplicationGroup, ComplicationPrototype):
	widgetPositions: dict[Position:Union[QWidget, ClusterGrid]]

	center: ClusterGrid

	topArray: ClusterGrid
	bottomArray: ClusterGrid
	leftArray: ClusterGrid
	rightArray: ClusterGrid

	topLeft: ClusterGrid
	topRight: ClusterGrid
	bottomLeft: ClusterGrid
	bottomRight: ClusterGrid

	cornerWidgets = [Position.TopLeft, Position.TopRight, Position.Center,
	                 Position.BottomLeft, Position.BottomRight]

	arrays = [Position.Top, Position.Left,
	          Position.Bottom, Position.Right]

	_showTitle: bool = True
	_showCenterTitle: bool = False
	_isGrid: bool = False
	_lineWeight: int = 2
	_classColor = randomColor()
	sizeGripBR: Gripper = None
	sizeGripBL: Gripper = None

	# def childEvent(self, event: QChildEvent) -> None:
	# 	if isinstance(event.child(), ComplicationPrototype):
	# 		print(event.child())
	# 	super(ComplicationCluster, self).childEvent(event)

	def __init__(self, parent, showCenterTitle: bool = None, *args, **kwargs):
		super(ComplicationCluster, self).__init__(*args, **kwargs)
		self.setupUi(self)
		self.titleLabel.setIsTitle()
		self.frozen = False
		self.widgetPositions = {
				Position.Top:          self.topArray,
				Position.TopCenter:    self.topArray,
				Position.TopLeft:      self.topLeft,
				Position.TopRight:     self.topRight,
				Position.Center:       self.center,
				Position.CenterLeft:   self.leftArray,
				Position.Left:         self.leftArray,
				Position.CenterRight:  self.rightArray,
				Position.Right:        self.rightArray,
				Position.Bottom:       self.bottomArray,
				Position.BottomCenter: self.bottomArray,
				Position.BottomLeft:   self.bottomLeft,
				Position.BottomRight:  self.bottomRight,
		}
		self.widgetPositions.update({key.value: value for key, value in self.widgetPositions.items()})
		# self.cornerWidgets = [self.topLeft, self.topRight, self.bottomLeft, self.bottomRight]
		# self.grids = [self.center, self.topArray, self.bottomArray, self.leftArray, self.rightArray]
		self.allWidgets = [self.topLeft, self.topArray, self.topRight,
		                   self.leftArray, self.center, self.rightArray,
		                   self.bottomLeft, self.bottomArray, self.bottomRight]
		self._color = QColor(randomColor())
		# self._originalPositions = list(self.layout.getItemPosition(x) for x in range(len([item for item in self.cornerWidgets])))
		# self.fillEmptyCells()
		self.update()
		# self.setAttribute(Qt.WA_StyledBackground, True)
		self.setMouseTracking(True)
		self.titleLabel.hide()
		x = self.titleLabel.sizePolicy()
		x.setRetainSizeWhenHidden(False)
		self.titleLabel.setSizePolicy(x)
		self.topLeft.square = True
		self.bottomLeft.square = True
		self.topRight.square = True
		self.bottomRight.square = True
		self.setMinimumSize(QSize(100, 100))
		self._cell.w = 2
		self._cell.h = 2

		self.mouseHoldTimer = QTimer(self)
		self.mouseHoldTimer.timeout.connect(self.startPickup)
		self.setAcceptDrops(True)
		self.sizeGripBR = Gripper(self)
		self.sizeGripBL = Gripper(self)
		g = self.sizeGripBR.rect()
		g.setWidth(10)
		g.setHeight(10)
		self.sizeGripBR.setGeometry(g)
		self.sizeGripBL.setGeometry(g)

	# def paintEvent(self, event):
	# 	p = QPainter(self)
	# 	top = 0
	# 	bottom = self.rect().bottom()
	# 	lower = self.height()/3
	# 	lowest = lower * 2
	# 	left = self.width()/3
	# 	right = left * 2
	# 	p.drawLine(left, top, left, bottom)
	# 	p.drawLine(right, top, right, bottom)
	# 	# p.drawRect(self.rect())

	def dragEnterEvent(self, event):
		event.accept()

	def dragMoveEvent(self, event):
		print(event)

	def makeResizable(self):
		self.setWindowFlag(Qt.SubWindow, False)
		self.setWindowFlag(Qt.SubWindow, True)
		self.setGripper()

	def mousePressEvent(self, event: QMouseEvent):
		self.clickStart = event.pos()
		self.mouseHoldTimer.start(1000)

	def mouseReleaseEvent(self, event: QMouseEvent):
		self.mouseHoldTimer.stop()

	def mouseMoveEvent(self, event: QMouseEvent) -> None:
		if event.buttons() == Qt.LeftButton and self.clickStart:
			travelFromPress = (event.pos() - self.clickStart).manhattanLength()
			if travelFromPress > 20:
				self.mouseHoldTimer.stop()
			yChange = self.clickStart.y() - event.pos().y()
			if abs(yChange) < self.height() / 3:
				if yChange > 0:
					self.titleLabel.show()
					self._showTitle = True
				else:
					self.titleLabel.hide()
					self._showTitle = False

	def hideEmpty(self, skip: QWidget = None):
		skip = self if skip is None else skip
		if len(self.complications) == 0:
			self.showAll()
		else:
			for item in self.allWidgets:
				if item.isEmpty and item is not skip:
					item.hide()
			withoutCenter = [item.isEmpty for item in self.allWidgets if item is not self.center]
			if any(withoutCenter):
				self.mainLayout.setStretch(0, 0)
				self.mainLayout.setStretch(1, 1)
				self.mainLayout.setStretch(2, 0)
			else:
				self.mainLayout.setStretch(0, 3)
				self.mainLayout.setStretch(1, 6)
				self.mainLayout.setStretch(2, 3)
		self.setGripper()

	@property
	def complications(self):
		return [item for sublist in self.allWidgets for item in sublist._complications]

	def copy(self):
		return self.__class__(self.parent())

	@property
	def state(self):
		state = {'cell':  {k.strip('_'): v for k, v in vars(self.cell).items() if k != 'item'},
		         'type':  'Cluster',
		         'title': self.title}
		for each in self.allWidgets:
			loc = each.objectName()
			state.update({loc: [comp.state for comp in each.complications]})
		return state

	def decideDestination(self, sender, event: QDropEvent):
		boxes = sorted(self.complications, key=lambda widget: goToNewYork(widget, event.pos()))[:1]
		return boxes[0]

	def update(self):
		# if hasattr(self, 'sizeGrip'):
		# 	g = self.sizeGrip.rect()
		# 	g.moveBottom(self.rect().bottom())
		# 	g.moveRight(self.rect().right())
		# 	self.sizeGrip.setGeometry(g)
		super(ComplicationCluster, self).update()

	# def eventFilter(self, obj, event: QEvent):
	# if event.type() == QEvent.MouseButtonPress and isinstance(obj, QSizeGrip):
	# 	event.accept()
	# 	p = self.parent()
	# 	p.layout.removeWidget(self)
	# if event.type() == QEvent.MouseButtonRelease and isinstance(obj, QSizeGrip):
	# 	event.accept()
	# 	self.autoSetCell()
	# 	self.parent().buildGrid()

	def showAll(self):
		for item in self.allWidgets:
			# item.setMinimumSize(QSize(100, 100))
			item.show()

	def hideAll(self):
		for item in self.allWidgets:
			# item.setMinimumSize(QSize(0, 0))
			if item.isEmpty:
				item.hide()

	@property
	def isEmpty(self):
		return any(comp.isEmpty for comp in self.complications)

	@property
	def isGrid(self) -> bool:
		return self._isGrid

	@isGrid.setter
	def isGrid(self, value):
		self._isGrid = value
		if value:
			oldWidget = self.center
			self.center = ClusterGrid(self)
			self.layout.replaceWidget(oldWidget, self.center)
		else:
			oldWidget = self.center
			self.center = Complication(self)
			self.layout.replaceWidget(oldWidget, self.center)

	def addItems(self,
	             *item: Union[Measurement, str, int, float, QWidget, type],
	             position: Position = Position.Bottom,
	             **kwargs):

		destination = self.widgetPositions[position.value]

		# Fill Center first
		if self.center.isEmpty and position != Position.Center:
			if isinstance(item, Iterable):
				item = list(item)
				i = item.pop(0)
			else:
				i = item
			self.center.insert(i)  # , **kwargs)  <--- Implement this!
		if item:
			if position in self.arrays:
				destination.insert(*item)
				destination.show()
			elif position.value in self.cornerWidgets:
				if isinstance(item, tuple) and len(item) > 1:
					self._log.warn(f'Only one [{item[0]}] item can be added here, the rest will be ignored: [{item[1:]}]')
					item = item[0]
				else:
					item = item[0]
				if isinstance(item, (str, int, float)):
					item = Complication(parent=self, value=item)
					# item.setMinimumHeight(100)
					item.setMinimumWidth(100)
					item.show()
				elif issubclass(item, Measurement):
					item = Complication(parent=self, title=item.title, subscriptionKey=item.subscriptionKey)
					item.setMinimumWidth(100)
				elif isinstance(item, QWidget):
					self.layout.replaceWidget(destination, item)
				else:
					self._log.error(f'This item [{item}] can not be added as this [{type(item)}] class')
					return None

	@property
	def title(self):
		if self._title:
			return self._title
		return None

	@title.setter
	def title(self, value):
		if self.showTitle and not self._isGrid:
			self._title = value
		else:
			self._title = None

	@property
	def value(self):
		return self.center.complications

	@value.setter
	def value(self, value):
		if self._isGrid:
			self._log.warn('setting a value does not work with ComplicationGrids')
		else:
			self.center.value = value
			if self.showTitle:
				self.titleLabel.show()
				self.center.titleLabel.hide()
			else:
				self.titleLabel.hide()
				if self._showCenterTitle:
					self.center.titleLabel.show()
				else:
					self.center.titleLabel.hide()

	@property
	def maxFontSize(self):
		return self.center.maxFontSize

	@property
	def valueLabel(self):
		return self.center.valueLabel

	# def resizeEvent(self, event):
	# 	height3 = self.height() * .3
	# 	self.bottomArray.setMaximumHeight(height3)
	# 	self.bottomRight.setMaximumSize(height3, height3)
	# 	self.bottomLeft.setMaximumSize(height3, height3)
	# 	self.topRight.setMaximumSize(height3, height3)
	# 	self.topLeft.setMaximumSize(height3, height3)
	# 	self.leftArray.setMaximumWidth(height3)
	# 	self.rightArray.setMaximumWidth(height3)
	# 	self.topArray.setMaximumHeight(height3)
	# 	super(ComplicationCluster, self).resizeEvent(event)

	def dragCancel(self, index, child, status, drag):
		if status == status.IgnoreAction and child is self:
			if self._complications and index > 0:
				self.parent().plop(self, index)
				self.parent().show()
				self.show()
			else:
				drag.cancel()

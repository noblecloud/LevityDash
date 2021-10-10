import logging
from typing import Optional

from PySide2 import QtSvg
from PySide2.QtGui import QDrag, QFont, QMouseEvent, QPainter, QResizeEvent
from PySide2.QtWidgets import QDialogButtonBox, QFrame, QLineEdit, QMessageBox, QSizeGrip, QSizePolicy, QVBoxLayout, QWidget

from src.api import API
from colors import randomColor
from src.grid.Cell import Cell
from src.observations._observations import Observation, ObservationRealtime
from src.fonts import compact, rounded
from ui.Complication_UI import Ui_Frame
from PySide2.QtCore import QEvent, QMimeData, QPoint, QRect, QSize, Qt, QTimer

from WeatherUnits.base import Measurement

from src.utils import climbFamilyTree
from widgets.grip import Gripper
from widgets.Proto import ComplicationPrototype

log = logging.getLogger(__name__)


class Complication(Ui_Frame, ComplicationPrototype):
	sizeGripBR: Gripper = None
	innerHitBox: QRect
	clickStart: Optional[QPoint] = None
	_classColor = randomColor()
	_lineWeight = 5
	_orphan: bool = None
	_api: API = None
	_cell: Cell

	# def __init__(self, title: str = None, value: Union[Measurement, int, float, str] = None):
	def __init__(self, *args, api: API = None, **kwargs):
		super(Complication, self).__init__(*args, **kwargs)
		self.a = QLineEdit(self)
		self.a.hide()
		self.setupUi(self)
		self.titleLabel.setIsTitle()
		self.setLayout(self.verticalLayout)
		self.update()

		policy = self.sizePolicy()
		policy.setHorizontalPolicy(QSizePolicy.Preferred)
		policy.setVerticalPolicy(QSizePolicy.Preferred)
		policy.setRetainSizeWhenHidden(True)
		self.setSizePolicy(policy)

		self.value = self._value
		self.mouseHoldTimer = QTimer(self)
		self.mouseHoldTimer.timeout.connect(self.startPickup)

		self.setWindowFlag(Qt.SubWindow)
		# self.setAttribute(Qt.WA_NoMousePropagation)
		self.cell.h = 1
		self.cell.w = 1

		if self._glyphTitle:
			self.titleLabel.setGlyph(self._glyphTitle)
		if self._widget:
			self.setWidget(self._widget)
		if self._value is None and self._widget is None:
			self.hide()
		if 'miniature' in kwargs.keys():
			if kwargs['miniature']:
				self.titleLabel.setMinimumHeight(5)
				self.titleLabel.setMaximumHeight(30)

		if 'subTitleUnit' in kwargs.keys():
			self._subTitleUnit = kwargs['subTitleUnit']
		self.sizeGripBR = Gripper(self)
		self.sizeGripBL = Gripper(self)
		g = self.sizeGripBL.rect()
		g.setWidth(20)
		g.setHeight(20)
		self.sizeGripBR.setGeometry(g)
		self.sizeGripBL.setGeometry(g)
		self._indoorRect = None
		if api is not None:
			self.api = api

	def makeResizable(self, value: bool = True):
		self.setWindowFlag(Qt.SubWindow, False)
		self.setWindowFlag(Qt.SubWindow, True)
		self.setGripper()

	def paintEvent(self, event):
		p = QPainter(self)
		if self.indoor:
			p.drawRect(self.indoorRect)
		super(Complication, self).paintEvent(event)

	def update(self):
		if self._showTitle:
			self.titleLabel.setText(self.title)

	@property
	def orphan(self):
		if self._orphan is None:
			parent = climbFamilyTree(self, ComplicationPrototype)
			self._orphan = bool(parent)
		return self._orphan

	@property
	def isEmpty(self):
		return not any([self.valueWidget, self.valueLabel.value])

	@property
	def api(self) -> API:
		return self._api

	@api.setter
	def api(self, value):
		self._api = value

	@property
	def hitBox(self):
		if self.value:
			return self.valueLabel.hitBox
		elif self.widget:
			return self.widget.hitBox
		else:
			log.debug(f'No hitBox defined for {self}')
			return self.rect()

	@property
	def indoor(self):
		if isinstance(self._value, Measurement) and self._value.indoor:
			return True
		return False

	@property
	def state(self):

		return {
				'key':    self.subscriptionKey,
				'type':   'MeasurementComplication',
				'api':    self.api.name,
				'title':  self.title,
				'widget': self.widget,
				'cell':   {k.strip('_'): v for k, v in vars(self.cell).items() if k != 'item'}
		}

	def copy(self):
		itemCopy: Complication = self.__class__(self.parent())
		itemCopy._cell = Cell(**{k.strip('_'): v for k, v in vars(self.cell).items()})
		itemCopy.title = self.title
		itemCopy.value = self.value
		if hasattr(self, 'valueWidget') and self.valueWidget is not None:
			itemCopy.setWidget(self.valueWidget.__class__())
		if hasattr(self, 'source'):
			if self.api is not None and self.api != 'local':
				itemCopy.api = self.api
				itemCopy.api.realtime.subscribe(itemCopy)
		return itemCopy

	def suggestTitle(self, value: str):
		if self._title is None:
			self._title = value

	def setWidget(self, widget: QWidget):
		self.valueWidget = widget
		widget.setParent(self)
		self.layout.replaceWidget(self.valueLabel, self.valueWidget)
		self.valueWidget.show()
		# self.valueWidget.stackUnder(self.sizeGripBL)
		self.valueWidget.stackUnder(self.sizeGripBR)
		self.valueLabel.clear()
		self.titleLabel.hide()
		self.show()

	def resizeEvent(self, event: QResizeEvent) -> None:

		# if hasattr(self, 'sizeGrip') and self.sizeGrip:
		# 	x = self.sizeGrip.geometry()
		# 	x.moveRight(self.rect().right())
		# 	x.moveBottom(self.rect().bottom())
		# 	self.sizeGrip.setGeometry(x)
		# if self._direction is not None:
		# 	self.layout.setDirection(self._direction)
		# 	alignmentValue = Qt.AlignBottom if self._direction == QVBoxLayout.BottomToTop else Qt.AlignTop
		# 	alignmentTitle = Qt.AlignTop if self._direction == QVBoxLayout.BottomToTop else Qt.AlignBottom
		# 	self.valueLabel.setAlignment(Qt.AlignHCenter | alignmentValue)
		# 	self.titleLabel.setAlignment(Qt.AlignHCenter | alignmentTitle)
		# elif self.parent() is not None and self.parent().height() / 2 < self.pos().y() and self._direction is None:
		# 	self.layout.setDirection(QVBoxLayout.BottomToTop)
		# 	self.valueLabel.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
		if self.indoor:
			self.indoorRect.moveTop(self.rect().top() + 5)
			self.indoorRect.moveRight(self.rect().right() - 5)
		super().resizeEvent(event)

	@property
	def indoorRect(self):
		if self._indoorRect is None:
			self._indoorRect = QRect(10, 10, 10, 10)
		return self._indoorRect

	def __repr__(self):
		return f"Complication | {self.title} | {self.value}"

	@property
	def dynamicFont(self) -> QFont:
		if str(self.fontInfo().family()).startswith('SF'):
			if self.dynamicFontSize > 21:
				font = QFont(rounded)
			else:
				font = QFont(compact)
		else:
			font = QFont(self.font())
		font.setPointSizeF(self.dynamicFontSize)
		return font

	@property
	def dynamicFontSize(self):
		return max(self.height() * 0.15, 14)

	def eventFilter(self, obj, event: QEvent):
		if event.type() == QEvent.KeyPress:
			if event.key() == Qt.Key_Return or event.key() == Qt.Key_Escape:
				print('enter')
				if event.key() == Qt.Key_Return:
					self.titleLabel.setText(self.a.text())
					self._title = self.a.text()
				self.a.removeEventFilter(self)
				self.a.hide()
				self.layout.replaceWidget(self.a, self.titleLabel)
				self.titleLabel.show()
		return super(Complication, self).eventFilter(obj, event)

	def mousePressEvent(self, event: QMouseEvent):
		self.clickStart = event.pos()
		if self.hitBox.contains(event.pos()):
			event.accept()
			self.mouseHoldTimer.start(600)

		elif self.titleLabel.hitBox.contains(self.titleLabel.mapFromParent(event.pos())):
			g = self.titleLabel.geometry()
			self.a.setGeometry(g)
			self.a.setFont(self.titleLabel.font())
			self.a.setAlignment(Qt.AlignCenter)
			self.a.setText(self.titleLabel.text)
			self.a.installEventFilter(self)
			self.a.setAttribute(Qt.WA_TranslucentBackground)
			self.layout.replaceWidget(self.titleLabel, self.a)
			self.titleLabel.hide()
			self.a.show()

		else:
			event.ignore()
			super(Complication, self).mousePressEvent(event)

	def mouseReleaseEvent(self, event):
		self.clickStart = None
		self.mouseHoldTimer.stop()
		super(Complication, self).mouseReleaseEvent(event)

	def mouseMoveEvent(self, event: QMouseEvent) -> None:
		print(event.pos())
		if self.clickStart:
			travelFromPress = abs((event.pos() - self.clickStart).manhattanLength())
			if travelFromPress > 5:
				self.mouseHoldTimer.stop()
		if event.buttons() == Qt.LeftButton and self.clickStart:

			yChange = self.clickStart.y() - event.pos().y()
			if abs(yChange) > self.height() / 3:
				if yChange < 0:
					self.titleLabel.show()
					self._showTitle = True
				else:
					self.titleLabel.hide()
					self._showTitle = False

	# self.clickStart = None

	# def update(self):
	# 	self.valueLabel.updateHitBox()
	# 	super(Complication, self).update()

	# def titleOnTop(self, value: bool = True):
	# 	self._direction = QVBoxLayout.TopToBottom if value else QVBoxLayout.BottomToTop
	# 	self.update()

	def showEvent(self, event):
		super(Complication, self).showEvent(event)

	'''customTitle = self._glyphTitle if self._glyphTitle is not None else self._title'''

	def dragCancel(self, index, child, status, drag):
		if status == status.IgnoreAction and child is self:
			self.parent().plop(self, child.cell.i)
			self.show()
			drag.cancel()
		else:
			drag.cancel()


class LocalComplication(Complication):
	_name: str = None

	def __init__(self, *args, **kwargs):
		super(LocalComplication, self).__init__(*args, **kwargs)
		self.setMouseTracking(True)

	@property
	def state(self):
		return {
				'type':   'LocalComplication',
				'title':  self.title,
				'widget': self.widget,
				'class':  self.__class__.__name__,
				'cell':   {k.strip('_'): v for k, v in vars(self.cell).items() if k != 'item'}
		}

	@property
	def name(self):
		return self._name if self._name is not None else self.__class__.__name__

	@property
	def hitBox(self):
		return self.rect()

	def mouseMoveEvent(self, event: QMouseEvent):
		super(LocalComplication, self).mouseMoveEvent(event)


class EditBox(QMessageBox):

	def __init__(self, *args, **kwargs):
		super(EditBox, self).__init__(*args, **kwargs)
		layout = QVBoxLayout(self)
		layout.setObjectName(u"verticalLayout")
		self.textBox = QLineEdit(self)
		self.textBox.setObjectName(u"textBox")
		self.textBox.setClearButtonEnabled(True)
		self.textBox.setPlaceholderText('title')
		layout.addWidget(self.textBox)
		self.buttons = QDialogButtonBox(self)
		self.buttons.setObjectName(u"buttons")
		self.buttons.setOrientation(Qt.Horizontal)
		# self.buttons.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
		layout.addWidget(self.buttons)

	def showWithProperty(self, text: str, value: str):
		self.setWindowTitle(text)
		self.exec_()


class LockedAspectRatio(QFrame):
	def resizeEvent(self, event):
		new_size = self.size()
		new_size.scale(event.size(), Qt.KeepAspectRatio)
		self.resize(new_size)
# super(LockedAspectRatio, self).resizeEvent(event)

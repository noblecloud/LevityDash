from typing import Optional, Union

from PySide2.QtCore import QPoint, QRect, QRectF, QSize
from PySide2.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPaintEvent, QPen, QRegion, QShowEvent, Qt
from PySide2.QtWidgets import QFrame, QGraphicsScene, QGraphicsView, QLabel, QWidget

from WeatherUnits.base import Measurement

from src.colors import Default
from src.fonts import compact, rounded, weatherGlyph
from src.utils import Logger
from colors import randomColor
from widgets.Status import StatusLabel

fontPrecision = 0.5


# def estimateTextSize(font: QFont, string: str) -> tuple[float, float]:
# 	p = QPainterPath()
# 	p.addText(QPoint(0, 0), font, string)
# 	w = p.boundingRect().width()
# 	p.clear()
# 	p.addText(QPoint(0, 0), font, self.text if self.isGlyph else 'E')
# 	h = p.boundingRect().height()
# 	return w, h

@Logger
class DynamicLabel(QWidget):
	_measurement: Optional[Measurement] = None
	_text: Optional[str] = None
	_glyph: Optional[str] = None
	_sharedFontSize: float = None
	_ratio: float = 0
	_maxFontSize: float = 0
	_color: QColor
	_scalar: float = 1.0
	_needsFontSizeUpdate: bool = True
	_type: str = '_text'
	_localHeight: int = None
	_sharedHeight: int = None
	_debug = False
	_hitBox: QRect = None
	_title: bool = False

	def __repr__(self):
		return f"DLabel [{self.name}] | {self.text.__repr__()} in {self.parent().__class__.__name__}"

	def __init__(self, *args: object, **kwargs: object) -> None:
		super(DynamicLabel, self).__init__(*args, **kwargs)
		self._color = QColor(randomColor())
		self._colorAlt = QColor(randomColor())
		self.textWidth = 50
		self.setFont(rounded)
		self.setMinimumHeight(15)
		self.setAttribute(Qt.WA_Hover, False)
		self.setAttribute(Qt.WA_TransparentForMouseEvents)

		self.setFocusPolicy(Qt.NoFocus)

	def clear(self):
		self._text = None
		self._glyph = None
		self._measurement = None
		self.hide()

	@property
	def name(self):
		return self.property('objectName')

	def update(self):
		self.updateFontSize()
		self.updateHitBox()
		super(DynamicLabel, self).update()

	@property
	def isGlyph(self):
		return self._glyph is not None

	@property
	def isText(self):
		return self._text is not None

	@property
	def isMeasurement(self):
		return self._measurement is not None

	@property
	def value(self):
		return self.text

	@value.setter
	def value(self, value):
		if isinstance(value, Measurement):
			self.setMeasurement(value)
		elif isinstance(value, str):
			self.setText(value)
		elif isinstance(value, (float, int)):
			self.setText(str(value))
		else:
			try:
				self.setText(str(value))
			except TypeError:
				self._log.warning(f'{value} can not be converted to text')

	def setFont(self, font):
		self._needsFontSizeUpdate = False
		super().setFont(font)

	@property
	def textSizeHint(self):
		if self._measurement:
			return self._measurement.sizeHint
		return self.text

	@property
	def sharedHeight(self):
		return self._sharedHeight

	@sharedHeight.setter
	def sharedHeight(self, value):
		# if self._sharedHeight is None:
		# 	self._sharedHeight = value
		self._sharedHeight = value

	@property
	def localY(self):
		return self._localHeight

	def setText(self, text: str):
		self._text = text
		self._type = '_text'
		self._glyph = None
		self._measurement = None
		self._needsFontSizeUpdate = True

	def setMeasurement(self, value: Measurement, showUnit: bool = None):
		self._measurement = value
		if showUnit is not None:
			self._measurement.showUnit = showUnit
		self._type = '_measurement'
		self._glyph = None
		self._text = None
		self.update()

	def setGlyph(self, value: str):
		self.setFont(weatherGlyph)
		self._type = '_glyph'
		self._glyph = value
		self._measurement = None
		self._text = None
		self._needsFontSizeUpdate = True

	@property
	def text(self):
		s = getattr(self, self._type)
		return str(s)

	def showEvent(self, event: QShowEvent) -> None:
		super().showEvent(event)

	@property
	def dynamicFont(self) -> QFont:
		height = self.height()
		if not self.isGlyph:
			if height > 60:
				font = QFont(rounded)
			else:
				font = QFont(compact)
		else:
			font = QFont(self.font())
		return font

	def updateFontSize(self):
		font = self.dynamicFont
		self.setFont(font)
		self.textWidth = self.fontMetrics().width(self.textSizeHint)
		self._ratio = self.width() / self.textWidth
		self._maxFontSize = min(font.pointSizeF() * self._ratio, self.height() * .7)

	@property
	def maxSize(self):
		return self._maxFontSize

	@maxSize.setter
	def maxSize(self, value):
		self._maxFontSize = value

	def setScaledContents(self, value):
		pass

	def setMargin(self, value):
		pass

	def resizeEvent(self, event):
		self.updateHitBox()
		super(DynamicLabel, self).resizeEvent(event)

	def updateHitBox(self):
		font = self.font()
		self.updateFontSize()
		size = self.maxSize if not self._sharedFontSize else self._sharedFontSize
		font.setPointSizeF(size)
		self.setFont(font)
		rect = self.fontMetrics().boundingRect(self.rect(), Qt.AlignVCenter | Qt.AlignHCenter, self.text)
		rect.translate(0, rect.height() * .1)
		rect.setHeight(rect.height() * 0.8)
		self._hitBox = rect

	def paintEvent(self, event: QPaintEvent) -> None:
		painter = QPainter(self)
		painter.setPen(self.palette().text().color())

		painter.setBrush(self._color)

		painter.setRenderHint(QPainter.HighQualityAntialiasing)
		painter.setRenderHint(QPainter.Antialiasing)
		painter.setRenderHint(QPainter.TextAntialiasing)

		# minSize = minSize*1.3 if self._glyph else minSize
		font = self.font()
		painter.setBrush(QColor(self._colorAlt))
		if self.debug:
			painter.drawRect(self.rect())
		painter.setBrush(QColor(self._color))

		painter.setFont(font)
		valueRect = painter.boundingRect(self.rect(), Qt.AlignVCenter | Qt.AlignHCenter, self.text)
		tightRect = painter.fontMetrics().tightBoundingRect(self.text)
		tightRect.moveCenter(valueRect.center())
		x = self.height() - tightRect.bottom()
		subFont = QFont(font)
		subFont.setPointSizeF(max(min(x * .7, self.height() * .18), 14))
		if self.debug:
			painter.drawRect(valueRect)
		# painter.drawText(valueRect, Qt.AlignBottom | Qt.AlignHCenter, self._measurement.withoutUnit if self.showSubUnit else str(self._measurement))
		# self._localHeight = valueRect.top()
		if self._measurement is not None and self._measurement._decorator:
			point = valueRect.center()
			point.setX(valueRect.center().x() + self.offsetDecorator())
			valueRect.moveCenter(point)

		if self.showSubUnit:
			painter.setFont(subFont)
			subRect = painter.boundingRect(self.rect(), Qt.AlignVCenter | Qt.AlignCenter, self._measurement.unit)
			# localRect.moveTop(valueRect.top() if self._sharedHeight is None else self._sharedHeight - subRect.height()*.4)
			# valueRect.moveTop(valueRect.top() - subRect.height()*.4)
			tightSubRect = painter.fontMetrics().tightBoundingRect(self._measurement.unit)
			tightSubRect.moveCenter(subRect.center())
			valueRect.translate(0, -tightSubRect.height())
			tightRect.translate(0, -tightSubRect.height() * 0.9)
			subRect.moveTop(tightRect.bottom())
			# place unit name
			painter.drawText(subRect, Qt.AlignTop | Qt.AlignCenter, self._measurement.unit)

		# valueRect.moveTop(valueRect.top() if self._sharedHeight is None else self._sharedHeight)
		painter.setFont(font)
		if self._measurement:
			text = self._measurement.withoutUnit if self.showSubUnit else str(self._measurement)
		else:
			text = self.text
		if self._glyph:
			valueRect.translate(0, self.height() * .05)
			painter.drawText(valueRect, Qt.AlignTop, text)
		else:
			painter.drawText(valueRect, Qt.AlignBottom | Qt.AlignHCenter, text)

		#
		# else:
		# 	self._localHeight = int(valueRect.y())
		# 	if self._sharedHeight is not None:
		# 		# valueRect.setY(self._sharedHeight)
		# 		valueRect.moveTop(self._sharedHeight)
		# 	# painter.drawRect(valueRect)
		# 	painter.drawText(valueRect, Qt.AlignTop | Qt.AlignHCenter, self.text)
		# r = QRectF(valueRect.left(), valueRect.bottom() - valueRect.height() * 0.21, valueRect.width(), self.height())
		# painter.drawRect(r)

		# if hasattr(self.parent(), 'showUnit') and self.parent().showUnit and self._measurement is not None:
		# if self._measurement is not None:

		# brush = QBrush(Default.main)
		# pen = QPen(QColor(Default.main))
		# painter.setBrush(brush)
		# painter.setPen(pen)

		# path.addText((cx - x*1.1), cy + y, self.text)
		# painter.drawPath(path)
		painter.end()

	def hit(self, sender, position: QPoint):
		if self._hitBox is None:
			return True
		position = self.mapFrom(sender, position)
		return self._hitBox.contains(position)

	@property
	def hitBox(self):
		return self._hitBox

	def offsetDecorator(self):
		decorator = self._measurement.decorator
		if decorator == 'º':
			width = self.fontMetrics().widthChar(decorator) * .5
		else:
			width = self.fontMetrics().averageCharWidth() * 0
		return width

	def setSharedFontSize(self, fontSize):
		self._sharedFontSize = min(fontSize, self.maxSize)

	@property
	def sharedFontSize(self):
		return self.maxSize if self.font().family() == 'Weather Icons' else self._sharedFontSize

	def setAlignment(self, *args):
		pass

	def setIndent(self, *args):
		pass

	@property
	def debug(self):
		return self._debug if hasattr(self.parent(), '_debug') and self.parent()._debug else False

	@property
	def showSubUnit(self):
		hasUnit = self._measurement is not None and self._measurement.unit != ''
		if hasUnit:
			return self._measurement._unitSpacer
			unitString = self._measurement.unit
			isLargeEnough = self.height() > 60

			canDisplay = isLargeEnough and hasUnit

			isNotSet = self.parent().subTitleUnit is None
			parentWantsSubUnit = self.parent().subTitleUnit and self.parent().subTitleUnit is not None
			parentWantsUnit = self.parent().showUnit and self.parent().showUnit is not None

			unitTooLarge = canDisplay and len(unitString) >= 3
			valueTooLarge = len(self._measurement.withoutUnit.replace('.', '')) > 4

			if valueTooLarge and unitTooLarge and (parentWantsSubUnit or parentWantsUnit):
				return True

			similarTitle = self.parent().title.lower() == unitString.lower()
			auto = isNotSet and (unitTooLarge or valueTooLarge) and not similarTitle
			return canDisplay and (parentWantsSubUnit or auto)
		else:
			return False

	def setIsTitle(self, value: bool = True):
		self._title = value

	def getObjectName(self):
		if self._title:
			return 'titleLabel'
		else:
			return 'valueLabel'


# class DynamicLabel(StatusLabel):
#
# 	_fontSize: Union[float, int] = None
#
# 	def __init__(self, *args, **kwargs):
# 		super().__init__(*args, **kwargs)
# 		self.setIndent(0)
# 		self.setFont(rounded)
# 		self.setFontSize(100)
# 		# self.setStyleSheet(f"background: {randomColor()}")
#
# 	def resizeEvent(self, event) -> None:
# 		fontSize = min(self.width() * self._ratio * 0.83, self.height() *0.83)
# 		font = QFont(self.font())
# 		font.setPointSizeF(fontSize)
# 		self.setFont(font)
# 		super().resizeEvent(event)
#
# 	def __set__(self, value):
# 		self.setText(value)
# 		super().__set__(value)
#
# 	def setFontSize(self, minSize):
# 		self._fontSize = minSize
#
# 	@property
# 	def maxSize(self):
# 		return self.getWidgetMaximumFontSize(self.text())
#
# 	def setText(self, value):
# 		super(DynamicLabel, self).setText(value)
# 		self._ratio = self.ratio()
#
# 	def setFont(self, value):
# 		super(DynamicLabel, self).setFont(value)
# 		self._ratio = self.ratio()
#
# 	def ratio(self) -> float:
# 		font = QFont(self.font(), pointSize=1000)
# 		estimateWidth, estimateHeight = estimateTextSize(font, self.text())
# 		return estimateHeight / estimateWidth if estimateWidth else 1
#
# 	def getWidgetMaximumFontSize(self, string: str):
#
# 		font = self.font()
# 		widgetRect = self.rect()
# 		widgetWidth = self.width()
# 		widgetHeight = self.height()
#
# 		newFontSize = QRectF()
# 		currentSize = font.pointSizeF()
#
# 		step = currentSize / 4
#
# 		if step <= fontPrecision:
# 			step = fontPrecision * 4.0
#
# 		lastTestedSize = currentSize
#
# 		currentHeight = 0
# 		currentWidth = 0
#
# 		if string == '':
# 			return currentSize
#
# 		while step > fontPrecision or currentHeight > widgetHeight or currentWidth > widgetWidth:
# 			lastTestedSize = currentSize
# 			font.setPointSizeF(currentSize)
# 			fm = QFontMetricsF(font)
#
# 			if isinstance(self, QLabel):
# 				newFontSizeRect = fm.boundingRect(widgetRect, (self.wordWrap() | self.alignment()), string)
# 			else:
# 				newFontSizeRect = fm.boundingRect(widgetRect, 0, string)
#
# 			currentHeight = newFontSizeRect.height()
# 			currentWidth = newFontSizeRect.width()
#
# 			if currentHeight > widgetHeight or currentWidth > widgetWidth:
# 				currentSize -= step
#
# 				if step > fontPrecision:
# 					step /= 2.0
#
# 				if currentSize <= 0:
# 					return currentSize
# 			else:
# 				currentSize += step
#
# 		return lastTestedSize


class DynamicLabelBuddy(StatusLabel):
	_buddy: DynamicLabel = None

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.setIndent(0)

	def setBuddy(self, buddy):
		self._buddy = buddy
		super().setBuddy(buddy)

	def paintEvent(self, event):
		if self._buddy:
			self.setFont(self._buddy.font())
		super().paintEvent(event)


if __name__ == '__main__':
	import sys
	from PySide2.QtWidgets import QApplication, QBoxLayout, QWidget

	import WeatherUnits as wu

	app = QApplication()

	window = DynamicLabel()
	window.show()
	window.setText('test')
	sys.exit(app.exec_())

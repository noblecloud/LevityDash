import logging
from typing import Optional, Union

from PySide2.QtCore import QPoint, QRectF, QSize
from PySide2.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPaintEvent, QPen, QShowEvent, Qt
from PySide2.QtWidgets import QFrame, QGraphicsScene, QGraphicsView, QLabel, QWidget

### Ported from https://github.com/jonaias/DynamicFontSizeWidgets/ ###
from WeatherUnits import Measurement

from src.translators import ConditionValue
from ui import fonts
from ui.colors import Default
from ui.fonts import compact, rounded, weatherGlyph
from utils import Logger, randomColor
from widgets.Graph import Text
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

	def __repr__(self):
		return f"{self.text.__repr__()} in {self.parent().__class__.__name__}: {self.parent().title}"

	def __init__(self, *args: object, **kwargs: object) -> None:
		super(DynamicLabel, self).__init__(*args, **kwargs)
		self._color = QColor(randomColor())
		self.textWidth = 50
		self.setFont(rounded)
		self.setMinimumHeight(30)

	def clear(self):
		self._text = None
		self._glyph = None
		self._measurement = None
		self.hide()

	def update(self):
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

	def setText(self, text: str):
		self._text = text
		self._type = '_text'
		self._glyph = None
		self._needsFontSizeUpdate = True

	# self.setFont(self.dynamicFont)

	def setMeasurement(self, value: Measurement, showUnit: bool = False):
		self._measurement = value
		self._measurement.showUnit = showUnit
		self._type = '_measurement'
		self._glyph = None
		self._text = None
		self._needsFontSizeUpdate = True

	def setGlyph(self, value: str):
		self.setFont(weatherGlyph)
		self._type = '_glyph'
		self._glyph = value
		self._measurement = None
		self._text = None
		self._needsFontSizeUpdate = True

	def resizeEvent(self, event):
		# if self.font().pixelSize() < 0:
		# 	self.setFont(self.dynamicFont)
		super(DynamicLabel, self).resizeEvent(event)

	@property
	def text(self):
		return str(getattr(self, self._type))

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

	@property
	def dynamicFontSize(self):
		if self.maxSize is None:
			return 12
		else:
			return max(self.maxSize, 12) if self._sharedFontSize is None else self._sharedFontSize

	@property
	def maxSize(self):
		font = self.dynamicFont
		self.setFont(font)
		self.textWidth = self.fontMetrics().width(self.textSizeHint)
		self._ratio = self.width() / self.textWidth
		minFontSize = min(font.pointSizeF() * self._ratio, self.height())
		return minFontSize * .95

	def paintEvent(self, event: QPaintEvent) -> None:
		painter = QPainter()
		painter.begin(self)
		font = self.font()
		size = self.maxSize if not self._sharedFontSize else self._sharedFontSize
		font.setPointSizeF(size)
		painter.setFont(font)
		painter.setRenderHint(QPainter.HighQualityAntialiasing)
		painter.setRenderHint(QPainter.Antialiasing)
		painter.setRenderHint(QPainter.TextAntialiasing)
		painter.setBrush(self._color)
		painter.drawRect(self.rect())
		rect = painter.boundingRect(self.rect(), Qt.AlignVCenter | Qt.AlignCenter, self.text)
		painter.drawText(rect, Qt.AlignVCenter | Qt.AlignHCenter, self.text)
		# if hasattr(self.parent(), 'showUnit') and self.parent().showUnit and self._measurement is not None:
		if self._measurement is not None:
			subTitleTop = rect.bottom() + self.height() * 0.2
			r = QRectF(rect.left(), rect.bottom(), rect.width(), rect.bottom() - self.height())
			painter.drawText(r, Qt.AlignVCenter | Qt.AlignBottom, self._measurement.unit)

		# brush = QBrush(Default.main)
		# pen = QPen(QColor(Default.main))
		# painter.setBrush(brush)
		# painter.setPen(pen)

		# path.addText((cx - x*1.1), cy + y, self.text)
		# painter.drawPath(path)
		painter.end()

	# @property
	# def maxSize(self):
	# 	return max(min(f.pointSizeF() * self._ratio, self.height()), 12)

	def setSharedFontSize(self, fontSize):
		self._sharedFontSize = max(fontSize, 12)

	@property
	def sharedFontSize(self):
		return self.maxSize if self.font().family() == 'Weather Icons' else self._sharedFontSize

	def setAlignment(self, *args):
		pass

	def setIndent(self, *args):
		pass


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
# 	def setFontSize(self, size):
# 		self._fontSize = size
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

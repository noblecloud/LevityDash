import logging

from PySide2.QtCore import QRectF
from PySide2.QtGui import QFontMetricsF, QMouseEvent
from PySide2.QtWidgets import QLabel

### Ported from https://github.com/jonaias/DynamicFontSizeWidgets/ ###

fontPrecision = 0.5


class DynamicLabel(QLabel):
	_maxSize: float = 400

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.setIndent(0)

	def paintEvent(self, event):
		newFont = self.font()
		fontSize = self.getWidgetMaximumFontSize(self.text())
		newFont.setPointSizeF(fontSize)
		self.setFont(newFont)

		super().paintEvent(event)

	def setProperty(self, name, value):
		super().setProperty(name, value)
		if name == 'maxSize':
			self._maxSize = float(value)

	def mousePressEvent(self, event: QMouseEvent) -> None:
		print(self)
		logging.info(self)

	@property
	def maxSize(self):
		return self._maxSize

	@maxSize.setter
	def maxSize(self, value):
		self._maxSize = float(value)

	def getWidgetMaximumFontSize(self, string: str):

		font = self.font()
		widgetRect = self.rect()
		widgetWidth = widgetRect.width()
		widgetHeight = widgetRect.height()

		newFontSize = QRectF()
		currentSize = font.pointSizeF()

		step = currentSize / 2.0

		if step <= fontPrecision:
			step = fontPrecision * 4.0

		lastTestedSize = currentSize

		currentHeight = 0
		currentWidth = 0

		if string == '':
			return currentSize

		# if currentSize > self._maxSize:
		# 	print('exting with {} of {}'.format(currentSize, self._maxSize))
		# 	return currentSize

		while step > fontPrecision or currentHeight > widgetHeight or currentWidth > widgetWidth:
			lastTestedSize = currentSize
			font.setPointSizeF(currentSize)
			fm = QFontMetricsF(font)

			# x = QLabel()
			# x.alignment()

			if isinstance(self, QLabel):
				newFontSizeRect = fm.boundingRect(widgetRect, (self.wordWrap() | self.alignment()), string)
			else:
				newFontSizeRect = fm.boundingRect(widgetRect, 0, string)

			currentHeight = newFontSizeRect.height()
			currentWidth = newFontSizeRect.width()

			if currentHeight > widgetHeight or currentWidth > widgetWidth:
				currentSize -= step

				if step > fontPrecision:
					step /= 2.0

				if currentSize <= 0:
					return currentSize
			else:
				currentSize += step

		return lastTestedSize

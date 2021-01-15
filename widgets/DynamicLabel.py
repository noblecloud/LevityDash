import logging

from PySide2.QtCore import QRectF
from PySide2.QtGui import QFont, QFontMetricsF
from PySide2.QtWidgets import QLabel

### Ported from https://github.com/jonaias/DynamicFontSizeWidgets/ ###
from translators._translator import ConditionValue
from widgets.Status import StatusLabel

fontPrecision = 0.5


class DynamicGlyph(StatusLabel):
	_glyphFont = QFont()
	_glyphFont.setFamily(u"Weather Icons")

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.setFont(self._glyphFont)
		self.setIndent(0)

	def paintEvent(self, event):
		newFont = self.font()
		fontSize = self.getWidgetMaximumFontSize(self.text())
		newFont.setPointSizeF(fontSize)
		# newFont.setFamily(u"Weather Icons")
		self.setFont(newFont)
		super().paintEvent(event)

	def _setGlyph(self, glyph):
		if isinstance(glyph, ConditionValue):
			self.setText(glyph.glyph)
		elif isinstance(glyph, str):
			try:
				self.setText(chr(int(glyph, 16)))
			except ValueError:
				logging.error('Glyph must be valid hex code: received: {}'.format(glyph))
		elif isinstance(glyph, int):
			self.setText(chr(glyph))
		else:
			self.setText('')

	@property
	def glyph(self):
		return self._glyph

	@glyph.setter
	def glyph(self, value):
		self._setGlyph(value)
		self.update()

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



class DynamicLabel(StatusLabel):
	_fontFamily: str
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

	def setBuddyFontSize(self):
		buddy = self.buddy()
		buddyFont = buddy.font()
		buddyFontSize = buddyFont.pointSizeF()

		ownFont = self.font()
		ownFontSize = ownFont.pointSizeF()
		print(buddyFontSize, ownFontSize)
		if buddyFontSize > ownFontSize:
			buddy.setFont(ownFont)
		else:
			self.setFont(buddyFont)

	def __set__(self, value):
		self.setText(value)
		super().__set__(value)

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

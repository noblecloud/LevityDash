from numpy import sqrt
from PySide2 import QtCore, QtWidgets
from PySide2.QtCore import Property, QEasingCurve, QPoint, QPointF, QPropertyAnimation, Qt, Signal
from PySide2.QtGui import QBrush, QFont, QPainter, QPainterPath, QPen, QPolygonF
from WeatherUnits.derived import Wind
from WeatherUnits.length import Meter
from WeatherUnits.others import Direction
from WeatherUnits.time import Second

from src.utils import estimateTextFontSize, estimateTextSize
from ui.colors import Default


class windRose(QtWidgets.QWidget):
	_rotation: Direction = Direction(0.0)
	_speed: Wind = Wind(Meter(0.0), Second(1))
	_animation: QPropertyAnimation
	speed: Wind
	rotation: int
	valueChanged = Signal(float)
	clicked = Signal()

	def __init__(self, *args, **kwargs):
		super(windRose, self).__init__(*args, **kwargs)
		self._animation = QPropertyAnimation(self, b'rotation')
		self._animation.setEasingCurve(QEasingCurve.InOutCubic)

	def animate(self, rotation: Direction = None, absolute: bool = False, duration: int = 2000):
		if self._animation.state() != QtCore.QAbstractAnimation.Running:
			if rotation is not None:
				self._animation.setStartValue(self.rotation)
				if absolute:
					if self._animation.startValue() > 180 and rotation.int % 360 == 0:
						self._animation.setEndValue(Direction(360))
					else:
						self._animation.setEndValue(rotation.int)
				else:
					self._animation.setEndValue(self.rotation + rotation.int)
				self._animation.setDuration(duration)
			else:
				self._animation.setStartValue(Direction(0))
				self._animation.setEndValue(Direction(360))
				self._animation.setDuration(duration)
			self._animation.start()

	def resizeEvent(self, event):
		self.fontLarge = QFont(self.font())
		self.fontLarge.setKerning(QFont.AbsoluteSpacing)
		self.fontLarge.setWeight(70)
		self.fontLarge.setPixelSize(self.radius * .6)
		super().resizeEvent(event)

	@property
	def radius(self):
		return min(self.height(), self.width()) * .4

	def paintEvent(self, event):
		paint = QPainter()
		paint.begin(self)
		paint.setRenderHint(QPainter.HighQualityAntialiasing)
		paint.setRenderHint(QPainter.Antialiasing)
		cx, cy = self.width() * 0.5, self.height() * 0.5
		cw, ch = self.width(), self.height()
		pointerHeight = self.radius * 0.178
		base = pointerHeight

		# Draw Circle
		radius = self.radius
		paint.translate(cx, cy)
		paint.rotate(self._rotation)
		paint.translate(-cx, -cy)
		penWidth = sqrt(self.height() ** 2 + self.width() ** 2) * 0.08
		pen = QPen(Default.main, 1)
		paint.setPen(pen)
		paint.setBrush(QBrush(Default.main))
		path = QPainterPath()
		path.addEllipse(QPoint(cx, cy), radius, radius)
		path.addEllipse(QPoint(cx, cy), radius * 0.7, radius * 0.7)
		paint.drawPath(path)
		paint.setBrush(Default.main)

		paint.setPen(QPen(Default.main, 0))

		# Draw Arrow
		middle = QPointF(cx, cy - pointerHeight - radius)
		left = QPointF(cx - base, cy - radius + 10)
		right = QPointF(cx + base, cy - radius + 10)
		arrow = QPolygonF()
		arrow.append(middle)
		arrow.append(left)
		arrow.append(right)
		paint.drawPolygon(arrow)

		paint.translate(cx, cy)
		paint.rotate(-self._rotation)
		paint.translate(-cx, -cy)
		text = QPainterPath()
		text.setFillRule(Qt.WindingFill)
		speed = self.speed
		font = QFont(self.fontLarge)
		x, y, cardFont = estimateTextFontSize(self.fontLarge, self._rotation.cardinal, (radius * 0.5 * 2, radius * 0.5 * 2))
		x1, y1, speedFont = estimateTextFontSize(self.fontLarge, self.speed.str, (radius * 0.5 * 2, radius * 0.5 * 2))
		text.addText(cx - (x / 2) * 1.05, cy, cardFont, self._rotation.cardinal)
		text.addText(cx - (x1 / 2) * 1.05, cy + y1 + radius * 0.05, speedFont, self.speed.str)
		paint.drawPath(text)

	def shrinkFont(self, text: str):
		font = QFont(self.fontLarge)
		x, y = estimateTextSize(font, text)
		radius = self.radius
		while x > radius * 0.5 * 2:
			size = font.pixelSize()
			if font.pixelSize() < 10:
				break
			font.setPixelSize(size - 3)
			x, y = estimateTextSize(font, text)
		return font

	@property
	def duration(self):
		return self._animation.duration()

	@duration.setter
	def duration(self, value):
		self._animation.setDuration(value)

	@property
	def easing(self):
		return self._animation.getEasingCurve()

	@easing.setter
	def easing(self, value: QEasingCurve):
		if isinstance(QEasingCurve, value):
			self._animation.setEasingCurve(value)
		else:
			print('Not a valid easing curve')

	@Property(float)
	def rotation(self) -> float:
		return float(self._rotation)

	@rotation.setter
	def rotation(self, value: float):
		if value != self._rotation:
			self._rotation = Direction(value)
			self.update()
			self.valueChanged.emit(value)

	@property
	def speed(self):
		return self._speed

	@speed.setter
	def speed(self, value):
		self._speed = value

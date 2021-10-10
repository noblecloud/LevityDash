from dataclasses import dataclass

from math import log

from PySide2.QtGui import QColor, QLinearGradient
from WeatherUnits import Temperature


def cleanup(value, limit):
	if value < 0:
		value = 0
	elif value > limit:
		value = limit
	else:
		value = int(value)
	return value


k = 500


def kelvinToRGB(temp):
	global k
	# https://tannerhelland.com/2012/09/18/convert-temperature-rgb-algorithm-code.html

	temp = temp / 100

	# calculate red
	if temp <= 66:
		red = 255
	else:
		red = temp - 60
		red = 329.698727446 * pow(red, -0.1332047592)

	red = cleanup(red, 255)

	# calculate green
	if temp <= 66:
		green = temp
		green = 99.4708025861 * log(green) - 161.1195681661
	else:
		green = temp - 60
		green = 288.1221695283 * pow(green, -0.0755148492)

	green = cleanup(green, 255)

	# calculate blue
	if temp >= 66:
		blue = 255
	else:
		if temp <= 19:
			blue = 0
		else:
			blue = temp - 10
			blue = 138.5177312231 * log(blue) - 305.0447927307

	blue = cleanup(blue, 255)
	k += 100
	return red, green, blue


def rgbHex(r, g, b):
	r = hex(r)[2:]
	g = hex(g)[2:]
	b = hex(b)[2:]
	return f'#{r}{g}{b}'


class Default:
	main = QColor(*kelvinToRGB(6500))


import random

x = "* {background-color: black; color: " + str(random.random()) + "}"


def color():
	return f"* {{background-color: black; color: {rgbHex(*kelvinToRGB(k))}}}"


def kelvinToQColor(kelvin: int = None):
	return QColor(*kelvinToRGB(kelvin if kelvin else 6500))


def randomColor(min: int = 0, max: int = 255, prefix: str = '#') -> str:
	from random import randrange
	rgb = [0, 0, 0]
	while sum(rgb) < 300 or any(map(lambda x: x > 200, rgb)) and any(map(lambda x: x < 50, rgb)):
		rgb = list(map(lambda _: randrange(min, max, 1), rgb))
	return prefix + ''.join([f'{i:02x}' for i in rgb]).upper()


@dataclass
class Rain:
	azure = QColor(59, 171, 253)
	maya = QColor(109, 193, 255)
	freshAir = QColor(178, 221, 255)
	vividSky = QColor(6, 205, 244)
	cornflower = QColor(34, 75, 139)


@dataclass
class Gradients:

	def grad(self) -> QLinearGradient:
		d = self.parent.figure.palette().text().color()
		gradient = QLinearGradient(QPointF(0, self.parent.gradientPoints[0]), QPointF(0, self.parent.gradientPoints[1]))

		# gradient = QLinearGradient(QPointF(0, 0), QPointF(0, 1000))
		def t(v):
			return 100 / 120 * v / 100

		gradient.setColorAt(t(120), colors.qcolor(4000))
		gradient.setColorAt(t(100), colors.qcolor(2000))
		gradient.setColorAt(t(75), colors.qcolor(2500))
		gradient.setColorAt(t(50), colors.qcolor(6500))
		gradient.setColorAt(t(70), colors.qcolor(6500))
		# gradient.setColorAt(.65, colors.qcolor(6500))
		gradient.setColorAt(t(0), colors.qcolor(25000))
		return gradient

	@property
	def Temperature(self) -> QLinearGradient:
		gradient = QLinearGradient(0, 0, 0, 0)

		gradient.setColorAt(t(120), kelvinToQColor(4000))
		gradient.setColorAt(t(100), kelvinToQColor(2000))
		gradient.setColorAt(t(75), kelvinToQColor(2500))
		gradient.setColorAt(t(70), kelvinToQColor(6500))
		gradient.setColorAt(t(50), kelvinToQColor(6500))
		gradient.setColorAt(t(0), kelvinToQColor(25000))
		return gradient

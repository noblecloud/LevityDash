from math import log

from PySide2.QtGui import QColor


def __clampChannel(value):
	return 0 if value < 0 else 255 if value > 255 else value


def kelvinToRGB(temp):
	# https://tannerhelland.com/2012/09/18/convert-temperature-rgb-algorithm-code.html

	def cleanup(value, limit):
		if value < 0:
			value = 0
		elif value > limit:
			value = limit
		else:
			value = int(value)
		return value

	temp /= 100

	# calculate red
	if temp <= 66:
		red = 255
	else:
		red = temp - 60
		red = 329.698727446*pow(red, -0.1332047592)

	red = __clampChannel(red)

	# calculate green
	if temp <= 66:
		green = temp
		green = 99.4708025861*log(green) - 161.1195681661
	else:
		green = temp - 60
		green = 288.1221695283*pow(green, -0.0755148492)

	green = __clampChannel(green)

	# calculate blue
	if temp >= 66:
		blue = 255
	else:
		if temp <= 19:
			blue = 0
		else:
			blue = temp - 10
			blue = 138.5177312231*log(blue) - 305.0447927307

	blue = __clampChannel(blue)
	return red, green, blue


def rgbHex(r, g, b, a=None):
	r = hex(r)[2:]
	g = hex(g)[2:]
	b = hex(b)[2:]
	if a is None:
		return f'#{r}{g}{b}'
	a = hex(a)[2:]
	return f'#{r}{g}{b}{a}'


def kelvinToQColor(kelvin: int = None):
	return QColor(*kelvinToRGB(kelvin if kelvin else 6500))


def randomColor(min: int = 0, max: int = 255, prefix: str = '#') -> str:
	from random import randrange
	rgb = [0, 0, 0]
	while sum(rgb) < 300 or any(map(lambda x: x > 200, rgb)) and any(map(lambda x: x < 50, rgb)):
		rgb = list(map(lambda _: randrange(min, max, 1), rgb))
	return prefix + ''.join([f'{i:02x}' for i in rgb]).upper()


__all__ = ['kelvinToQColor', 'kelvinToRGB', 'rgbHex', 'randomColor']

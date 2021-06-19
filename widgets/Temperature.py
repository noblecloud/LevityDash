from utils import Position
from widgets.Complication import Complication, ComplicationArrayHorizontal
from widgets.LargeComplication import LargeComplication
from widgets.moon import Moon
import logging

if __name__ == '__main__':
	import sys
	from PySide2.QtWidgets import QApplication, QDesktopWidget, QMainWindow

	logging.getLogger('MBDisplay').setLevel(logging.ERROR)

	import WeatherUnits as wu

	app = QApplication()

	window = QMainWindow()
	hor = ComplicationArrayHorizontal()
	window.setCentralWidget(hor)
	hor.setProperty('balanced', True)
	a = LargeComplication(app, title='Temperature', showTitle=False)
	b = LargeComplication(app, title='Temperature', showTitle=False)
	c = LargeComplication(app, title='grid', isGrid=True)
	light = LargeComplication(window, title='Light', subscriptionKey='illuminance', showTitle=False)
	a.value = wu.temperature.Celsius(20)
	uvi = wu.others.UVI(7)
	light.center.value = wu.others.Illuminance(11923.0)
	b.value = uvi
	strikes = wu.others.Strikes(4)
	ts = wu.others.Voltage(2.45)
	s = wu.derived.Wind(wu.length.Mile(3.4), wu.time.Hour(1))
	# humidity = Complication(window, value=wu.others.Humidity(64), glyphTitle='')
	# c.center.insert(light, uvi, strikes)
	# window.addItems(humidity, light, position=Position.Top)
	a.addItems(uvi, strikes, position=Position.Left)
	b.addItems(ts, s)
	# window.addItems(uvi, position=Position.TopLeft)
	hor.insert(a, b)

	display_monitor = 1
	monitor = QDesktopWidget().screenGeometry(display_monitor)
	w, h = 600, 600
	window.setGeometry((monitor.left() - w) / 2, 200, w, h)

	window.show()
	sys.exit(app.exec_())

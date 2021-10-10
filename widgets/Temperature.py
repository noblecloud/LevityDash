import logging

from widgets.Complication import Complication
from widgets.ComplicationArray import ComplicationArrayGrid, ComplicationArrayHorizontal
from widgets.DragDropWindow import DragDropWindow
from widgets.DynamicLabel import DynamicLabel
from widgets.ComplicationCluster import ComplicationCluster
from widgets.moon import Moon
from PySide2.QtWidgets import QApplication, QDesktopWidget, QFrame, QLabel, QMainWindow, QVBoxLayout, QWidget

from widgets.Proto import ComplicationPrototype
from widgets.Wind import WindSubmodule

debug = True

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class Window(QMainWindow):

	def __init__(self, *args, **kwargs):
		super(Window, self).__init__(*args, **kwargs)


if __name__ == '__main__':
	import sys
	from PySide2.QtWidgets import QApplication, QDesktopWidget, QMainWindow

	# logging.getLogger().setLevel(logging.CRITICAL)
	import WeatherUnits as wu

	app = QApplication()

	window = DragDropWindow()
	window.setLayout(QVBoxLayout())
	hor = ComplicationArrayGrid(acceptCluster=True)
	# grid = ComplicationArrayGrid()
	# hor.insert(grid)

	a = ComplicationCluster(app, title='Temperature', showTitle=False)
	fahrenheit = wu.Temperature.Fahrenheit(66.6)
	humidity = wu.others.Humidity(84)
	dewpointComp = Complication(value=wu.Temperature.Fahrenheit(74), title='Dewpoint')
	a.addItems(Complication(window, value=fahrenheit))
	uvi = wu.Light.UVI(7)
	a.addItems(humidity)
	a.addItems(dewpointComp)
	a.addItems(uvi)

	b = ComplicationCluster(app, title='Wind', showTitle=False)
	windValue = Complication(value=wu.derived.Wind(wu.length.Mile(3.4), wu.Time.Hour(1)), showTitle=False)
	b.addItems(windValue)

	c = ComplicationCluster(app, title='c', showTitle=False)
	strikes = wu.others.Strikes(4)
	c.addItems(Complication(value=strikes))
	c.setObjectName('c')

	ts = Complication(value=fahrenheit, showUnit=True, debug=False)
	s = Complication(value='\uf019', debug=False, glyph=True)
	c.addItems(ts, s)

	hor.insert(a, b, c)
	print(hor._complications)

	window.setCentralWidget(hor)

	display_monitor = 1
	monitor = QDesktopWidget().screenGeometry(display_monitor)
	w, h = 600, 600
	window.setGeometry((monitor.left() - w) / 2, 200, w, h)

	window.show()
	loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict]
	sys.exit(app.exec_())

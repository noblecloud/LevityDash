# This Python file uses the following encoding: utf-8
import sys
from time import strftime

from PySide2 import QtCore
from PySide2.QtCore import QFile
from PySide2.QtUiTools import QUiLoader
from PySide2.QtWidgets import QApplication, QMainWindow

from display import dataDisplay
from forecast import nowcast, hourlyForecast
from realtime import Realtime
from ui.main_UI import QFont, QSizePolicy, Ui_weatherDisplay
from widgets.Complication import Complication
from widgets.DynamicLabel import DynamicLabel
from widgets.GlyphBox import GlyphBox
from widgets.Temperature import LargeBox


class MainWindow(QMainWindow, Ui_weatherDisplay):
	ui: QMainWindow

	def __init__(self, *args, **kwargs):
		super(MainWindow, self).__init__()
		self.setupUi(self)
		self.indoor.title.setText('Indoors')
		self.outdoor.title.setText('Outdoors')
		self.moonPhase.glyph = 0xF09A
		self.subA.glyph = 0xF025
		self.installEventFilter(self)

		lat, lon = 37.40834, -76.54845
		key = "q2W59y2MsmBLqmxbw34QGdtS5hABEwLl"
		AmbKey = 'e574e1bfb9804a52a1084c9f1a4ee5d88e9e850fc1004aeaa5010f15c4a23260'
		AmbApp = 'ec02a6c4e29d42e086d98f5db18972ba9b93d864471443919bb2956f73363395'

		self.forecast = hourlyForecast(key, (lat, lon), 'hourly',
		                          measurementFields=['temp', 'precipitation', 'sunrise', 'sunset',
		                                             'feels_like', 'dewpoint', 'precipitation_probability'])

		self.realtime = Realtime(AmbKey, AmbApp)
		self.realtime.getData()

		self.forecastDisplay = dataDisplay(self.forecast, (1920, 1080, 200))

		self.frame = self.forecastDisplay.setQtCanvas()
		self.forecastDisplay.plot()

		sizePolicy7 = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
		sizePolicy7.setHorizontalStretch(9)
		sizePolicy7.setVerticalStretch(0)
		sizePolicy7.setHeightForWidth(self.frame.sizePolicy().hasHeightForWidth())
		self.frame.setSizePolicy(sizePolicy7)

		self.gridLayout_3.addWidget(self.frame, 0, 1, 1, 1)

		self.update()

	def buildUI(self):

		loader = QUiLoader()
		loader.registerCustomWidget(DynamicLabel)
		loader.registerCustomWidget(Complication)
		loader.registerCustomWidget(LargeBox)
		loader.registerCustomWidget(GlyphBox)

		file = QFile("ui/main.ui")
		file.open(QFile.ReadOnly)
		self.ui = loader.load(file)
		file.close()

		self.loadStyle()

	def loadStyle(self):
		sshFile = "styles/main.qss"
		with open(sshFile, "r") as fh:
			self.setStyleSheet(fh.read())
		self.update()

	def eventFilter(self, obj, event):
		if event.type() == QtCore.QEvent.KeyPress:
			if event.key() == QtCore.Qt.Key_R:
				print('refresh')
				self.loadStyle()
			if event.key() == QtCore.Qt.Key_B:
				print('rebuild')
				self.hide()
				self.buildUI()
				self.show()
			if event.key() == QtCore.Qt.Key_P:
				self.forecastDisplay.plot()
				self.update()
		elif event.type() == QtCore.QEvent.MouseButtonPress:
			print(obj)
		return super(MainWindow, self).eventFilter(obj, event)

	def update(self):
		self.time.setText(strftime('%-I:%M'))
		self.date.setText(strftime('%a, %B %-d'))
		self.indoor.temperature.setText(str(self.realtime.nearest.indoor.temperature) + 'º')
		self.outdoor.temperature.setText(str(self.realtime.nearest.outdoor.temperature) + 'º')

		glyphs = QFont()
		glyphs.setPointSize(30)
		glyphs.setFamily(u"Weather Icons")
		self.sunSet.value.setText(self.forecast.data['sunrise'][0].strftime('%-I:%M'))
		self.sunSet.title.setText('')
		self.sunSet.title.setFont(glyphs)
		# self.sunSet.title.setFontSize(20)
		self.sunRise.value.setText(self.forecast.data['sunset'][0].strftime('%-I:%M'))
		self.sunRise.title.setFont(glyphs)
		self.sunRise.title.setText('')


# def keyPressEvent(self, event):
# 	print('test')
# 	if event.key() == QtCore.Qt.Key_R:
# 		print("refreshing")
# 		self.loadStyle()
# 	elif event.key() == QtCore.Qt.Key_U:
# 		self.ui.setupUi(self)
# 	elif event.key() == QtCore.Qt.Key_B:
# 		print('building UI')
# 		self.buildUI()
# 	event.accept()


if __name__ == "__main__":
	app = QApplication()
	window = MainWindow()

	# print(window.ui.moonPhase.setProperty('charStr', ''))

	window.show()
	# window.showFullScreen()

	sys.exit(app.exec_())

# This Python file uses the following encoding: utf-8
import logging
import sys
from time import strftime
# import pretty_errors

# pretty_errors.configure(filename_display=pretty_errors.FILENAME_FULL)

from PySide2 import QtCore
from PySide2.QtCore import QTimer
from PySide2.QtGui import QFont, QPainter, QPixmap
from PySide2.QtWidgets import QApplication, QDesktopWidget, QMainWindow

from src.api import AmbientWeather, AWStation
from src.api.errors import APIError
from src.api.forecast import dailyForecast, hourlyForecast
from src.api.weatherFlow import WeatherFlow, WFStation
from src.translators import ClimacellConditionInterpreter, ConditionInterpreter
from ui.main_UI import Ui_weatherDisplay
from utils import Logger
from widgets.Complication import Complication
from widgets.LargeComplication import LargeComplication
from widgets.Graph import Graph
import WeatherUnits

from widgets.moon import Moon
from widgets.Wind import WindSubmodule
from widgets.WindRose import windRose

WeatherUnits.config.read('config.ini')


@Logger
class MainWindow(QMainWindow, Ui_weatherDisplay):
	forecastGraph: Graph
	weatherFlow: WeatherFlow
	ambientWeather: AmbientWeather
	dailyForecast: dailyForecast
	forecast: hourlyForecast
	glyphs: QFont
	checkThreadTimer: QTimer
	ui: QMainWindow
	interpreter: ConditionInterpreter = ClimacellConditionInterpreter()
	live = True
	timeTraveling = False

	def __init__(self, *args, **kwargs):
		super(MainWindow, self).__init__()
		self.setupUi(self)

		# Clear preset data
		# self.fadeRealtimeItems()

		self.checkThreadTimer = QtCore.QTimer(self)

		self.installEventFilter(self)
		self.buildFonts()
		self.buildUI()

		self.lat, self.lon = 37.40834, -76.54845
		self.key = "q2W59y2MsmBLqmxbw34QGdtS5hABEwLl"
		self.AmbKey = 'e574e1bfb9804a52a1084c9f1a4ee5d88e9e850fc1004aeaa5010f15c4a23260'
		self.AmbApp = 'ec02a6c4e29d42e086d98f5db18972ba9b93d864471443919bb2956f73363395'

		# self.connectForecast()
		self.aw = AWStation()
		self.wf = WFStation()
		self.connectAW()
		self.connectWF()
		self.setRealtimeItems()
		self.refreshTimeDateTemp()

		# self.subA.value.setText(self.forecast.data['sunrise'][0].strftime('%-I:%M'))
		# self.subA.title.setFont(self.glyphs)

		self.loadStyle()
		self.subscribe()

	def subscribe(self):
		self.aw.indoor.subscribe(self.indoor)
		self.aw.indoor.subscribe(*self.indoor.complications)
		self.wf.obs.subscribe(self.outdoor)
		self.wf.obs.subscribe(*self.bottom.complications)
		self.wf.obs.subscribe(*self.outdoor.complications)
		self.wf.obs.subscribe(self.light)

	def testEvent(self, event):
		self._log.info('Testing Signal:')
		self._log.info(event)

	def connectAW(self):
		try:
			self.aw.getData()
			self.checkThreadTimer.singleShot(1000 * 1, self.updateAW)
		except APIError:
			self._log.error("Unable to reach AmbientWeather API, trying again in 1 minute")
			self.checkThreadTimer.singleShot(1000 * 60, self.connectAW)

	def updateAW(self):

		try:
			self.aw.update()
			self.checkThreadTimer.singleShot(1000 * 60, self.updateAW)
		except APIError:
			self.fadeRealtimeItems()
			self._log.error("No realtime data, trying again in 1 minute")
			self.checkThreadTimer.singleShot(1000 * 60, self.updateAW)

	def connectWF(self):
		try:
			self.wf.getData()
			self._log.info('WeatherFlow connected')
			self.checkThreadTimer.singleShot(1000 * 60, self.updateWF)

		# self.wf.messenger.signal.connect(self.setRealtimeItems)
		except APIError:
			self._log.error("Unable to reach WeatherFlow API, trying again in 1 minute")
			self.checkThreadTimer.singleShot(1000 * 60, self.connectWF)

	def updateWF(self):

		try:
			self.wf.getData()
			self._log.info('WeatherFlow updated')
			self.checkThreadTimer.singleShot(1000 * 60, self.updateWF)
		except APIError:
			self.fadeRealtimeItems()
			self._log.error("No realtime data, trying again in 1 minute")
			self.checkThreadTimer.singleShot(1000 * 60, self.updateWF)

	def connectForecast(self):

		try:
			self.forecast = hourlyForecast()
			self.dailyForecast = dailyForecast(measurementFields=['weather_code'])
			self.forecastGraph.data = self.forecast
			self.checkThreadTimer.singleShot(1000 * 60 * 5, self.updateForecast)
		except ValueError:
			self._log.error("No forecast data, trying again in 1 minute")
			self.checkThreadTimer.singleShot(1000 * 60, self.connectForecast)

	def pickEvent(self, event):
		self._log.info('Graph pickEvent')
		thisline = event.artist
		xdata = thisline.get_xdata()
		ydata = thisline.get_ydata()
		ind = event.ind
		points = tuple(zip(xdata[ind], ydata[ind]))
		print(points[1][0])

	def buildFonts(self):
		self.glyphs = QFont()
		self.glyphs.setPointSize(30)
		self.glyphs.setFamily(u"Weather Icons")

	def timeTravel(self, event):
		from matplotlib.dates import num2date
		travel = num2date(event.xdata)
		self.time.setText(travel.strftime('%-I:%M'))
		self.date.setText(travel.strftime('%a, %B %-d'))

	def startTimeTravel(self, event):
		print('starting time travel')
		self.timeTraveling = True
		self.travelID = self.forecastGraph.mpl_connect('motion_notify_event', self.timeTravel)

	def stopTimeTravel(self, event):
		print('stopping time travel')
		self.timeTraveling = False
		self.forecastGraph.mpl_disconnect(self.travelID)
		self.refreshTimeDateTemp()

	def setForecastItems(self):
		if not self.timeTraveling:
			self._log.info('setting forecast items')
			# Current Conditions
			today = self.dailyForecast.data[0]
		# self.conditions.glyph = self.interpreter[today.measurements['weather_code'].value]

		# Outdoor Air Quality
		# self.outdoor.SubAValue.setText(('{:4d}'.format(round(self.forecast.data['epa_aqi'][0]))))

		# Sunrise/Sunset
		self.sunSet.value = self.forecast.data['sunset'][0].strftime('%-I:%M')
		self.sunRise.value = self.forecast.data['sunrise'][0].strftime('%-I:%M')

	def updateForecast(self):
		try:
			self.forecast.update()
			self.dailyForecast.update()
			self.forecastGraph.data = self.forecast
			self.setForecastItems()
			self._log.debug('Forecast updated')
			self.checkThreadTimer.singleShot(1000 * 60 * 5, self.updateForecast)
		except AttributeError:
			self.fadeForecastItems()
			self._log.error("No forecast data, trying again in 1 minute")
			self.checkThreadTimer.singleShot(1000 * 60, self.updateForecast)

	def setRealtimeItems(self) -> None:
		pass

	# Wind Widget
	# self.subB.setVector(self.wf.obs.speed, self.wf.obs.direction)
	# self.subB.topLeft.value = self.wf.obs.gust
	# self.subB.topRight.value = self.wf.obs.lull
	#
	# self.subA.main.value = self.wf.obs.rate
	# self.subA.a2.value = self.wf.obs.daily
	# self.subA.a3.value = self.wf.obs.minutes.auto
	#
	# # Temperatures

	# # Outdoor
	# # self.outdoor.live = True

	# self.wind.value = windRose()

	# self.outdoor.SubAValue.setText(str(round(self.forecast.data['epa_aqi'][0])))

	def loadStyle(self):
		sshFile = "styles/main.qss"
		with open(sshFile, "r") as fh:
			self.setStyleSheet(fh.read())

	def eventFilter(self, obj, event):
		if event.type() == QtCore.QEvent.KeyPress:
			if event.key() == QtCore.Qt.Key_P:
				self.aw.indoor.update({'temperature': self.aw.indoor.temperature})
			if event.key() == QtCore.Qt.Key_I:
				self.bottom.insert(self.light)
			if event.key() == QtCore.Qt.Key_Q:
				self.close()
			if event.key() == QtCore.Qt.Key_F:
				if self.isFullScreen():
					self.showMaximized()
				else:
					self.showFullScreen()
		# 		print('refresh')
		# 		self.loadStyle()
		# 	if event.key() == QtCore.Qt.Key_B:
		# 		print('rebuild')
		# 		self.hide()
		# 		self.buildUI()
		# 		self.show()
		# 	if event.key() == QtCore.Qt.Key_P:
		# 		self.forecastDisplay.plot()
		# 		self.update()
		# 	if event.key() == QtCore.Qt.Key_F:
		# 		if self.live:
		# 			print('fading items')
		# 			self.fadeForecastItems()
		# 			self.fadeRealtimeItems()
		# 			self.live = False
		# 		else:
		# 			print('setting items')
		# 			self.setForecastItems()
		# 			self.setRealtimeItems()
		# 			self.live = True
		# elif event.type() == QtCore.QEvent.MouseButtonPress:
		# 	print(obj)
		return super(MainWindow, self).eventFilter(obj, event)

	# resizeStarted = True
	# resizeTimer = QTimer()
	#
	# def resizeFinished(self):
	# 	self.resizeStarted = False
	# 	self.centralwidget.show()
	#
	#
	# def resizeStartedFunc(self):
	# 	self.resizeStarted = True
	# 	self.img = self.grab(self.rect())
	# 	self.centralwidget.hide()
	#
	# def paintEvent(self, event):
	# 	if self.resizeStarted and self.img:
	# 		painter = QPainter()
	# 		painter.begin(self)
	# 		painter.drawPixmap(self.rect(), self.img)
	# 		painter.end()
	# 	else:
	# 		super().paintEvent(event)
	#
	# def resizeEvent(self, event):
	# 	if not self.resizeStarted:
	# 		self.resizeStartedFunc()
	# 	self.resizeTimer.start(300)
	# 	super(MainWindow, self).resizeEvent(event)

	def buildUI(self):
		# self.resizeTimer.timeout.connect(self.resizeFinished)

		self.indoor = LargeComplication(self.bottom, title='Indoor', subscriptionKey='temperature')
		dewpoint = Complication(title='Dewpoint')
		self.indoor.addItems(WeatherUnits.others.Humidity, Complication(title='Dewpoint'))

		self.outdoor = LargeComplication(self.bottom, title='Outdoor', subscriptionKey='temperature')
		self.outdoor.addItems(dewpoint, WeatherUnits.others.UVI)

		self.temperatures.insert(self.indoor, self.outdoor)

		# moon = Complication(title='Moon Phase', widget=Moon())
		# self.moonLarge = LargeComplication(self.bottom, widget=Moon())

		self.light = LargeComplication(self.bottom, title='Light', subscriptionKey='illuminance', showTitle=False)
		self.light.center.titleLabel.hide()
		# self.wind = WindSubmodule(self.bottom, title='Wind')
		self.wind = Complication(self.bottom, title='Wind', subscriptionKey='speed', showUnit=True)
		self.rain = Complication(self.bottom, title='Rain', subscriptionKey='rate', showUnit=True)
		# self.bottom.insert(self.moonLarge)
		# self.bottom.insert(self.outdoor)
		# self.bottom.insert(self.rain)
		self.bottom.insert(self.wind, self.light, self.rain)
		self.complicationMini
		self.am = Complication(self.complicationMini, value='pm', square=True)
		self.sunRise = Complication(self.complicationMini, glyphTitle='', value='8:00', miniature=True, square=True)
		self.sunSet = Complication(self.complicationMini, glyphTitle='', value='10:00', miniature=True, square=True)
		# self.conditions = Complication(self.ComplicationFrame)
		# self.complicationMini.isGrid = True
		self.complicationMini.insert(self.am, self.sunSet, self.sunRise)

	# self.sunSet.title.setFont(self.glyphs)
	# self.sunRise.title.setFont(self.glyphs)

	# self.outdoor.subATitle.setText('Air Quality')
	# self.outdoor.subBTitle.setText('Dewpoint')

	def testValues(self):
		self.outdoor.value = WeatherUnits.temperature.Fahrenheit(80)
		self.light.value = WeatherUnits.others.Illuminance(12383.7)
		# self.outdoor.addItems(WeatherUnits.others.Humidity(87))
		self.indoor.value = WeatherUnits.temperature.Fahrenheit(80)
		self.rain.value = 12

	def refreshTimeDateTemp(self, auto=True):

		if not self.timeTraveling:
			self.time.setText(strftime('%-I:%M'))
			self.date.setText(strftime('%a, %B %-d'))

			if auto:
				self.checkThreadTimer.singleShot(500, self.refreshTimeDateTemp)


if __name__ == "__main__":
	logging.getLogger().setLevel(logging.INFO)
	app = QApplication()
	window = MainWindow()
	# window.sunSet.connect(window.forecastDisplay.showSolar)

	# print(window.ui.moonPhase.setProperty('charStr', ''))

	window.show()
	display_monitor = 1
	monitor = QDesktopWidget().screenGeometry(display_monitor)
	window.move(monitor.left(), monitor.top())
	# window.showFullScreen()

	sys.exit(app.exec_())

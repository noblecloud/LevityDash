# This Python file uses the following encoding: utf-8
import logging
import sys
from time import strftime

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PySide2 import QtCore
from PySide2.QtCore import QFile, QSize, QTimer
from PySide2.QtGui import QFont
from PySide2.QtUiTools import QUiLoader
from PySide2.QtWidgets import QApplication, QDesktopWidget, QMainWindow

from src.api import AmbientWeather, AWStation
from src.api.errors import APIError
from src import config
from translators._translator import ClimacellConditionInterpreter, ConditionInterpreter
from display import dataDisplay
from src.api.forecast import dailyForecast, hourlyForecast
from ui.main_UI import QFont, QSizePolicy, Ui_weatherDisplay
from src.api.weatherFlow import WFStation, WeatherFlow
from widgets.Complication import Complication
from widgets.DynamicLabel import DynamicLabel
from widgets.GlyphBox import GlyphBox
from widgets.Temperature import LargeBox


class MainWindow(QMainWindow, Ui_weatherDisplay):
	forecastGraph: FigureCanvasTkAgg
	weatherFlow: WeatherFlow
	ambientWeather: AmbientWeather
	dailyForecast: dailyForecast
	forecast: hourlyForecast
	glyphs: QFont
	checkThreadTimer: QTimer
	forecastDisplay: dataDisplay
	ui: QMainWindow
	interpreter: ConditionInterpreter = ClimacellConditionInterpreter()
	live = True
	timeTraveling = False

	def __init__(self, *args, **kwargs):
		super(MainWindow, self).__init__()
		self.setupUi(self)
		self.indoor.title.setText('Indoors')
		self.outdoor.title.setText('Outdoors')

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
		self.subB.clicked.connect(self.testEvent)

		# self.subA.value.setText(self.forecast.data['sunrise'][0].strftime('%-I:%M'))
		# self.subA.title.setFont(self.glyphs)

		self.loadStyle()

	def testEvent(self, event):
		logging.info('Testing Signal:')
		logging.info(event)

	def connectAW(self):
		try:
			self.aw.getData()
			self.checkThreadTimer.singleShot(1000 * 3, self.updateAW)
		except APIError:
			logging.error("Unable to reach AmbientWeather API, trying again in 1 minute")
			self.checkThreadTimer.singleShot(1000 * 60, self.connectAW)

	def connectWF(self):
		try:
			self.wf.getData()
			self.checkThreadTimer.singleShot(1000 * 3, self.updateWF)

			self.wf.messenger.signal.connect(self.setRealtimeItems)
		except APIError:
			logging.error("Unable to reach WeatherFlow API, trying again in 1 minute")
			self.checkThreadTimer.singleShot(1000 * 60, self.connectAW)

	def updateAW(self):

		try:
			self.aw.update()
			self.setRealtimeItems()
			logging.debug('AmbientWeather updated')
			self.checkThreadTimer.singleShot(1000 * 5, self.updateAW)
		except APIError:
			self.fadeRealtimeItems()
			logging.error("No realtime data, trying again in 1 minute")
			self.checkThreadTimer.singleShot(1000 * 60, self.updateAW)

	def updateWF(self):

		try:
			self.aw.update()
			self.setRealtimeItems()
			logging.debug('AmbientWeather updated')
			self.checkThreadTimer.singleShot(1000 * 5, self.updateAW)
		except APIError:
			self.fadeRealtimeItems()
			logging.error("No realtime data, trying again in 1 minute")
			self.checkThreadTimer.singleShot(1000 * 60, self.updateAW)

	def connectForecast(self):
		try:
			self.forecast = hourlyForecast(self.key, (self.lat, self.lon), 'hourly',
			                               measurementFields=['temp', 'precipitation', 'sunrise', 'sunset',
			                                                  'feels_like', 'dewpoint', 'precipitation_probability',
			                                                  'cloud_cover', 'surface_shortwave_radiation',
			                                                  'wind_speed',
			                                                  'epa_aqi', 'cloud_ceiling', 'cloud_base',
			                                                  'wind_direction'])
			self.dailyForecast = dailyForecast(self.key, (self.lat, self.lon), 'hourly',
			                                   measurementFields=['weather_code'])
			# self.buildGraph()
			self.setForecastItems()
			self.checkThreadTimer.singleShot(1000 * 15, self.updateForecast)
		except ValueError:
			logging.error("No forecast data, trying again in 1 minute")
			self.checkThreadTimer.singleShot(1000 * 60, self.connectForecast)

	def pickEvent(self, event):
		logging.info('Graph pickEvent')
		thisline = event.artist
		xdata = thisline.get_xdata()
		ydata = thisline.get_ydata()
		ind = event.ind
		points = tuple(zip(xdata[ind], ydata[ind]))
		print(points[1][0])


	def motionEvent(self, event):
		print(event.xdata, event.ydata)
		self.forecastDisplay.showLine(event)

	def buildGraph(self):
		logging.debug('Building Graph')
		self.forecastDisplay = dataDisplay(self.forecast, (1920, 1080, 200))
		self.forecastGraph = self.forecastDisplay.setQtCanvas()
		self.forecastGraph.mpl_connect('pick_event', self.pickEvent)
		self.forecastGraph.mpl_connect('figure_enter_event', self.startTimeTravel)
		self.forecastGraph.mpl_connect('figure_leave_event', self.stopTimeTravel)
		# self.forecastDisplay.testPicker()
		self.forecastDisplay.showTemperature()
		self.forecastDisplay.showDewpoint()
		self.forecastDisplay.showFeelsLike()
		# self.forecastDisplay.showLight()
		self.forecastDisplay.addDaysOfWeek()
		# self.forecastDisplay.showWind()
		# self.forecastDisplay.showRain()
		# self.forecastDisplay.showCloudCover()
		# self.forecastDisplay.showLunar()
		self.forecastDisplay.plot()
		sizePolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
		sizePolicy.setHorizontalStretch(9)
		sizePolicy.setVerticalStretch(0)
		sizePolicy.setHeightForWidth(self.forecastGraph.sizePolicy().hasHeightForWidth())
		self.forecastGraph.setSizePolicy(sizePolicy)
		self.gridLayout_3.addWidget(self.forecastGraph, 0, 1, 1, 1)

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
			logging.info('setting forecast items')
			# Current Conditions
			today = self.dailyForecast.data[0]
			self.subB.live = True
			self.subA.glyph = self.interpreter[today.measurements['weather_code'].value]
			self.subA.currentCondition = str(self.interpreter[today.measurements['weather_code'].value])

			# Outdoor Air Quality
			self.outdoor.live = True
			self.outdoor.SubAValue.setText(('{:4d}'.format(round(self.forecast.data['epa_aqi'][0]))))

			# Sunrise/Sunset
			self.sunSet.live = True
			self.sunSet.value.setText(self.forecast.data['sunrise'][0].strftime('%-I:%M'))
			self.sunRise.live = True
			self.sunRise.value.setText(self.forecast.data['sunset'][0].strftime('%-I:%M'))

	def clearForecastItems(self):
		# Current Conditions
		self.subA.glyph = ''
		self.subA.currentCondition = ''

		# Outdoor Air Quality
		self.outdoor.SubAValue.setText('')

		# Sunrise/Sunset
		self.sunSet.value.setText('')
		self.sunRise.value.setText('')

	def fadeForecastItems(self):
		# Current Conditions
		self.subA.live = False

		# Outdoor Air Quality
		self.outdoor.SubAValue.live = False

		# Sunrise/Sunset
		self.sunSet.live = False
		self.sunRise.live = False

	def updateForecast(self):
		try:
			self.forecast.update()
			self.dailyForecast.update()
			self.forecastDisplay.update()
			self.setForecastItems()
			logging.debug('Forecast updated')
			self.checkThreadTimer.singleShot(1000 * 60 * 5, self.updateForecast)
		except AttributeError:
			self.fadeForecastItems()
			logging.error("No forecast data, trying again in 1 minute")
			self.checkThreadTimer.singleShot(1000 * 60, self.updateForecast)

	def setRealtimeItems(self):

		if not self.timeTraveling:
			print('updating')

			# Wind Widget
			self.subB.live = True
			self.subB.speed = self.wf.current.speed
			self.subB.direction = self.wf.current.direction
			self.subB.gust = str(self.wf.current.gust)
			self.subB.max = str(self.wf.current.lull)

			# Temperatures
			self.indoor.live = True
			self.indoor.temperature.setText(str(self.aw.indoor.temperature) + 'º')
			self.indoor.SubAValue.setText(str(self.aw.indoor.humidity))
			self.indoor.SubBValue.setText(str(self.aw.indoor.dewpoint) + 'º')

			# Outdoor
			self.outdoor.live = True
			self.outdoor.temperature.setText(str(self.wf.current.temperature) + 'º')
			# SubAValue relies on forecast data
			self.outdoor.SubBValue.setText(str(self.wf.current.dewpoint) + 'º')

	def fadeRealtimeItems(self):

		self.subB.live = False
		# Temperatures
		self.indoor.live = False
		self.outdoor.live = False
		# Sunrise/Sunset
		self.sunSet.live = False
		self.sunRise.live = False

		self.subB.live = False

	def clearRealtimeItems(self):

		# Wind Widget
		self.subB.speed.setText('')
		self.subB.direction.setText('')
		# Temperatures
		self.indoor.temperature.setText('')
		self.outdoor.temperature.setText('')
		# Sunrise/Sunset
		self.sunSet.value.setText('')
		self.sunRise.value.setText('')
		# Outdoor
		self.outdoor.SubAValue.setText('')
		self.outdoor.SubBValue.setText('')
		# Outdoor
		self.indoor.SubAValue.setText('')
		self.indoor.SubBValue.setText('')

	def loadStyle(self):
		sshFile = "styles/main.qss"
		with open(sshFile, "r") as fh:
			self.setStyleSheet(fh.read())

	# def eventFilter(self, obj, event):
	# 	if event.type() == QtCore.QEvent.KeyPress:
	# 		if event.key() == QtCore.Qt.Key_R:
	# 			print('refresh')
	# 			self.loadStyle()
	# 		if event.key() == QtCore.Qt.Key_B:
	# 			print('rebuild')
	# 			self.hide()
	# 			self.buildUI()
	# 			self.show()
	# 		if event.key() == QtCore.Qt.Key_P:
	# 			self.forecastDisplay.plot()
	# 			self.update()
	# 		if event.key() == QtCore.Qt.Key_F:
	# 			if self.live:
	# 				print('fading items')
	# 				self.fadeForecastItems()
	# 				self.fadeRealtimeItems()
	# 				self.live = False
	# 			else:
	# 				print('setting items')
	# 				self.setForecastItems()
	# 				self.setRealtimeItems()
	# 				self.live = True
	# 	elif event.type() == QtCore.QEvent.MouseButtonPress:
	# 		print(obj)
	# 	return super(MainWindow, self).eventFilter(obj, event)

	def buildUI(self):

		self.sunSet.title.setFont(self.glyphs)
		self.sunSet.title.setText('')

		self.sunRise.title.setFont(self.glyphs)
		self.sunRise.title.setText('')

		self.outdoor.subATitle.setText('Air Quality')
		self.outdoor.subBTitle.setText('Dewpoint')

		self.indoor.subATitle.setText('Humidity')
		self.indoor.subBTitle.setText('Dewpoint')

	def refreshTimeDateTemp(self, auto=True):
		if not self.timeTraveling:
			self.time.setText(strftime('%-I:%M'))
			self.date.setText(strftime('%a, %B %-d'))

			if auto:
				self.checkThreadTimer.singleShot(100, self.refreshTimeDateTemp)


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
	logging.getLogger().setLevel(logging.INFO)
	app = QApplication()
	window = MainWindow()
	# window.sunSet.connect(window.forecastDisplay.showSolar)

	# print(window.ui.moonPhase.setProperty('charStr', ''))

	window.show()
	display_monitor = 0
	monitor = QDesktopWidget().screenGeometry(display_monitor)
	window.move(monitor.left(), monitor.top())
	# window.showFullScreen()

	sys.exit(app.exec_())

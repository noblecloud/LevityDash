# This Python file uses the following encoding: utf-8
import logging
import sys
import traceback
from json import JSONDecodeError, load
from time import strftime
# import pretty_errors

# pretty_errors.configure(filename_display=pretty_errors.FILENAME_FULL)

from PySide2 import QtCore, QtGui
from PySide2.QtCore import QTimer
from PySide2.QtGui import QColor, QFont, QMouseEvent, QPainter
from PySide2.QtWidgets import QApplication, QDesktopWidget, QMainWindow

from src.api.tomorrowIO import TomorrowIO
from src.grid.Cell import Cell
from src import colors
from src.api import AWStation, API
from src.api.errors import APIError
from src.api.forecast import dailyForecast, hourlyForecast
from src.api.weatherFlow import WeatherFlow, WFStation
from src.utils import Logger, Position
from widgets.Complication import Complication
from widgets.ComplicationArray import ComplicationArrayGrid, MainBox
from widgets.ComplicationCluster import ComplicationCluster

from widgets.Proto import ComplicationPrototype
from widgets.WidgetBox import Tabs


@Logger
class MainWindow(QMainWindow):
	glyphs: QFont
	checkThreadTimer: QTimer
	apiDict: dict[str, API] = {}

	def __init__(self, *args, **kwargs):
		super(MainWindow, self).__init__(*args, **kwargs)
		self.__ui_init__()
		self.checkThreadTimer = QtCore.QTimer(self)
		self.show()

	def __ui_init__(self):
		if not self.objectName():
			self.setObjectName(u"weatherDisplay")
		self.resize(1792, 1067)
		font = QFont()
		font.setFamily(u"SF Pro Rounded")
		self.setFont(font)
		self.setUnifiedTitleAndToolBarOnMac(True)
		self.centralwidget = MainBox(self)
		self.buildFonts()
		self.installEventFilter(self)
		self.setCentralWidget(self.centralwidget)
		self.loadStyle()

	def connectAPIs(self):
		self.wf = WFStation()
		self.aw = AWStation()
		self.tm = TomorrowIO()
		self.apiDict['WFStation'] = self.wf
		self.apiDict['AWStation'] = self.aw
		self.apiDict['TomorrowIO'] = self.tm
		self.toolbox = Tabs()
		self.toolbox.addAPI(self.wf)
		self.toolbox.addAPI(self.tm)
		self.toolbox.addAPI(self.aw)
		# self.connectAW()
		# self.connectTM()
		self.connectWF()

	def testEvent(self, event):
		self._log.info('Testing Signal:')
		self._log.info(event)

	def load(self):

		def rebuildComplication(item, location: ComplicationArrayGrid):

			api = None
			if 'api' in item:
				try:
					api = self.APIs[item['api']]
				except KeyError:
					api = None
			if api is not None and 'key' in item:
				comp: Complication = location.makeComplication(Complication, subscriptionKey=item['key'], api=api, title=item['title'])
			else:
				if item['class'] == 'GraphComplication':
					comp: 'GraphComplication' = location.makeComplication(Tabs.localComplications[item['class']], apis=self.APIs)
					comp.state = item
				elif item['class'] == 'WindComplication':
					item.pop('type')
					comp: 'WindComplication' = location.makeComplication(Tabs.localComplications[item['class']], **item)
					print('')
				else:
					comp = location.makeComplication(Tabs.localComplications[item['class']], title=item['title'])
			comp.cell = Cell(comp, **item['cell'])
			location.plop(comp, comp.cell.i, update=False, afterIndex=False)

		def rebuildCluster(data, location: ComplicationArrayGrid):
			t = data.pop('type')
			cluster = ComplicationCluster(location, title=data.pop('title'))
			g = cluster.geometry()
			g.moveBottom(self.geometry().bottom())
			g.moveRight(self.geometry().right())
			cluster.setGeometry(g)
			cluster.cell = Cell(cluster, **data.pop('cell'))

			for name, sectionItems in data.items():
				section = getattr(cluster, name)
				for item in sectionItems:
					rebuildComplication(item, section)
				section.update()

			cluster.hideEmpty()
			location.plop(cluster, cluster.cell.i)

		def recursive(data, location=self.centralwidget):
			for item in data:
				# if 'type' not in data:
				# 	rebuildComplication(item, location)
				if item['type'] == 'ComplicationCluster':
					rebuildCluster(item, location)
				else:
					rebuildComplication(item, location)
			location.update()

		with open('save.json', 'r') as inf:
			try:
				state = load(inf)
			except JSONDecodeError:
				state = []
		recursive(state)

	def connectAW(self):
		try:
			self.aw.getData()
			self.checkThreadTimer.singleShot(1000 * 15, self.updateAW)
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

	def connectTM(self):
		try:
			self.tm.getCurrent()
			self._log.info('Tomorrow.io connected')
			self.checkThreadTimer.singleShot(1000 * 60 * 5, self.updateWF)

		# self.wf.messenger.signal.connect(self.setRealtimeItems)
		except APIError:
			self._log.error("Unable to reach Tomorrow.io API, trying again in 1 minute")
			self.checkThreadTimer.singleShot(1000 * 60 * 5, self.connectWF)

	def updateTM(self):

		try:
			self.tm.getCurrent()
			self._log.info('Tomorrow.io updated')
			self.checkThreadTimer.singleShot(1000 * 60 * 5, self.updateWF)
		except APIError:
			self._log.error("No realtime, trying again in 1 minute")
			self.checkThreadTimer.singleShot(1000 * 60 * 5, self.updateWF)

	def connectForecast(self):

		try:
			self.forecast = hourlyForecast()
			self.dailyForecast = dailyForecast(measurementFields=['weather_code', 'feels_like'])
			self.forecastGraph.data = self.forecast
			self.checkThreadTimer.singleShot(1000 * 60 * 5, self.updateForecast)
			self.setForecastItems()
		except ValueError:
			self._log.error("No forecast data, trying again in 1 minute")
			self.checkThreadTimer.singleShot(1000 * 60, self.connectForecast)
		except APIError:
			self._log.error("No forecast data, trying again in 30 minutes")
			self.checkThreadTimer.singleShot(1000 * 60 * 30, self.connectForecast)

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
		# Current Conditions
		today = self.dailyForecast.data[0]

		# self.conditions.value = self.interpreter[today.measurements['weather_code'].value].glyph

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

	def rise(self):
		palette = self.palette()
		palette.setColor(QtGui.QPalette.Text, QColor(*colors.kelvinToRGB(4000)))
		palette.setColor(QtGui.QPalette.Window, QtGui.Qt.black)
		self.setPalette(palette)

	# self.setStyleSheet(colors.color())

	def loadStyle(self):
		# self.rise()
		# palette = self.palette()
		# palette.setColor(QtGui.QPalette.Text, colors.qcolor())
		# self.setPalette(palette)
		# self.setStyleSheet(colors.color())
		sshFile = "styles/main.qss"
		with open(sshFile, "r") as fh:
			self.setStyleSheet(fh.read())

	def eventFilter(self, obj, event):

		if isinstance(obj, ComplicationPrototype):
			if event.type() == QtCore.Qt.KeyPress:
				if event.key() == QtCore.Qt.Key_Delete:
					self.centralwidget.yank(obj)

		elif event.type() == QtCore.QEvent.KeyPress:
			if event.key() == QtCore.Qt.Key_P:
				if self.toolbox.isVisible():
					self.toolbox.hide()
				else:
					self.toolbox.setGeometry(self.rect())
					self.toolbox.show()
			if event.key() == QtCore.Qt.Key_C:
				self.rise()
			if event.key() == QtCore.Qt.Key_L:
				self.load()
			if event.key() == QtCore.Qt.Key_S:
				self.centralWidget().save()
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


class MyApp(QApplication):
	def notify(self, obj, event):
		isex = False
		try:
			return QApplication.notify(self, obj, event)
		except Exception:
			isex = True
			print
			"Unexpected Error"
			print
			traceback.format_exception(*sys.exc_info())
			return False
		finally:
			if isex:
				self.quit()


if __name__ == "__main__":
	logging.getLogger().setLevel(logging.INFO)
	app = MyApp()
	window = MainWindow()
	window.load()
	display_monitor = 1
	monitor = QDesktopWidget().screenGeometry(display_monitor)
	window.move(monitor.left(), monitor.top())
	if '-f' in sys.argv:
		window.showFullScreen()
	try:
		sys.exit(app.exec_())
	except Exception as e:
		print(e)
		sys.exit(app.exec_())

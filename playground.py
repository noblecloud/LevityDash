import os

import pygubu

from classes import display
from classes.forecast import hourlyForecast
from classes.realtime import Realtime
from time import strftime

lat, lon = 37.40834, -76.54845
key = "q2W59y2MsmBLqmxbw34QGdtS5hABEwLl"

AmbKey = 'e574e1bfb9804a52a1084c9f1a4ee5d88e9e850fc1004aeaa5010f15c4a23260'
AmbApp = 'ec02a6c4e29d42e086d98f5db18972ba9b93d864471443919bb2956f73363395'

PROJECT_PATH = os.path.dirname(__file__)
PROJECT_UI = os.path.join(PROJECT_PATH, "main.ui")


class WeatherBoard:
	screenx = 1920
	screeny = 1080
	# screenx = 1080
	# screeny = 720
	dpi = 212
	forecast: hourlyForecast = None

	def __init__(self, root):

		self.root = root

		self.builder = builder = pygubu.Builder()
		builder.add_resource_path(PROJECT_PATH)
		builder.add_from_file(PROJECT_UI)
		self.mainwindow = builder.get_object('Main')

		builder.connect_callbacks(self)

		self.forecast = hourlyForecast(key, (lat, lon), 'hourly',
		                               measurementFields=['temp', 'precipitation', 'sunrise', 'sunset',
		                                                  'feels_like', 'dewpoint'])
		self.realtime = Realtime(AmbKey, AmbApp)

		self.forecast.daemon = True
		self.realtime.daemon = True

		self.graphCanvas = self.builder.get_object('graph')
		sizeX = self.graphCanvas.winfo_width()
		sizeY = self.graphCanvas.winfo_height()
		self.forecastDisplay = display.dataDisplay(self.forecast, (sizeX, sizeY, 200))
		self.forecastDisplay.setTkCanvas(self.graphCanvas)
		self.forecastDisplay.plot()

	# self.graphUpdate()

	def callback(self, event=None):
		pass

	def indoorTemp(self):
		return str(self.realtime.nearest.indoor.temperature.temp)

	def time(self):
		time = self.builder.get_object('timeText')
		time.configure(font=("", 40))
		time.config(text = strftime('%-H:%M').lower())
		time.after(100, self.time)

	def _quit(self):
		# self.forecast.join()
		# self.realtime.join()
		self.forecast.stop()
		root.quit()  # stops mainloop
		root.destroy()  # this is necessary on Windows to prevent

	def run(self):
		self.forecast.start()
		self.realtime.start()
		self.root.update()
		self.time()
		self.updateForecastDisplay()
		self.updateRealtime()
		# await asyncio.gather(self.buildGraph(), self.update(), self.mainwindow.mainloop())
		# asyncio.gather(self.mainwindow.mainloop())
		# await asyncio.gather(self.buildGraph(), self.update())
		self.mainwindow.mainloop()

	# def fetch(self):
	# 	self.forecast.dataUpdate()
	# 	self.graphCanvas.after()

	def updateForecastDisplay(self):

		try:
			self.forecastDisplay.update()
			print('updating graph')
			self.graphCanvas.update()
			self.graphCanvas.after(10000, self.updateForecastDisplay)
		except KeyError:
			print('data unavailable will try again in 1 second')
			self.graphCanvas.after(1000, self.updateForecastDisplay)

	# self.graphCanvas.after(1000, self.buildGraph)

	def updateRealtime(self):
		x = self.builder.get_variable('indoorTemp')
		l = self.builder.get_object('indoorTemp')
		try:
			value = str(self.realtime.nearest.indoor.temperature)
			print('setting label to {}'.format(value))
			x.set(value)
			l.after(6000, self.updateRealtime)
		except:
			l.after(1000, self.updateRealtime)


# finally:
# l.update()


if __name__ == '__main__':
	import tkinter as tk

	root = tk.Tk(className='WeatherBoard')
	# root.tk.call("::tk::unsupported::MacWindowStyle", "style", root._w, "plain", "none")
	root.geometry('1920x1080')
	root.attributes("-topmost", True)
	root.attributes("-fullscreen", 'true')
	# root.wm_attributes("-transparent")
	app = WeatherBoard(root)
	# app.mainwindow.configure(background='black')
	# app.forecast.start()
	# root.update()
	# app.forecast.join()
	# root.update_idletasks()
	app.run()
# root.after(4000, app.buildGraph())
# asyncio.run(app.run())

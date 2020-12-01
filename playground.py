import os
from time import strftime
from datetime import datetime
from typing import Union

import pygubu
import pylunar

from classes import display
from classes.forecast import hourlyForecast
from classes.realtime import Realtime

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
	location: tuple[float, float]
	forecast: hourlyForecast = None

	def __init__(self, root):

		self.root = root

		self.builder = builder = pygubu.Builder()
		builder.add_resource_path(PROJECT_PATH)
		builder.add_from_file(PROJECT_UI)
		self.mainwindow = builder.get_object('Main')
		self.mainwindow.geometry = '{}x{}'.format(self.screenx, self.screeny)

		builder.connect_callbacks(self)

		root.bind('r', self.refresh)
		root.bind('b', self.setColor)
		root.bind('esc', self.quit)
		root.bind('q', self.quit)

		# self.setColor()

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
		self.updateMoonPhase()

	def quit(self, value=None):
		print(value)
		self.forecast.join()
		self.realtime.join()
		self.root.quit()
		self.root.destroy()

	def refresh(self, value=None):
		print('refreshing')
		self.builder = builder = pygubu.Builder()
		builder.add_resource_path(PROJECT_PATH)
		builder.add_from_file(PROJECT_UI)
		self.mainwindow = builder.get_object('Main')
		self.graphCanvas = self.builder.get_object('graph')
		sizeX = self.graphCanvas.winfo_width()
		sizeY = self.graphCanvas.winfo_height()
		self.forecastDisplay = display.dataDisplay(self.forecast, (sizeX, sizeY, 200))
		self.forecastDisplay.setTkCanvas(self.graphCanvas)
		self.forecastDisplay.plot()
		self.updateMoonPhase()
		self.time()
		self.formatText()
		# self.root.after(2000, self.refresh)

	def moonHex(self):
		start = 61589

		moon = pylunar.MoonInfo((int(lat), 0, 0), (int(lon), 0, 0), datetime.now())
		moonAge = moon.age()
		if moonAge > 28:
			return chr(start + 28)
		else:
			return chr(start + int(moonAge))


	def callback(self, event=None):
		pass

	def formatText(self):
		moon = self.builder.get_object('moonLabel.WI')
		self.autoFontSize(['moonLabel.WI'], font='Weather Icons')
		self.autoFontSize(['timeLabel'], scale=1.1)
		self.autoFontSize(['dayOrdinalLabel'], 0.5)
		self.setFontSize(['outsideLabel', 'insideLabel'], 30)
		self.setFontSize(['insideSubA', 'insideSubB', 'outsideSubA', 'outsideSubB'], 70)
		self.setFontSize(['insideTempLabel', 'outsideTempLabel'], 180)
		self.autoFontSize(['monthLabel'], scale=.7)
		self.setFontSize(['sunriseTitle.WI', 'sunsetTitle.WI'], 25,font='Weather Icons')
		self.autoFontSize(['sunriseLabel', 'sunsetLabel'], 0.45)

	def setWeatherIconFont(self):
		icons = {'sunrise': chr(0xF051), 'sunset': chr(0xf052)}
		for key in self.builder.objects.keys():
			if key[:-3] == '.WI':
				widget = self.builder.objects[key]
				widget.config(font='Weather Icons')
				widget.set_text()

	def setColor(self, valueb):
		ignore = ['label', 'title']
		for widget in self.builder.objects.keys():
			print(widget)
			widgetObject = self.builder.get_object(widget)
			widgetObject.configure(background='black')
			if 'label' in widget.lower() or 'title' in widget.lower():
				widgetObject.configure(foreground='white')

	def time(self):
		dateText = self.builder.get_variable('monthText')
		dateText.set(strftime('%a, %B %-d'))

		self.setText('dayOrdinalText', self.ordinal(strftime('%-d')))

		self.setText('timeText', strftime('%-I:%M').lower())
		self.setText('timeText', strftime('12:33').lower())


		# self.root.after(400, self.time)

	def setText(self, target: str, value: str):
		textVariable = self.builder.get_variable(target)
		textVariable.set(value)

	def setFontSize(self, targets: list[str], value: int, font='Baloo 2'):
		for widget in targets:
			widget = self.builder.get_object(widget)
			widget.configure(font=(font, value))
			# widget['height'] = int(value * 1.1*72)

	def autoFontSize(self, target: Union[str, list[str]], scale=0.9, font='Baloo 2'):
		if target is str:
			target = [target]
		for widget in target:
			print('resizing, ' + widget)
			widget = self.builder.get_object(widget)
			parentHeight = widget.master.winfo_height()
			widget.configure(font=(font, int(parentHeight * scale)))

	def textWidth(self, text, size):
		return len(text) * (size * .9)

	def updateRealtime(self):
		indoor = self.builder.get_variable('insideTempText')
		outdoor = self.builder.get_variable('outsideTempText')
		try:
			indoor.set(self.realtime.nearest.indoor.temperature)
			outdoor.set(self.realtime.nearest.outdoor.temperature)
			root.after(6000, self.updateRealtime)
		except IndexError:
			print('no value yet')
			root.after(1000, self.updateRealtime)

	def ordinal(self, value: str) -> str:
		digit = int(value[:-1])
		return 'th' if digit < 5 else {0: 'th', 1: 'st', 2: 'nd', 3: 'rd', 4: 'th'}[digit]

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
		self.formatText()
		self.mainwindow.mainloop()

	# def fetch(self):
	# 	self.forecast.dataUpdate()
	# 	self.graphCanvas.after()

	def updateMoonPhase(self):
		# self.builder.get_object('moonLabel.WI').config(font="Weather Info")
		moon = self.builder.get_variable('moonText')
		moon.set(self.moonHex())
		self.root.after(1000*60*15, self.updateMoonPhase)

	def updateForecastDisplay(self):

		try:
			self.forecastDisplay.update()
			sunrise = self.forecast.data['sunrise'][0]
			sunset = self.forecast.data['sunset'][0]
			self.setText('sunriseText', sunrise.strftime('%-I:%M%p').lower())
			self.setText('sunsetText', sunset.strftime('%-I:%M%p').lower())
			print('updating graph')
			self.graphCanvas.update()
			self.graphCanvas.after(10000, self.updateForecastDisplay)
		except KeyError:
			print('data unavailable will try again in 1 second')
			self.graphCanvas.after(1000, self.updateForecastDisplay)


# self.graphCanvas.after(1000, self.buildGraph)


# finally:
# l.update()


if __name__ == '__main__':
	import tkinter as tk

	root = tk.Tk(className='WeatherBoard')
	# root.tk.call("::tk::unsupported::MacWindowStyle", "style", root._w, "plain", "none")
	# root.geometry('1080x720')
	root.geometry('1920x1080')
	root.attributes("-topmost", True)
	# root.attributes("-fullscreen", 'true')
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

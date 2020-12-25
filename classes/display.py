from datetime import datetime, timedelta
from typing import Optional, Union

import matplotlib as mp
import matplotlib.font_manager as fm
import numpy as np
import pylab
from matplotlib import pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import LinearSegmentedColormap
from numpy.core._multiarray_umath import ndarray
from scipy.signal import find_peaks

from classes.forecast import Forecast
from constants import EaseFade, FadeFilter


class dataDisplay:
	solarColorMap: LinearSegmentedColormap
	rain: plt.axes
	temperature: plt.axes
	timeFloat: list[float] = None
	_interpTime: Union[ndarray, tuple[ndarray, Optional[float]]] = None
	font = {'size': 6}
	mp.rc('font', **font)
	largeFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Rounded-Light.otf', size=4)
	smallFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Rounded-Light.otf', size=12)
	tempFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Rounded-Bold.otf', size=20)
	bigThickFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Rounded-Heavy.otf', size=24)
	weatherIconsFont = fm.FontProperties(fname='fonts/weathericons.ttf', size=24)
	smallMono = fm.FontProperties(fname='/Library/Fonts/SF-Mono-Light.otf', size=10)
	# mainColor = Colors().kelvinToHEX(3000)
	mainColor = 'w'
	_forecast: Forecast
	_canvas: FigureCanvasTkAgg = None

	def __init__(self, forecastData: Forecast, size: tuple[int, int, int]):

		self.toFix = []
		self.x, self.y, self.d = size
		self._forecast = forecastData
		self.tempMax = 0
		self.tempMin = 0

		self.buildColorMaps()

		# Construct graph
		self.graph = pylab.figure(figsize=[self.x / self.d, self.y / self.d], dpi=self.d, facecolor='k')
		self.graph.patch.set_facecolor('k')
		plt.margins(0, 0.0)
		plt.subplots_adjust(left=0, right=1, top=1, bottom=-0.01)
		plt.gca().set_axis_off()

		# Construct plotter
		# self.temperature: plt.axes.Axes = self.graph.add_subplot(label='temperature')
		self.temperature: plt.axes.Axes = self.graph.gca()

		self.temperature.set_facecolor('k')
		self.lastUpdate = self.temperature.text(0.97, 0.97, '',
		                                        horizontalalignment='right',
		                                        verticalalignment='center',
		                                        transform=self.temperature.transAxes, color=self.mainColor,
		                                        fontproperties=self.smallFont)

	def buildColorMaps(self):
		from matplotlib.colors import LinearSegmentedColormap
		solarColorDict = {'red':   [(0.0, 0.0, 0.0),
		                            (0.5, 0.5, 0.5),
		                            (1.0, 1.0, 1.0)],
		                  'green': [(0.0, 0.0, 0.0),
		                            (0.5, 0.5, 0.5),
		                            (1.0, 1.0, 1.0)],
		                  'blue':  [(0.0, 0.0, 0.0),
		                            (0.5, 0.5, 0.5),
		                            (1.0, 1.0, 1.0)]}
		# 'alpha': [(0.0, 0.0, 0.0),
		#           (0.25, 0.0, 0.0),
		#           (.5, 0.5, 0.5)]}

		self.solarColorMap = LinearSegmentedColormap('colorMap', solarColorDict, 256)

	def interpTime(self):
		self.timeFloat = list(map((lambda i: i.timestamp()), self.data['timestamp']))
		self._interpTime = np.linspace(self.timeFloat[0], self.timeFloat[:-1], 68)

	def splineData(self, data):
		from scipy.interpolate import make_interp_spline

		self.interpTime()
		time = list(map((lambda i: i.timestamp()), self.data['timestamp']))
		spl = make_interp_spline(time, data)
		ynew = spl(self._interpTime)
		flat = ynew.flatten()
		return flat

	def interp(self, x, y):
		from scipy.interpolate import interp1d
		x = interp1d(x, y)
		return x

	def preview(self):
		self.plot()
		self.graph.show()

	# cover = self.splineData(self.data['cloud_cover'])

	def findTemperaturePeaks(self, plotter, measurement: str):

		def daterange(start_date, end_date):
			for n in range(int((end_date - start_date).days)):
				yield start_date + timedelta(n)

		import matplotlib.patheffects as PathEffects

		self.tempMax = self._forecast.data['temp'].max()
		self.tempMin = self._forecast.data['temp'].min()

		# for x in self.data['timestamp']:

		# def removeDuplicates(array: list, spread):
		# 	for i in range(0, len(array)):
		# 		difference = array[i+1] - array[i]
		# 		if difference < spread:
		# 			print('AHHHH')

		range = self.tempMax - self.tempMin

		peaks, _ = find_peaks(self._forecast.data[measurement], distance=80)
		troughs, _ = find_peaks(-self._forecast.data[measurement], distance=80)

		both = np.concatenate((peaks, troughs))
		both = list(np.sort(both))

		t = plotter.text(self.data['timestamp'][0] + timedelta(hours=2),
		                 self.data['temp'][0],
		                 str(round(self._forecast.data[measurement][0])) + 'º'.lower(),
		                 ha='center',
		                 va='center',
		                 color=self.mainColor,
		                 fontproperties=self.tempFont)
		t.set_path_effects([PathEffects.withStroke(linewidth=6, foreground='k')])

		for value in both:
			text = str(round(self._forecast.data[measurement][value])) + 'º'.lower()
			time = self._forecast['timestamp'][value].strftime('%-I%p').lower()
			x = pylab.date2num(self._forecast['timestamp'][value])
			y = self._forecast.data[measurement][value]
			# if y >= self.tempMax:
			# 	y -= 3
			t = plotter.text(x + 0.02,
			                 y,
			                 text.lower(),
			                 ha='center',
			                 va='center',
			                 color=self.mainColor,
			                 fontproperties=self.tempFont)
			t.set_path_effects([PathEffects.withStroke(linewidth=6, foreground='k')])

			# t.
			# d = plotter.text(0,
			#                  0,
			#                  time.lower(),
			#                  ha='center',
			#                  va='center',
			#                  color=self.mainColor,
			#                  fontproperties=self.tempFont,
			#                  # transform=t.get_window_extent(),
			#                  fontsize=10).set_path_effects(
			# 		[PathEffects.withStroke(linewidth=6, foreground='k')])

			# from matplotlib.text import OffsetFrom
			#
			# d = OffsetFrom(plotter, t.get_position())
			# self.graph.artist

			'''
			(0.98, 0.03, '',
		                                        horizontalalignment='right',
		                                        verticalalignment='center',
		                                        transform=self.temperature.transAxes, color=self.mainColor,
		                                        fontproperties=self.smallFont)

			'''

	# plotter.plot([x, x], [y - 5, self.tempMin], color='w', linewidth=1, alpha=.5, zorder=-15)

	# for value in troughs:
	# 	text = str(round(self.forecastData.data[measurement][value])) + 'º'
	# 	time = self.forecastData['timestamp'][value].strftime('%-I%p').lower()
	# 	x = pylab.date2num(self.forecastData['timestamp'][value])
	# 	y = self.forecastData.data[measurement][value]
	# 	# if y < self.tempMin:
	# 	# 	y += 5
	# 	t = plotter.text(x+0.02,
	# 					 y,
	# 					 text.lower(),
	# 					 ha='center',
	# 					 va='center',
	# 					 color=self.mainColor,
	# 					 fontproperties=self.tempFont)
	# 	d = plotter.text(x,
	# 					 y - 3,
	# 					 time.lower(),
	# 					 ha='center',
	# 					 va='center',
	# 					 color=self.mainColor,
	# 					 fontproperties=self.tempFont, fontsize=10)
	# plotter.plot([x, x], [y - 5, self.tempMin], color='w', linewidth=1, alpha=.5, zorder=-15)
	# t.set_path_effects([PathEffects.withStroke(linewidth=2, foreground='k')])

	@property
	def data(self):
		return self._forecast.data

	def addDaysOfWeek(self, plotter):
		ypos = (self.tempMax - self.tempMin) / 2 + self.tempMin - 8

		days = [item[0] for item in self.data['splitDates']]

		for d in days:
			noon = datetime(year=d.year, month=d.month, day=d.day, hour=12)
			midnight = datetime(year=d.year, month=d.month, day=d.day)
			if datetime.now() < noon:
				# temperature.text(d, 30, 'test', color='white', fontsize=14, fontproperties=prop)
				plotter.text(noon, ypos, d.strftime('%a'), horizontalalignment='center', color='k',
			             fontproperties=self.bigThickFont, zorder=-100)

			pos = pylab.date2num(midnight)
			if datetime.now() < midnight:
				plotter.axvspan(midnight, midnight, color=self.mainColor, linestyle=(0, (5, 10)), linewidth=2, alpha=0.5)

	# if d.hour in (6, 12, 18):
	# 	pos = pylab.date2num(d)
	# 	plotter.axvspan(pos, pos, color=self.mainColor, linestyle=(0, (5, 10)), linewidth=1, alpha=0.5)
	#
	# if d.hour not in (0, 6, 12, 18):
	# 	pos = pylab.date2num(d)
	# 	plotter.axvspan(pos, pos, color=self.mainColor, linestyle=(0, (5, 10)), linewidth=1, alpha=0.2)
	# plotter.axvspan(pos, pos+0.005, color='white', alpha=.5, ec=None)

	def daylight(self, plotter):

		plotter.set_xlim(self._forecast.data['timestamp'][0], self._forecast.data['timestamp'][-1])

		sunrise: list[datetime] = list(set(self._forecast.data['sunrise']))
		sunset: list[datetime] = list(set(self._forecast.data['sunset']))
		sunrise.sort()
		sunset.sort()

		for x in range(0, len(sunrise)):
			plotter.axvspan(sunrise[x], sunset[x], color=self.mainColor, alpha=0.2, ec=None, zorder=-120)

	def addTicks(self, plotter):

		from classes.constants import tz

		from matplotlib import dates as mdates
		plotter.xaxis.set_major_locator(mdates.HourLocator(byhour=0, tz=tz))
		plotter.xaxis.set_minor_formatter(mdates.DateFormatter('%-I%p', tz=tz))
		plotter.xaxis.set_major_formatter(mdates.DateFormatter('%-I%p', tz=tz))
		plotter.xaxis.set_minor_locator(mdates.HourLocator(byhour=range(0, 24, 6)))

		for x in plotter.get_xmajorticklabels():
			x.set_color('white')
			x.set_fontproperties(self.smallFont)
			x.set_horizontalalignment('center')
			x.set_visible(True)

		for tick in plotter.xaxis.get_major_ticks():
			tick.tick1line.set_markersize(1)
			tick.tick2line.set_markersize(1)
			tick.label.set_horizontalalignment('center')

		for x in plotter.get_xminorticklabels(): x.set_color('white'); x.set_fontproperties(self.smallFont)
		plotter.grid(color=self.mainColor, alpha=.75, axis='y', visible=True)
		plotter.grid(axis='x', alpha=1, linestyle=(0, (11, 12)), color=self.mainColor)

	# plotter.grid()

	def plot(self):

		# Smooth Data
		# self._forecast.data['temp'] = self.splineData(self._forecast.data['temp'])
		# self._forecast.data['feels_like'] = self.splineData(self._forecast.data['feels_like'])
		# self._forecast.data['dewpoint'] = self.splineData(self._forecast.data['dewpoint'])
		# self._forecast.data['precipitation'] = self.smoothData(self._forecast.data['precipitation'], 1, 6)

		# Find peaks in data
		self.findTemperaturePeaks(self.temperature, 'temp')
		self.tempMax = self._forecast.data['temp'].max()
		self.tempMin = self._forecast.data['temp'].min()

		self.temperature.zorder = 10

		# x = list(map(lambda z: datetime.utcfromtimestamp(z), self._interpTime.flatten()[68:]))

		self.temperature.plot('timestamp', 'temp', data=self._forecast.data,
		                      label='Hourly Forecast', zorder=2,
		                      color=self.mainColor, linewidth=4)

		self.temperature.plot('timestamp', 'feels_like', data=self._forecast.data, label='Hourly Forecast',
		                      zorder=-20,
		                      color=(.25, .89, .96), linestyle='dashed', alpha=.8, linewidth=3)

		self.temperature.plot('timestamp', 'dewpoint', data=self._forecast.data, zorder=-20,
		                      color=self.mainColor, label='Hourly Forecast', linestyle='dashed', alpha=.8, linewidth=2)

		self.addDaysOfWeek(self.temperature)
		self.showWind()
		# self.showLunar()
		# self.daylight(self.temperature)
		self.showLight()
		self.addTicks(self.temperature)

		self.temperature.set_ylim(self.hiLow(5))

	# self.rain = self.temperature.twinx()
	# n = 2
	# rainSplit = [
	# 		sum(self._forecast.data['precipitation_probability'][i:i + n]) // n for i in
	# 		range(0, len(self._forecast.data['precipitation_probability']), n)]
	#
	# rainSplit = np.array(rainSplit)
	#
	# date = self._forecast.data['timestamp'][::n]
	# self.rain.plot('timestamp', 'precipitation', data=self._forecast.data)
	# self.rain.bar(date, rainSplit, zorder=200, width=.08, color=(.25, .89, .96))
	# x = rainSplit.max()
	# self.rain.set_ylim(0, x * 2)

	# self.solar = self.graph.add_subplot(111, label='lights', frame_on=False)

	def showWind(self):
		self.wind = self.graph.add_subplot(212, label='wind', frame_on=False, sharex=self.temperature)
		self.wind.plot('timestamp', 'wind_speed', data=self.data)

	def showSolar(self):
		self.solar = self.graph.add_subplot(111, label='solar', frame_on=False, sharex=self.temperature)
		self.solar.set_ylim(-18, 360)
		# self.solar.set_xlim(self._forecast.data['minutes'][0], self._forecast.data['minutes'][-1])
		self.solar.plot('timestamp', 'sun', data=self.data)
		# self.solar.scatter('timestamp', 'sun', data=self._forecast.data,
		#                    cmap=self.solarColorMap,
		#                    edgecolor='none')

		# self.solar.plot('minutes', 'moon', data=self._forecast.data)
		self.updateCanvas()

	def showLunar(self):
		self.lunar = self.graph.add_subplot(111, label='lunar', frame_on=False, sharex=self.temperature)
		self.lunar.set_ylim(-16, 360)
		# for time in self._forecast.data['moonTimes']:
		# 	self.solar.axvspan(time['rise'], time['set'], alpha=0.1)

		for d in self._forecast.data['lunarTransit']:
			if d['time'] is not None:
				self.lunar.text(d['time'] + timedelta(hours=5), d['maxAltitude'], self.moonAge(d['age']),
				                horizontalalignment='center',
				                color='w',
				                fontproperties=self.weatherIconsFont, zorder=-100)

		# self.lunar.plot('timestamp', 'moon', data=self.data)
		self.updateCanvas()

	def moonAge(self, age):
		start = int(0xF095)
		return chr(round(age) + start)

	def showLight(self):
		limits = (self.data['timestampInt'][0], self.data['timestampInt'][-1])
		filter = EaseFade()
		a = self.mapImage(self.data['surface_shortwave_radiation'], filter)
		self.radiation = self.graph.add_subplot(111, label='radiation', frame_on=False)
		# self.radiation = self.temperature.twinx()
		# self.radiation.set_xlim(self.data['timestampInt'][0])
		self.radiation.imshow(a, aspect='auto', cmap=self.solarColorMap, alpha=1, interpolation='bilinear')

	def mapImage(self, array: Union[list, np.ndarray], fadeFilter: Union[FadeFilter, None] = None):

		if isinstance(array, list):
			array = np.array(array)
		max: int = array.max()
		newArray = []
		for x in array:
			s = x / max
			newArray.append(s)
		a = (np.outer(np.ones(len(newArray)), newArray))
		if fadeFilter:
			return fadeFilter.fadeArray(a)
		return a

	# light = np.array(self._forecast.data['radiation'])
	# self.solar.imshow(light[np.newaxis,:], cmap="plasma", aspect="auto")
	# self.updateCanvas()

	def hideSolar(self):
		self.solar.cla()
		self.updateCanvas()

	def showRain(self):
		self.rain = self.temperature.twinx()
		n = 2
		rainSplit = [
				sum(self._forecast.data['precipitation_probability'][i:i + n]) // n for i in
				range(0, len(self._forecast.data['precipitation_probability']), n)]

		rainSplit = np.array(rainSplit)

		date = self._forecast.data['timestamp'][::n]
		self.rain.plot('timestamp', 'precipitation', data=self._forecast.data)
		# self.rain.plot(date, rainSplit, zorder=200, width=.08, color=(.25, .89, .96), capstyle='round')
		# from matplotlib.patches import FancyBboxPatch
		# new_patches = []
		# for patch in reversed(self.rain.patches):
		# 	bb = patch.get_bbox()
		# 	color = patch.get_facecolor()
		# 	p_bbox = FancyBboxPatch((bb.xmin, bb.ymin),
		# 	                        abs(bb.width), abs(bb.height),
		# 	                        # boxstyle="round,pad=-0.0080,rounding_size=0.015",
		# 	                        ec="none", fc=color,
		# 	                        mutation_aspect=4
		# 	                        )
		# 	patch.remove()
		# 	new_patches.append(p_bbox)
		# for patch in new_patches:
		# 	self.rain.add_patch(patch)
		x = rainSplit.max()
		self.rain.set_ylim(0, x * 2)
		self.updateCanvas()

	def hideRain(self):
		self.rain.cla()
		self.updateCanvas()

	def updateCanvas(self):
		if self._canvas:
			self._canvas.draw()

	def hiLow(self, offset=None):

		if self._forecast.data['temp'].max() > self._forecast.data['feels_like'].max():
			h = self._forecast.data['temp'].max()
		else:
			h = self._forecast.data['feels_like'].max()

		if self._forecast.data['temp'].min() < self._forecast.data['feels_like'].min():
			l = self._forecast.data['temp'].min()
		else:
			l = self._forecast.data['feels_like'].min()

		l = self._forecast.data['dewpoint'].min()

		variance = (h - l) * 0.1

		return l - variance - 1, h + variance

	def rasterRender(self):

		from matplotlib.backends.backend_agg import FigureCanvasAgg, RendererAgg
		import matplotlib.backends.backend_agg as agg
		mp.use("Agg")

		canvas: FigureCanvasAgg = agg.FigureCanvasAgg(self.graph)
		canvas.draw()
		renderer: RendererAgg = canvas.get_renderer()
		raw_data = renderer.tostring_rgb()

		return raw_data

	def setTkCanvas(self, canvas):
		from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
		mp.use('TkAgg')
		self._canvas = FigureCanvasTkAgg(self.graph, canvas)
		self._canvas.draw()
		self._canvas.get_tk_widget().pack(side='top', fill='both', expand=1)

	def setQtCanvas(self):
		from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
		# this is the Canvas Widget that displays the `figure`
		# it takes the `figure` instance as a parameter to __init__
		self._canvas = FigureCanvas(self.graph)
		return self._canvas

	def plotQtCanvas(self):
		self.plot()
		self._canvas.draw()

	def update(self):
		self.lastUpdate.set_text(datetime.now().strftime('%-I:%M%p').lower())
		self.updateCanvas()


class MplCanvas(FigureCanvasQTAgg, dataDisplay):

	def __init__(self, parent=None, width=5, height=4, dpi=100):
		from matplotlib.figure import Figure
		fig = Figure(figsize=(width, height), dpi=dpi)
		self.axes = fig.add_subplot(111)
		super(MplCanvas, self).__init__(fig)

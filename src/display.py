from datetime import datetime, timedelta
from typing import Optional, Union

import matplotlib as mp
import matplotlib.font_manager as fm
import matplotlib.patheffects as PathEffects
import numpy as np
import pylab
from matplotlib import pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import LinearSegmentedColormap
from numpy.core._multiarray_umath import ndarray
from PIL import Image, ImageChops, ImageDraw
from scipy.signal import find_peaks

from src.api.forecast import dailyForecast, Forecast, hourlyForecast
from src.constants import EaseFade, FadeFilter, LinearFade


class dataDisplay:
	solarColorMap: LinearSegmentedColormap

	pickTolerance: int = 4

	markers: plt.axes
	wind: plt.axes
	rain: plt.axes
	cloudCover: plt.axes
	temperature: plt.axes
	radiation: plt.axes

	forecast: hourlyForecast
	dailyForecast: dailyForecast

	timeFloat: list[float] = None
	_interpTime: Union[ndarray, tuple[ndarray, Optional[float]]] = None

	font = {'size': 6}
	mp.rc('font', **font)
	largeFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Rounded-Light.otf', size=4)
	smallFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Rounded-Light.otf', size=12)
	tempFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Rounded-Bold.otf', size=20)
	bigThickFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Rounded-Heavy.otf', size=80)
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
		plt.margins(0.0, 0.0, tight=True)
		plt.subplots_adjust(left=0, right=1, top=1, bottom=-0.01)
		plt.gca().set_axis_off()

		# Construct plotter
		# self.temperature: plt.axes.Axes = self.graph.add_subplot(label='temperature')
		self.temperature: plt.axes.Axes = self.graph.gca()

		self.lastUpdate = self.temperature.text(0.97, 0.97, '',
		                                        horizontalalignment='right',
		                                        verticalalignment='center',
		                                        transform=self.temperature.transAxes, color=self.mainColor,
		                                        fontproperties=self.smallFont, alpha=0.5)

	def buildColorMaps(self):
		from matplotlib.colors import LinearSegmentedColormap
		solarColorDict = {'red':   [(0.0, 0.0, 0.0),
		                            # (0.12, 1, 1),
		                            (0.2, 0.9, 0.9),
		                            # (0.3, 0.3, 0.3),
		                            # (0.4, 0.4, 0.4),
		                            # (0.5, 0.5, 0.5),
		                            # (0.6, 0.6, 0.6),
		                            # (0.7, 0.7, 0.7),
		                            # (0.8, 0.8, 0.8),
		                            (0.7, 1, 1),
		                            (1, 1, 1)],
		                  'green': [(0.0, 0.0, 0.0),
		                            (0.2, 0.75, 0.75),
		                            # (0.2, 0.2, 0.2),
		                            # (0.3, 0.3, 0.3),
		                            # (0.4, 0.4, 0.4),
		                            # (0.5, 0.5, 0.5),
		                            # (0.6, 0.6, 0.6),
		                            # (0.7, 0.7, 0.7),
		                            # (0.8, 0.8, 0.8),
		                            (0.7, 1, 1),
		                            (1, 1, 1)],
		                  'blue':  [(0.0, 0.0, 0.0),
		                            (0.1, 0.2, 0.2),
		                            # (0.2, 0.2, 0.2),
		                            # (0.3, 0.3, 0.3),
		                            (0.4, 0.4, 0.4),
		                            # (0.5, 0.5, 0.5),
		                            # (0.6, 0.6, 0.6),
		                            (0.75, 1, 1),
		                            # (0.8, 0.8, 0.8),
		                            # (0.9, 0.9, 0.9),
		                            (1, 1, 1)
		                            ]  # ,
		                  # 'alpha': [(0.0, 0.0, 0.0),
		                  #           (0.1, 0.1, 0.1),
		                  #           (0.2, 0.2, 0.2),
		                  #           (0.3, 0.3, 0.3),
		                  #           (0.4, 0.4, 0.4),
		                  #           (0.5, 0.5, 0.5),
		                  #           (0.6, 0.6, 0.6),
		                  #           (0.7, 0.7, 0.7),
		                  #           (0.8, 0.8, 0.8),
		                  #           (0.9, 0.9, 0.9),
		                  #           (1, 1, 1.0)]
		                  }

		gray = {'red':   ((0.0, 0, 0), (1.0, 1, 1)),
		        'green': ((0.0, 0, 0), (1.0, 1, 1)),
		        'blue':  ((0.0, 0, 0), (1.0, 1, 1))}

		rain = {'red':   [(0.0, 0.1, 0.1),
		                  (1.0, .4, .4)],

		        'green': [(0.0, 0.1, 0.1),
		                  (1.0, .6, .6)],

		        'blue':  [(0.0, .2, .2),
		                  (0.0, .6, .6),
		                  (1.0, 0.8, 0.8)],

		        'alpha': [(0.0, 0.0, 0.0),
		                  (0.1, 0.2, 0.2),
		                  (1.0, 1, 1)]}
		# 'alpha': [(0.0, 0.0, 0.0),
		#           (0.25, 0.0, 0.0),
		#           (.5, 0.5, 0.5)]}

		self.rainColorMap = LinearSegmentedColormap('colormap', rain)

		self.solarColorMap = LinearSegmentedColormap('colorMap', solarColorDict)

	# self.solarColorMap = LinearSegmentedColormap('colorMap', x)

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

		#TODO: add conditional first temperature
		# if False:
		# 	t = plotter.text(self.data['timestamp'][0] + timedelta(hours=2),
		# 	                 self.data['temp'][0],
		# 	                 str(round(self._forecast.data[measurement][0])) + 'º'.lower(),
		# 	                 ha='center',
		# 	                 va='center',
		# 	                 color=self.mainColor,
		# 	                 fontproperties=self.tempFont)
		# 	t.set_path_effects([PathEffects.withStroke(linewidth=6, foreground='k')])

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
			                 fontproperties=self.tempFont,
			                 zorder=310)
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

	@property
	def dateRange(self):
		return self._forecast.dateRange

	@property
	def dates(self):
		return self._forecast.dates

	@property
	def maxTemp(self):
		return self.data['temp'].max()

	@property
	def minTemp(self):
		return self.data['temp'].min()

	# def showLine(self, data):
	# 	self.highlighter.clear()
	# 	self.highlighter.axvspan(data.ydata, data.ydata, color='red', zorder=500)
	# 	self.updateCanvas()

	def addDaysOfWeek(self):

		# self.highlighter = self.graph.add_subplot(111, label='highlighter', frame_on=False)
		# self.highlighter.set_ylim(0, 1)
		# self.highlighter.set_xlim(self.dateRange)

		location = 0.2

		self.markers = self.graph.add_subplot(111, label='markers', frame_on=False)
		self.markers.set_ylim(0, 1)
		self.markers.set_xlim(self.dateRange)

		days = self.dates
		x = self.data['splitDates']
		print(days)
		for d in days:
			noon = datetime(year=d.year, month=d.month, day=d.day, hour=12, tzinfo=d.tzinfo)
			midnight = datetime(year=d.year, month=d.month, day=d.day, hour=0, tzinfo=d.tzinfo)
			now = datetime.now(tz=d.tzinfo)
			self.markers.axvspan(midnight, midnight, color=self.mainColor, linestyle=(0, (5, 10)), linewidth=2, alpha=0.5)
			# temperature.text(d, 30, 'test', color='white', fontsize=14, fontproperties=prop)
			self.markers.text(noon, location, d.strftime('%a'), horizontalalignment='center',
			                  verticalalignment='center',
			                  color='w',
			                  fontproperties=self.bigThickFont, zorder=-100, alpha=0)
			linewidth = 10
			for x in reversed(range(1, 25)):
				adjustedLineWidth = x*.2
				s = self.markers.text(noon, location, d.strftime('%a'), horizontalalignment='center',
				                      verticalalignment='center',
				                      color='black',
				                      alpha=0,
				                      fontproperties=self.bigThickFont, zorder=-100 - x)
				s.set_path_effects([PathEffects.withStroke(linewidth=adjustedLineWidth, foreground='w',
				                                           alpha=0.01)])
			# s = self.markers.text(noon, .6, d.strftime('%a'), horizontalalignment='center',
			#                       verticalalignment='center',
			#                       color=self.mainColor,
			#                       fontproperties=self.bigThickFont, zorder=-100 - 10, alpha=0)
			# s.set_path_effects([PathEffects.withStroke(linewidth=1, foreground='w', alpha=0.1)])
			# pos = pylab.date2num(midnight)

			for x in range(0,24,6):
				if x in [0]:
					pass
				else:
					time = datetime(year=d.year, month=d.month, day=d.day, hour=x, tzinfo=d.tzinfo)
					self.markers.text(time, 0.05, time.strftime('%-I%p').lower(), horizontalalignment='center',
					                  verticalalignment='center',
					                  color='w',
					                  fontsize=10,
					                  alpha=0.2,
					                  fontproperties=self.bigThickFont, zorder=100)

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

		# from src.constants import tz
		#
		# from matplotlib import dates as mdates
		# plotter.xaxis.set_major_locator(mdates.HourLocator(byhour=0, tz=tz))
		# plotter.xaxis.set_minor_formatter(mdates.DateFormatter('%-I%p', tz=tz))
		# plotter.xaxis.set_major_formatter(mdates.DateFormatter('%-I%p', tz=tz))
		# plotter.xaxis.set_minor_locator(mdates.HourLocator(byhour=range(0, 24, 6)))
		#
		# for x in plotter.get_xmajorticklabels():
		# 	x.set_color('white')
		# 	x.set_fontproperties(self.smallFont)
		# 	x.set_horizontalalignment('center')
		# 	x.set_visible(True)
		#
		# for tick in plotter.xaxis.get_major_ticks():
		# 	tick.tick1line.set_markersize(1)
		# 	tick.tick2line.set_markersize(1)
		# 	tick.label.set_horizontalalignment('center')
		#
		# for x in plotter.get_xminorticklabels(): x.set_color('white'); x.set_fontproperties(self.smallFont)
		plotter.grid(color=self.mainColor, alpha=.75, axis='y', visible=True)
		plotter.grid(axis='x', alpha=1, linestyle=(0, (11, 12)), color=self.mainColor)

	# plotter.grid()

	def plot(self):
		pass

	# Smooth Data
	# self._forecast.data['temp'] = self.splineData(self._forecast.data['temp'])
	# self._forecast.data['feels_like'] = self.splineData(self._forecast.data['feels_like'])
	# self._forecast.data['dewpoint'] = self.splineData(self._forecast.data['dewpoint'])
	# self._forecast.data['precipitation'] = self.smoothData(self._forecast.data['precipitation'], 1, 6)

	# self.addDaysOfWeek()
	# self.addTicks(self.temperature)

	# self.showLunar()
	# self.daylight(self.temperature)
	# self.addTicks(self.temperature)

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

	def showTemperature(self):
		# Find peaks in data
		self.findTemperaturePeaks(self.temperature, 'temp')

		self.temperature.zorder = 10

		self.temperature.set_ylim(self.hiLow(0.3))
		self.temperature.plot('timestamp', 'temp', data=self._forecast.data,
		                      label='Hourly Forecast', zorder=300,
		                      color=self.mainColor, linewidth=4, picker=self.pickTolerance)

	def testPicker(self):
		# Find peaks in data
		# self.findTemperaturePeaks(self.temperature, 'temp')

		self.temperature.set_ylim(self.hiLow(0.3))
		self.temperature.plot('timestamp', 'temp', data=self._forecast.data,
		                      label='temperature', zorder=2,
		                      color=self.mainColor, linewidth=4)

	def showFeelsLike(self):
		self.temperature.plot('timestamp', 'feels_like', data=self._forecast.data, label='feelsLike',
		                      zorder=-20,
		                      color=(.25, .89, .96), linestyle='dashed', alpha=.8, linewidth=3, picker=self.pickTolerance)

	def showDewpoint(self):
		self.temperature.plot('timestamp', 'dewpoint', data=self._forecast.data, zorder=-20,
		                      color=self.mainColor, label='dewpoint', linestyle='dashed', alpha=.8, linewidth=2,
		                      picker=self.pickTolerance)

	def showWind(self):
		self.wind = self.graph.add_subplot(313, label='wind', frame_on=False, sharex=self.temperature)
		self.wind.plot('timestamp', 'wind_speed', data=self.data, linestyle='dashed', color=self.mainColor, alpha=0.4,
		               linewidth=2, picker=self.pickTolerance)

		i = 12
		max = self.data['wind_speed'].max()
		self.wind.set_ylim(-1, max * 1.1)
		for x, s, d in zip(self.data['timestamp'][::i], self.data['wind_speed'][::i], self.data['wind_direction'][::i]):
			self.wind.text(x, s, '', fontproperties=self.weatherIconsFont,
			               horizontalalignment='center',
			               verticalalignment='center',
			               color='w', rotation=round(d), zorder=300)
			pass

	def windDirection(self, direction):
		start = int(0xf0b1)
		# return start
		return chr(round(direction) + start)

	def showSolar(self):
		self.solar = self.graph.add_subplot(111, label='solar', frame_on=False, sharex=self.temperature)
		self.solar.set_ylim(-18, 360)
		# self.solar.set_xlim(self._forecast.data['minutes'][0], self._forecast.data['minutes'][-1])
		self.solar.plot('timestamp', 'sun', data=self.data, picker=self.pickTolerance)
		# self.solar.scatter('timestamp', 'sun', data=self._forecast.data,
		#                    cmap=self.solarColorMap,
		#                    edgecolor='none')

		# self.solar.plot('minutes', 'moon', data=self._forecast.data)
		self.updateCanvas()

	def showLunar(self):
		# self.lunar = self.graph.add_subplot(111, label='lunar', frame_on=False)
		self.lunar = self.temperature.twinx()
		self.lunar.set_ylim(-16, 90)

		# for time in self._forecast.data['moonTimes']:
		# 	self.solar.axvspan(time['rise'], time['set'], alpha=0.1)
		# a = self.drawMoon(self.data['lunarTransit'][0], 400, 400)
		# self.lunar.imshow(a)
		for d in self.data['lunarTransit']:
			if d['time'] is not None and d['time'] > datetime.now(d['time'].tzinfo):
				phase = self.lunar.text(d['time'], d['maxAltitude'], self.moonAge(d['age']),
				                        rotation_mode='anchor',
				                        rotation=d['rotation'],
				                        # bbox=dict(facecolor='blue', edgecolor='red'),
				                        horizontalalignment='center',
				                        verticalalignment='center',
				                        color='#e6efff',
				                        fontproperties=self.weatherIconsFont, zorder=-100, fontsize=30)
		# outline = self.lunar.text(d['time'], d['maxAltitude'], '',
		#                           # bbox=dict(facecolor='None', edgecolor='red', pad=0),
		#                           horizontalalignment='center',
		#                           verticalalignment='center',
		#                           color='#e6efff',
		#                           fontproperties=self.weatherIconsFont, zorder=-100, fontsize=30,
		#                           rotation=d['rotation'],
		#                           rotation_mode='anchor')

		# self.lunar.plot('timestamp', 'moon', data=self.data)
		self.updateCanvas()

	def drawMoon(self, moonInfo, y, size):
		# based on @miyaichi's fork -> great idea :)
		_size = 1000

		illuminated = Image.new("RGBA", (_size + 2, _size + 2))
		shadow = Image.new("RGBA", (_size + 2, _size + 2))
		draw = ImageDraw.Draw(illuminated)
		remove = ImageDraw.Draw(shadow)

		radius = int(_size / 2)

		# draw full moon
		draw.ellipse([(1, 1), (_size, _size)], fill='white')

		# draw dark side of the moon
		theta = moonInfo['age'] / 14.765 * np.pi
		sum_x = sum_length = 0

		for _y in range(-radius, radius, 1):
			alpha = np.arccos(_y / radius)
			x = radius * np.sin(alpha)
			length = radius * np.cos(theta) * np.sin(alpha)

			if moonInfo['age'] < 15:
				start = (radius - x, radius + _y)
				end = (radius + length, radius + _y)
			else:
				start = (radius - length, radius + _y)
				end = (radius + x, radius + _y)

			remove.line((start, end), fill='white')

			sum_x += 2 * x
			sum_length += end[0] - start[0]

		# logger.debug(f"moon phase age: {moonInfo['age']} percentage: {round(100 - (sum_length / sum_x) * 100, 1)}")
		final = ImageChops.subtract(illuminated, shadow).rotate(200 + moonInfo['rotation'])
		# illuminated = illuminated.rotate(200+moonInfo['rotation'])
		# print(moonInfo['rotation'])
		# print(200+moonInfo['rotation'])
		illuminated = illuminated.resize((size, size), Image.LANCZOS)

		return final

	def moonAge(self, age):
		start = int(0xF095)
		# start = int(0xf0d0)
		return chr(round(age) + start)

	def showLight(self):
		filter = EaseFade()
		a = self.mapImage(self.data['surface_shortwave_radiation'], filter)
		self.radiation: plt.subplot = self.graph.add_subplot(111, label='radiation', frame_on=False)
		# self.radiation = self.temperature.twinx()
		# self.radiation.set_xlim(self.data['timestampInt'][0], self.data['timestampInt'][-1])
		self.radiation.imshow(a, aspect='auto', cmap=self.solarColorMap, alpha=0.95, interpolation='bilinear',
		                      zorder=-1000, picker=self.pickTolerance)

	# self.radiation.plot('timestamp', 'surface_shortwave_radiation', data=self.data)

	def mapImage(self, array: Union[list, np.ndarray], fadeFilter: Union[FadeFilter, None] = None):

		if isinstance(array, list):
			array = np.array(array)

		a = np.flip((np.outer(np.ones(len(array)), array)))

		if fadeFilter:
			return fadeFilter.fadeArray(a)
		return a

	# light = np.array(self._forecast.data['radiation'])
	# self.solar.imshow(light[np.newaxis,:], cmap="plasma", aspect="auto")
	# self.updateCanvas()

	def showCloudCover(self):
		cloud = self.data['cloud_cover']
		m = np.full(self.data['length'], 10)
		t = m + (cloud / 400)
		b = m - (cloud / 200)
		# t = m + np.nan_to_num(self.data['cloud_ceiling'])
		# b = m + np.nan_to_num(self.data['cloud_base'])
		time = self.data['timestamp']
		# ax.plot(time, m)
		self.cloudCover = self.graph.add_subplot(111, label='cloud cover', frame_on=False, sharex=self.temperature)
		# self.cloudCover = self.graph.add_subplot(111, label='cloud cover', frame_on=False)
		# self.cloudCover = self.temperature.twinx()
		# self.cloudCover.plot(time, t)
		# self.cloudCover.plot(time, b)
		self.cloudCover.fill_between(time, t, b, color='w', alpha=0.9, linewidth=0.0)
		self.cloudCover.set_ylim(0, 10.4)
		self.cloudCover.margins(0.0, 0.0, tight=True)
		self.cloudCover.set_axis_off()

	def hideSolar(self):
		self.solar.cla()
		self.updateCanvas()

	def showRain(self):
		# self.rain = self.temperature.twinx()

		filter = LinearFade(direction='up')
		data = self.data['precipitation']
		noise = self._forecast.smoothData(np.random.uniform(1, 1.80, round(data.size / 1)))
		a = np.fliplr(self.mapImage(data * np.repeat(noise, 1), filter))

		self.rainAccumulation: plt.subplot = self.graph.add_subplot(111, label='rain', frame_on=False,
		                                                            sharex=self.temperature, picker=self.pickTolerance)
		self.rain: plt.subplot = self.graph.add_subplot(111, label='rain', frame_on=False, sharex=self.radiation)
		# self.radiation = self.temperature.twinx()
		# self.radiation.set_xlim(self.data['timestampInt'][0])
		self.rain.imshow(a, aspect='auto', cmap=self.rainColorMap, alpha=1, interpolation='bilinear',
		                 zorder=-500)
		self.rain.imshow(a, aspect='auto', cmap=self.rainColorMap, alpha=1, interpolation='bilinear',
		                 zorder=-500, picker=self.pickTolerance)
		self.rainAccumulation.plot('timestamp', 'precipitation_accumulation', data=self.data, picker=self.pickTolerance)
		self.rainAccumulation.set_ylim(0, self.data['precipitation_accumulation'][-1] * 3)

		# # n = 2
		# # rainSplit = [
		# # 		sum(self._forecast.data['precipitation_probability'][i:i + n]) // n for i in
		# # 		range(0, len(self._forecast.data['precipitation_probability']), n)]
		#
		# # rainSplit = np.array(rainSplit)
		# m = np.full(self.data['length'], 0)
		# # date = self._forecast.data['timestamp'][::n]
		# self.data['precipitation'] = pow(self.data['precipitation'], .2)
		# self.rain.fill_between(self.data['timestamp'], self.data['precipitation'], m, data=self._forecast.data,
		#                        zorder=-30, alpha=0.7)
		# # self.rain.plot(date, rainSplit, zorder=200, width=.08, color=(.25, .89, .96), capstyle='round')
		# # from matplotlib.patches import FancyBboxPatch
		# # new_patches = []
		# # for patch in reversed(self.rain.patches):
		# # 	bb = patch.get_bbox()
		# # 	color = patch.get_facecolor()
		# # 	p_bbox = FancyBboxPatch((bb.xmin, bb.ymin),
		# # 	                        abs(bb.width), abs(bb.height),
		# # 	                        # boxstyle="round,pad=-0.0080,rounding_size=0.015",
		# # 	                        ec="none", fc=color,
		# # 	                        mutation_aspect=4
		# # 	                        )
		# # 	patch.remove()
		# # 	new_patches.append(p_bbox)
		# # for patch in new_patches:
		# # 	self.rain.add_patch(patch)
		# x = self.data['precipitation'].max()
		# max = 2 if x * 2 < 2 else x * 2
		# # self.rain.set_yscale('log')
		# self.rain.set_ylim(0, 2)
		self.updateCanvas()

	def hideRain(self):
		self.rain.cla()
		self.updateCanvas()

	def updateCanvas(self):
		if self._canvas:
			self._canvas.draw()

	def hiLow(self, offset=None):

		#TODO Change to properties
		if self.maxTemp > self._forecast.data['feels_like'].max():
			h = self._forecast.data['temp'].max()
		else:
			h = self._forecast.data['feels_like'].max()

		if self._forecast.data['temp'].min() < self._forecast.data['feels_like'].min():
			l = self._forecast.data['temp'].min()
		else:
			l = self._forecast.data['feels_like'].min()

		l = self._forecast.data['dewpoint'].min()

		variance = (h - l) * offset

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

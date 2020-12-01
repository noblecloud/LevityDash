from datetime import datetime

import matplotlib as mp
import matplotlib.font_manager as fm
import numpy as np
import pylab
from matplotlib import pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

from classes.forecast import Forecast


class dataDisplay:
	font = {'size': 6}
	mp.rc('font', **font)
	largeFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Text-Light.otf', size=4)
	smallFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Text-Light.otf', size=12)
	tempFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Display-Bold.otf', size=20)
	bigThickFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Text-Heavy.otf', size=24)
	smallMono = fm.FontProperties(fname='/Library/Fonts/SF-Mono-Light.otf', size=10)
	mp.rcParams['font.family'] = 'SF Pro Text Light'
	# mainColor = Colors().kelvinToHEX(3000)
	mainColor = 'w'
	_forecast: Forecast
	_canvas: FigureCanvasTkAgg

	def __init__(self, forecastData: Forecast, size: tuple[int, int, int]):

		self.toFix = []
		self.x, self.y, self.d = size
		self._forecast = forecastData
		self.tempMax = 0
		self.tempMin = 0

		# Construct graph
		self.graph = pylab.figure(figsize=[self.x / self.d, self.y / self.d], dpi=self.d, facecolor='k')
		self.graph.patch.set_facecolor('k')
		plt.margins(0.4, 0.4)
		plt.subplots_adjust(left=0.01, right=.99)
		# plt.gca().set_axis_off()

		# Construct plotter
		self.temperature = self.graph.gca()
		self.temperature.set_facecolor('k')
		self.lastUpdate = self.temperature.text(0.98, 0.03, '',
		                                        horizontalalignment='right',
		                                        verticalalignment='center',
		                                        transform=self.temperature.transAxes, color=self.mainColor,
		                                        fontproperties=self.smallFont)

	@staticmethod
	def smoothData(data: np.ndarray, sigma: int = 1, count: int = 1) -> np.ndarray:
		for x in range(0, count):
			data = gaussian_filter1d(data, sigma)
		return data

	def findTemperaturePeaks(self, plotter, measurement: str):

		import matplotlib.patheffects as PathEffects

		self.tempMax = self._forecast.data['temp'].max()
		self.tempMin = self._forecast.data['temp'].min()

		def removeDuplicates(array, spread):
			for i in array[:-1]:
				print(i)

		range = self.tempMax - self.tempMin

		peaks, _ = find_peaks(self._forecast.data[measurement], distance=12)
		troughs, _ = find_peaks(-self._forecast.data[measurement], distance=12)

		both = np.concatenate((peaks, troughs))
		both = np.sort(both)

		removeDuplicates(both, 5)

		for value in both:
			text = str(round(self._forecast.data[measurement][value])) + 'º'.lower()
			time = self._forecast['timestamp'][value].strftime('%-I%p').lower()
			x = pylab.date2num(self._forecast['timestamp'][value])
			y = self._forecast.data[measurement][value]
			# if y > self.tempMax:
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

			from matplotlib.text import OffsetFrom

			d = OffsetFrom(plotter, t.get_position())
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

	def addDaysOfWeek(self, plotter):
		ypos = (self.tempMax - self.tempMin) / 2 + self.tempMin
		for d in self._forecast.data['timestamp']:
			if d.hour == 12:
				# temperature.text(d, 30, 'test', color='white', fontsize=14, fontproperties=prop)
				plotter.text(d, ypos, d.strftime('%a'), horizontalalignment='center', color='k',
				             fontproperties=self.bigThickFont, zorder=-10)

	# if d.hour == 0:
	# 	pos = pylab.date2num(d)
	# 	plotter.plot([pos, pos], plotter.get_ylim(), color=self.mainColor, linestyle=(0, (5,
	# 																									10)),
	# 				 linewidth=1)
	# plotter.axvspan(pos, pos+0.005, color='white', alpha=.5, ec=None)

	def daylight(self, plotter):

		plotter.set_xlim(self._forecast.data['timestamp'][0], self._forecast.data['timestamp'][-1])

		sunrise: list[datetime] = list(set(self._forecast.data['sunrise']))
		sunset: list[datetime] = list(set(self._forecast.data['sunset']))
		sunrise.sort()
		sunset.sort()

		for x in range(0, len(sunrise)):
			plotter.axvspan(sunrise[x], sunset[x], color=self.mainColor, alpha=0.2, ec=None, zorder=-20)

	def addTicks(self, plotter):

		from classes.constants import tz

		from matplotlib import dates as mdates
		plotter.xaxis.set_major_locator(mdates.HourLocator(byhour=0, tz=tz))
		# plotter.xaxis.set_minor_formatter(mdates.DateFormatter('%-I%p', tz=tz))
		# plotter.xaxis.set_major_formatter(mdates.DateFormatter('%-I%p', tz=tz))
		# plotter.xaxis.set_minor_locator(mdates.HourLocator(byhour=range(0, 24, 6)))

		for x in plotter.get_xmajorticklabels():
			x.set_color('white')
			x.set_fontproperties(self.smallFont)
			x.set_horizontalalignment('center')
			x.set_visible(False)

		# for tick in plotter.xaxis.get_major_ticks():
		# 	tick.tick1line.set_markersize(1)
		# 	tick.tick2line.set_markersize(1)
		# 	tick.label.set_horizontalalignment('center')

		for x in plotter.get_xminorticklabels(): x.set_color('white'); x.set_fontproperties(self.smallFont)
		plotter.grid(color=self.mainColor, alpha=.75, axis='y', visible=False)
		plotter.grid(axis='x', alpha=1, linestyle=(0, (11, 12)), color=self.mainColor)

	# plotter.grid()

	def plot(self):

		# Smooth Data
		self._forecast.data['temp'] = self.smoothData(self._forecast.data['temp'], 1, 3)
		self._forecast.data['feels_like'] = self.smoothData(self._forecast.data['feels_like'], 1, 3)
		self._forecast.data['dewpoint'] = self.smoothData(self._forecast.data['dewpoint'], 1, 3)

		# Find peaks in data
		self.findTemperaturePeaks(self.temperature, 'temp')
		self.tempMax = self._forecast.data['temp'].max()
		self.tempMin = self._forecast.data['temp'].min()

		self.temperature.zorder = 10

		self.temperature.plot('timestamp', 'temp', data=self._forecast.data, label='Hourly Forecast', zorder=2,
		                      color=self.mainColor, linewidth=4)

		self.temperature.plot('timestamp', 'feels_like', data=self._forecast.data, label='Hourly Forecast', zorder=-20,
		                      color=(.25, .89, .96), linestyle='dashed', alpha=.8, linewidth=3)

		self.temperature.plot('timestamp', 'dewpoint', data=self._forecast.data, zorder=-20,
		                      color=self.mainColor, label='Hourly Forecast', linestyle='dashed', alpha=.8, linewidth=2)

		self.addDaysOfWeek(self.temperature)
		self.daylight(self.temperature)
		self.addTicks(self.temperature)

	def rasterRender(self, figure):

		from matplotlib.backends.backend_agg import FigureCanvasAgg, RendererAgg
		import matplotlib.backends.backend_agg as agg
		mp.use("Agg")

		canvas: FigureCanvasAgg = agg.FigureCanvasAgg(figure)
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

	def update(self):
		self.lastUpdate.set_text(datetime.now().strftime('%-I:%M%p').lower())
		self._canvas.draw()

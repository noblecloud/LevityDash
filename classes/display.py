import numpy as np
from matplotlib import dates as mdates, pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg, RendererAgg
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
import matplotlib as mp
from datetime import datetime

mp.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.backends.backend_agg as agg
import pylab

from classes.constants import Colors


class dataDisplay():
	renderer: RendererAgg
	canvas: FigureCanvasAgg
	font = {'size': 6}
	mp.rc('font', **font)
	largeFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Text-Light.otf', size=4)
	smallFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Text-Light.otf', size=12)
	tempFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Display-Bold.otf', size=20)
	bigThickFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Text-Heavy.otf', size=24)
	mp.rcParams['font.family'] = 'SF Pro Text Light'
	mainColor = Colors().kelvinToHEX(3000)
	# mainColor = 'w'
	def __init__(self, forecastData, size: tuple[int, int, int]):

		self.toFix = []
		self.x, self.y, self.d = size
		self.forecastData = forecastData
		self.tempMax = 0
		self.tempMin = 0

	@staticmethod
	def smoothData(data: np.ndarray, sigma: int = 1, count: int = 1) -> np.ndarray:
		for x in range(0,count):
			data = gaussian_filter1d(data, sigma)
		return data

	def findTemperaturePeaks(self, plotter, measurement: str):

		import matplotlib.patheffects as PathEffects

		self.tempMax = self.forecastData.data['temp'].max()
		self.tempMin = self.forecastData.data['temp'].min()

		def removeDuplicates(array, spread):
			for i in array[:-1]:
				print(i)

		range = self.tempMax - self.tempMin

		peaks, _ = find_peaks(self.forecastData.data[measurement], distance=12)
		troughs, _ = find_peaks(-self.forecastData.data[measurement], distance=12)

		both = np.concatenate((peaks, troughs))
		both = np.sort(both)

		removeDuplicates(both, 5)

		for value in both:
			text = str(round(self.forecastData.data[measurement][value])) + 'º'.lower()
			time = self.forecastData['timestamp'][value].strftime('%-I%p').lower()
			x = pylab.date2num(self.forecastData['timestamp'][value])
			y = self.forecastData.data[measurement][value]
			# if y > self.tempMax:
			# 	y -= 3
			t = plotter.text(x+0.02,
							 y,
							 text.lower(),
							 ha='center',
							 va='center',
							 color=self.mainColor,
							 fontproperties=self.tempFont)
			t.set_path_effects([PathEffects.withStroke(linewidth=6, foreground='k')])

			# t.
			d = plotter.text(x,
							 y - 4,
							 time.lower(),
							 ha='center',
							 va='center',
							 color=self.mainColor,
							 fontproperties=self.tempFont, fontsize=10).set_path_effects([PathEffects.withStroke(linewidth=6, foreground='k')])
			# plotter.plot([x, x], [y - 5, self.tempMin], color='w', linewidth=1, alpha=.5, zorder=-15)
			print(t)

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
		from datetime import datetime
		ypos = (self.tempMax - self.tempMin) / 2 + self.tempMin
		for d in self.forecastData.data['timestamp']:
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

		plotter.set_xlim(self.forecastData.data['timestamp'][0], self.forecastData.data['timestamp'][-1])

		sunrise: list[datetime] = list(set(self.forecastData.data['sunrise']))
		sunset: list[datetime] = list(set(self.forecastData.data['sunset']))
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

	def makeFigurePix(self, fields):

		# Construct figure
		fig = pylab.figure(figsize=[self.x / self.d, self.y / self.d], dpi=self.d, facecolor='k')
		fig.patch.set_facecolor('k')
		plt.margins(0.4, 0.4)
		plt.subplots_adjust(left=0.01, right=.99)
		# plt.gca().set_axis_off()

		# Construct plotter
		temperature = fig.gca()
		temperature.set_facecolor('k')

		# Make it Rain
		# forecastData['precipitation'] = data.makeItRain(len(forecastData['precipitation']))

		# Smooth Data
		# self.forecastData.data['precipitation'] = self.smoothData(self.forecastData.data['precipitation'])
		self.forecastData.data['temp'] = self.smoothData(self.forecastData.data['temp'], 1, 3)
		self.forecastData.data['feels_like'] = self.smoothData(self.forecastData.data['feels_like'], 1, 3)
		self.forecastData.data['dewpoint'] = self.smoothData(self.forecastData.data['dewpoint'], 1, 3)

		# Find peaks in data
		self.findTemperaturePeaks(temperature, 'temp')
		self.tempMax = self.forecastData.data['temp'].max()
		self.tempMin = self.forecastData.data['temp'].min()

		feelsLike = temperature.twinx()

		temperature.plot('timestamp', 'temp', data=self.forecastData.data, label='Hourly Forecast', zorder=2,
						 color=self.mainColor, linewidth=4)

		temperature.plot('timestamp', 'feels_like', data=self.forecastData.data, label='Hourly Forecast', zorder=-20,
						 color=(.25, .89, .96), linestyle='dashed', alpha=.8, linewidth=3)

		temperature.zorder = 10

		dewpoint = temperature.twinx()

		temperature.plot('timestamp', 'dewpoint', data=self.forecastData.data, zorder=-20,
					   color=self.mainColor, label='Hourly Forecast', linestyle='dashed', alpha=.8, linewidth=2)


		# precipitation = temperature.twinx()
		# precipitation.set_ylim([0, 100])
		# precipitation.bar('timestamp'[1:10], 'precipitation'[:10], data=self.forecastData.data, label='Precipitation',
		# 				  zorder=-2,
		# 				  color='cornflowerblue')

		plt.xticks(rotation=0)
		self.addDaysOfWeek(temperature)
		self.daylight(temperature)
		self.addTicks(temperature)

		# for spine in plt.gca().spines.values():
		# 	spine.set_visible(False)

		self.canvas = agg.FigureCanvasAgg(fig)
		self.canvas.draw()
		self.renderer = self.canvas.get_renderer()
		raw_data = self.renderer.tostring_rgb()

		return raw_data

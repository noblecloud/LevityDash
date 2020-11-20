import numpy as np
from matplotlib import dates as mdates, pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg, RendererAgg
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
import matplotlib as mp

mp.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.backends.backend_agg as agg
import pylab


class dataDisplay():
	renderer: RendererAgg
	canvas: FigureCanvasAgg
	font = {'size': 6}
	mp.rc('font', **font)
	largeFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Text-Light.otf', size=4)
	smallFont = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Text-Light.otf', size=6)
	mp.rcParams['font.family'] = 'SF Pro Text Light'

	def __init__(self, forecastData, size: tuple[int, int, int]):

		self.x, self.y, self.d = size
		self.forecastData = forecastData

	@staticmethod
	def smoothData(data: np.ndarray, sigma: int = 1) -> np.ndarray:
		return gaussian_filter1d(data, sigma)

	def findTemperaturePeaks(self, plotter, measurement: str):

		peaks, _ = find_peaks(self.forecastData.data[measurement], height=3, wlen=4)
		troughs, _ = find_peaks(-self.forecastData.data[measurement], height=-200, wlen=4)
		for value in peaks:
			plotter.text(self.forecastData['timestamp'][value], self.forecastData.data[measurement][value] + 1,
						 str(round(self.forecastData.data[measurement][value])) +
						 self.forecastData.data['units'][measurement] + 'º', horizontalalignment='center',
						 color='white',
						 fontsize=12,
						 fontproperties=self.largeFont)

		for value in troughs:
			plotter.text(self.forecastData.data['timestamp'][value], self.forecastData.data[measurement][value] - 3,
						 str(round(self.forecastData.data[measurement][value])) +
						 self.forecastData.data['units'][measurement] + 'º',
						 horizontalalignment='center', color='white', fontsize=12, fontproperties=self.largeFont)

	def addDaysOfWeek(self, plotter):
		ypos = round(self.y/7)
		print(self.y)
		print(ypos)
		for d in self.forecastData.data['timestamp']:
			if d.hour == 12:
				# pos = date2num(d)
				# temperature.text(d, 30, 'test', color='white', fontsize=14, fontproperties=prop)
				plotter.text(d, ypos, d.strftime('%a'), horizontalalignment='center', color='darkgrey',
							 fontsize=14, fontproperties=self.largeFont)

	def addTicks(self, plotter):
		from matplotlib import dates as mdates
		plotter.xaxis.set_major_locator(mdates.DayLocator())
		plotter.xaxis.set_minor_formatter(mdates.DateFormatter('%-I%p'))
		plotter.xaxis.set_minor_locator(mdates.HourLocator(byhour=range(0, 24, 6)))

		for x in plotter.get_xmajorticklabels():
			x.set_color('white')
			x.set_fontproperties(self.smallFont)
			x.set_horizontalalignment('center')
			x.set_visible(False)

		for tick in plotter.xaxis.get_major_ticks():
			tick.tick1line.set_markersize(0)
			tick.tick2line.set_markersize(0)
			tick.label.set_horizontalalignment('center')

		for x in plotter.get_xminorticklabels(): x.set_color('white'); x.set_fontproperties(self.smallFont)
		plotter.grid(color='white', alpha=0.5)
		plotter.grid(axis='y', alpha=0)

	def makeFigurePix(self, fields):

		# Construct figure
		fig = pylab.figure(figsize=[self.x / self.d, self.y / self.d], dpi=self.d, facecolor='k')
		fig.patch.set_facecolor('gray')
		plt.margins(0, 0)
		plt.subplots_adjust(left=0.01, right=.99)
		plt.gca().set_axis_off()

		# Construct plotter
		temperature = fig.gca()
		temperature.set_facecolor('k')

		# Make it Rain
		# forecastData['precipitation'] = data.makeItRain(len(forecastData['precipitation']))
		# Smooth Data
		self.forecastData.data['precipitation'] = self.smoothData(self.forecastData.data['precipitation'])
		self.forecastData.data['temp'] = self.smoothData(self.forecastData.data['temp'], 2)

		# dates = self.dateArray(type)

		# Find peaks in data

		self.findTemperaturePeaks(temperature, 'temp')

		temperature.margins(x=None, y=None, tight=True)
		# temperature.xaxis.set_formatter(mdates.DayLocator())
		#
		# temperature.xaxis.set_major_formatter(mdates.DateFormatter('%a'))
		# temperature.xaxis.set_major_locator(mdates.DayLocator())
		temperature.tick_params(axis='x', pad=0)

		temperature.plot('timestamp', 'temp', data=self.forecastData.data, label='Hourly Forecast', zorder=-1,
						 color='white')

		# precipitation = temperature.twinx()
		# precipitation.set_ylim([0, 100])
		# precipitation.bar('timestamp'[1:10], 'precipitation'[:10], data=self.forecastData.data, label='Precipitation',
		# 				  zorder=-2,
		# 				  color='cornflowerblue')

		# plt.xticks(rotation=0)
		self.addDaysOfWeek(temperature)
		# self.addTicks(temperature)

		# from matplotlib.patches import FancyBboxPatch
		# new_patches = []
		# for patch in reversed(precipitation.patches):
		# 	bb = patch.get_bbox()
		# 	color = patch.get_facecolor()
		# 	p_bbox = FancyBboxPatch((bb.xmin, bb.ymin),
		# 							abs(bb.width), abs(bb.height),
		# 							boxstyle="round,pad=.4,rounding_size=0.031",
		# 							ec="none", fc=color,
		# 							mutation_aspect=0.5
		# 							)
		# 	patch.remove()
		# 	new_patches.append(p_bbox)
		# for patch in new_patches:
		# 	precipitation.add_patch(patch)

		# for i, date in enumerate(self.dateArray):
		# 	print(self.forecastDict['sunrise'][i])
		# 	if d > datetime.strptime(self.forecastDict['sunrise'][i],):
		# 		print(i)
		# 		pos = date2num(d)
		# 		ax.axvspan(pos, pos + 0.02, color='#DDDDDD')
		#

		for spine in plt.gca().spines.values():
			spine.set_visible(False)

		# import cairo
		# import pygame
		# import rsvg

		self.canvas = agg.FigureCanvasAgg(fig)
		self.canvas.draw()
		self.renderer = self.canvas.get_renderer()
		raw_data = self.renderer.tostring_rgb()

		return raw_data

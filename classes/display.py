import numpy as np
from matplotlib import dates as mdates, pyplot as plt
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks


class dataDisplay():

	def __init__(self, forecastData):
		self.forecastData = forecastData

	@staticmethod
	def smoothData(data: np.ndarray, sigma: int = 1) -> np.ndarray:
		return gaussian_filter1d(data, sigma)

	def makeFigurePix(self, data, size: tuple[int, int, int], forecastType=None, fields):

		x, y, d = size

		if forecastType is None:
			forecastType = ['hourly']

		import matplotlib as mp
		mp.use("Agg")
		import matplotlib.font_manager as fm
		import matplotlib.backends.backend_agg as agg
		import pylab

		# Attempting to set a font...
		font = {'size': 6}
		mp.rc('font', **font)
		prop = fm.FontProperties(fname='/Library/Fonts/SF-Pro-Text-Light.otf')
		mp.rcParams['font.family'] = 'SF Pro Text Light'

		# Construct figure
		fig = pylab.figure(figsize=[x / d, y / d], dpi=d, facecolor='k')
		fig.patch.set_facecolor('k')

		# Construct plotter
		temperature = fig.gca()
		temperature.set_facecolor('k')

		forecastData: dict[str: np.ndarray] = data.combineForecasts(forecastType, fields)

		# Make it Rain
		forecastData['precipitation'] = data.makeItRain(len(forecastData['precipitation']))

		# Smooth Data
		forecastData['precipitation'] = self.smoothData(forecastData['precipitation'])
		forecastData['temp'] = self.smoothData(forecastData['temp'], 2)

		# dates = self.dateArray(type)

		# Find peaks in data

		# noinspection PySameParameterValue
		def findTemperaturePeaks(plotter, measurmentData: dict[str:np.ndarray], measurement: str):

			peaks, _ = find_peaks(forecastData[measurement], height=3, wlen=3)
			troughs, _ = find_peaks(-forecastData[measurement], height=-200, wlen=3)
			for value in peaks:
				plotter.text(measurmentData['timestamp'][value], measurmentData[measurement][value] + 1,
							 str(round(measurmentData[measurement][value])) +
							 data.units[measurement] + 'º', horizontalalignment='center', color='white', fontsize=12,
							 fontproperties=prop)

			for value in troughs:
				print(value)
				plotter.text(measurmentData['timestamp'][value], measurmentData[measurement][value] - 2, round(measurmentData[measurement][value]),
							 horizontalalignment='center', color='white', fontsize=12, fontproperties=prop)

		findTemperaturePeaks(temperature, forecastData, 'temp')

		temperature.margins(x=None, y=None, tight=True)

		temperature.plot('timestamp', 'temp', data=forecastData, label='Hourly Forecast', zorder=-1)

		precipitation = temperature.twinx()
		precipitation.set_ylim([0, 100])
		precipitation.bar('timestamp'[1:10], 'precipitation'[:10], data=forecastData, label='Precipitation', zorder=-2,
						  color='cornflowerblue')

		temperature.xaxis.set_major_formatter(mdates.DateFormatter('%a'))
		temperature.xaxis.set_major_locator(mdates.DayLocator())
		temperature.tick_params(axis='x', pad=0)

		plt.xticks(rotation=0)

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

		def addDaysOfWeek(plotter, data):
			for d in data['timestamp']:
				if d.hour == 12:
					# pos = date2num(d)
					# temperature.text(d, 30, 'test', color='white', fontsize=14, fontproperties=prop)
					plotter.text(d, 60, d.strftime('%a'), horizontalalignment='center', color='darkgrey',
								 fontsize=14, fontproperties=prop)

		# for i, date in enumerate(self.dateArray):
		# 	print(self.forecastDict['sunrise'][i])
		# 	if d > datetime.strptime(self.forecastDict['sunrise'][i],):
		# 		print(i)
		# 		pos = date2num(d)
		# 		ax.axvspan(pos, pos + 0.02, color='#DDDDDD')

		addDaysOfWeek(temperature, forecastData)

		def addTicks(plotter):
			plotter.xaxis.set_minor_formatter(mdates.DateFormatter('%-I%p'))
			plotter.xaxis.set_minor_locator(mdates.HourLocator(byhour=range(0, 24, 6)))

			for x in plotter.get_xmajorticklabels():
				x.set_color('white')
				x.set_fontproperties(prop)
				x.set_horizontalalignment('center')
				x.set_visible(False)

			for tick in plotter.xaxis.get_major_ticks():
				tick.tick1line.set_markersize(0)
				tick.tick2line.set_markersize(0)
				tick.label.set_horizontalalignment('center')

			for x in plotter.get_xminorticklabels(): x.set_color('white'); x.set_fontproperties(prop)
			plotter.grid(color='white', alpha=0.5)
			plotter.grid(axis='y', alpha=0)

		addTicks(temperature)

		for spine in plt.gca().spines.values():
			spine.set_visible(False)

		# import cairo
		# import pygame
		# import rsvg

		self.canvas = agg.FigureCanvasAgg(fig)
		self.canvas.draw()
		renderer = self.canvas.get_renderer()
		raw_data = renderer.tostring_rgb()

		return raw_data

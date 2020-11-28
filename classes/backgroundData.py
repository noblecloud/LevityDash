import threading

from classes.forecast import Forecast
from classes.realtime import realtime

class BackgroundData(threading.Thread):

	realtime: realtime
	forecast: Forecast

	def __init__(self):
		super().__init__()

	def run(self):
		pass


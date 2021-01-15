from configparser import ConfigParser
import utils


class _Config(ConfigParser):

	def __init__(self, *args, **kwargs):
		self.path = utils.rootPath.joinpath('config.ini')
		super(_Config, self).__init__(*args, **kwargs)
		self.read()

	def read(self, *args, **kwargs):
		super().read(self.path, *args, **kwargs)

	def update(self):
		# TODO: Add change indicator
		self.read()

	def __getattr__(self, item):
		return self[item]

	@property
	def wf(self):
		return self['WeatherFlow']

	@property
	def aw(self):
		return self['AmbientWeather']


config = _Config()

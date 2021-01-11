from configparser import ConfigParser

class Config:
	_config: ConfigParser = ConfigParser()

	def __init__(self, path):
		# path = abspath('./config.ini')
		self._config.read(path)

	def __getitem__(self, item):
		return self._config[item]


conf = Config('./config.ini')

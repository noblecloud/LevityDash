# from .general import *
import WeatherUnits as units

units.config.read('../config.ini')
from src._config import config
from src._easyDict import SmartDictionary
from src import observations
from src import api
from src import translators
from src import utils

# from .general import *
import WeatherUnits as wu

wu.config.read('config.ini')
from src._config import config
from src import observations
from src import api
from src import translators
from src import colorLog
from src import utils
from src import colors
from src import fonts

import json
from src import logging
from configparser import ConfigParser, SectionProxy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, List, Tuple, Union

import requests
from PySide2.QtCore import QObject, Signal
from PySide2.QtNetwork import QHostAddress, QNetworkDatagram, QUdpSocket
from WeatherUnits.base import Measurement

from src.api.baseAPI import API, URLs
from src.api.tomorrowIO import log
from field import Fields
from src.observations.tomorrowIO import TomorrowIOForecastDaily, TomorrowIOForecastHourly, TomorrowIOObservationRealtime
from src import utils
from src.api.errors import APIError, InvalidCredentials, RateLimitExceeded
from src.observations import ObservationRealtime, WFObservationHour, ObservationForecast, WFForecastHourly
from src import config
from src.udp import weatherFlow as udp
from src.utils import Logger, UpdateDispatcher


from pathlib import Path

from datetime import datetime
from typing import Union
from pytz import timezone, tzinfo, utc

from src import config

rootPath = Path(__file__).parent


def utcCorrect(utcTime: datetime, tz: timezone = None):
	return utcTime.replace(tzinfo=utc).astimezone(tz if tz else config.tz)


def formatDate(value, **kwargs):
	"""
	Convert a date string, int or float into a datetime object with an optional timezone setting
	and converting UTC to local time

	:param value: The raw date two be converted into a datetime object
	:param tz: Local timezone
	:param utc: Specify if the time needs to be adjusted from UTC to the local timezone
	:param format: The format string needed to convert to datetime
	:param microseconds: Specify that the int value is in microseconds rather than seconds
	:type value: str, int, float
	:type tz: pytz.tzinfo
	:type utc: bool
	:type format: str
	:type microseconds: bool

	:return datetime:

	"""
	tz = timezone(kwargs['tz']) if kwargs['tz'] else config.tz
	if isinstance(value, str):
		time = datetime.strptime(value, kwargs['format'])
	elif isinstance(value, int):
		time = datetime.fromtimestamp(value * 0.001 if kwargs['microseconds'] else value)
	else:
		time = value

	return utcCorrect(time, tz) if kwargs['utc'] else time.astimezone(tz)

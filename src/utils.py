import logging
from datetime import datetime
from typing import Union

from pytz import timezone, utc

from src import config


def utcCorrect(utcTime: datetime, tz: timezone = None):
	"""Correct a datetime from utc to local time zone"""
	return utcTime.replace(tzinfo=utc).astimezone(tz if tz else config.tz)


def formatDate(value, tz: Union[str, timezone], utc: bool = False, format: str = '', microseconds: bool = False):
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
	tz = timezone(tz) if tz else config.tz
	if isinstance(value, str):
		try:
			time = datetime.strptime(value, format)
		except ValueError as e:
			logging.error('A format string must be provided')
			raise e
	elif isinstance(value, int):
		time = datetime.fromtimestamp(value * 0.001 if microseconds else value)
	else:
		time = value

	return utcCorrect(time, tz) if utc else time.astimezone(tz)

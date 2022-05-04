from datetime import datetime, timedelta
from typing import Union

import WeatherUnits as wu
from .shared import now


# def closest(lst: List, value: Any):
# 	return lst[min(range(len(lst)), key=lambda i: abs(lst[i] - value))]


## TODO: Look into LCS (Longest Common Subsequence) algorithms


# TODO: Look into using dateutil.parser.parse as a backup for if util.formatDate is given a string without a format


def timedeltaToDict(value: timedelta):
	ignored = ('microseconds', 'resolution', 'total_seconds', 'min', 'max')
	return {i: v for i in dir(value) if (v := getattr(value, i)) != 0 and i not in ignored and not i.startswith('_')}


def ISODuration(s: str) -> timedelta:
	def ISOsplit(s, split):
		'''https://stackoverflow.com/a/64232786/2975046'''
		if split in s:
			n, s = s.split(split)
		else:
			n = 0
		return n, s

	# Remove prefix
	s = s.split('P')[-1]

	# Step through letter dividers
	days, s = ISOsplit(s, 'D')
	_, s = ISOsplit(s, 'T')
	hours, s = ISOsplit(s, 'H')
	minutes, s = ISOsplit(s, 'M')
	seconds, s = ISOsplit(s, 'S')
	a = timedelta(days=1)
	a.days

	return timedelta(days=int(days), hours=int(hours), minutes=int(minutes), seconds=int(seconds))


def datetimeFilterMask(value: timedelta):
	_ = [1, 60, 3600, 86400, 604800, 2592000, 31536000]
	if value is None:
		return None
	s = value.total_seconds()
	return [i%s for i in _]


class DateTimeRange:
	__slots__ = ('__start', '__end')
	__start: datetime
	__end: datetime

	def __init__(self, *args: Union[datetime, timedelta]):
		if len(args) != 2:
			raise ValueError('DateTimeRange must be constructed with at least two arguments')
		start, end = args
		if isinstance(start, timedelta):
			start = now() + start
		if isinstance(end, timedelta):
			end = now() + end
		self.__start = start
		self.__end = end

	# match start:
	# 	case datetime():
	# 		pass
	# 	case timedelta():
	# 		start = now() + start
	# 	case wu.Time():
	# 		start = now() + timedelta(seconds=start.second)
	# 	case _ if hasattr(start, 'timestamp'):
	# 		timestamp = start.timestamp
	# 		if isinstance(timestamp, Callable):
	# 			timestamp = timestamp()
	# 		if isinstance(timestamp, (int, float)):
	# 			start = datetime.fromtimestamp(timestamp)
	# 		elif isinstance(timestamp, datetime):
	# 			start = timestamp
	# 		else:
	# 			raise TypeError(f'{start} is not a valid timestamp')
	# 	case _:
	# 		raise TypeError(f'{start} is not a valid start')

	def __repr__(self):
		s, e = sorted((self.__start, self.__end))
		s = wu.Time.Second((s - now()).total_seconds()).autoAny
		e = wu.Time.Second((e - now()).total_seconds()).autoAny
		diff = (e - s).autoAny
		return f'<{self.__class__.__name__}[{diff}] {s} to {e}>'

	def __contains__(self, val: datetime) -> bool:
		return self.__start <= val <= self.__end

	def __call__(self, *values: 'TimeAwareValue', assumeSorted: bool = True) -> iter:
		if not assumeSorted:
			values = sorted(values, key=lambda val: val.timestamp)
		period = timedelta((values[0].timestamp - values[-1].timestamp).total_seconds()/len(values))

		# if the first value is after the start of the range, use the period to infer the start
		if abs(values[0].timestamp - self.__start) > period:
			valueStartIndex = int((values[0].timestamp - self.__start).total_seconds()/period.total_seconds())
			while valueStartIndex >= 0 and values[valueStartIndex].timestamp > self.__start:
				valueStartIndex -= 1
			values = values[valueStartIndex:]

		for value in values:
			if self.__start <= value.timestamp <= self.__end:
				yield value
			break


NoValue = object()

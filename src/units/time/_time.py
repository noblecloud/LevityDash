from units import Union

from units._unit import AbnormalScale


class _Time(AbnormalScale):
	_format = '{:2.2f}'
	# milliseconds, second, minute, hour, day
	_factors = [1, 1000, 60, 60, 12]

	def _milliseconds(self):
		return self.changeScale(0)

	def _seconds(self):
		return self.changeScale(1)

	def _minutes(self):
		return self.changeScale(2)

	def _hours(self):
		return self.changeScale(3)

	def _days(self):
		return self.changeScale(4)

	@property
	def ms(self):
		from units.time import Millisecond
		return Millisecond(self._milliseconds())

	@property
	def s(self):
		from units.time import Second
		return Second(self._seconds())

	@property
	def min(self):
		from units.time import Minute
		return Minute(self._minutes())

	@property
	def hr(self):
		from units.time import Hour
		return Hour(self._hours())

	@property
	def day(self):
		from units.time import Day
		return Day(self._days())

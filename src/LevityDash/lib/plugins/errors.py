class InvalidData(Exception):
	pass


class NoSourceForPeriod(Exception):
	pass


class NotPreferredSource(Exception):
	pass


class PreferredSourceDoesNotHavePeriod(NoSourceForPeriod, NotPreferredSource):
	pass

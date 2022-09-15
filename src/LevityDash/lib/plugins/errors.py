class InvalidData(Exception):
	pass


class NoSourceForPeriod(Exception):
	pass


class NotPreferredSource(Exception):
	pass


class PreferredSourceDoesNotHavePeriod(NoSourceForPeriod, NotPreferredSource):
	pass


class MissingPluginDeclaration(AttributeError):
	"""Raised when a plugin is missing the __plugin__ declaration."""
	pass


class PluginDisabled(Exception):
	"""Raised when a plugin is loaded but is disabled."""
	pass

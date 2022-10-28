from typing import Type, TypeAlias, TypeVar, Union

_E: TypeAlias = TypeVar('_E')

_mixin_type_cache: dict[Type[Exception], Type['PluginError']] = {}


class InvalidData(Exception):
	pass


class NoSourceForPeriod(Exception):
	pass


class NotPreferredSource(Exception):
	pass


class PreferredSourceDoesNotHavePeriod(NoSourceForPeriod, NotPreferredSource):
	pass


class PluginError(Exception):

	@classmethod
	def build_mixin_error(cls, error: _E) -> Type[Union[Type[_E], 'PluginError']]:
		try:
			return _mixin_type_cache[error]
		except KeyError:
			error_cls = type(error)
			mixed = type(f'{cls.__name__}({error_cls.__name__})', (cls, error_cls), {})
			_mixin_type_cache[error_cls] = mixed
		return mixed

	@classmethod
	def mix_in_error(cls, error: _E) -> Union[Type[_E], 'PluginError']:
		if isinstance(error, cls):
			return error
		return cls.build_mixin_error(error)


class MissingPluginDeclaration(PluginError, AttributeError):
	"""Raised when a plugin is missing the __plugin__ declaration."""
	pass


class PluginDisabled(PluginError):
	"""Raised when a plugin is loaded but is disabled."""
	pass


class PluginLoadError(PluginError, ImportError):
	pass

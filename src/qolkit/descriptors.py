"""Descriptor and cache-management utilities."""
from functools import cached_property, partial
from typing import Any, Callable, get_args


class classproperty:
	"""Read-only computed class-level attribute.

	Replaces the ``@classmethod`` + ``@property`` decorator stack, which
	Python 3.13 removed (chaining classmethod over another descriptor no
	longer works). Works uniformly for access via a class, an instance, or a
	metaclass: the getter always receives the owning class.

	Deliberately duplicated (not imported) from LevityDash.lib._descriptors -
	that module is kept import-free so it can load very early (before the
	utils/log chain exists); depending on qolkit that early would risk that.
	"""

	def __init__(self, fget: Callable):
		self.fget = fget
		self.__doc__ = getattr(fget, '__doc__', None)

	def __set_name__(self, owner, name):
		self.__name__ = name

	def __get__(self, obj, owner=None):
		if owner is None:
			owner = type(obj)
		return self.fget(owner)


class guarded_cached_property(cached_property):

	def __new__(cls, *args, guardFunc: Callable[[Any], bool] = None, default: Any = None):
		if not args:
			return partial(guarded_cached_property, guardFunc=guardFunc, default=default)
		return cached_property.__new__(cls)

	def _guardFunc(self, instance):
		return instance is not None

	def __init__(self, *args, guardFunc: Callable[[Any], bool] = None, default: Any = None):
		super().__init__(*args)
		self.guardFunc = guardFunc or self._guardFunc
		self.default = default

	def __call__(self, *args, **kwargs):
		pass

	def __get__(self, instance, owner=None):
		value = super().__get__(instance, owner)
		if self.guardFunc(value):
			return value
		else:
			instance.__dict__.pop(self.attrname, None)
			if isinstance(defaultFunc := self.default, Callable):
				if 'self' in get_args(defaultFunc):
					return defaultFunc(instance)
				return self.default()
			elif isinstance(defaultFunc, property):
				return defaultFunc.__get__(instance, owner)
			return self.default


def clearCacheAttr(obj: object, *attr: str):
	for a in attr:
		try:
			del obj.__dict__[a]
			continue
		except AttributeError:
			pass
		except KeyError:
			pass



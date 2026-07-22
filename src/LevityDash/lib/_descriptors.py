"""Tiny, dependency-free descriptors.

Kept deliberately import-free so it can be pulled in during very early module
initialisation (e.g. config.py, before the utils/log chain is ready) without
triggering import-order side effects.
"""
from typing import Callable


class classproperty:
	"""Read-only computed class-level attribute.

	Replaces the ``@classmethod`` + ``@property`` decorator stack, which
	Python 3.13 removed (chaining classmethod over another descriptor no
	longer works). Works uniformly for access via a class, an instance, or a
	metaclass: the getter always receives the owning class. Getter bodies keep
	their original name-mangling since they stay defined in the class body.
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

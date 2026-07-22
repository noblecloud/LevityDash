"""Dict/mapping utilities: dotted-key access, deep merging, sorting, getters."""
import logging
import re
from collections import ChainMap
from functools import lru_cache
from typing import Any, Callable, Hashable, Mapping, Type

from .sentinels import Unset, UnsetKwarg

log = logging.getLogger("qolkit")


def __get(obj: Mapping, key, default=UnsetKwarg):
	"""getter for mappings"""
	if default is not UnsetKwarg:
		return obj.get(key, default)
	return obj.get(key)


def get(
	obj: Mapping | object,
	*keys: [Hashable, ...],
	default: Any = UnsetKwarg,
	expectedType: Type | Any = object,
	castVal: bool = False,
	getter: Callable = __get,
) -> Any:
	"""
	Gets the value of a given key or iterable of keys from an object or mapping.
	Can also cast the value to a specified type and return a default value if
	the key is not found. An expected type can be specified for determining
	the correct value if there are multiple keys.
	"""
	values = tuple(r for key in keys if (r := getter(obj, key, Unset)) is not Unset)
	match len(values):
		case 0:
			if default is Unset:
				raise KeyError(f'{keys} not found in {obj}')
			return default
		case 1:
			value = values[0]
			if castVal:
				try:
					return expectedType(value)
				except TypeError as e:
					log.warning(f'Could not cast {value} to {expectedType}', exc_info=e)
			return value
		case _:
			log.warning(f'Multiple values found for {keys} in {obj}, returning first value.')
			for value in (k for key in keys if isinstance(k := getter(obj, key, Unset), expectedType) or (castVal and k is not Unset)):
				if castVal:
					return expectedType(value)
				return value


class DotDict(dict):

	def __init__(self, *args, **kwargs):
		args = list(args)
		self.parent = kwargs.get('parent', Unset)
		self.key = kwargs.get('key', Unset)
		dicts = [args.pop(i) for i, item in enumerate(list(args)) if isinstance(item, dict)]
		super(DotDict, self).__init__(*args, **kwargs)
		for d in dicts:
			self.update(d)

	@property
	def key(self):
		if self.parent is not Unset:
			return '.'.join([self.parent.key, self.__key])
		return self.__key or ':'

	@key.setter
	def key(self, value):
		value = self.makeKey(value)
		if self.parent:
			parentKey = self.parent.key
		else:
			parentKey = ()
		if len(value) > 1 and value[:-1] == parentKey:
			value = value[-1]
		self.__key = value

	@staticmethod
	@lru_cache(maxsize=1024)
	def makeKey(key: str) -> tuple:
		if isinstance(key, tuple):
			return key
		elif not isinstance(key, str) and isinstance(key, Hashable):
			return key,
		return tuple(re.findall(rf"[\w|\-|\_]+", key), )

	def __setitem__(self, key, value):
		key = self.makeKey(key)
		if len(key) == 1:
			dict.__setitem__(self, key[0], value)
		else:
			if key[0] not in self:
				self[key[0]] = DotDict(key=key[0], parent=self)
			dict.__getitem__(self, key[0]).__setitem__(key[1:], value)

	def __contains__(self, key):
		key = self.makeKey(key)
		if len(key) == 1:
			return dict.__contains__(self, key[0])
		else:
			if key[0] not in self:
				return False
			return dict.__getitem__(self, key[0]).__contains__(key[1:])

	def popValue(self):
		return self.popitem()[1]

	def __getitem__(self, item):
		key = self.makeKey(item)
		if len(key) == 1:
			return dict.__getitem__(self, key[0])
		else:
			if key[0] not in self:
				raise KeyError(key)
			return dict.__getitem__(self, key[0]).__getitem__(key[1:])

	def get(self, key, default: Any = UnsetKwarg):
		key = self.makeKey(key)
		if key in self:
			return self[key]
		else:
			if default is UnsetKwarg:
				raise KeyError
			return default

	def update(self, data: dict):
		for key, value in data.items():
			self[key] = value


def recursiveRemove(existingDict: dict, subtracting: dict) -> dict:
	for key, subtractingValue in subtracting.items():
		existing = existingDict.get(key, None)
		if existing is None:
			continue
		if isinstance(subtractingValue, dict):
			if isinstance(existing, dict):
				if existing == subtractingValue:
					existingDict.pop(key)
				else:
					existingDict[key] = recursiveRemove(existingDict.get(key, {}), subtractingValue)
					if not existingDict[key]:
						existingDict.pop(key)
			elif subtractingValue:
				existingDict[key] = subtractingValue
			else:
				existingDict.pop(key, None)
			continue
		if existing == subtractingValue:
			existingDict.pop(key, None)
	return existingDict


def remove_empty_dicts(d: dict) -> dict:
	return {k: remove_empty_dicts(v) if isinstance(v, dict) else v for k, v in d.items() if v != {}}


class DeepChainMap(ChainMap):
	"""A recursive subclass of ChainMap"""

	def __init__(self, *maps: Mapping, origin: Any = None, origin_map: Mapping = None):
		self._originMap = origin_map or {}
		self.origin = origin
		super().__init__(self._originMap, *maps)

	def __getitem__(self, key):
		submaps = [mapping for mapping in self.maps if key in mapping]
		if not submaps:
			return self.__missing__(key)
		if isinstance(submaps[0][key], Mapping):
			return DeepChainMap(*(submap[key] for submap in submaps))
		return super().__getitem__(key)

	def to_dict(self, d: dict | Mapping = None) -> dict:
		d = d or {}
		for mapping in reversed(self.maps):
			if type(mapping) is not dict:
				mapping = dict(mapping)
			self._depth_first_update(d, mapping)
		return d

	def _depth_first_update(self, target: dict, source: Mapping) -> None:
		if isinstance(source, DeepChainMap):
			source = source.to_dict()
		for key, src_val in source.items():
			if not isinstance(src_val, Mapping):
				target[key] = src_val
				continue
			if key not in target:
				target[key] = {}
			target_val = target.get(key, {})
			if isinstance(target_val, Mapping):
				self._depth_first_update(target_val, src_val)
			else:
				target[key] = src_val

	@property
	def originMap(self) -> dict:
		return self._originMap

	def new_child(self, origin: Any = None, child_map: Mapping = None) -> 'DeepChainMap':
		return self.__class__(*self.maps, origin=origin, origin_map=child_map)


def sortDict(d: dict, reverse: bool = False) -> dict:
	return {key: value for key, value in sorted(d.items(), key=lambda x: x[0], reverse=reverse)}



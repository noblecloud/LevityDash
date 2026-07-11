"""Qt-aware facade over statekit.

statekit.Stateful/StateProperty/StatefulMetaclass are pure Python (no Qt).
Every real consumer class in LevityDash (Panel, Gauge, Text, ...) mixes
Stateful in alongside QGraphicsObject/QObject, which needs a metaclass
compatible with both statekit's StatefulMetaclass and Shiboken's
QObjectType. This module builds that composition once and re-exports every
symbol consumers already import from here, so no consumer file needed to
change when Stateful/StateProperty moved into statekit.

Domain-specific concerns that don't belong in a Qt-independent package stay
here too: SharedOption (a concrete tagged Stateful subclass) below.
"""
from typing import Any, ClassVar, TypeVar

from abc import abstractmethod
from PySide6.QtCore import QObject

import statekit
from statekit import DefaultFalse, DefaultGroup, DefaultTrue, SourceType, StatefulDumper, StatefulLoader, StatefulMixin
from statekit import StateProperty
from qolkit import Unset

QObjectType = type(QObject)


class StatefulMetaclass(statekit.StatefulMetaclass, QObjectType):
	"""statekit's pure StatefulMetaclass composed with Shiboken's QObjectType.

	Verified in isolation before this landed: a pure type-based metaclass
	composed with QObjectType produces a valid MRO, real Qt signal/slot
	behavior works through it, and subclassing (what every Panel/Gauge/etc
	actually does) works too.
	"""
	pass


class Stateful(statekit.Stateful, metaclass=StatefulMetaclass):
	"""The Qt-compatible Stateful all LevityDash UI classes inherit from.

	Adds nothing over statekit.Stateful except the metaclass - no QObject
	base needed here (today's classes get QObject-ness from QGraphicsObject/
	QObject in their own bases; this only needs a compatible metaclass).
	"""
	pass



OptionType = TypeVar('OptionType')


class SharedOption(Stateful, tag='SharedOption'):
	key: ClassVar[str]
	value: OptionType = None

	def __init_subclass__(cls):
		super().__init_subclass__()
		key = cls.__name__.replace('Shared', '')
		cls.key = key
		cls.__tag__ = f"Shared{key.title()}"
		cls.__loader__.add_constructor(f"{cls.__tag__}", cls.loader)

	# if optionType is not Unset:
	# 	cls.__annotations__['value'] = optionType

	@classmethod
	def loader(cls, loader: StatefulLoader, data):
		data = loader.construct_mapping(data)
		return cls(**data)

	def __init__(self, value: OptionType = Unset, default: Any = Unset):
		self.value = value
		self.default = default
		super().__init__()

	@StateProperty(default=Unset)
	def value(self) -> OptionType:
		return self._value

	@value.setter
	def value(self, value: OptionType):
		changed = value != self._value
		self._value = value
		if changed:
			self.valueChanged()

	@abstractmethod
	def valueChanged(self):
		pass

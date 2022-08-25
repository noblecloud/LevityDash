from functools import cached_property
from typing import TypeVar, ClassVar, Dict, Type, Any, Tuple, Callable, Union, List

import numpy as np
from PySide2.QtCore import QPoint, QPointF
from PySide2.QtGui import QLinearGradient

from yaml import SafeDumper

from LevityDash.lib.stateful import StateProperty
from LevityDash.lib.utils import getOrSet
from .color import Color

GradientValueType = TypeVar('GradientValueType')


class MappedGradientValue:
	__slots__ = ('__color', '__value')
	__types__: ClassVar[Dict[Type, Type]] = {}
	__item__: ClassVar[Type]
	value: GradientValueType
	color: Color

	def __class_getitem__(cls, item):
		if isinstance(item, TypeVar):
			return cls
		if not isinstance(item, type):
			item = type(item)
		if item not in cls.__types__:
			t = type(f'MappedGradientValue[{item.__name__}]', (cls,), {'__annotations__': {'value': item}, '__item__': item})
			cls.__types__[item] = t
		return cls.__types__[item]

	def __init__(self, value: Any, color: Color | str | Tuple[int | float]):
		self.value = value
		self.color = color if isinstance(color, Color) else Color(color)

	@property
	def color(self):
		return self.__color

	@color.setter
	def color(self, value):
		self.__color = value

	@property
	def value(self):
		return self.__value

	@value.setter
	def value(self, value):
		if not isinstance(value, self.expectedType):
			value = self.expectedType(value)
		self.__value = value

	@property
	def expectedType(self) -> Type | Callable:
		t = self.__class__.__item__
		if not issubclass(t, TypeVar):
			return t
		return lambda x: x

	@expectedType.setter
	def expectedType(self, value):
		self.__class__.__item__ = value

	@classmethod
	def representer(cls, dumper: SafeDumper, data):
		value = float(data.value)
		if value.is_integer():
			value = int(value)
		return dumper.represent_mapping(cls.__name__, {'value': value, 'colors': data.color})


class Gradient(dict[str, MappedGradientValue[GradientValueType]]):
	__types__: ClassVar[Dict[Type, Type]] = {}
	__presets__: ClassVar[Dict[str, 'Gradient']] = {}
	__item__: ClassVar[Type]

	class QtGradient(QLinearGradient):
		def __init__(self, plot: 'Plot', values):
			self.plot = plot
			self.values = values
			super().__init__(0, 0, 0, 1)
			self.__genGradient()

		def __genGradient(self):
			T = self.localized
			locations = (T - T.min())/T.ptp()
			for position, value in zip(locations, self.values):
				self.setColorAt(position, value.color.QColor)

		@cached_property
		def localized(self):
			try:
				unitType = self.plot.data.dataType
				values = [unitType(t.value) for t in self.values.list]
			except Exception:
				values = [t.value for t in self.values.list]
			return np.array(values)

		@property
		def gradientPoints(self) -> Tuple[QPoint, QPoint]:
			T = (self.localized - self.plot.data.data[1].min())/(self.plot.data.data[1].ptp() or 1)
			t = self.plot.data.combinedTransform*self.plot.scene().view.transform()
			bottom = QPointF(0, T.max())
			top = QPointF(0, T.min())
			top = t.map(top)
			bottom = t.map(bottom)
			return top, bottom

		def update(self):
			start, stop = self.gradientPoints
			self.setStart(start)
			self.setFinalStop(stop)

		def __str__(self):
			return self.__class__.__name__

	def __class_getitem__(cls, item) -> Union['Gradient', Type['Gradient']]:
		if isinstance(item, type):
			if not item in cls.__types__:
				t = type(f'Gradient[{item.__name__}]', (Gradient,), {'__item__': MappedGradientValue[item]})
				cls.__types__[item] = t
			return cls.__types__[item]
		if isinstance(item, str) and item in cls.__presets__:
			return cls.__presets__[item]

	def __new__(cls, name: str = None, *args, **kwargs):
		if name is not None:
			if name not in cls.__presets__:
				cls.__presets__[name] = super().__new__(cls, *args, **kwargs)
				cls.__presets__[name].presetName = name
			return cls.__presets__[name]
		return super().__new__(cls, *args, **kwargs)

	def __init__(self, name: str = None, *color, **colors: Tuple[int | float, Color | str | Tuple[int | float]]):
		super().__init__()
		itemType = self.itemCls()
		for key, item in colors.items():
			self[key] = itemType(*item)
		for color in color:
			match color:
				case int(p) | float(p), Color(c) | str(c) | tuple(c):
					self[str(c)] = itemType(p, c)
				case _:
					raise TypeError(f'{color} is not a valid colors')

	@StateProperty(unwrap=True)
	def data(self) -> Dict:
		return self

	@classmethod
	def itemCls(cls) -> GradientValueType:
		if hasattr(cls, '__item__'):
			return cls.__item__
		return Any

	@classmethod
	def presets(cls) -> List[str]:
		return list(cls.__presets__.keys())

	@property
	def list(self) -> List[MappedGradientValue[GradientValueType]]:
		return sorted(list(self.values()), key=lambda x: x.value, reverse=False)

	@property
	def min(self) -> int | float:
		return min(self, key=lambda x: x.value)

	@property
	def max(self) -> int | float:
		return max(self, key=lambda x: x.value)

	def __iter__(self):
		return iter(self.list)

	def __get__(self, instance, owner):
		from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import Plot
		if isinstance(instance, Plot):
			return self.toQGradient(instance)
		return self

	@property
	def valueRange(self):
		return self.max - self.min

	def toQGradient(self, plot: 'Plot') -> QtGradient:
		gradients = getOrSet(self.__dict__, '__QtGradients__', {})
		if plot not in gradients:
			gradients[plot] = self.QtGradient(plot, self)
		return gradients[plot]

	@classmethod
	def representer(cls, dumper: SafeDumper, data):
		if name := getattr(data, 'presetName', None):
			return dumper.represent_scalar(u'tag:yaml.org,2002:str', name)
		return dumper.represent_mapping(cls.__name__, {k: v.value for k, v in data.items()})


__all__ = ('Gradient', 'MappedGradientValue')

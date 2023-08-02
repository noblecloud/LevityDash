import numpy as np
from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QLinearGradient, QConicalGradient, QPainter, Qt
from difflib import get_close_matches
from functools import cached_property, lru_cache
from numbers import Number
from rich.repr import auto as auto_repr
from typing import TypeVar, ClassVar, Dict, Type, Tuple, Callable, Union, List, runtime_checkable, Protocol
from yaml import SafeDumper, SafeLoader, SequenceNode, MappingNode, ScalarNode

from LevityDash.lib.stateful import StatefulLoader
from LevityDash.lib.ui.colors.color import Color
from LevityDash.lib.utils import getOrSet
from LevityDash.shims.Qt import QImage
from WeatherUnits import Measurement, Percentage

GradientValueType = TypeVar('GradientValueType', bound=Number)


@runtime_checkable
class SupportsMath(Protocol):
	def __add__(self, other) -> 'SupportsMath': ...
	def __sub__(self, other) -> 'SupportsMath': ...
	def __mul__(self, other) -> 'SupportsMath': ...
	def __truediv__(self, other) -> 'SupportsMath': ...


@auto_repr
class MappedGradientValue:
	__slots__ = ('__color', '__value')
	__types__: ClassVar[Dict[Type, Type]] = {}
	__item__: ClassVar[Type] = GradientValueType

	__value: GradientValueType
	value: GradientValueType

	__color: Color
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

	def __init__(self, value: Number, color: Color | str | Tuple[int | float]):
		self.value = value
		self.color = color if isinstance(color, Color) else Color(color)

	def __rich_repr__(self):
		yield 'value', str(self.value)
		yield 'color', self.color

	def __hash__(self) -> int:
		return hash((self.value, self.color, self.expectedType))

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
	__item__: ClassVar[Type] = MappedGradientValue[float]

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
				values = [unitType(t.value) for t in self.values.as_list]
			except Exception:
				values = [t.value for t in self.values.as_list]
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

	def __hash__(self) -> int:
		return hash(tuple(self.keys()))

	def __init__(
		self,
		name: str = None,
		*color,
		colors: dict[GradientValueType, Color | str | Tuple[int | float | GradientValueType]] = None,
		**kwargs: dict[str, Color | str | Tuple[int | float | GradientValueType]]
	):
		super().__init__()

		itemType = type(self).itemCls

		try:
			value_type = itemType.__item__
		except AttributeError:
			value_type = float

		colors = colors or {}

		if len(kwargs) > 0:
			colors = {**colors, **kwargs}

		for key, item in colors.items():
			if isinstance(key, Number):
				if not isinstance(key, value_type):
					key = value_type(key)
				self[str(key)] = itemType(key, item)
			elif isinstance(key, str) and isinstance(item, (tuple, list)) and len(item) == 2:
				value, color = item
				self[key] = itemType(value, color)

		for color in color:
			match color:
				case (Number() as p, Color() as c):
					self[str(c)] = itemType(p, c)
				case (Number() as p,  str() | tuple() as c):
					c = Color(c)
					self[str(c)] = itemType(p, c)

	def as_type(self, type_: Type[Measurement], _min: Measurement, _max: Measurement) -> 'Gradient':
		cls = Gradient[type_]
		own_min = float(self.min.value)
		own_max = float(self.max.value)
		own_range = own_max - own_min

		own_normalized_values = {(float(item.value) - own_min) / own_range: item.color for item in self.values()}

		other_min = float(_min)
		other_max = float(_max)
		other_range = other_max - other_min

		new_values_from_normals = dict((type_(other_min + (other_range * k)), v) for k, v in own_normalized_values.items())

		return cls(colors=new_values_from_normals)

	@classmethod
	@property
	def itemCls(cls) -> Type[MappedGradientValue]:
		if hasattr(cls, '__item__'):
			return cls.__item__
		return MappedGradientValue[float]

	@classmethod
	def presets(cls) -> List[str]:
		return list(cls.__presets__.keys())

	@property
	def as_list(self) -> List[MappedGradientValue[GradientValueType]]:
		return sorted(list(self.values()), key=lambda x: x.value, reverse=False)

	@property
	def min(self) -> int | float:
		return min(self, key=lambda x: x.value)

	@property
	def max(self) -> int | float:
		return max(self, key=lambda x: x.value)

	def __iter__(self):
		return iter(self.as_list)

	def __get__(self, instance, owner):
		from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import Plot
		if isinstance(instance, Plot):
			return self.toQGradient(instance)
		return self

	@property
	def valueRange(self) -> GradientValueType:
		return self.max.value - self.min.value

	def toQGradient(self, plot: 'Plot') -> QtGradient:
		gradients = getOrSet(self.__dict__, '__QtGradients__', {})
		if plot not in gradients:
			gradients[plot] = self.QtGradient(plot, self)
		return gradients[plot]

	def gen_gradient_image(self, step_size: float = 0.1) -> QImage:
		value_range = self.valueRange
		min_value = self.min.value
		if isinstance(value_range, Percentage):
			step_size /= 100
		width = int(value_range / step_size) + 2
		height = 1
		image = QImage(width, height, QImage.Format.Format_ARGB32)
		image.fill(Qt.transparent)
		painter = QPainter(image)
		gradient = QLinearGradient(QPoint(0, 0), QPoint(width, 0))
		for point in self.as_list:
			color = point.color.QColor
			value = float(point.value)
			normalized_value = float(value - min_value) / float(value_range)
			gradient.setColorAt(normalized_value, color)
		painter.fillRect(image.rect(), gradient)
		painter.end()
		return image

	@lru_cache(maxsize=512)
	def get_color_for_value(self, value: GradientValueType) -> Color:
		map = self.map
		pixel_pos = round((float(value) - float(self.min.value)) / float(self.valueRange) * float(map.width()))
		pixel_pos = max(0, min(pixel_pos, map.width()-1))
		color = Color(map.pixelColor(pixel_pos, 0))
		return color

	@cached_property
	def map(self) -> QImage:
		return self.gen_gradient_image()

	def toQConicalGradient(
		self,
		start_angle: float = 0,
		stop_angle: float = 360,
		min_value: float = None,
		max_value: float = None,
	) -> QConicalGradient:
		"""
		Converts the gradient to a QConicalGradient object.
		Args:
			start_angle (float): The starting angle of the gradient.
			stop_angle (float): The stopping angle of the gradient.
			min_value (float): The minimum value of the gradient.
			max_value (float): The maximum value of the gradient.
		Returns:
			QConicalGradient: The converted QConicalGradient object.
		"""
		gradient = QConicalGradient()

		inverted = float(start_angle) > float(stop_angle)
		modifier = (lambda x: x) if inverted else (lambda x: 1-x)

		min_angle, max_angle = sorted((start_angle, stop_angle))

		full_angle = stop_angle - start_angle
		mean_angle = min_angle + (full_angle / 2) * (1 if not inverted else -1)

		# Sets the starting angle of the gradient to the between the start and stop angle
		gradient.setAngle(-90 + -mean_angle)

		own_value_cls = type(self.min.value)

		# if no min or max value is provided, use the min and max values of the gradient
		own_min_value = self.min.value
		if min_value is None:
			min_value = own_min_value
		if not isinstance(min_value, own_value_cls):
			min_value = own_value_cls(min_value)

		own_max_value = self.max.value
		if max_value is None:
			max_value = own_max_value
		if not isinstance(max_value, own_value_cls):
			max_value = own_value_cls(max_value)

		stops = self.as_list

		if min_value != own_min_value:
			stops.append(self.itemCls(min_value, self.get_color_for_value(min_value)))
		if max_value != own_max_value:
			stops.append(self.itemCls(max_value, self.get_color_for_value(max_value)))

		stops.sort(key=lambda x: x.value)
		values = np.array([float(point.value) for point in stops])

		value_range = max_value - min_value

		angle_scalar = float(abs(full_angle) / 360)

		# Normalize the values to the new range of the gradient
		normalized_values = (values - min_value) / value_range

		# insure the values start at 0
		normalized_values = normalized_values - (m_offset := normalized_values.min())

		# scale the values to the full angle relative to a full circle
		normalized_values = normalized_values * angle_scalar

		# add the offset back to the values
		normalized_values = normalized_values + (m_offset * angle_scalar)

		# offset the values by half of the remaining angle
		normalized_values = normalized_values + ((360 - abs(full_angle)) / 2 / 360)

		# Add all the stops that are between 0.0 and 1.0 to the gradient
		for point, item in zip(normalized_values, stops):
			if 0 <= round(point, 6) <= 1:
				gradient.setColorAt(modifier(point), item.color.QColor)

		# if there are stops outside the range of the gradient, add stops at the edge of the gradient
		value_per_degree = float(value_range / abs(full_angle))
		padding = (360 - abs(full_angle)) / 2

		if max_value < own_max_value and normalized_values.max() > 1:
			gradient.setColorAt(
				modifier(1),
				self.get_color_for_value(max_value + padding * value_per_degree).QColor
			)

		if min_value > own_min_value and normalized_values.min() < 0:
			gradient.setColorAt(
				modifier(0),
				self.get_color_for_value(min_value - padding * value_per_degree).QColor
			)

		return gradient

	@cached_property
	def stops(self) -> Tuple[GradientValueType]:
		return sorted(list(self.values()), key=lambda x: x.value, reverse=False)

	@classmethod
	def representer(cls, dumper: SafeDumper, data):
		if name := getattr(data, 'presetName', None):
			return dumper.represent_scalar(u'tag:yaml.org,2002:str', name)
		return dumper.represent_mapping(cls.__name__, {k: v.value for k, v in data.items()})

	@classmethod
	def constructor(cls, loader: SafeLoader, node):
		match node:
			case MappingNode():
				data = loader.construct_mapping(node)
				return cls(colors=data)
			case SequenceNode():
				data = loader.construct_sequence(node)
				return cls(*data)
			case ScalarNode():
				if (preset := cls.__presets__.get(loader.construct_scalar(node), None)) is not None:
					return preset
				return cls.__presets__['RainbowDefault']
			case _:
				raise NotImplementedError

	@classmethod
	def decode(cls, data: str | dict | list | tuple) -> 'Gradient':
		match data:
			case {'name': name, **rest}:
				return cls(name=name, colors=rest)
			case dict():
				return cls(colors=data)
			case [str(name), *rest]:
				return cls(name=name, *rest)
			case [*colors]:
				return cls(*colors)
			case str(name):
				if (preset := cls.__presets__.get(name, None)) is not None:
					return preset
				return cls.__presets__.get(next(iter(get_close_matches(name, cls.__presets__.keys(), n=1)), 'RainbowDefault'))
			case _:
				raise NotImplementedError


StatefulLoader.add_constructor('!gradient', Gradient.constructor)

__all__ = ('Gradient', 'MappedGradientValue')

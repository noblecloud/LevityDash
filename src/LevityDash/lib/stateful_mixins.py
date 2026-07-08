from PySide6.QtGui import QGradient, QBrush
from abc import abstractmethod
from numbers import Number
from typing import TypeVar

from LevityDash.lib.stateful import StateProperty, StatefulMixin
from LevityDash.lib.ui import Color, Gradient
from LevityDash.lib.utils import defer

Brush = TypeVar('Brush')

"""
Mixins for to support stateful properties in LevityDash. 
"""


class FillBrushMixin(StatefulMixin):
	"""
	A mixin class for items that have a fill brush.
	The fill brush can be a color, gradient, pattern or any other type of brush that would be used to fill the item.

	Subclasses must implement the `_set_fill_brush` method for this mixin to work.
	This method is responsible for setting the appearance of the item's fill paintbrush,
	which can be modified by multiple state properties in subclasses.

	Properties
	----------
	fill_brush : Brush
		The fill brush for the item

	Abstract Methods
	----------------
	_set_fill_brush(brush: Brush)
		Sets the appearance of the item's fill paintbrush using the provided brush.

	Notes
	-----
	- The fill_brush property can be overloaded by subclasses or submixins to change how the fill is determined.
		For example, the subclass `ColorGradientMixin` overloads it to give priority to the gradient.

	"""

	@defer
	def _update_appearance(self) -> None:
		"""
		This method is called after the brush is changed.  It is a protected method
		that should never be overridden to ensure the call is deferred unless you
		are absolutely sure you know what you are doing.
		"""
		self._set_fill_brush(self.fill_brush)

	@property
	@abstractmethod
	def fill_brush(self) -> Brush:
		"""
		Returns
		-------
		Brush
		"""
		raise NotImplementedError('Subclasses must implement fill_brush')

	@abstractmethod
	def _set_fill_brush(self, brush: Brush):
		"""
		Sets the appearance of the item's fill paintbrush using the provided brush.

		Since the actual application of the brush cannot be assumed, this method must remain an abstract method when it
		is overloaded by a submixin.

		This method should be overridden by subclasses to customize how the fill brush is set.
		The brush type hint should be changed to the appropriate type for the subclass.

		Parameters
		----------
		brush : Brush
			The brush to set as the fill paintbrush for the item.
		"""
		raise NotImplementedError("Subclasses must implement _set_fill_brush(brush: Brush)")


class ColorMixin(FillBrushMixin):
	"""
	A mixin that adds a color StateProperty to a Stateful class.

	This mixin expects its Brush type to be QBrush since currently only PySide6/Qt6 is supported in LevityDash.
	A super class will need to be created to support other UI frameworks,
	and this mixin will need to be renamed to something like `QtColorMixin` or `QColorMixin`.

	State Properties
	----------------
	color : Color
		The color of the item

	Note
	----
	The fill_brush property can be overloaded by subclasses or submixins to change how the fill is determined.
	For example, the subclass `ColorGradientMixin` overloads it to give priority to the gradient.

	"""

	@StateProperty(key='color', default=Color.default, allowNone=False, after=FillBrushMixin._update_appearance, decode=Color.decode)
	def color(self) -> Color:
		"""
		Color to use for the item's fill brush

		Valid values
		------------
		- Hexadecimal color codes (with or without the leading '#')
		- Comma-separated RGB[A] values
		- Web Color names (case-insensitive)

		Example Config
		--------------

		```yaml
		color: '#ff0000'
		color: white
		color: 255, 0, 0
		```

		Returns
		-------
		Color
		"""

		return self._color

	@color.setter
	def color(self, value: Color):
		self._color = value

	@property
	def fill_brush(self) -> QBrush:
		return QBrush(self.color.QColor)

	@abstractmethod
	def _set_fill_brush(self, brush: QBrush):
		raise NotImplementedError('Subclasses must implement _set_fill_brush(brush: QBrush)')


class ColorGradientMixin(ColorMixin):
	"""
	A mixin class for items that have a color and/or gradient.

	This mixin provides a `color` property and a `gradient` property that can be used to set the color and/or gradient
	of an item. The `color` property is a solid color, while the `gradient` property is a gradient that can be mapped
	to a QGradient relative to the item's position and size.

	Subclasses must implement either the `_get_color_value` method or the `_map_gradient` method. If `_get_color_value`
	is implemented, the item's color will be solid and not a gradient. If `_map_gradient` is implemented, the item's
	color will be a gradient.

	State Properties
	----------------
	gradient: Gradient | None
		The gradient of the item.

	Properties
	----------
	fill_brush : QBrush
		The fill brush for the item (either a color or gradient) determined by the `color` and `gradient` properties,
		with the gradient taking priority.

	Abstract Methods
	----------------
	_get_color_value() -> Number
		Used to get the value that determines a single color from the gradient to use for the item's color.
	_map_gradient(gradient: Gradient) -> QGradient
		Used to map the gradient to a QGradient relative to the item.
	"""

	@StateProperty(key='gradient', default=None, after=ColorMixin.color, decoder=Gradient.decode)
	def gradient(self) -> Gradient | None:
		return getattr(self, '_gradient', None)

	@gradient.setter
	def gradient(self, value: Gradient | None):
		self._gradient = value

	def __init_subclass__(cls, **kwargs):
		super().__init_subclass__(**kwargs)
		cls_map_grad = cls._map_gradient
		cls_get_val = cls._get_color_value
		abstract_grad = getattr(cls_map_grad, '__isabstractmethod__', False)
		abstract_val = getattr(cls_get_val, '__isabstractmethod__', False)
		if abstract_grad and abstract_val:
			if cls.fill_brush is not ColorGradientMixin.fill_brush:
				# TODO: insert logic to varify the signature of the method
				pass
			else:
				raise TypeError(f"Class '{cls.__name__}' must override either '_get_color_value' or '_map_gradient'")

	@abstractmethod
	def _get_color_value(self) -> Number:
		"""
		Get the value used to determine a single color from the gradient
		to use for the item's color.

		When this method is overridden and a gradient is provided, the
		color will be determined by the color value on the gradient
		associated with the value returned by this method.

		Using this method, the item's color will be solid and not a gradient.

		Returns
		-------
		Number
		"""
		raise NotImplementedError('Mixin must implement _get_color_value() or _map_gradient()')

	@abstractmethod
	def _map_gradient(self, gradient) -> QGradient:
		"""
		Map a gradient to a QGradient relative to the item.

		When this method is overridden and a gradient is provided, the gradient
		will be mapped to a QGradient relative to the item's position and size.

		Using this method, the item's color will be a gradient.

		Returns
		-------
		QGradient
		"""
		raise NotImplementedError('Mixin must implement _get_color_value() or _map_gradient()')

	@abstractmethod
	def _set_fill_brush(self, color: Brush):
		"""{insert appropriate docstring}"""
		raise NotImplementedError('Mixin must implement _set_fill_brush()')

	@property
	def fill_brush(self) -> Brush:
		"""{insert appropriate docstring}"""
		if (gradient := self.gradient) is not None:
			# Try to map the gradient to a QGradient
			try:
				return QBrush(self._map_gradient(gradient))
			except NotImplementedError:
				pass
			# Try to get the color value from the gradient
			try:
				return QBrush(gradient.get_color_for_value(self._get_color_value()).QColor)
			except NotImplementedError:
				raise NotImplementedError('Mixin must implement _get_color_for_value() or _map_gradient()')
		return super().fill_brush

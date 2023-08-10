from PySide6.QtGui import QGradient, QBrush
from abc import abstractmethod
from numbers import Number
from typing import TypeVar

from LevityDash.lib.stateful import StateProperty, StatefulMixin
from LevityDash.lib.ui import Color, Gradient
from LevityDash.lib.utils import defer

Brush = TypeVar('Brush')


class ColorMixin(StatefulMixin):
	"""
	A mixin class for items that have a color.

	This mixin provides a `color` property that can be used to set the color of an item.

	Subclasses must implement the `_set_color` method to set the item's color.

	Attributes
	----------
	color : Color
			The color of the item.

	Methods
	-------
	_set_color(color: Color)
			Set the color of the item.
	"""

	@defer
	def __update_color(self) -> None:
		"""
		This method is called after the color is changed.  It is a protected method
		that should never be overridden to ensure the call is deferred.

		Returns
		-------
		Color
		"""
		self._set_fill_brush(self.fill_brush)

	@StateProperty(key='color', default=Color.default, allowNone=False, after=__update_color, decode=Color.decode)
	def color(self) -> Color:
		"""
		The color of the item.

		Returns
		-------
		Color
				The color value.
		"""
		return self._color

	@color.setter
	def color(self, value: Color):
		self._color = value

	@property
	def fill_brush(self) -> Brush:
		return QBrush(self.color.QColor)

	@abstractmethod
	def _set_fill_brush(self, brush: Brush):
		"""
		This method should be overridden to fit the needs of how the subclass sets its
		fill brush.

		Parameters
		----------
		brush : QBrush
				The color to set.
		"""
		raise NotImplementedError('Mixin must implement _set_fill_brush()')


class ColorGradientMixin(ColorMixin):
	"""
	A mixin class for items that have a color and/or gradient.

	This mixin provides a `color` property and a `gradient` property that can be used to set the color and/or gradient
	of an item. The `color` property is a solid color, while the `gradient` property is a gradient that can be mapped
	to a QGradient relative to the item's position and size.

	Subclasses must implement either the `_get_color_value` method or the `_map_gradient` method. If `_get_color_value`
	is implemented, the item's color will be solid and not a gradient. If `_map_gradient` is implemented, the item's
	color will be a gradient.

	Attributes
	----------
	color : Color
		The color of the item.
	gradient : Gradient | None
		The gradient of the item.

	Methods
	-------
	_get_color_value() -> Number
		Get the value used to determine a single color from the gradient to use for the item's color.
	_map_gradient(gradient: Gradient) -> QGradient
		Map a gradient to a QGradient relative to the item.
	_set_color(color: Color)
		Set the color of the item.
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
		"""
		Set the color of the item.

		This method is called after the color is updated and must
		be overridden to set the color of the item.

		Parameters
		----------
		color : Color
		"""
		raise NotImplementedError('Mixin must implement _set_fill_brush()')

	@property
	def fill_brush(self) -> Brush:
		if (gradient := self.gradient) is not None:
			try:
				return QBrush(self._map_gradient(gradient))
			except NotImplementedError:
				pass
			try:
				return QBrush(gradient.get_color_for_value(self._get_color_value()).QColor)
			except NotImplementedError:
				raise NotImplementedError('Mixin must implement _get_color_for_value() or _map_gradient()')
		return super().fill_brush

"""The things a meter is made of, minus anything that only works on a dial.

A meter holds *items*: the track, its ticks, the needle or pointer that reads the
value, the fill that trails it, the text around it. These are the bases those
items share - the reference back to the meter they belong to, and the stateful and
path-item flavours of it - plus the value type variable the tick machinery is
generic over.

`Gauge.py` imports everything here and re-exports it, so nothing outside this
package has to know the split. The direction is one way: this module never
imports a display class at import time. Where it must name `Gauge` - to recognise
it in the arguments an item is constructed with - it imports it inside the call,
because a gauge imports this module.
"""
from functools import cached_property
from typing import TYPE_CHECKING, Optional, Union

from PySide6.QtGui import QPainterPath
from PySide6.QtWidgets import QGraphicsPathItem

from LevityDash.lib.stateful import Stateful
from LevityDash.lib.ui import Color
from LevityDash.lib.utils.shared import get, guarded_cached_property

from .scale import GaugeValue, Numeric

if TYPE_CHECKING:  # the real import would be a cycle; see `gauge_class`
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Gauge import Gauge

__all__ = ['GaugeItem', 'GaugePathItem', 'GaugeValue', 'Numeric', 'StatefulGaugeItem', 'StatefulGaugePathItem']


def gauge_class():
	"""The `Gauge` class, imported when it is needed rather than at import time.

	`Gauge.py` imports this module, so importing it back at module level would be
	a cycle. The class here is the one an item recognises its owner by.
	"""
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Gauge import Gauge
	return Gauge


class GaugeItem:
	"""
	Base class for all gauge items.  This class provides a reference to the gauge that the item belongs to
	and will raise a ValueError if no gauge is provided.
	"""

	_gauge: 'Gauge'

	def __extract_gauge(self, args, kwargs):
		gauge = get(kwargs, 'gauge' 'parent', default=None, expectedType=gauge_class())
		if gauge is None:
			gauge = next((arg for arg in args if isinstance(arg, gauge_class())), None)
		if gauge is None:
			gauge = next((kwarg for kwarg in kwargs.values() if isinstance(kwarg, gauge_class())), None)
		if gauge is None:
			raise ValueError(f'No gauge provided for {self.__class__.__name__}')
		return gauge

	def __init__(self, *args, **kwargs):

		self._gauge = self.__extract_gauge(args, kwargs)

		try:
			super().__init__(*args, **kwargs)
		except TypeError:
			super().__init__()

	@property
	def gauge(self) -> 'Gauge':
		return self._gauge

	def remove(self):
		self.gauge.scene().removeItem(self)


class StatefulGaugeItem(GaugeItem, Stateful):

	def __init__(self, *args, **kwargs):
		super(StatefulGaugeItem, self).__init__(*args, **kwargs)
		self.prep_init(args=args, kwargs=kwargs, stateful_parent=self.gauge)


class GaugePathItem(GaugeItem, QGraphicsPathItem):

	_weight_scale: float = 1.0
	_shape: QPainterPath = QPainterPath()

	def __init__(self, *args, **kwargs):
		super(GaugePathItem, self).__init__(*args, **kwargs)
		self.setPen(self.gauge.pen)

	def _set_color(self, color: Color):
		self.setBrush(color.QColor)

	@guarded_cached_property(guardFunc=lambda x: x is not None, default=None)
	def gauge(self) -> 'Gauge':
		try:
			return self._gauge
		except AttributeError:
			pass

		parent = self.parentItem()
		while not isinstance(parent, gauge_class()):
			try:
				parent = parent.parentItem()
			except AttributeError:
				return None
		return parent


class StatefulGaugePathItem(Stateful, GaugePathItem):

	def __init__(self, *args, **kwargs):
		super(StatefulGaugePathItem, self).__init__(*args, **kwargs)
		self.prep_init(args=args, kwargs=kwargs, stateful_parent=self.gauge)

import copy
import PySide6.QtGui
import numpy as np
from PySide6 import QtCore
from PySide6.QtCore import QPointF, QRectF, QPoint, QPropertyAnimation, QVariantAnimation, QTimer, Signal, QEasingCurve, QSizeF, Slot, QLineF, QObject
from PySide6.QtGui import (
	QFontMetricsF,
	QBrush, QFont, QPainter, QPainterPath,
	QPen, QPolygonF, QTransform, QRadialGradient, QGradient, QColor, Qt, QConicalGradient, QPainterPathStroker
)
from PySide6.QtWidgets import (
	QGraphicsItem, QGraphicsPathItem,
	QGraphicsScene, QStyleOptionGraphicsItem,
	QWidget, QGraphicsItemGroup
)
from enum import Enum
from functools import cached_property
from itertools import combinations
from math import inf, isclose,isfinite, isinf, floor, log10, atan2, hypot
from numbers import Number
from numpy import ceil, cos, pi, radians, sin, sqrt, number as np_number
from collections.abc import Mapping
from typing import Any, Optional, Type, Union, Iterator, Iterable, TypeVar, Sequence, Dict

from LevityDash import LevityDashboard
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.expressions import Expression, ExpressionError
from LevityDash.lib.valuesource import openValueSource
from LevityDash.lib.plugins.plugin import AnySource
from LevityDash.lib.stateful import Binding, Stateful, StateProperty, SourceType
from LevityDash.lib.stateful_mixins import ColorGradientMixin
from LevityDash.lib.ui import UILogger, Color, Gradient
from LevityDash.lib.ui.Geometry import RelativeFloat, parseSize, DimensionType, size_px, Dimension, Size, Alignment, \
	AlignmentFlag, DisplayPosition, parseWidth, parseX, parseY, parseHeight, UnitDisplayPosition, ValueDisplayPosition
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays import SurfaceCentered, Surface
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Annotations import AnnotationText, AnnotationLabels
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.DisplayBase import Display
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.curvetext import CurveMode, WarpSpec, arcFit, normalizeCorner, warp_path
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import NonInteractiveLabel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import Text
from LevityDash.lib.ui.frontends.PySide.Modules.Handles import Handle
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import SizeGroup
from LevityDash.lib.ui.frontends.PySide.utils import DisplayType, addCrosshair, DebugPaint, SoftShadow, outline_path, \
	modifyTransformValues, rect_to_shape, addPath
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.elements import (
	GaugeItem, GaugePathItem, GaugeTickText, GaugeTickTextGroup, Graduations, StatefulGaugeItem, StatefulGaugePathItem,
	SubTick, Tick, TickSurface, gaugeKeyName as _gaugeKeyName,
)
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.scale import (
	CLOCK_HANDS, GaugeValue, Numeric, Scale, _isWholeSteps, clockTurn, decode_measurement,
	filter_factors, formatDuration, parseClockTime, shortestDelta,
)
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.track import ArcTrack
from LevityDash.lib.utils import Axis
from LevityDash.lib.utils.data import MinMax
from LevityDash.lib.utils.shared import radialPoint, defer, factors, is_prime, Unset, clearCacheAttr, \
	INVERSE_GOLDEN_RATIO, closestStringInList, camelCase, guarded_cached_property, get, ClosestMatchEnumMeta, now
from WeatherUnits import Measurement, Angle, Wind, Humidity, auto as auto_wu, Length, Percentage

log = UILogger.getChild('Gauge')


@DebugPaint
class GaugeArc(StatefulGaugePathItem):

	_weight_scale = 0.75

	#: The arc this item strokes, in the item's own coordinates. Rebuilt by `draw`,
	#: and built on demand before that, since a tick can be drawn first.
	_track: Optional[ArcTrack] = None

	@property
	def track(self) -> ArcTrack:
		"""The dial's track: its rect and its angles, in this item's coordinates."""
		if self._track is None:
			self._track = ArcTrack(self.centered_gauge_rect, self.startAngle, self.endAngle)
		return self._track

	@property
	def safe_area(self) -> QPainterPath:
		return QPainterPath(self.shape())

	@property
	def scene_safe_area(self) -> QPainterPath:
		return self.mapToScene(self.shape())

	def __init__(self, *args, **kwargs):
		super(GaugeArc, self).__init__(*args, **kwargs)
		self.add_defaults_to_state(kwargs)
		self.state = kwargs

	def _debug_paint(self, painter: QPainter, opt, widget):
		color = QColor(Qt.GlobalColor.yellow)
		color.setAlphaF(0.5)
		addPath(painter, self.shape(), fill=color, color=QColor(Qt.GlobalColor.transparent))
		self._normal_paint(painter, opt, widget)
		# addCrosshair(painter, pos=self.path().boundingRect().center(), color=color, weight=4, size=10)

	def setPen(self, pen, *args, **kwargs):
		super(GaugeArc, self).setPen(pen, *args, **kwargs)

	@property
	def center(self):
		return self.gauge.rect().center()

	@property
	def center_offset(self) -> QPointF:
		return self._center_offset

	@property
	def centered_gauge_rect(self):
		rect = QRectF(self.gauge.gaugeRect)
		rect.moveCenter(QPoint(0, 0))
		return rect

	@defer
	def makeShape(self):
		inner_safe_radius = self.gauge.safe_radius
		outer_safe_radius = self.gauge.exterior_safe_radius

		width = outer_safe_radius - inner_safe_radius

		path = QPainterPath()
		path.setFillRule(Qt.FillRule.WindingFill)

		inner_rect = QRectF(-inner_safe_radius, -inner_safe_radius, inner_safe_radius * 2, inner_safe_radius * 2)
		radius_rect = QRectF(-outer_safe_radius, -outer_safe_radius, outer_safe_radius * 2, outer_safe_radius * 2)

		# draw the inner arc
		angle = self.startAngle
		path.arcMoveTo(inner_rect, -angle + 90)
		start_pos = path.currentPosition()
		path.arcTo(inner_rect, -angle + 90, -self.fullAngle)

		# draw a line going out from the inner arc to the outer arc
		current_pos = path.currentPosition()
		width_vector = radialPoint(QPointF(0, 0), width, self.endAngle - 90)
		path.lineTo(current_pos + width_vector)

		# draw the outer arc but in the opposite direction
		path.arcTo(radius_rect, -self.endAngle + 90, self.fullAngle)

		# draw a line going back to the inner arc
		path.lineTo(start_pos)

		path.closeSubpath()

		rect = self.parentItem().boundingRect()
		rect.moveCenter(path.boundingRect().center())
		pen = self.pen()
		path.addPath(outline_path(
			self.path(),
			weight=pen.widthF(),
			cap_style=pen.capStyle(),
			join_style=pen.joinStyle(),
			dash_pattern=pen.dashPattern()
		))
		self._shape = path

	def draw(self):
		self.resetTransform()
		self._track = ArcTrack(self.centered_gauge_rect, self.startAngle, self.endAngle)
		path = self._track.subPath(0, 1)
		self._center_offset = path.boundingRect().center()
		self.gauge.update_center_offset(self._center_offset)
		self.setPath(path)
		self.makeShape()

	def refresh(self):
		self.draw()
		self.updateAppearance()
		self.setPos(self.gauge.center)
		self.setZValue(-800)

	def updateAppearance(self):
		pen = QPen(self.gauge.pen)
		if weight := self.weight_px:
			pen.setWidthF(weight)
			pen.setCapStyle(self.capStyle)
			if (color := self.color) is not None:
				pen.setBrush(QBrush(color.QColor))
			if (gradient := self.gradient) is not None:
				brush = self.gauge.map_gradient_to(gradient, self)
				pen.setBrush(brush)
		else:
			pen.setWidthF(0)
			pen.setBrush(Qt.NoBrush)

		self.setPen(pen)
		self.makeShape()
		self.setPos(self.gauge.center)

	def shape(self):
		return self._shape

	@StateProperty(key='color', default=None, after=refresh, allowNone=True)
	def color(self) -> Color | None:
		"""Colour of the track. Defaults to the gauge colour; a dark grey gives the unfilled-track look."""
		return getattr(self, '_color', None)

	@color.setter
	def color(self, value: Color | None):
		self._color = value

	@color.decode
	def color(self, value) -> Color | None:
		return None if value is None else Color.decode(value)

	@color.encode
	def color(self, value: Color | None) -> str | None:
		return None if value is None else str(value)

	@StateProperty(key='gradient', default=None, after=refresh, decoder=Gradient.decode)
	def gradient(self) -> Gradient | None:
		return getattr(self, '_gradient', None)

	@gradient.setter
	def gradient(self, value: Gradient | None):
		self._gradient = value

	@StateProperty(key='weight', default=Size.Width(0.05, relative=True), after=refresh, allowNone=False, repr=True)
	def weight(self) -> Size.Width | Length:
		return self._weight

	@weight.setter
	def weight(self, value: Size.Width | Length):
		self._weight = value

	@weight.decode
	def weight(self, value: Size.Width | Length) -> float:
		return parseWidth(value, type(self).weight.default(type(self), self, update_source=False))

	@property
	def weight_px(self) -> float:
		return self.gauge.sizeAcross(self.weight, dimension=DimensionType.width)

	@StateProperty(key='start-angle', default=-120, after=refresh, allowNone=False, repr=True)
	def startAngle(self) -> float | int:
		return self._start_angle

	@startAngle.setter
	def startAngle(self, value: float | int):
		self._start_angle = value

	@StateProperty(key='end-angle', default=120, after=refresh, allowNone=False, repr=True)
	def endAngle(self) -> float | int:
		return self._end_angle

	@endAngle.setter
	def endAngle(self, value: float | int):
		self._end_angle = value

	@StateProperty(key='cap', default=Qt.PenCapStyle.FlatCap, after=refresh, allowNone=False)
	def capStyle(self) -> Qt.PenCapStyle:
		return self._cap_style

	@capStyle.setter
	def capStyle(self, value: Qt.PenCapStyle):
		self._cap_style = value

	@capStyle.decode
	def capStyle(value) -> Qt.PenCapStyle:
		caps: dict[str, Qt.PenCapStyle] = dict(Qt.PenCapStyle.__members__)
		capNames = list(caps.keys())
		cap = closestStringInList(value, capNames)
		return caps[cap]

	@capStyle.encode
	def capStyle(value) -> str:
		if value is None:
			return 'round'
		try:
			return camelCase(value.name.decode().strip('Cap'), titleCase=False)
		except AttributeError:
			return camelCase(value.name.strip('Cap'), titleCase=False)

	@property
	def fullAngle(self) -> float | int:
		return self.endAngle - self.startAngle

	@property
	def inverted(self) -> bool:
		"""Returns a bool of if the start angle is greater than the end angle"""
		return self.startAngle > self.endAngle


class Needle(StatefulGaugePathItem):
	_animation: QPropertyAnimation
	_animationSignal = Signal(float)

	class Type(str, Enum, metaclass=ClosestMatchEnumMeta):
		Needle = 'needle'
		Circle = 'circle'
		Triangle = 'triangle'
		Diamond = 'diamond'
		#: An arrowhead riding the arc itself rather than sweeping from the
		#: centre. The other edge shapes sit *at* the radius; this one is
		#: centred *on* the stroke, so it reads as a marker on the line.
		Marker = 'marker'
		#: A kite from the pivot to the tip, with an optional tail behind the
		#: pivot (``tail``) and a hub disc (``hub``): a barometer hand.
		Tapered = 'tapered'
		#: A shaft with an arrowhead at the rim (``point: out``, the default) or
		#: at the inner end (``point: in``). ``tail`` adds a second shaft on the
		#: opposite side and ``tail-dot`` caps it with a dot at the opposite rim:
		#: a wind-direction arrow.
		Arrow = 'arrow'
		#: A thin line from the pivot, with an optional counterweight disc
		#: (``tail-dot``) at the end of its tail (``tail``).
		Line = 'line'
		#: A knob riding the track, with an optional ``halo`` ring around it:
		#: a sun-path position.
		Dot = 'dot'
		#: A short bar across the track: a limit mark.
		Notch = 'notch'

	#: Styles drawn from the pivot, which can carry a ``hub``.
	_PIVOT_STYLES = frozenset({'needle', 'tapered', 'line'})

	_shown: Optional[float] = None
	_lastTarget: Optional[float] = None
	_anim: Optional[QVariantAnimation] = None
	_under: tuple = ()
	_over: tuple = ()

	def __init__(self, *args, **kwargs):
		super(Needle, self).__init__(*args, **kwargs)
		# self._animation = NeedleAnimation(self)
		pen = QPen()
		pen.setJoinStyle(Qt.RoundJoin)
		self.setPen(Qt.NoPen)
		self.add_defaults_to_state(kwargs)
		self.refresh()
		shadow = SoftShadow(owner=self)
		self.setGraphicsEffect(shadow)

	def draw(self):
		match self.type:
			case Needle.Type.Needle | 'needle':
				path = self._default()
			case Needle.Type.Circle | 'circle':
				path = self._edge_circle()
			case Needle.Type.Triangle | 'triangle':
				path = self._edge_triangle()
			case Needle.Type.Diamond | 'diamond':
				path = self._edge_diamond()
			case Needle.Type.Marker | 'marker':
				path = self._edge_marker()
			case Needle.Type.Tapered:
				path = self._style_tapered()
			case Needle.Type.Arrow:
				path = self._style_arrow()
			case Needle.Type.Line:
				path = self._style_line()
			case Needle.Type.Dot:
				path = self._style_dot()
			case Needle.Type.Notch:
				path = self._style_notch()
			case _:
				path = self._default()
		self.prepareGeometryChange()
		self._under, self._over = self._extras()
		self.setPath(path)

	def _brushColor(self) -> QColor:
		color = getattr(self, '_color', None)
		return self.gauge.defaultColor if color is None else color.QColor

	def refresh(self):
		gauge = self.gauge

		self.resetTransform()
		self.setBrush(QBrush(self._brushColor()))
		self.draw()

		self._applyAngle(gauge.value_to_angle(gauge.value))
		self.setPos(gauge.center)
		# resetTransform() above dropped the shift recenter() gave this item.
		# A value change refreshes the needle without a recenter, so put the
		# shift back or the pivot drifts off the arc's centre.
		self.setTransform(gauge._recenterTransform, combine=False)
		self.setZValue(-500)
		self.setVisible(getattr(self, '_visible', True))

	@StateProperty(key='visible', default=True, allowNone=False, after=refresh)
	def visible(self) -> bool:
		"""``false`` hides the needle itself, for a dial drawn with a ``fill`` and markers."""
		return getattr(self, '_visible', True)

	@visible.setter
	def visible(self, value: bool):
		self._visible = bool(value)

	@StateProperty(key='type', default=Type.Needle, allowNone=False, repr=True, after=refresh)
	def type(self) -> Type:
		return self._type

	@type.setter
	def type(self, value: Type):
		self._type = value

	@type.decode
	def type(self, value: str) -> Type:
		return Needle.Type[value]

	@StateProperty(key='width', allowNone=False, repr=True, dependencies={'type'}, after=refresh)
	def width(self) -> Size.Width | Length:
		return self._width

	@width.setter
	def width(self, value: Size.Width | Length):
		self._width = value

	@width.item_default
	def width(self) -> Size.Width | Length:
		# The styles added with the hands are thin; every older one keeps 10%.
		match self.type:
			case Needle.Type.Tapered:
				return Size.Width(0.09, relative=True)
			case Needle.Type.Arrow:
				return Size.Width(0.025, relative=True)
			case Needle.Type.Line:
				return Size.Width(0.012, relative=True)
			case Needle.Type.Dot:
				return Size.Width(0.09, relative=True)
			case Needle.Type.Notch:
				return Size.Width(0.02, relative=True)
			case _:
				return Size.Width(0.1, relative=True)

	@width.decode
	def width(self, value: str | float | int) -> Size.Width | Length:
		return parseWidth(value, type(self).width.default(type(self), self, update_source=False))

	@property
	def width_px(self) -> float:
		return self.gauge.sizeAcross(self.width, dimension=DimensionType.width)

	@StateProperty(key='length', allowNone=False, repr=True, dependencies={'type'}, after=refresh)
	def length(self) -> Size.Height | Length:
		return self._length

	@length.setter
	def length(self, value: Size.Height | Length):
		self._length = value

	@length.item_default
	def length(self) -> Size.Height | Length:
		match self.type:
			case Needle.Type.Needle | 'needle':
				return Size.Height(1.0, relative=True)
			case Needle.Type.Circle | 'circle':
				return Size.Height(0.2, relative=True)
			case Needle.Type.Triangle | 'triangle':
				return Size.Height(0.2, relative=True)
			case Needle.Type.Diamond | 'diamond':
				return Size.Height(0.2, relative=True)
			case Needle.Type.Tapered:
				return Size.Height(0.85, relative=True)
			case Needle.Type.Arrow:
				return Size.Height(0.4, relative=True)
			case Needle.Type.Line:
				return Size.Height(0.9, relative=True)
			case Needle.Type.Dot:
				return Size.Height(0.2, relative=True)
			case Needle.Type.Notch:
				return Size.Height(0.12, relative=True)
			case _:
				return Size.Height(1.0, relative=True)

	@length.decode
	def length(self, value: str | float | int) -> Size.Height | Length:
		return parseHeight(value, type(self).length.default(type(self), self, update_source=False))

	@property
	def length_px(self) -> float:
		return self.gauge.sizeAcross(self.length, dimension=DimensionType.height)

	@property
	def needleSize(self) -> QSizeF:
		return QSizeF(self.width_px, self.length_px)

	@StateProperty(key='offset', default=Size.Height(0, relative=True), allowNone=False, repr=True, after=refresh)
	def offset(self) -> Size.Height | Length:
		return self._offset

	@offset.setter
	def offset(self, value: Size.Height | Length):
		self._offset = value

	@offset.decode
	def offset(self, value: str | float | int) -> Size.Height | Length:
		return parseHeight(value, type(self).offset.default(type(self), self, update_source=False))

	@property
	def offset_px(self) -> float:
		return self.gauge.sizeAcross(self.offset, dimension=DimensionType.height)

	@StateProperty(key='color', default=None, allowNone=True, repr=True, after=refresh)
	def color(self) -> Color | None:
		"""Colour of the needle. Default: the gauge's text colour."""
		return getattr(self, '_color', None)

	@color.setter
	def color(self, value: Color | None):
		self._color = value

	@color.decode
	def color(self, value) -> Color | None:
		return None if value is None else Color.decode(value)

	@color.encode
	def color(self, value: Color | None) -> str | None:
		return None if value is None else str(value)

	@staticmethod
	def _optionalSize(parse, value):
		return None if value is None else parse(value, None)

	@staticmethod
	def _encodeSize(value) -> str | None:
		return None if value is None else str(value)

	@StateProperty(key='tail', default=None, allowNone=True, after=refresh)
	def tail(self) -> Size.Height | Length | None:
		"""Length behind the pivot, as a share of the radius (``tapered``, ``arrow``, ``line``)."""
		return getattr(self, '_tail', None)

	@tail.setter
	def tail(self, value):
		self._tail = value

	@tail.decode
	def tail(self, value):
		return Needle._optionalSize(parseHeight, value)

	@tail.encode
	def tail(self, value):
		return Needle._encodeSize(value)

	@StateProperty(key='tail-dot', default=None, allowNone=True, after=refresh)
	def tailDot(self) -> Size.Width | Length | None:
		"""Diameter of the dot at the end of the tail (``arrow``, ``line``)."""
		return getattr(self, '_tailDot', None)

	@tailDot.setter
	def tailDot(self, value):
		self._tailDot = value

	@tailDot.decode
	def tailDot(self, value):
		return Needle._optionalSize(parseWidth, value)

	@tailDot.encode
	def tailDot(self, value):
		return Needle._encodeSize(value)

	@StateProperty(key='head', default=None, allowNone=True, after=refresh)
	def head(self) -> Size.Height | Length | None:
		"""Length of the arrowhead (``arrow``). Default 12% of the radius."""
		return getattr(self, '_head', None)

	@head.setter
	def head(self, value):
		self._head = value

	@head.decode
	def head(self, value):
		return Needle._optionalSize(parseHeight, value)

	@head.encode
	def head(self, value):
		return Needle._encodeSize(value)

	@StateProperty(key='point', default=None, allowNone=True, after=refresh)
	def point(self) -> str | None:
		"""Where the ``arrow`` head sits: ``out`` (at the rim, default) or ``in`` (at the inner end)."""
		return getattr(self, '_point', None)

	@point.setter
	def point(self, value):
		self._point = value

	@point.decode
	def point(self, value):
		if value is None:
			return None
		value = str(value).strip().lower()
		if value not in ('in', 'out'):
			raise ValueError(f'needle point must be in or out, not {value!r}')
		return value

	@StateProperty(key='hub', default=None, allowNone=True, after=refresh)
	def hub(self) -> Size.Width | Length | None:
		"""Diameter of a disc at the pivot (``needle``, ``tapered``, ``line``), as a share of the radius."""
		return getattr(self, '_hub', None)

	@hub.setter
	def hub(self, value):
		self._hub = value

	@hub.decode
	def hub(self, value):
		return Needle._optionalSize(parseWidth, value)

	@hub.encode
	def hub(self, value):
		return Needle._encodeSize(value)

	@StateProperty(key='hub-color', default=None, allowNone=True, after=refresh)
	def hubColor(self) -> Color | None:
		"""Colour of the hub. Default: the needle colour."""
		return getattr(self, '_hubColor', None)

	@hubColor.setter
	def hubColor(self, value):
		self._hubColor = value

	@hubColor.decode
	def hubColor(self, value):
		return None if value is None else Color.decode(value)

	@hubColor.encode
	def hubColor(self, value):
		return None if value is None else str(value)

	@StateProperty(key='hub-hole', default=None, allowNone=True, after=refresh)
	def hubHole(self) -> float | None:
		"""Share of the hub's diameter cut out of its middle: a ring instead of a disc."""
		return getattr(self, '_hubHole', None)

	@hubHole.setter
	def hubHole(self, value):
		self._hubHole = value

	@hubHole.decode
	def hubHole(self, value):
		if value is None:
			return None
		if isinstance(value, str):
			value = float(value.strip().rstrip('%')) / 100 if value.strip().endswith('%') else float(value)
		return min(max(float(value), 0.0), 0.95)

	@StateProperty(key='halo', default=None, allowNone=True, after=refresh)
	def halo(self) -> Size.Width | Length | None:
		"""Width of a ring around a ``dot``, in the ``halo-color``."""
		return getattr(self, '_halo', None)

	@halo.setter
	def halo(self, value):
		self._halo = value

	@halo.decode
	def halo(self, value):
		return Needle._optionalSize(parseWidth, value)

	@halo.encode
	def halo(self, value):
		return Needle._encodeSize(value)

	@StateProperty(key='halo-color', default=None, allowNone=True, after=refresh)
	def haloColor(self) -> Color | None:
		return getattr(self, '_haloColor', None)

	@haloColor.setter
	def haloColor(self, value):
		self._haloColor = value

	@haloColor.decode
	def haloColor(self, value):
		return None if value is None else Color.decode(value)

	@haloColor.encode
	def haloColor(self, value):
		return None if value is None else str(value)

	@StateProperty(key='animate', default=0, allowNone=False, after=refresh)
	def animate(self) -> float:
		"""Milliseconds the hand takes to move to a new value; 0 (default) jumps.
		With a wrapping range (``range: {wrap: true}``) it takes the shorter way round."""
		return self._animate

	@animate.setter
	def animate(self, value: float):
		self._animate = value

	@animate.decode
	def animate(self, value) -> float:
		if isinstance(value, str):
			text = value.strip().lower()
			value = float(text[:-2]) if text.endswith('ms') else float(text[:-1]) * 1000 if text.endswith('s') else float(text)
		return max(0.0, float(value))

	def _radial(self, size: Size.Height | Size.Width | None, default: float = 0.0, *, dimension=DimensionType.height) -> float:
		"""A relative size in pixels, or ``default`` (a share of the radius) when unset."""
		if size is None:
			return default * self.gauge.radius
		return self.gauge.sizeAcross(size, dimension=dimension) or 0.0

	def _pivotY(self) -> float:
		return self.offset_px

	def _hubPath(self) -> Optional[QPainterPath]:
		hub = self.hub
		if hub is None or self.type.value not in self._PIVOT_STYLES:
			return None
		diameter = self.gauge.sizeAcross(hub, dimension=DimensionType.width) or 0.0
		if diameter <= 0:
			return None
		path = QPainterPath()
		path.setFillRule(Qt.FillRule.OddEvenFill)
		path.addEllipse(QPointF(0, self._pivotY()), diameter / 2, diameter / 2)
		if self.hubHole:
			hole = diameter / 2 * self.hubHole
			path.addEllipse(QPointF(0, self._pivotY()), hole, hole)
		return path

	def _extras(self) -> tuple[tuple, tuple]:
		"""Disc paths drawn beside the main path: ``(under, over)``, each a tuple of ``(path, colour)``."""
		under, over = [], []
		if (hub := self._hubPath()) is not None:
			over.append((hub, self._hubColor.QColor if getattr(self, '_hubColor', None) is not None else self.brush().color()))
		if self.type is Needle.Type.Dot and self.halo is not None:
			halo = self.gauge.sizeAcross(self.halo, dimension=DimensionType.width) or 0.0
			if halo > 0 and (color := getattr(self, '_haloColor', None)) is not None:
				r = self.width_px / 2 + halo
				path = QPainterPath()
				path.addEllipse(QPointF(0, self.offset_px - self.gauge.radius), r, r)
				under.append((path, color.QColor))
		return tuple(under), tuple(over)

	def boundingRect(self) -> QRectF:
		rect = super().boundingRect()
		for path, _ in (*self._under, *self._over):
			rect = rect.united(path.boundingRect())
		return rect

	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
		painter.setPen(Qt.NoPen)
		for path, color in self._under:
			painter.setBrush(QBrush(color))
			painter.drawPath(path)
		super().paint(painter, option, widget)
		painter.setPen(Qt.NoPen)
		for path, color in self._over:
			painter.setBrush(QBrush(color))
			painter.drawPath(path)

	def _setShape(self, path: QPainterPath) -> QPainterPath:
		self._shape = QPainterPath(path)
		self._bounding_rect = path.boundingRect()
		return path

	@staticmethod
	def _stroke(line: QPainterPath, width: float, cap=Qt.PenCapStyle.FlatCap) -> QPainterPath:
		stroker = QPainterPathStroker()
		stroker.setWidth(max(width, 0.5))
		stroker.setCapStyle(cap)
		return stroker.createStroke(line)

	def _style_tapered(self) -> QPainterPath:
		"""A kite: wide at the pivot, narrowing to the tip, with a short tail behind.

		Length: pivot to tip. Width: across the pivot. Tail: behind the pivot.
		Offset: moves the pivot. Add ``hub`` for the disc over the pivot.
		"""
		y, w = self._pivotY(), self.width_px
		tip = QPointF(0, y - self.length_px)
		tail = self._radial(self.tail)
		path = QPainterPath()
		path.moveTo(tip)
		path.lineTo(w / 2, y)
		path.lineTo(w * 0.3, y + tail)
		path.lineTo(-w * 0.3, y + tail)
		path.lineTo(-w / 2, y)
		path.closeSubpath()
		return self._setShape(path)

	def _style_line(self) -> QPainterPath:
		"""A thin line with a counterweight: ``tail`` is the line behind the pivot,
		``tail-dot`` the disc at its end. Length: pivot to tip."""
		y, w = self._pivotY(), self.width_px
		tail = self._radial(self.tail)
		line = QPainterPath(QPointF(0, y + tail))
		line.lineTo(0, y - self.length_px)
		path = self._stroke(line, w, Qt.PenCapStyle.RoundCap)
		if self.tailDot is not None:
			r = self.gauge.sizeAcross(self.tailDot, dimension=DimensionType.width) / 2
			disc = QPainterPath()
			disc.addEllipse(QPointF(0, y + tail), r, r)
			path = path.united(disc)
		return self._setShape(path)

	def _style_arrow(self) -> QPainterPath:
		"""A wind-direction arrow: a shaft and head at the rim, and optionally a
		tail shaft ending in a dot at the opposite rim.

		Length: the shaft, from the rim inward. Width: shaft width.
		Head: head length (default 12%). Point: ``out`` (head at the rim) or ``in``.
		Tail: the opposite shaft's length, from the opposite rim inward.
		Tail-dot: diameter of the dot at the opposite rim. Offset: moves it all inward.
		"""
		radius, w = self.gauge.radius, self.width_px
		off = self.offset_px
		head = self._radial(self.head, 0.12)
		half = head * 0.42
		length = max(self.length_px, head)
		rim = off - radius
		path = QPainterPath()
		if (self.point or 'out') == 'out':
			shaft = QPainterPath(QPointF(0, rim + head * 0.6))
			shaft.lineTo(0, rim + length)
			path.addPath(self._stroke(shaft, w))
			path.moveTo(0, rim)
			path.lineTo(half, rim + head)
			path.lineTo(-half, rim + head)
			path.closeSubpath()
		else:
			shaft = QPainterPath(QPointF(0, rim))
			shaft.lineTo(0, rim + length - head * 0.6)
			path.addPath(self._stroke(shaft, w))
			path.moveTo(0, rim + length)
			path.lineTo(half, rim + length - head)
			path.lineTo(-half, rim + length - head)
			path.closeSubpath()
		tail = self._radial(self.tail)
		dot = (self.gauge.sizeAcross(self.tailDot, dimension=DimensionType.width) or 0.0) if self.tailDot is not None else 0.0
		far = radius - off
		if tail > 0:
			shaft = QPainterPath(QPointF(0, far - dot * 0.5))
			shaft.lineTo(0, far - tail)
			path.addPath(self._stroke(shaft, w))
		if dot > 0:
			path.addEllipse(QPointF(0, far - dot / 2), dot / 2, dot / 2)
		return self._setShape(path)

	def _style_dot(self) -> QPainterPath:
		"""A knob centred on the track. Width: diameter. Halo/halo-color: a ring around it."""
		r = self.width_px / 2
		path = QPainterPath()
		path.addEllipse(QPointF(0, self.offset_px - self.gauge.radius), r, r)
		return self._setShape(path)

	def _style_notch(self) -> QPainterPath:
		"""A bar across the track. Width: along the track. Length: across it."""
		w, length = self.width_px, self.length_px
		rect = QRectF(-w / 2, self.offset_px - self.gauge.radius - length / 2, w, length)
		path = QPainterPath()
		path.addRoundedRect(rect, w * 0.25, w * 0.25)
		return self._setShape(path)

	def _animateMs(self) -> float:
		try:
			return float(self.animate or 0)
		except (AttributeError, TypeError, ValueError):
			return 0.0

	def _applyAngle(self, target: float) -> None:
		"""Rotate to ``target`` degrees, easing there when ``animate`` is set.

		With a wrapping range the hand turns the shorter way across the join.
		Without ``animate`` this is a plain ``setRotation``, as it always was.
		"""
		target = float(target)
		ms = self._animateMs()
		if not ms or self._shown is None:
			self._stopAnimation()
			self._shown = self._lastTarget = target
			self.setRotation(target)
			return
		if target == self._lastTarget:
			self.setRotation(self._shown)
			return
		self._lastTarget = target
		shown = self._shown
		if getattr(self.gauge._range, 'wrap', False):
			destination = shown + shortestDelta(shown, target, float(self.gauge.fullAngle))
		else:
			destination = target
		self._stopAnimation()
		animation = QVariantAnimation()
		animation.setDuration(int(ms))
		animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
		animation.setStartValue(float(shown))
		animation.setEndValue(float(destination))
		animation.valueChanged.connect(self._onAnimated)
		self._anim = animation
		animation.start()

	def _onAnimated(self, value) -> None:
		self._shown = float(value)
		try:
			self.setRotation(self._shown)
		except RuntimeError:
			self._stopAnimation()

	def _stopAnimation(self) -> None:
		animation, self._anim = self._anim, None
		if animation is not None:
			animation.stop()

	_shape: QPainterPath = QPainterPath()

	def shape(self) -> QPainterPath:
		return self._shape or self.path()

	def _default(self) -> QPainterPath:
		"""
		Returns a standard tapering needle with a rounded bottom.

		Length: Controls the length of the needle
		Width: Controls the width of the needle
		Offset: Controls the offset of the needle from the center of the gauge
		"""

		cx = 0
		cy = self.offset_px
		middle = QPointF(cx, cy - self.length_px)
		needleWidth = self.width_px
		left = QPointF(cx - needleWidth / 2, cy)
		right = QPointF(cx + needleWidth / 2, cy)
		arcStart = QPointF(left)
		arcStart.setY(left.y() + needleWidth * 0.6)
		arcEnd = QPointF(right)
		arcEnd.setY(right.y() + needleWidth * 0.6)
		arcRect = QRectF(arcStart, QSizeF(needleWidth, -needleWidth))

		needlePath = QPainterPath()
		needlePath.arcMoveTo(arcRect, 0)
		needlePath.lineTo(middle)
		needlePath.arcTo(arcRect, 180, -180)
		needlePath.addEllipse(QPointF(cx, cy), needleWidth / 3, needleWidth / 3)

		# Set the needle's bounding rect and shape
		self._shape = shape = QPainterPath()
		bounding_rect = QRectF(0, 0, needleWidth, needleWidth)
		bounding_rect.moveCenter(QPointF(cx, cy))
		shape.addEllipse(bounding_rect)
		self._bounding_rect = shape.boundingRect()

		return needlePath

	def _edge_circle(self) -> QPainterPath:
		"""
		Returns a circle that is used as the indicator instead of a needle.

		Length: Not used
		Width: Controls the diameter of the circle
		Offset: Controls the offset of the circle from the arch path of the gauge
		"""

		cx = 0
		cy = self.offset_px
		pos = QPointF(cx, cy - self.gauge.radius)

		path = QPainterPath()
		path.addEllipse(pos, self.width_px / 2, self.width_px / 2)

		# Set the needle's bounding rect and shape
		self._shape = shape = QPainterPath(path)
		# bounding_rect = QRectF(0, 0, self.width_px, self.width_px)
		# bounding_rect.moveCenter(QPointF(pos))
		# shape.addEllipse(bounding_rect)
		self._bounding_rect = shape.boundingRect()

		return path

	def _edge_triangle(self) -> QPainterPath:
		"""
		Returns a triangle that is used as the indicator instead of a needle.

		Length: Controls the length of the triangle.  Positive values will point in, negative values will point out.
		Width: Controls the base width of the triangle
		Offset: Controls the offset of the triangle from the arch path of the gauge

		"""
		cx = 0
		cy = self.offset_px
		l = self.length_px
		w = self.width_px
		pos = QPointF(cx, cy - self.gauge.radius)
		shape = QPainterPath()
		tri_point = QPointF(pos + QPointF(0, l))
		tri_base_y = pos.y()
		tri_base_left = QPointF(pos.x() - w / 2, tri_base_y)
		tri_base_right = QPointF(pos.x() + w / 2, tri_base_y)
		shape.moveTo(tri_point)
		shape.lineTo(tri_base_left)
		shape.lineTo(tri_base_right)
		shape.lineTo(tri_point)
		shape.closeSubpath()
		self._shape = QPainterPath(shape)
		self._bounding_rect = shape.boundingRect()
		return shape

	def _edge_marker(self) -> QPainterPath:
		"""
		Returns an arrowhead that sits *on* the arc rather than pointing at it
		from the centre.

		Unlike the other edge shapes, which are placed at the radius, this one
		is centred on the arc's stroke, so with a matching weight it reads as a
		marker travelling along the line. The notched back keeps it an arrow
		rather than a triangle at a glance.

		Length: depth across the arc. Positive points inward.
		Width: width along the arc
		Offset: nudges it off the arc line
		"""
		cx = 0
		cy = self.offset_px
		l = self.length_px
		w = self.width_px
		# Centre on the stroke, not on the radius, so half sits either side.
		pos = QPointF(cx, cy - self.gauge.radius)
		shape = QPainterPath()
		tip = QPointF(pos.x(), pos.y() + l / 2)
		back_left = QPointF(pos.x() - w / 2, pos.y() - l / 2)
		back_right = QPointF(pos.x() + w / 2, pos.y() - l / 2)
		notch = QPointF(pos.x(), pos.y() - l / 6)
		shape.moveTo(tip)
		shape.lineTo(back_left)
		shape.lineTo(notch)
		shape.lineTo(back_right)
		shape.lineTo(tip)
		shape.closeSubpath()
		self._shape = QPainterPath(shape)
		self._bounding_rect = shape.boundingRect()
		return shape

	def _edge_diamond(self) -> QPainterPath:
		"""
		Returns a diamond that is used as the indicator instead of a needle.

		Length: Controls the height of the diamond
		Width: Controls the width of the diamond
		Offset: Controls the offset of the diamond from the arch path of the gauge

		"""
		cx = 0
		cy = self.offset_px
		l = self.length_px
		w = self.width_px
		pos = QPointF(cx, cy - self.gauge.radius)
		shape = QPainterPath()
		diamond_top = QPointF(pos.x(), pos.y() - l / 2)
		diamond_left = QPointF(pos.x() - w / 2, pos.y())
		diamond_bottom = QPointF(pos.x(), pos.y() + l / 2)
		diamond_right = QPointF(pos.x() + w / 2, pos.y())
		shape.moveTo(diamond_top)
		shape.lineTo(diamond_left)
		shape.lineTo(diamond_bottom)
		shape.lineTo(diamond_right)
		shape.lineTo(diamond_top)
		shape.closeSubpath()
		self._shape = QPainterPath(shape)
		self._bounding_rect = shape.boundingRect()
		return shape



class Arrow(Needle):

	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget):
		# draw lines through the center
		painter.setPen(QPen(Qt.red))
		painter.drawRect(self.boundingRect())
		# c = self.boundingRect().center()
		# cTop = QPointF(c.x(), 0)
		# cBottom = QPointF(c.x(), self.boundingRect().height())
		# painter.drawLine(cTop, cBottom)
		# c = self.gauge.arc.center
		# cLeft = QPointF(0, c.y())
		# cRight = QPointF(self.boundingRect().width(), c.y())
		# horizontal = QLineF(cLeft, cRight)
		# painter.drawLine(horizontal)
		# horizontal.translate(0, self.gauge.radius/2/4)
		# painter.drawLine(horizontal)
		# horizontal.translate(0, -self.gauge.radius/2/4*2)
		# painter.drawLine(horizontal)
		# painter.drawLine(self.gauge.arc.center, self.gauge.arc.center + QPointF(0, self.needleLength))
		super(Arrow, self).paint(painter, option, widget)

	@property
	def safeZone(self):
		path = QPainterPath()
		radius = self.gauge.radius
		path.addEllipse(QPoint(0, 0), radius * 0.6, radius * 0.6)
		return path

	# super(Arrow, self).paint(painter, option, widget)

	def draw(self):
		# center = self._gauge.arc.center
		cx = 0
		cy = 0

		# Draw Circle
		radius = self.gauge.radius
		pointerHeight = radius * 0.178
		radius = radius - pointerHeight
		base = pointerHeight
		path = QPainterPath()

		# Draw Outer Circle
		path.setFillRule(Qt.FillRule.WindingFill)
		path.addEllipse(QPoint(cx, cy), radius, radius)

		# Draw Arrow
		middle = QPointF(cx, cy - pointerHeight - radius)
		left = QPointF(cx - base, cy - radius + 10)
		right = QPointF(cx + base, cy - radius + 10)
		arrow = QPolygonF()
		path.moveTo(left)
		path.lineTo(middle)
		path.lineTo(right)
		# arrow.append(middle)
		# arrow.append(left)
		# arrow.append(right)
		# path.addPolygon(arrow)


		# path.setFillRule(Qt.FillRule.WindingFill)

		# Draw Center Circle
		path.addEllipse(QPoint(0, 0), radius * 0.8, radius * 0.8)
		path.setFillRule(Qt.FillRule.OddEvenFill)

		self.setPath(path)


# Unit positions that hang the unit under the value. `float-under` is the
# Realtime text display's name for it; `below` is the gauge's older one.
_UNIT_UNDER_VALUE = frozenset({UnitDisplayPosition.Below, UnitDisplayPosition.FloatUnder})


def _markerText(spec) -> str:
	"""The ``value:`` text of a marker spec, for log messages. Never raises."""
	try:
		return str(spec.get('value'))
	except Exception:
		return str(spec)


class GaugeMarker(Needle):
	"""An extra indicator on a gauge, with its own value.

	Shares every visual option with the needle (``type``, ``width``,
	``length``, ``offset``). The value comes from ``value:``, a number or a
	key, not from the panel's key. With no value yet the marker is hidden.
	"""

	_markerValue = None
	_markerColor: Optional[QColor] = None
	_binding: Optional[Binding] = None
	_warned = False
	_clockTimer: Optional[QTimer] = None
	_clockHand: Optional[str] = None

	#: Used when the marker names no ``length``: the needle default for the
	#: ``marker`` type is the full radius, which is far too long for a tick.
	DEFAULT_LENGTH = '20%'

	def configure(self, spec: Mapping) -> None:
		"""Apply the visual options and start the value source from ``spec``."""
		visual = {k: v for k, v in spec.items() if k not in ('value', 'color', 'time', 'at')}
		visual.setdefault('type', 'marker')
		if Needle.Type[visual['type']] is Needle.Type.Marker:
			visual.setdefault('length', self.DEFAULT_LENGTH)
		with self.action_pool:
			self.setItemState(visual)

		if (color := spec.get('color')) is not None:
			self._markerColor = Color.decode(color).QColor

		if spec.get('time') is not None:
			self._followClock(spec['time'], spec.get('at'))
			self.refresh()
			return

		raw = spec.get('value')
		if isinstance(raw, bool):
			raise TypeError(f'a marker value must be a number or a key, not {raw!r}')
		if isinstance(raw, (int, float)):
			self._markerValue = raw
		elif isinstance(raw, str):
			if (source := openValueSource(raw, f'Gauge {_gaugeKeyName(self.gauge)} marker value', 'the marker stays hidden')) is not None:
				self._binding = Binding(source, self.setMarkerValue)
		else:
			raise TypeError(f'a marker value must be a number or a key, not {raw!r}')
		self.refresh()

	def close(self):
		self._stopAnimation()
		if self._clockTimer is not None:
			self._clockTimer.stop()
			self._clockTimer = None
		if self._binding is not None:
			self._binding.unlink()
			self._binding = None

	def _followClock(self, hand, at) -> None:
		"""Drive the marker from the time of day: ``time: hour|minute|second|day``.
		The hand turns once round the gauge's range (``range: {min: 0, max: 12, wrap: true}``
		for a 12 hour dial) however many units that holds.

		``at: 'HH:MM[:SS]'`` shows that fixed time instead and starts no timer.
		The timer runs on the GUI thread, once a second.
		"""
		hand = str(hand).strip().lower()
		if hand not in CLOCK_HANDS:
			raise ValueError(f'time must be one of {", ".join(CLOCK_HANDS)}, not {hand!r}')
		self._clockHand = hand
		if at is not None:
			self._fixedTime = parseClockTime(at)
			self._tickClock()
			return
		self._fixedTime = None
		self._clockTimer = QTimer()
		self._clockTimer.setInterval(1000)
		self._clockTimer.timeout.connect(self._tickClock)
		self._clockTimer.start()
		self._tickClock()

	def _tickClock(self) -> None:
		try:
			if self._fixedTime is not None:
				hours, minutes, seconds = self._fixedTime
			else:
				# The app's own clock, not the wall clock: `shared.now()` is what
				# `--freeze-time` patches (see _boot.freeze_time), so reading
				# datetime.now() here meant a frozen render still drew a live hand.
				current = now()
				hours, minutes, seconds = current.hour, current.minute, current.second + current.microsecond / 1e6
			self._clockFraction = clockTurn(self._clockHand, hours, minutes, seconds)
		except Exception as e:
			log.warning(f'Gauge {_gaugeKeyName(self.gauge)} clock hand stopped: {e}')
			if self._clockTimer is not None:
				self._clockTimer.stop()
			return
		self.refresh()

	def setMarkerValue(self, value) -> None:
		"""Set the value to show. GUI thread only (the feed's slot runs there)."""
		self._markerValue = value
		self.refresh()

	_clockFraction: Optional[float] = None
	_fixedTime = None

	def _markerAngle(self) -> Optional[float]:
		if self._clockHand is not None:
			# Placed against the range as it is now: the range may load after the marker.
			if self._clockFraction is None:
				return None
			_range = self.gauge._range
			self._markerValue = float(_range.rounded_min) + self._clockFraction * float(_range.rounded_range)
		value = self._markerValue
		if value is None:
			return None
		gauge = self.gauge
		valueClass = gauge.valueClass
		try:
			if not isinstance(value, valueClass):
				value = valueClass(value)
		except Exception:
			value = float(value)
		try:
			return gauge.value_to_angle(value)
		except Exception as e:
			if not self._warned:
				self._warned = True
				log.warning(f'Gauge {_gaugeKeyName(gauge)} cannot place marker value {value!r}: {e}')
			return None

	def refresh(self):
		gauge = self.gauge
		self.resetTransform()
		self.setBrush(QBrush(gauge.defaultColor if self._markerColor is None else self._markerColor))
		self.draw()
		angle = self._markerAngle()
		if angle is None:
			self.hide()
			return
		self._applyAngle(angle)
		self.setPos(gauge.center)
		# resetTransform() above dropped the shift recenter() gave this item.
		# A value change refreshes the needle without a recenter, so put the
		# shift back or the pivot drifts off the arc's centre.
		self.setTransform(gauge._recenterTransform, combine=False)
		self.setZValue(-500)
		self.show()


class GaugeZones(GaugeItem, QGraphicsItem):
	"""Coloured bands over the arc track, from a list of plain mappings.

	Each entry: ``from`` and ``to`` (numbers; default the range ends),
	``color`` (required), ``weight`` (default the arc's) and ``mark`` (draw a
	tick across the arc at each cutoff that is not a range end). A bad entry
	logs the gauge key and is skipped; nothing here raises during load.
	"""

	#: Over the arc (-800), under the fill (-700) and the needle (-500).
	Z_VALUE = -750

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._zones: list = []
		self._strokes: list = []
		self._rect = QRectF()
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents, False)

	def close(self):
		self._zones = []
		self._strokes = []

	def configure(self, specs: Sequence) -> list:
		"""Validate ``specs``; keep the good ones. Returns the plain mappings kept."""
		name = _gaugeKeyName(self.gauge)
		zones, kept = [], []
		for spec in specs:
			try:
				if not isinstance(spec, Mapping):
					raise TypeError('expected a mapping with from, to and color')
				unknown = set(spec) - {'from', 'to', 'color', 'weight', 'mark'}
				if unknown:
					log.warning(f'Gauge {name} zone ignored unknown keys {sorted(map(str, unknown))}')
				ends = []
				for end in ('from', 'to'):
					raw = spec.get(end)
					if raw is None:
						ends.append(None)
						continue
					if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not isfinite(raw):
						raise TypeError(f'{end} must be a finite number, not {raw!r}')
					ends.append(float(raw))
				if spec.get('color') is None:
					raise ValueError('a zone needs a color')
				color = Color.decode(spec['color']).QColor
				weight = None
				if (raw := spec.get('weight')) is not None:
					weight = parseWidth(raw, None)
					if weight is None:
						raise ValueError(f'weight {raw!r} is not a size')
				zones.append({'from': ends[0], 'to': ends[1], 'color': color, 'weight': weight, 'mark': bool(spec.get('mark', False))})
				kept.append(copy.deepcopy(dict(spec)))
			except Exception as e:
				log.warning(f'Gauge {name} skipped zone {spec!r}: {e}')
		self._zones = zones
		return kept

	def _span(self, zone) -> tuple[float, float]:
		"""The zone's start and end as dial angles; a missing end is the dial's end."""
		gauge = self.gauge
		lo = float(gauge.startAngle) if zone['from'] is None else self._angle(zone['from'])
		hi = float(gauge.endAngle) if zone['to'] is None else self._angle(zone['to'])
		return tuple(sorted((lo, hi)))

	def colorAtAngle(self, angle: float) -> Optional[QColor]:
		"""The colour of the zone holding ``angle``; the later zone wins on a shared cutoff."""
		found = None
		for zone in self._zones:
			try:
				lo, hi = self._span(zone)
			except Exception:
				continue
			if lo - 1e-9 <= angle <= hi + 1e-9:
				found = zone['color']
		return found

	def colorAt(self, value) -> Optional[QColor]:
		"""The colour of the zone holding ``value`` (a number or a measurement)."""
		try:
			return self.colorAtAngle(self._angle(value))
		except Exception:
			return None

	def _angle(self, value: float) -> float:
		gauge = self.gauge
		valueClass = gauge.valueClass
		try:
			converted = valueClass(value)
		except Exception:
			converted = float(value)
		return float(gauge.value_to_angle(converted))

	def refresh(self):
		self.prepareGeometryChange()
		self._strokes = []
		gauge = self.gauge
		bounds = QRectF()
		if not self._zones:
			self._rect = bounds
			self.hide()
			return
		try:
			rect = gauge.arc.centered_gauge_rect
			arcWeight = gauge.arc.weight_px
			marks = set()
			for zone in self._zones:
				a, b = self._span(zone)
				weight = gauge.sizeAcross(zone['weight'], dimension=DimensionType.width) if zone['weight'] is not None else arcWeight
				if zone['mark']:
					marks.update(x for x in (a, b) if float(gauge.startAngle) + 1e-6 < x < float(gauge.endAngle) - 1e-6)
				if not weight or a == b:
					continue
				path = QPainterPath()
				path.arcMoveTo(rect, -a + 90)
				path.arcTo(rect, -a + 90, -(b - a))
				pen = QPen(zone['color'], weight)
				pen.setCapStyle(Qt.PenCapStyle.FlatCap)
				self._strokes.append((path, pen))
				bounds = bounds.united(path.boundingRect().adjusted(-weight, -weight, weight, weight))
			for angle in sorted(marks):
				radius = rect.width() / 2
				reach = (arcWeight or 0) * 0.75
				path = QPainterPath()
				path.moveTo(radialPoint(QPointF(0, 0), radius - reach, angle))
				path.lineTo(radialPoint(QPointF(0, 0), radius + reach, angle))
				pen = QPen(gauge.defaultColor, max(1.5, (arcWeight or 0) * 0.12))
				pen.setCapStyle(Qt.PenCapStyle.FlatCap)
				self._strokes.append((path, pen))
				bounds = bounds.united(path.boundingRect().adjusted(-2, -2, 2, 2))
		except Exception as e:
			log.warning(f'Gauge {_gaugeKeyName(gauge)} zones not drawn: {e}')
			self._strokes = []
		self._rect = bounds
		self.setPos(gauge.center)
		self.setZValue(self.Z_VALUE)
		self.setVisible(bool(self._strokes))
		self.update()

	def boundingRect(self) -> QRectF:
		return self._rect

	def paint(self, painter: QPainter, option, widget=None):
		painter.setBrush(Qt.BrushStyle.NoBrush)
		for path, pen in self._strokes:
			painter.setPen(pen)
			painter.drawPath(path)


class _FillEnd:
	"""Adapts one end of a fill to the setter a ``Binding`` drives."""

	def __init__(self, fill: 'GaugeFill', end: str):
		self._fill = fill
		self._end = end

	def setMarkerValue(self, value) -> None:
		self._fill.setEnd(self._end, value)


class GaugeFill(GaugePathItem):
	"""A value-driven arc stroked over the track and under the needle.

	Spec keys: ``from`` (a number, key or expression; default the range
	minimum), ``to`` (a number, key or expression; omitted means the gauge value), ``weight`` (default the arc's) and
	``color`` (default the gauge colour). With no value to draw to, it is hidden.
	A source-fed end with no value yet hides the fill; a bad spec logs the gauge key and hides it.
	"""

	#: Between the arc (-800) and the needle (-500).
	Z_VALUE = -700

	_from: Optional[float] = None
	_to: Optional[float] = None
	_weight = None
	_color: Optional[QColor] = None
	_valid = False
	_warned = False
	_colorFromZones = False
	_segments: int = 0
	_gap = None
	_strokes: list = ()

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		# Ends fed by a value source that has not delivered yet: the fill is hidden.
		self._pending: set = set()
		self._bindings: list = []

	def close(self):
		"""Unlink the bindings, which releases the value sources."""
		bindings = self._bindings
		self._bindings, self._pending = [], set()
		for binding in bindings:
			binding.unlink()

	def setEnd(self, end: str, value) -> None:
		"""Set a source-fed end. GUI thread only (the feed's slot runs there)."""
		try:
			value = float(value)
		except (TypeError, ValueError):
			return
		if not isfinite(value):
			return
		setattr(self, f'_{end}', value)
		self._pending.discard(end)
		self._safeRefresh()

	def configure(self, spec: Mapping) -> None:
		"""Read ``spec``. Never raises: a bad spec warns and leaves the fill hidden."""
		self.close()
		self._valid = False
		self._from = self._to = self._weight = self._color = self._gap = None
		self._colorFromZones, self._segments, self._strokes = False, 0, ()
		name = _gaugeKeyName(self.gauge)
		unknown = set(spec) - {'from', 'to', 'weight', 'color', 'segments', 'gap'}
		if unknown:
			log.warning(f'Gauge {name} fill ignored unknown keys {sorted(map(str, unknown))}')
		try:
			for end in ('from', 'to'):
				raw = spec.get(end)
				if raw is None:
					continue
				if isinstance(raw, bool):
					raise TypeError(f'{end} must be a number, a key or an expression, not {raw!r}')
				if isinstance(raw, (int, float)):
					if not isfinite(raw):
						raise TypeError(f'{end} must be finite, not {raw!r}')
					setattr(self, f'_{end}', float(raw))
				elif isinstance(raw, str):
					self._pending.add(end)
					if (source := openValueSource(raw, f'Gauge {name} fill {end}', 'the fill stays hidden')) is None:
						raise ValueError(f'{end} {raw!r} is not usable')
					self._bindings.append(Binding(source, _FillEnd(self, end).setMarkerValue))
				else:
					raise TypeError(f'{end} must be a number, a key or an expression, not {raw!r}')
			if (weight := spec.get('weight')) is not None:
				self._weight = parseWidth(weight, None)
				if self._weight is None:
					raise ValueError(f'weight {weight!r} is not a size')
			if isinstance(spec.get('color'), str) and spec['color'].strip().lower() == 'zone':
				self._colorFromZones = True
			elif (color := spec.get('color')) is not None:
				self._color = Color.decode(color).QColor
			if (segments := spec.get('segments')) is not None:
				if isinstance(segments, bool) or not isinstance(segments, int) or segments < 1:
					raise TypeError(f'segments must be a whole number of 1 or more, not {segments!r}')
				self._segments = segments
				if (gap := spec.get('gap')) is not None:
					self._gap = parseWidth(gap, None)
					if self._gap is None:
						raise ValueError(f'gap {gap!r} is not a size')
		except Exception as e:
			log.warning(f'Gauge {name} fill ignored, hidden: {e}')
			self.close()
			self._safeRefresh()
			return
		self._valid = True
		self._safeRefresh()

	def _safeRefresh(self):
		# The gauge may not be laid out yet while its state loads; Gauge.refresh redraws later.
		try:
			self.refresh()
		except Exception as e:
			log.debug(f'Gauge {_gaugeKeyName(self.gauge)} fill not drawn yet: {e}')

	def _toValueClass(self, value):
		valueClass = self.gauge.valueClass
		try:
			if not isinstance(value, valueClass):
				value = valueClass(value)
		except Exception:
			value = float(value)
		return value

	def _angles(self) -> Optional[tuple[float, float]]:
		gauge = self.gauge
		start = self._from if self._from is not None else gauge._range.rounded_min
		end = self._to if self._to is not None else gauge.value
		if start is None or end is None:
			return None
		try:
			a = gauge.value_to_angle(self._toValueClass(start))
			b = gauge.value_to_angle(self._toValueClass(end))
			a, b = float(a), float(b)
		except Exception as e:
			if not self._warned:
				self._warned = True
				log.warning(f'Gauge {_gaugeKeyName(gauge)} cannot place fill {start!r} to {end!r}: {e}')
			return None
		if not (isfinite(a) and isfinite(b)):
			return None
		return a, b

	def refresh(self):
		"""Redraw. Geometry and colour only; never asks the gauge to relayout."""
		gauge = self.gauge
		angles = self._angles() if self._valid and not self._pending else None
		if angles is None:
			self.hide()
			return
		# Either order: draw from the smaller angle to the larger. Both ends were
		# already clamped to the arc by value_to_angle. Equal angles draw nothing.
		a, b = sorted(angles)
		if a == b:
			self.hide()
			return
		weight = gauge.sizeAcross(self._weight, dimension=DimensionType.width) if self._weight is not None else gauge.arc.weight_px
		rect = gauge.arc.centered_gauge_rect
		zones = gauge._zonesItem
		base = gauge.defaultColor if self._color is None else self._color
		strokes = []
		if weight and self._segments:
			start, full = float(gauge.startAngle), float(gauge.fullAngle)
			step = full / self._segments
			radius = rect.width() / 2 or 1
			gapDeg = 0.0
			if self._gap is not None:
				gapPx = gauge.sizeAcross(self._gap, dimension=DimensionType.width) or 0
				gapDeg = gapPx / radius * 180 / pi
			# Never let the gap swallow the segment.
			gapDeg = min(max(gapDeg, 0.0), step * 0.8)
			for i in range(self._segments):
				sa, sb = start + i * step + gapDeg / 2, start + (i + 1) * step - gapDeg / 2
				mid = start + (i + 0.5) * step
				if not (a <= mid <= b):
					continue
				path = QPainterPath()
				path.arcMoveTo(rect, -sa + 90)
				path.arcTo(rect, -sa + 90, -(sb - sa))
				color = base
				if self._colorFromZones and zones is not None:
					color = zones.colorAtAngle(mid) or base
				strokes.append((path, color))
		elif weight:
			path = QPainterPath()
			path.arcMoveTo(rect, -a + 90)
			path.arcTo(rect, -a + 90, -(b - a))
			color = base
			if self._colorFromZones and zones is not None:
				endValue = self._to if self._to is not None else gauge.value
				color = zones.colorAt(endValue) or base
			strokes.append((path, color))
		full = QPainterPath()
		for path, _ in strokes:
			full.addPath(path)
		pen = QPen(gauge.pen)
		pen.setWidthF(weight or 0)
		pen.setCapStyle(Qt.PenCapStyle.FlatCap)
		pen.setBrush(QBrush(strokes[0][1] if strokes else base))
		self.setPen(pen)
		self.setBrush(Qt.BrushStyle.NoBrush)
		self.prepareGeometryChange()
		self._strokes = strokes
		self.setPath(full)
		self.setPos(gauge.center)
		self.setZValue(self.Z_VALUE)
		self.show()

	def _valueAtAngle(self, angle: float) -> float:
		gauge = self.gauge
		lo, span = float(gauge._range.rounded_min), float(gauge._range.rounded_range)
		return lo + (angle - float(gauge.startAngle)) / float(gauge.fullAngle) * span

	def paint(self, painter: QPainter, option, widget=None):
		painter.setBrush(Qt.BrushStyle.NoBrush)
		for path, color in self._strokes:
			pen = QPen(self.pen())
			pen.setBrush(QBrush(color))
			painter.setPen(pen)
			painter.drawPath(path)


class GaugeCaption(GaugePathItem):
	"""A small line of text above (``caption``) or below (``sub-label``) the centre value.

	The spec is a string (static text) or a mapping: ``text`` (may hold ``{}``
	where the value goes), ``value`` (a key or expression to show; with no
	``format`` it prints as the value does, unit and all), ``format``
	(``duration`` turns minutes into ``4h 49m``; any other string is a Python
	format spec, and a mapping is the value label's ``format``, e.g. ``{precision: 0, show_unit: false}``), ``warp`` (bend the text along a
	circle, see `WarpSpec`; then ``gap`` and ``offset`` do not apply), ``size`` (text height as a share of the dial's diameter,
	default 7%), ``color``, ``weight`` (``bold``), ``gap`` (distance from the
	value, a share of the diameter, default 2%) and ``offset`` (``{x, y}``, shares of the
	diameter, added to where the gap puts it). A value source with no value
	yet shows nothing. A bad spec logs the gauge key and shows nothing.
	"""

	Z_VALUE = -400

	_text = ''
	_template = None
	_value = None
	_hasValue = False
	_format = None
	_size = None
	_gap = None
	_color: Optional[QColor] = None
	_bold = False
	_offset: Optional[tuple] = None
	_binding: Optional[Binding] = None
	_warp: Optional[WarpSpec] = None

	def __init__(self, gauge: 'Gauge', side: str):
		super().__init__(gauge)
		self._side = side
		self.setPen(Qt.PenStyle.NoPen)
		self.hide()

	def close(self):
		if self._binding is not None:
			self._binding.unlink()
			self._binding = None

	def configure(self, spec) -> None:
		self.close()
		if isinstance(spec, str):
			spec = {'text': spec}
		name = _gaugeKeyName(self.gauge)
		unknown = set(spec) - {'text', 'value', 'format', 'size', 'color', 'weight', 'gap', 'offset', 'warp'}
		if unknown:
			log.warning(f'Gauge {name} {self._side} ignored unknown keys {sorted(map(str, unknown))}')
		self._offset = _decodeOffset(spec.get('offset'))
		self._warp = WarpSpec.decode(spec.get('warp'))
		self._template = spec.get('text')
		self._hasValue = False
		self._format = spec.get('format')
		self._size = parseHeight(spec.get('size', '7%'), None)
		self._gap = parseHeight(spec.get('gap', '2%'), None)
		self._color = Color.decode(spec['color']).QColor if spec.get('color') is not None else None
		self._bold = str(spec.get('weight', '')).lower() == 'bold'
		raw = spec.get('value')
		if raw is not None:
			if (source := openValueSource(raw, f'Gauge {name} {self._side} value', 'the text stays hidden')) is not None:
				self._binding = Binding(source, self.setCaptionValue)
		self._rebuildText()

	def setCaptionValue(self, value) -> None:
		"""Set the shown value. GUI thread only."""
		self._value, self._hasValue = value, True
		self._rebuildText()
		self.gauge._syncCaptions()

	def _valueText(self) -> str:
		value, spec = self._value, self._format
		if spec == 'duration':
			return formatDuration(value)
		if spec is not None:
			try:
				if isinstance(value, Measurement):
					return value.__format__('', **spec) if isinstance(spec, Mapping) else value.__format__(spec)
				return format(float(value), spec)
			except Exception:
				return str(value)
		return str(value)

	def _rebuildText(self) -> None:
		if self._binding is not None and not self._hasValue:
			text = ''
		elif self._hasValue:
			shown = self._valueText()
			text = shown if self._template is None else str(self._template).replace('{}', shown)
		else:
			text = '' if self._template is None else str(self._template)
		self._text = text
		self._layoutDirty = True

	def _placeWarped(self, font) -> None:
		"""Bend the text along the warp circle instead of setting it beside the value.
		`gap` and `offset` do not apply: the circle decides where the text sits."""
		gauge = self.gauge
		card = gauge.parentItem() or gauge
		cardRect = gauge.mapRectFromItem(card, card.rect() if hasattr(card, 'rect') else card.boundingRect())
		place = self._warp.resolve(cardRect, (gauge.center, gauge.radius))
		fm = QFontMetricsF(font)
		scale = arcFit(fm.horizontalAdvance(self._text), fm.ascent() + fm.descent(), 1.0, place.radius)
		view = getattr(self.scene(), 'viewScale', None)
		epsilon = 0.25 / ((getattr(view, 'x', 1) or 1) if view is not None else 1)
		path = warp_path(self._text, font, scale, place.radius, place.side, self._warp.mode, epsilon)
		self.prepareGeometryChange()
		self.setPath(path)
		self.setTransform(QTransform().scale(scale, scale))
		self.setRotation(place.rotation)
		self.setPos(place.point)
		color = self._color
		if color is None:
			color = QColor(gauge.defaultColor)
			color.setAlphaF(0.65)
		self.setBrush(QBrush(color))
		self.setZValue(self.Z_VALUE)
		self.show()

	def refresh(self):
		"""Place the text against the centre value. Never raises."""
		gauge = self.gauge
		try:
			if not self._text:
				self.hide()
				return
			font = gauge.tickFont
			font.setPixelSize(max(1, int(size_px(self._size, gauge.radius * 2, dimension=DimensionType.height) or 1)))
			if self._bold:
				font.setWeight(QFont.Weight.Bold)
			path = QPainterPath()
			path.addText(0, 0, font, self._text)
			rect = path.boundingRect()
			if rect.isEmpty():
				self.hide()
				return
			if self._warp is not None:
				self._placeWarped(font)
				return
			self.setTransform(QTransform())
			self.setRotation(0)
			anchor = gauge._valueAnchor()
			gap = size_px(self._gap, gauge.radius * 2, dimension=DimensionType.height) or 0.0
			x = anchor.center().x() - rect.center().x()
			if self._side == 'caption':
				y = anchor.top() - gap - rect.bottom()
			else:
				y = anchor.bottom() + gap - rect.top()
			if self._offset:
				x += self._offset[0] * gauge.radius * 2
				y += self._offset[1] * gauge.radius * 2
			self.prepareGeometryChange()
			self.setPath(path)
			self.setPos(x, y)
			color = self._color
			if color is None:
				color = QColor(gauge.defaultColor)
				color.setAlphaF(0.65)
			self.setBrush(QBrush(color))
			self.setZValue(self.Z_VALUE)
			self.show()
		except Exception as e:  # noqa: BLE001 - layout must never abort a load
			log.warning(f'Gauge {_gaugeKeyName(gauge)} could not place its {self._side}: {e!r}')


class GaugeText(AnnotationText, GaugeItem):
	def __init__(self, *args, **kwargs):
		super(GaugeText, self).__init__(*args, **kwargs)


def _decodeOffset(value) -> Optional[tuple]:
	"""`{x, y}` (or `[x, y]`) as a pair of floats; None for nothing or all zero."""
	if value is None:
		return None
	if isinstance(value, Mapping):
		pair = (value.get('x', 0), value.get('y', 0))
	elif isinstance(value, (list, tuple)) and len(value) == 2:
		pair = tuple(value)
	else:
		raise ValueError(f'offset must be a mapping {{x, y}} or a pair, got {value!r}')
	x, y = float(pair[0]), float(pair[1])
	return None if x == 0 and y == 0 else (x, y)


def _shiftByOffset(box) -> None:
	"""Move a label's text box by its label's `offset`, in the gauge's own coordinates.
	Run after a refit has put the box where the layout wants it, so the shift never builds up."""
	if getattr(box, '_warpActive', False):
		return  # a warped label is pinned to its circle; `offset` would drag it off
	try:
		shift = box.parent.offsetPx()
	except Exception as e:  # noqa: BLE001 - layout must never abort a load
		log.warning(f'could not read a label offset: {e!r}')
		return
	if shift.isNull():
		return
	t = box.transform()
	box.setTransform(QTransform(t.m11(), t.m12(), t.m21(), t.m22(), t.dx() + shift.x(), t.dy() + shift.y()))


class GaugeLabel(NonInteractiveLabel, ColorGradientMixin, GaugeItem):

	def __init__(self, *args, **kwargs):
		GaugeItem.__init__(self, *args, **kwargs)
		assert isinstance(self.gauge, Gauge)
		NonInteractiveLabel.__init__(self, *args, **kwargs)

	def _get_color_value(self) -> Number:
		return self.gauge.value

	def _set_fill_brush(self, color: Color):
		self.textBox.setBrush(QBrush(color))

	@StateProperty(key='visible', default=True, allowNone=False, singleVal=True)
	def visible(self) -> bool:
		# The textBox is reparented to the gauge (see the `valueLabel` factory),
		# so the label wrapper's own visibility says nothing about what is drawn
		# - the textBox is the thing the viewer sees.
		return self.textBox.isVisible()

	@visible.setter
	def visible(self, value: bool):
		self.textBox.setVisible(value)
		if (gauge := self.gauge) is not None:
			# full_gauge_path counts only visible labels, so the cached centre
			# is stale the moment this changes.
			gauge.__dict__.pop('full_gauge_path', None)

	@StateProperty(key='offset', default=None, allowNone=True)
	def offset(self) -> Optional[tuple]:
		"""Shift the label from where it would sit: ``{x, y}`` as shares of the dial's diameter
		(``{x: 0, y: -0.1}`` is a tenth of the diameter up). Gauge Studio writes it when you drag the label."""
		return getattr(self, '_offset', None)

	@offset.setter
	def offset(self, value: Optional[tuple]):
		self._offset = value

	@offset.decode
	def offset(self, value) -> Optional[tuple]:
		return _decodeOffset(value)

	@offset.encode
	def offset(self, value: Optional[tuple]) -> Optional[dict]:
		return None if not value else {'x': round(value[0], 4), 'y': round(value[1], 4)}

	def offsetPx(self) -> QPointF:
		"""`offset` in gauge pixels."""
		value = getattr(self, '_offset', None)
		if not value:
			return QPointF()
		d = self.gauge.radius * 2
		return QPointF(value[0] * d, value[1] * d)


class GaugeValueLabel(GaugeLabel):

	parent: 'Gauge'

	_debug_paint_color = Color.randomColor.QColor

	__defaults__ = {
		'format': {
			# `show_unit` hides the WORD unit - 'mph', 'inHg' - which reads
			# fine as its own label beneath the dial.
			#
			# `unit_symbol` is deliberately NOT set here. It used to be False,
			# which also stripped '%' and '°' - symbols that belong glued to
			# the number, so a humidity gauge read a bare '56'. And it cannot
			# simply be flipped to True: unit_symbol is a *string*, not a
			# flag, so True renders the literal word ('61True'). Omitting it
			# lets each unit class supply its own symbol, which is the point.
			'show_unit': False,
		},
		# Relative, not the absolute 100px this used to be: a gauge is sized
		# by its panel, so a fixed-pixel label is correct at exactly one gauge
		# size and wildly wrong everywhere else - in a small panel it drew the
		# value several times larger than the dial it belonged to.
		'geometry': {
			'x': '0px',
			'y': '0px',
			'width': '45%',
			'height': '28%',
		},
		'margins': ('0', '0', '0', '0'),
	}

	class TextBox(Text):
		parent: 'GaugeValueLabel'
		surface: 'Gauge'

		@Text.alignment.getter
		def alignment(self):
			return self.parent.alignment

		@property
		def _position(self) -> ValueDisplayPosition:
			if (position := self.parent.position) is ValueDisplayPosition.Auto:
				position = self.parent.position_auto()
			return position

		def __rich_repr__(self):
			yield from super().__rich_repr__()
			yield 'alignment', self.alignment

		def _format_value_func(self, value):
			try:
				return self.parent.format_value(value.value)
			except AttributeError:
				return self.parent.format_value(value)

		# def paint(self, painter: QPainter, option, widget):
		# 	f = QRadialGradient(rainbow)
		# 	f.setRadius(max(self.boundingRect().width(), self.boundingRect().height()))
		# 	# f.setCenter(-self.boundingRect().topLeft())
		# 	# f.setFocalPoint(-self.boundingRect().topLeft())
		# 	f.setCoordinateMode(QGradient.CoordinateMode.LogicalMode)
		# 	painter.save()
		# 	# painter.setOpacity(0.5)
		# 	# painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
		#
		# 	shape = self.shape()
		# 	addPath(painter, shape, fill=f, color=Qt.GlobalColor.transparent)
		#
		# 	# shape = self.mapFromParent(self.parentItem()._gauge_path())
		# 	# addPath(painter, shape, fill=QBrush(Qt.GlobalColor.red), color=Qt.GlobalColor.transparent)
		#
		# 	painter.restore()
		# 	super().paint(painter, option, widget)
		#
		# 	painter.setBrush(QBrush(Qt.white))
		# painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Difference)

		# gauge = self.parent.parent
		# for collision_item in self.collidingItems():
		# 	if not gauge.isAncestorOf(collision_item):
		# 		continue
		# 	item_path = self.mapFromItem(collision_item, collision_item.shape())
		# 	painter.drawPath(item_path)

		@property
		def limitRect(self) -> QRectF:
			if self._position in (DisplayPosition.Left, DisplayPosition.Right):
				return self.parent.parent._sideValueRect().translated(-self.pos())
			arc = self.parent.parent.arc.sceneBoundingRect()
			# r = max(arc.width(), arc.height()) / sqrt(2)
			# g = self.parent.parent
			# r = g.radius
			# r /= self.transform().m11()
			# r = QRectF(0, 0, r, r)
			# r.moveCenter(self.mapFromItem(g, g.center))
			r = self.mapRectFromScene(arc)

			# self._debug_paint_shape = rect_to_shape(r)
			return r

		def getTextPosition(self, limitRect: QRectF = None) -> QPointF:

			gauge: Gauge = self.parent.parent
			arc: GaugeArc = gauge.arc

			min_angle, max_angle = sorted((arc.startAngle, arc.endAngle))

			angle_spread = max_angle - min_angle

			# if angle_spread <= 200:
			# 	return gauge.center

			arc_center = arc.mapToParent(arc.path().boundingRect().center())
			gauge_center = gauge.center

			match self._position:
				case ValueDisplayPosition.Left | ValueDisplayPosition.Right:
					# Beside the dial: the middle of the strip the dial left free.
					return gauge._sideValueRect().center()
				case ValueDisplayPosition.Inline:
					diff = arc_center - gauge_center
					return arc_center - (diff * (angle_spread / 360))
				case ValueDisplayPosition.Center:
					return gauge.center
				case ValueDisplayPosition.Top:
					return gauge.center + QPointF(0, max(-gauge.safe_radius, self.mapRectFromItem(gauge, gauge.gaugeRect).top()))
					# return gauge.center + QPointF(0, -gauge.safe_radius)
				case ValueDisplayPosition.Bottom:
					# Stands on the panel's bottom edge, above the strip a unit
					# label below it needs; bottom-aligned, so it grows upward
					# until getTextScale finds it touching the dial. It used to
					# be centred on the arc's lowest point, which left no room
					# under it and none to shrink into.
					return QPointF(gauge.center.x(), gauge.rect().bottom() - self._unit_reserve() - 1)
				case _:
					raise NotImplementedError

		def _valueAccessor(self):
			return self.parent.parent.value

		@defer(pool_attr='action_pool')
		def updateTransform(self, rect: QRectF = None, updateShared: bool = True, updatePath: bool = True, reason: str = None, *args):
			super().updateTransform(rect, updateShared, updatePath, reason=reason, *args)
			_shiftByOffset(self)
			# A refit resets this label to where the fit puts it, and Gauge.recenter
			# is not called again. Re-hang the unit from the value as it now is.
			self.parent.parent._syncUnitUnderValue()
			self.parent.parent._syncCaptions()

		def getTextScale(self, textRect: QRectF = None, limitRect: QRectF = None) -> float:

			"""
			Modifies the local transform until no there are no collisions, restores the original transform and returns the scale.
			"""

			gauge = self.parent.parent
			if self._position in (DisplayPosition.Left, DisplayPosition.Right):
				# The strip beside the dial is empty by construction, so there is
				# nothing to collide with: fit the glyphs to the strip.
				strip = gauge._sideValueRect()
				strip = strip.adjusted(*([self.parent.value_padding_px] * 2), *([-self.parent.value_padding_px] * 2))
				scale = Text.getTextScale(self, textRect, strip.translated(-self.pos()))
				base_path = self.path()
				if (size := self.parent.size) is not None and (glyph_height := base_path.boundingRect().height()) > 0:
					scale = min(scale, size_px(size, gauge.radius * 2) / glyph_height)
				return round(scale, 4)

			scale = super(GaugeValueLabel.TextBox, self).getTextScale()

			gauge_path = gauge._gauge_path()

			if self._position is DisplayPosition.Inline:
				# Without the recenter shift: that shift is computed from this
				# label's size, so fitting against the shifted needle would feed
				# back into the layout it depends on.
				needle = gauge.needle
				unshifted, _ = needle.transform().inverted()
				gauge_path.addPath(gauge.mapFromItem(needle, unshifted.map(needle.shape())))

			# PURE. The base class documents that getTextScale must not mutate
			# the transform, because a SizeGroup calls it on every member to
			# pick a shared scale - and this override used to violate that,
			# applying each trial scale to the live item and asking the scene
			# "am I colliding now?". Probing one member moved it in the scene,
			# which changed the answers for the others, and the group then
			# applied a shared scale that invalidated whatever the probe had
			# concluded. That is why collision fitting and size groups fought
			# each other.
			#
			# The test is the same, done arithmetically: this item's parent IS
			# the gauge (the factory reparents textBox to it), so a transform
			# built from the label's position and a trial scale maps the glyph
			# path into gauge coordinates without touching anything.
			#
			# Built from getTextPosition, NOT self.transform(): updateTransform
			# resets the transform to identity before asking for a scale, so
			# the old copy of it tested every trial at the gauge's top-left
			# corner. That always failed `bounds.contains`, and every gauge
			# value sat on the 0.2 floor whatever room it had.
			base_path = self.path()
			origin = self.getTextPosition(limitRect)
			# Which box the label has to stay inside depends on where it sits.
			# A Center/Inline label lives among the dial's own parts, so the
			# dial's square is the right constraint. A Below/Above one is
			# deliberately OUTSIDE the dial, and judging it against gaugeRect
			# rejected every size that cleared the graduations - the wind value
			# measured 'outside the dial but colliding with nothing' and was
			# shrunk anyway, all the way to the floor. Those positions belong
			# to the panel, not the dial.
			if self._position in (DisplayPosition.Center, DisplayPosition.Inline):
				bounds = gauge.gaugeRect
			else:
				bounds = gauge.rect()

			reserve = self._unit_reserve()
			gap = self.parent.value_padding_px

			# A bottom value hangs under the needle's pivot. The needle is not
			# part of gauge_path here (only an Inline value dodges it), so
			# without this the label grew upward until it touched the arc and
			# covered the hub. Its top must stay below the hub's lowest point.
			hub_bottom = None
			if self._position is DisplayPosition.Below and gauge.needle.type is Needle.Type.Needle:
				needle = gauge.needle
				hub_bottom = gauge.center.y() + needle.offset_px + needle.width_px * 0.6 + gauge.radius * 0.03

			gauge_bounds = gauge_path.boundingRect()

			def collides_at(trial: float) -> bool:
				t = QTransform.fromTranslate(origin.x(), origin.y())
				t.scale(trial, trial)
				candidate = t.map(base_path)
				if hub_bottom is not None and candidate.boundingRect().top() < hub_bottom:
					return True
				if reserve:
					# The unit hangs beneath the value, so the value has to
					# leave it a strip as wide as itself.
					rect = candidate.boundingRect()
					candidate.addRect(QRectF(rect.left(), rect.bottom(), rect.width(), reserve))
				if not bounds.contains(candidate.boundingRect()):
					return True
				# Clear of the dial's parts by a gap, not merely not touching:
				# without one, a bottom value grew until its edge stood against
				# the end tick labels beside it.
				# The padded shape is the glyphs plus a stroke around them.
				# Testing the two against the dial one after the other answers
				# the same as testing their union, which is slow to build. The
				# dial path has thousands of segments, and a boolean test
				# against all of them costs milliseconds per step. Cut it to
				# the box the label can touch first (a rectangle clip is
				# cheap); only the few segments inside are left to test.
				reach = candidate.boundingRect().adjusted(-gap, -gap, gap, gap) if gap else candidate.boundingRect()
				if not reach.intersects(gauge_bounds):
					return False
				clip = QPainterPath()
				clip.addRect(reach.adjusted(-1, -1, 1, 1))
				near = gauge_path.intersected(clip)
				if near.isEmpty():
					return False
				if gap and outline_path(candidate, gap * 2).intersects(near):
					return True
				return candidate.intersects(near)

			# The floor is relative: a bare 0.2 is in glyph-path units, so it
			# meant something different for every font size and stopped the
			# value long before it cleared the dial.
			# Steps of 5% down from the start scale. The answer is the first
			# step that is clear, or the step that reaches the floor. Collision
			# only gets rarer as the label shrinks, so bisect over the step
			# count instead of testing every step in turn.
			floor = scale * 0.2
			start = scale
			steps = 0
			while start * 0.95 ** steps > floor:
				steps += 1
			lo, hi = 0, steps  # the answer is in lo..hi; `hi` is accepted untested
			while lo < hi:
				mid = (lo + hi) // 2
				if collides_at(start * 0.95 ** mid):
					lo = mid + 1
				else:
					hi = mid
			scale = start
			for _ in range(lo):
				scale *= 0.95

			# `size` caps the glyph height at a share of the dial's diameter,
			# so a short value ('N', '0') stays as small as a long one.
			if (size := self.parent.size) is not None and (glyph_height := base_path.boundingRect().height()) > 0:
				scale = min(scale, size_px(size, gauge.radius * 2) / glyph_height)

			return round(scale, 4)

		def _unit_reserve(self) -> float:
			"""Height, in gauge pixels, a visible unit label below the value needs."""
			gauge = self.parent.parent
			unit = getattr(gauge, '_unitLabel', None)
			if not isinstance(unit, GaugeUnit) or not unit.textBox.isVisibleTo(gauge):
				return 0
			try:
				if unit.textBox._position not in _UNIT_UNDER_VALUE:
					return 0
				return unit.height_px + self.parent.value_padding_px
			except Exception as e:  # noqa: BLE001 - sizing must never abort a load
				log.warning(f'Gauge {_gaugeKeyName(gauge)} could not size its unit label: {e!r}')
				return 0

		_shapePath: QPainterPath = QPainterPath()

		def setPath(self, path: QPainterPath):
			matrix = self.transform()
			scale_x = matrix.m11() * self.scale()
			scale_y = matrix.m22() * self.scale()
			scale_value = (self.scaleSelection(scale_x, scale_y) or 1)
			self._debug_paint_shape = self._shape = outline_path(self._shapePath or path, self.parent.value_padding_px / scale_value)
			super().setPath(path)

		_shape: QPainterPath = QPainterPath()

		def setTransform(self, matrix: QTransform, **kwargs) -> None:
			super().setTransform(matrix, **kwargs)
			scale_x = matrix.m11() * self.scale()
			scale_y = matrix.m22() * self.scale()
			scale_value = (self.scaleSelection(scale_x, scale_y) or 1)
			self.prepareGeometryChange()
			self._shape = outline_path(self._shapePath or self.path(), self.parent.value_padding_px / scale_value)

		def shape(self) -> QPainterPath:
			return QPainterPath(self._shape)

		def boundingRect(self) -> QRectF:
			return self._shape.boundingRect()

		def sceneBoundingRect(self) -> QRectF:
			return self.mapToScene(self._shape).boundingRect()

	@StateProperty(key='alignment', allowNone=True, dependencies={'geometry', 'text', 'margins'})
	def alignment(self) -> Alignment:
		return getattr(self, '_alignment', None) or self.alignment_auto()

	@alignment.condition(method='get')
	def alignment(self) -> bool:
		return getattr(self, '_alignment', None) is not None

	@alignment.setter
	def alignment(self, value: Alignment):
		self._alignment = value

	@alignment.decode
	def alignment(self, value: str) -> Alignment:
		return Alignment(AlignmentFlag[value])

	@StateProperty(key='format', default=None, allowNone=False)
	def format_spec(self) -> str | dict:
		return getattr(self, '_format_spec', None)

	@format_spec.setter
	def format_spec(self, value: str | dict):
		self._format_spec = value

	def format_value(self, value: Measurement) -> str:
		format_spec = self.format_spec
		if format_spec == 'duration':
			return formatDuration(value)
		if format_spec is not None:
			if isinstance(value, Measurement):
				match format_spec:
					case str():
						return value.__format__(format_spec)
					case dict():
						return value.__format__('', **format_spec)
		elif value is None:
			return "⋯"
		return str(value)

	@StateProperty(key='size', default=None, allowNone=True)
	def size(self) -> Length | Dimension | None:
		"""
		Largest height of the value text, as a share of the dial's diameter.

		Without it the value grows until it touches the dial, so a short value
		such as 'N' or '0' comes out far larger than '7.4'.

		```yaml
		value-label: {size: 26%}
		```
		"""
		return getattr(self, '_size', None)

	@size.setter
	def size(self, value: Length | Dimension | None):
		self._size = value

	@size.decode
	def size(self, value: str | int | float) -> Length | Dimension | None:
		return parseSize(value, default=None)

	@StateProperty(key='value-padding', default=Size.Height(0.05, relative=True), allowNone=False)
	def value_padding(self) -> Length | Dimension | None:
		return self._value_padding

	@value_padding.setter
	def value_padding(self, value: Length | Dimension | None):
		self._value_padding = value

	@value_padding.decode
	def value_padding(self, value: str | int | float) -> Length | Dimension | None:
		return parseSize(value, default=None)

	@property
	def value_padding_px(self) -> float | int:
		value_padding = self.value_padding
		if value_padding is None:
			return 5
		return size_px(value_padding, (self.textBox._textRect or self.textBox.limitRect).height())

	@StateProperty(key='position', allowNone=False, default=ValueDisplayPosition.Auto, repr=True)
	def position(self) -> ValueDisplayPosition:
		return self._position

	@position.setter
	def position(self, value: ValueDisplayPosition):
		self._position = value

	@position.decode
	def position(self, value: str) -> ValueDisplayPosition:
		return ValueDisplayPosition[value]

	def alignment_auto(self) -> Alignment:
		# TODO: This a quick and slopy implementation and needs improvement

		# match self.position:
		# 	case ValueDisplayPosition.Inline:
		# 		return Alignment(AlignmentFlag.Bottom)
		# 	case _:
		# 		pass
		align = self.parent.alignment.combined

		if (position := self.position) is ValueDisplayPosition.Auto:
			position = self.position_auto()

		# A side value is centred on the middle of its strip.
		if position in (ValueDisplayPosition.Left, ValueDisplayPosition.Right):
			return Alignment(AlignmentFlag.Center)

		# A bottom value stands on the panel's bottom edge and grows upward
		# into the dial's mouth (see TextBox.getTextPosition).
		if position is ValueDisplayPosition.Bottom:
			return Alignment(self.parent.alignment.horizontal | AlignmentFlag.Bottom)

		min_angle, max_angle = sorted((self.parent.startAngle, self.parent.endAngle))

		angle_spread = max_angle - min_angle
		if angle_spread > 180 and position is not ValueDisplayPosition.Inline:
			return Alignment(align)

		angle_mid = ((min_angle + max_angle) / 2 + 90) % 360

		if 60 >= angle_mid or angle_mid >= 300:
			align |= AlignmentFlag.Right
		elif 240 >= angle_mid >= 120:
			align |= AlignmentFlag.Left

		if 135 >= angle_mid >= 45:
			align |= AlignmentFlag.Bottom
		elif 315 >= angle_mid >= 225:
			align |= AlignmentFlag.Top

		return Alignment(align)

	def position_auto(self) -> ValueDisplayPosition:
		if self.gauge.needle.type is Needle.Type.Needle and self.gauge.arc.fullAngle > 180:
			return ValueDisplayPosition.Inline
		return ValueDisplayPosition.Center


class GaugeUnit(GaugeLabel):

	surface: 'Gauge'
	__exclude__ = {'alignment'}

	_debug_paint_color = Color.randomColor.QColor

	__defaults__ = {
		# Relative for the same reason as GaugeValueLabel above.
		'geometry': {
			'x': '0px',
			'y': '0px',
			'width': '30%',
			'height': '14%',
		},
		'margins': ('0', '0', '0', '0'),
	}

	class TextBox(Text):

		surface: 'Gauge'

		@property
		def alignment(self) -> Alignment:
			return Alignment(AlignmentFlag.Center | AlignmentFlag.Top)

		@alignment.setter
		def alignment(self, value):
			pass

		@property
		def _position(self) -> UnitDisplayPosition:
			if (position := self.parent.position) is UnitDisplayPosition.Auto:
				position = self.parent.position_auto()
			return position

		@defer(pool_attr='action_pool')
		def updateTransform(self, rect: QRectF = None, updateShared: bool = True, updatePath: bool = True, reason: str = None, *args):
			super().updateTransform(rect, updateShared, updatePath, reason=reason, *args)
			_shiftByOffset(self)
			# Same as the value label's: a refit puts the unit back at the
			# value's raw box, which is not where it should hang.
			self.parent.parent._syncUnitUnderValue()
			self.parent.parent._syncCaptions()

		def getTextPosition(self, limitRect: QRectF = None) -> QPointF:
			match self._position:
				case UnitDisplayPosition.Below | UnitDisplayPosition.FloatUnder:
					return self._position_below()
				case UnitDisplayPosition.TrailingValue:
					return self._position_trailing_value()
				case _:
					raise NotImplementedError

		def _position_below(self) -> QPointF:
			try:
				value_label = self.surface.valueLabel.textBox.sceneBoundingRect()
				p = value_label.center()
				p.setY(value_label.bottom())
				p = self.mapFromScene(p)
				return p
			except AttributeError:
				pass

			return self.parent.parent.center

		def _position_trailing_value(self) -> QPointF:
			try:
				value_label = self.surface.valueLabel.textBox.sceneBoundingRect()
				p = value_label.bottomLeft()
				return self.mapFromScene(p)
			except AttributeError:
				pass

			return self.parent.parent.center

		def _position_leading_value(self) -> QPointF:
			raise NotImplementedError

		def setPath(self, path):
			self._shape = outline_path(path, self.parent.value_padding_px)
			super().setPath(path)

		_shape: QPainterPath = QPainterPath()

		def shape(self) -> QPainterPath:
			return self._shape

		def boundingRect(self) -> QRectF:
			return self.shape().boundingRect()

		def setTransform(self, *args, **kwargs):
			super().setTransform(*args, **kwargs)

			move_direction = QPointF(0, 1)

			moved_count = 0

			if not self.parentItem().alignment == AlignmentFlag.Center:
				return

			max_travel_distance = int(ceil(sqrt(sum(i ** 2 for i in self.limitRect.size().toTuple()))))

			# Move the unit label away from the value label if it collides with the needle
			# TODO: Make this use transformations rather than moveBy
			while self.collidesWithItem(self.surface.needle) and abs(moved_count) < max_travel_distance:
				self.moveBy(move_direction.x(), move_direction.y())
				moved_count += 1

		def _textAccessor(self) -> str:
			value_class = self.parent.parent.valueClass
			# A key with no unit class (a bare float, e.g. a plugin value whose
			# unit WeatherUnits does not know) has no unit to show. Raising here
			# aborted the whole dashboard load.
			return getattr(value_class, 'unit', None) or getattr(value_class, 'unit_symbol', None) or ''

		@property
		def limitRect(self) -> QRectF:
			arc = self.surface.arc.boundingRect()
			r = max(arc.width(), arc.height()) / sqrt(2)
			r = QRectF(0, 0, r, r)
			r.setHeight(self.parent.height_px)
			return r

	@cached_property
	def value_label(self) -> GaugeValueLabel:
		return self.gauge.valueLabel

	@StateProperty(key='height', default=Length.Millimeter(5), allowNone=False)
	def height(self) -> Measurement | Dimension | None:
		return self._height

	@height.setter
	def height(self, value: Measurement | Dimension | None):
		self._height = value

	@height.decode
	def height(self, value: str | int | float) -> Measurement | Dimension | None:
		return parseSize(value, default=None, allowFloat=False)

	@property
	def height_px(self) -> float | int:
		height = self.height
		if height is None:
			return 0
		return size_px(height, self.height_relative_to)

	@property
	def height_relative_to(self) -> float | int:
		return self.parent.radius

	@StateProperty(key='value-padding', default=Size.Height(0.05, relative=True), allowNone=False)
	def value_padding(self) -> Length | Dimension | None:
		return self._value_padding

	@value_padding.setter
	def value_padding(self, value: Length | Dimension | None):
		self._value_padding = value

	@value_padding.decode
	def value_padding(self, value: str | int | float) -> Length | Dimension | None:
		return parseSize(value, default=None)

	@property
	def value_padding_px(self) -> float | int:
		value_padding = self.value_padding
		if value_padding is None:
			return 5
		return size_px(value_padding, (self.textBox._textRect or self.textBox.limitRect).height())

	@StateProperty(key='position', default=UnitDisplayPosition.Auto, allowNone=False, repr=True)
	def position(self) -> UnitDisplayPosition:
		return self._position

	@position.setter
	def position(self, value: UnitDisplayPosition):
		self._position = value

	# @position.item_default
	# def position(self) -> UnitDisplayPosition:
	# 	label_position = self.value_label.position
	# 	match label_position:
	# 		case ValueDisplayPosition.Auto:
	# 			return self.position_auto()
	# 		case ValueDisplayPosition.Inline | ValueDisplayPosition.Center:
	# 			return UnitDisplayPosition.Below
	#
	# 	return UnitDisplayPosition.Below

	@position.decode
	def position(self, value: str) -> UnitDisplayPosition:
		return UnitDisplayPosition[value]

	def position_auto(self) -> UnitDisplayPosition:
		value_label_position = self.value_label.position
		if value_label_position is ValueDisplayPosition.Auto:
			value_label_position = self.value_label.position_auto()
		match value_label_position:
			case ValueDisplayPosition.Inline | ValueDisplayPosition.Center:
				return UnitDisplayPosition.Below
			case _:
				return UnitDisplayPosition.TrailingValue


@DebugPaint
class Gauge(Display):

	_center_offset: QPointF | QPointF = QPointF(0, 0)

	__value: float = 0.0
	_needleAnimation: QPropertyAnimation
	valueChanged = Signal(float)
	arc: GaugeArc

	class GaugeRange(StatefulGaugeItem):
		_min: Measurement
		_max: Measurement
		valueClass: Type[Measurement]

		ranges = {
			'inhg': MinMax(27, 31),
			'mmhg': MinMax(730, 790),
			'mbar': MinMax(970, 1060),
			'f': MinMax(0, 120),
			'c': MinMax(-20, 50),
			'mph': MinMax(0, 15),
			'in/hr': MinMax(0, 3),
			'mm/hr': MinMax(0, 75),
			'v': MinMax(2.5, 3.3),
			'default': MinMax(0, 120),
			'lux': MinMax(0, 100000),
			'angle': MinMax(0, 360),
			'percentage': MinMax(0, 1),

			CategoryItem('*.humidity.*'):
				MinMax(
					Humidity(0),
					Humidity(1)
				),

			CategoryItem('environment.wind.speed'):
				MinMax(
					Wind.MetersPerSecond(0),
					Wind.MetersPerSecond(10)
				),

			CategoryItem('environment.wind.speed.gust'):
				MinMax(
					Wind.MetersPerSecond(0),
					Wind.MetersPerSecond(35)
				),

		}

		def __init__(self, gauge: 'Gauge', **state):
			super().__init__(gauge, **state)
			self.add_defaults_to_state(state)
			self.state = state

		@StateProperty(key='wrap', default=False, allowNone=False, repr=True)
		def wrap(self) -> bool:
			"""A cyclic scale: a value past the maximum comes round again from the minimum.
			A clock face (0-12 hours) or a bearing (0-360) turns instead of stopping at the end."""
			return self._wrap

		@wrap.setter
		def wrap(self, value: bool):
			self._wrap = bool(value)

		@StateProperty(key='round-to', repr=True)
		def round_to(self) -> int | float:
			return self._round_to

		@round_to.setter
		def round_to(self, value: int | float):
			self._round_to = value

		@round_to.item_default
		def round_to(self) -> int | float:
			span = abs(float(self.max - self.min))
			if 99 < span <= 350:
				return 10
			if log10(span).is_integer():
				return span / 10
			_power = floor(log10(span))
			while _power > -12:
				_divisor = 10 ** _power
				if isclose(span / _divisor, round(span / _divisor), rel_tol=1e-9):
					return _divisor
				_power -= 1
			# Nothing divides it (a span like 1/3): keep rounded_min finite.
			return 10 ** floor(log10(span))

		@StateProperty(key='min', repr=True)
		def min(self) -> Measurement:
			return self._min

		@min.setter
		def min(self, value: Measurement):
			self._reset_cache()
			self._min = value

		@min.decode
		def min(self, value: str | int | float) -> Measurement:
			return decode_measurement(value, self._gauge.valueClass)

		@min.item_default
		def min(self) -> Measurement:
			_type = self._gauge.valueClass
			try:
				limits_min = _type(self.default_range.min)
			except AttributeError:
				limits_min = 0
			if isinf(limits_min):
				limits_min = 0
			return _type(limits_min)

		@min.condition(method='get')
		def min(self, value: Measurement):
			return value != type(value).typedLimits.min

		@cached_property
		def rounded_min(self) -> Measurement:
			round_to = self.round_to
			if not round_to:
				return self.min
			# Round the quotient first: 29.9 / 0.1 is 298.99999999999994, which floors to 29.8.
			return self._gauge.valueClass(floor(round(float(self.min) / round_to, 9)) * round_to)

		@StateProperty(key='max', repr=True)
		def max(self) -> Measurement:
			return self._max

		@max.setter
		def max(self, value: Measurement):
			self._reset_cache()
			self._max = value

		@max.decode
		def max(self, value: str | int | float) -> Measurement:
			return decode_measurement(value, self._gauge.valueClass)

		@max.item_default
		def max(self) -> Measurement:
			_type = self._gauge.valueClass
			try:
				limits_max = _type(self.default_range.max)
			except AttributeError:
				limits_max = 100
			if isinf(limits_max):
				limits_max = 100
			return _type(limits_max)

		@max.condition(method='get')
		def max(self, value: Measurement):
			return value != type(value).typedLimits.max

		@cached_property
		def _rounded_max(self) -> Measurement:
			round_to = self.round_to
			if not round_to:
				return self.max
			return self._gauge.valueClass(ceil(round(float(self.max) / round_to, 9)) * round_to)

		@cached_property
		def rounded_max(self):
			rounded_range = self._rounded_range
			if isinstance(rounded_range, int) or (isinstance(rounded_range, float) and rounded_range.is_integer()):
				if is_prime(rounded_range):
					return self._rounded_max + 1
				return self._rounded_max

			# Count whole round_to steps, as rounded_min does, and add them to rounded_min.
			round_to = self.round_to
			if not round_to:
				return self._rounded_max
			steps = ceil(round(float(rounded_range) / round_to, 9))
			return self._gauge.valueClass(float(self.rounded_min) + steps * round_to)

		@property
		def range(self) -> Measurement:
			return abs(self.max - self.min)

		@range.setter
		def range(self, value: MinMax):
			self.min, self.max = value

		@cached_property
		def rounded_range(self) -> Measurement:
			return abs(self.rounded_max - self.rounded_min)

		@cached_property
		def _rounded_range(self) -> Measurement:
			return abs(self._rounded_max - self.rounded_min)

		@cached_property
		def range_int(self) -> int:
			return int(self.rounded_range)

		@staticmethod
		def _as_value_class(preset: MinMax, value_class) -> MinMax:
			"""Express a preset range in the unit the gauge actually displays.

			The CategoryItem presets are written in the unit the author
			happened to think in - `environment.wind.speed` is stored in m/s -
			but a gauge shows whatever the config localizes to. A US config
			displays mph, so the gauge got a 0-10 range while its needle moved
			in mph, and the graduations came out wrong (the wind dial rendered
			as a bare arc with no ticks at all).

			Conversion, not reinterpretation: MetersPerSecond(10) becomes
			MilesPerHour(22.4), so the dial spans the same real-world range.
			"""
			try:
				return MinMax(value_class(preset.min), value_class(preset.max))
			except Exception:
				# Not convertible (a plain number, or an unrelated dimension) -
				# use it as written rather than losing the preset entirely.
				return preset

		@property
		def default_range(self) -> MinMax:
			_type = self._gauge.valueClass

			try:
				similar_keys = [
					i for i in self.ranges
					if not isinstance(i, str)
						 and self._gauge.parent.key < i
				]
				similar_keys.sort(key=lambda i: len(i), reverse=True)
				for key in similar_keys:
					try:
						return self._as_value_class(self.ranges[key], _type)
					except KeyError:
						pass
			except AttributeError:
				pass

			try:
				if (preset_range := self.ranges.get(_type.unit.lower(), None)) is not None:
					return preset_range
			except AttributeError:
				pass

			try:
				return MinMax(_type.typedLimits.min, _type.typedLimits.max)
			except AttributeError:
				pass

			return MinMax(0, 100)

		def _reset_cache(self):
			clearCacheAttr(self, 'rounded_min', 'rounded_max', '_rounded_max', 'rounded_range', '_rounded_range', 'range_int')

	grads: Graduations
	needleLength = 1.0
	needleWidth = 0.1
	_valueClass: Type[GaugeValue] = float
	_unit: Optional[str] = None
	_scene: QGraphicsScene
	_pen: QPen
	_cache: list
	__value: Union[Numeric, Measurement]

	def _init_defaults_(self):
		self._valueClass = self.parent.container.value_type
		self._markerItems = []
		self._markerSpecs = []
		self._fillItem = None
		self._fillSpec = None
		self._zonesItem = None
		self._zoneSpecs = []
		super()._init_defaults_()
		self.__value = value = self._valueClass(0)

		self._pen = QPen(self.defaultColor)

		self.major_ticks_surface = TickSurface(self, self.majorDivisions)
		self.minor_ticks_surface = TickSurface(self, self.minorDivisions)
		self.micro_ticks_surface = TickSurface(self, self.microDivisions)
		self.hide()
	# a = self.arc
	# self.unitLabel = unit_label = GaugeUnit(self)

	@StateProperty(key='range', link=GaugeRange, allowNone=False, repr=True, sortOrder=-2)
	def range(self) -> GaugeRange:
		return self._range

	@range.setter
	def range(self, value: GaugeRange):
		self._range = value

	@range.factory
	def range(self) -> GaugeRange:
		return Gauge.GaugeRange(self)

	@range.after
	def range(self):
		self.rebuild()

	@StateProperty(key='radius', default=Size.Height(1.0, relative=True), allowNone=False, repr=True, sortOrder=-1)
	def _radius(self) -> Length | Size.Height:
		return self._s_radius

	@_radius.setter
	def _radius(self, value: Length | Size.Height):
		self._s_radius = value

	@_radius.decode
	def _radius(self, value: int | float | str) -> Length | Size.Height:
		return parseSize(value, allowFloat=False, dimension=DimensionType.height)

	@_radius.encode
	def _radius(self, value: Length | Size.Height) -> str:
		return str(value)

	@StateProperty(key='arc', repr=True, dependencies={'radius'})
	def arc(self) -> GaugeArc:
		return self._arc

	@arc.factory
	def arc(self) -> GaugeArc:
		return GaugeArc(self)

	@arc.setter
	def arc(self, value: GaugeArc):
		self._arc = value

	@StateProperty(key='needle', repr=True)
	def needle(self) -> Needle:
		return self._needle

	@needle.factory
	def needle(self) -> Needle:
		return Needle(self)

	@needle.setter
	def needle(self, value: Needle):
		self._needle = value

	@StateProperty(key='fill', default=None, allowNone=True, dependencies={'range', 'arc'})
	def fill(self) -> Optional[dict]:
		"""A value-driven arc over the track: ``{from, to, weight, color}``.

		Kept as the plain mapping the user wrote; the scene item is ``self._fillItem``.
		"""
		return self._fillSpec

	@fill.setter
	def fill(self, value: Optional[dict]):
		self._clearFill()
		if not value:
			return
		# A bad fill is a warning, never a failed dashboard load.
		try:
			item = GaugeFill(self)
			item.configure(value)
		except Exception as e:
			log.warning(f'Gauge {_gaugeKeyName(self)} fill skipped: {e}')
			return
		self._fillItem = item
		self._fillSpec = copy.deepcopy(dict(value))

	@fill.decode
	def fill(self, value) -> Optional[dict]:
		if value is None:
			return None
		if not isinstance(value, Mapping):
			log.warning(f'Gauge {_gaugeKeyName(self)} ignored fill {value!r}: expected a mapping')
			return None
		return dict(value)

	@fill.encode
	def fill(self, value: Optional[dict]) -> Optional[dict]:
		return copy.deepcopy(value) if value else None

	def _clearFill(self):
		item = self._fillItem
		self._fillItem = None
		if item is not None:
			item.close()
		self._fillSpec = None
		if item is not None and (scene := item.scene()) is not None:
			scene.removeItem(item)

	_captionItem: Optional[GaugeCaption] = None
	_captionSpec = None
	_subItem: Optional[GaugeCaption] = None
	_subSpec = None

	def _setCaption(self, attr: str, specAttr: str, side: str, value) -> None:
		self._clearCaption(attr, specAttr)
		if not value:
			return
		# A bad caption is a warning, never a failed dashboard load.
		try:
			item = GaugeCaption(self, side)
			item.configure(value)
		except Exception as e:
			log.warning(f'Gauge {_gaugeKeyName(self)} {side} skipped: {e}')
			return
		setattr(self, attr, item)
		setattr(self, specAttr, copy.deepcopy(value))

	def _clearCaption(self, attr: str, specAttr: str) -> None:
		item = getattr(self, attr)
		setattr(self, attr, None)
		setattr(self, specAttr, None)
		if item is not None:
			item.close()
			if (scene := item.scene()) is not None:
				scene.removeItem(item)

	@staticmethod
	def _decodeCaption(value):
		if value is None or isinstance(value, (str, Mapping)):
			return value if not isinstance(value, Mapping) else dict(value)
		log.warning(f'ignored caption {value!r}: expected text or a mapping')
		return None

	@StateProperty(key='caption', default=None, allowNone=True, dependencies={'range', 'arc'})
	def caption(self) -> Optional[dict | str]:
		"""Small text above the centre value: a string, or ``{text, value, format, size, color}``."""
		return self._captionSpec

	@caption.setter
	def caption(self, value):
		self._setCaption('_captionItem', '_captionSpec', 'caption', value)

	@caption.decode
	def caption(self, value):
		return Gauge._decodeCaption(value)

	@caption.encode
	def caption(self, value):
		return copy.deepcopy(value) if value else None

	@StateProperty(key='sub-label', default=None, allowNone=True, dependencies={'range', 'arc'})
	def subLabel(self) -> Optional[dict | str]:
		"""Small text below the centre value (and its unit): same forms as ``caption``."""
		return self._subSpec

	@subLabel.setter
	def subLabel(self, value):
		self._setCaption('_subItem', '_subSpec', 'sub-label', value)

	@subLabel.decode
	def subLabel(self, value):
		return Gauge._decodeCaption(value)

	@subLabel.encode
	def subLabel(self, value):
		return copy.deepcopy(value) if value else None

	def _captionItems(self) -> list:
		return [i for i in (self._captionItem, self._subItem) if i is not None]

	def _valueAnchor(self) -> QRectF:
		"""The box the centre value (and a unit hung under it) occupies, in gauge coordinates.
		With no visible value, a point at the dial's centre."""
		rects = []
		vbox = self.valueLabel.textBox
		try:
			if vbox.isVisibleTo(self):
				r = self.mapRectFromScene(vbox.scenePath().boundingRect())
				if not r.isEmpty():
					rects.append(r)
			ubox = self.unitLabel.textBox
			if rects and ubox.isVisibleTo(self) and ubox._position in _UNIT_UNDER_VALUE:
				r = self.mapRectFromScene(ubox.scenePath().boundingRect())
				if not r.isEmpty():
					rects.append(r)
		except Exception as e:  # noqa: BLE001
			log.warning(f'Gauge {_gaugeKeyName(self)} could not measure its value: {e!r}')
		if not rects:
			return QRectF(self.center, QSizeF(0, 0))
		box = rects[0]
		for r in rects[1:]:
			box = box.united(r)
		return box

	def _syncCaptions(self):
		for item in self._captionItems():
			item.refresh()

	@StateProperty(key='zones', default=None, allowNone=True, dependencies={'range', 'arc'})
	def zones(self) -> Optional[list]:
		"""Coloured bands on the track: a list of ``{from, to, color, mark}`` mappings.

		Kept as the plain mappings the user wrote; the scene item is ``self._zonesItem``.
		"""
		return self._zoneSpecs or None

	@zones.setter
	def zones(self, value: Optional[list]):
		self._clearZones()
		if not value:
			return
		try:
			item = GaugeZones(self)
			kept = item.configure(value)
		except Exception as e:
			log.warning(f'Gauge {_gaugeKeyName(self)} zones skipped: {e}')
			return
		if not kept:
			scene = item.scene()
			if scene is not None:
				scene.removeItem(item)
			return
		self._zonesItem = item
		self._zoneSpecs = kept
		try:
			item.refresh()
		except Exception as e:
			log.debug(f'Gauge {_gaugeKeyName(self)} zones not drawn yet: {e}')

	@zones.decode
	def zones(self, value) -> list:
		if isinstance(value, Mapping):
			value = [value]
		if not isinstance(value, (list, tuple)):
			log.warning(f'Gauge {_gaugeKeyName(self)} ignored zones {value!r}: expected a list')
			return []
		for spec in value:
			if not isinstance(spec, Mapping):
				log.warning(f'Gauge {_gaugeKeyName(self)} skipped zone {spec!r}: expected a mapping')
		return [dict(spec) for spec in value if isinstance(spec, Mapping)]

	@zones.encode
	def zones(self, value: Optional[list]) -> Optional[list]:
		return copy.deepcopy(value) if value else None

	def _clearZones(self):
		item = self._zonesItem
		self._zonesItem = None
		self._zoneSpecs = []
		if item is not None:
			item.close()
			if (scene := item.scene()) is not None:
				scene.removeItem(item)

	@StateProperty(key='markers', default=None, allowNone=True, dependencies={'range', 'needle'})
	def markers(self) -> Optional[list]:
		"""Extra indicators: a list of ``{value, type, color, ...}`` mappings.

		Kept as the plain mappings the user wrote, so saving writes them back
		unchanged. The scene items built from them are ``self._markerItems``.
		"""
		return self._markerSpecs or None

	@markers.setter
	def markers(self, value: Optional[list]):
		self._clearMarkers()
		specs = []
		for spec in value or []:
			# One bad marker is skipped; it must never abort the dashboard load.
			try:
				marker = GaugeMarker(self)
				marker.configure(spec)
			except Exception as e:
				log.warning(f'Gauge {_gaugeKeyName(self)} skipped marker {_markerText(spec)!r}: {e}')
				try:
					marker.close()
					self.scene().removeItem(marker)
				except Exception:
					pass
				continue
			self._markerItems.append(marker)
			specs.append(copy.deepcopy(dict(spec)))
		self._markerSpecs = specs

	@markers.decode
	def markers(self, value) -> list:
		if isinstance(value, Mapping):
			value = [value]
		if not isinstance(value, (list, tuple)):
			log.warning(f'Gauge {_gaugeKeyName(self)} ignored markers {value!r}: expected a list')
			return []
		valid = []
		for spec in value:
			if isinstance(spec, Mapping):
				valid.append(dict(spec))
			else:
				log.warning(f'Gauge {_gaugeKeyName(self)} skipped marker {spec!r}: expected a mapping with a value')
		return valid

	@markers.encode
	def markers(self, value: Optional[list]) -> Optional[list]:
		return copy.deepcopy(value) if value else None

	def _clearMarkers(self):
		for marker in self._markerItems:
			marker.close()
			if (scene := marker.scene()) is not None:
				scene.removeItem(marker)
		self._markerItems = []
		self._markerSpecs = []

	def releaseSources(self):
		"""Stop and release every value source the markers and fill hold.
		Called when the owning panel is deleted; never raises."""
		for clear in (self._clearMarkers, self._clearFill, self._clearZones,
					lambda: self._clearCaption('_captionItem', '_captionSpec'),
					lambda: self._clearCaption('_subItem', '_subSpec')):
			try:
				clear()
			except Exception as e:
				log.warning(f'Gauge {_gaugeKeyName(self)} could not release its value sources: {e!r}')

	@StateProperty(key='major', repr=True, dependencies={'range'})
	def majorDivisions(self) -> Graduations:
		return self._majorDivisions

	@majorDivisions.factory
	def majorDivisions(self):
		return Graduations(gauge=self, type=Graduations.Type.Major)

	@majorDivisions.setter
	def majorDivisions(self, value: Graduations):
		self._majorDivisions = value

	@StateProperty(key='minor', repr=True, dependencies={'majorDivisions'})
	def minorDivisions(self) -> Graduations:
		return self._minorDivisions

	@minorDivisions.factory
	def minorDivisions(self):
		return Graduations(gauge=self, type=Graduations.Type.Minor)

	@minorDivisions.setter
	def minorDivisions(self, value: Graduations):
		self._minorDivisions = value

	@StateProperty(key='micro', repr=True, dependencies={'minorDivisions'})
	def microDivisions(self) -> Graduations:
		return self._microDivisions

	@microDivisions.factory
	def microDivisions(self):
		return Graduations(gauge=self, type=Graduations.Type.Micro)

	@microDivisions.setter
	def microDivisions(self, value: Graduations):
		self._microDivisions = value

	@StateProperty(key='value-label', repr=True)
	def valueLabel(self) -> GaugeValueLabel:
		return self._valueLabel

	@valueLabel.factory
	def valueLabel(self) -> GaugeValueLabel:
		label = GaugeValueLabel(self)
		label.textBox.setParentItem(self)
		label.hide()
		# NB: the textBox was reparented to the gauge above, so it is no longer
		# a child of the label and `label.hide()` does not reach it. The value
		# text is what the viewer actually sees, so it stays visible - the
		# label wrapper being hidden is incidental.
		return label

	@valueLabel.setter
	def valueLabel(self, value: GaugeValueLabel):
		self._valueLabel = value

	@valueLabel.decode
	def valueLabel(self, value) -> GaugeValueLabel:
		# `value-label: {visible: false}` arrives as a plain mapping. Without a
		# decoder the setter stored it verbatim, and `_afterSetState` -> refresh()
		# then reached `self.valueLabel.textBox` on a dict. That AttributeError
		# aborted the whole dashboard load, which is what left a board showing
		# nothing but the moon. See docs/tasks/dashboard-wont-load.md.
		return self._buildLabel('_valueLabel', GaugeValueLabel, value)

	@StateProperty(key='unit-label', repr=True)
	def unitLabel(self) -> GaugeUnit:
		return self._unitLabel

	@unitLabel.factory
	def unitLabel(self) -> GaugeUnit:
		label = GaugeUnit(self)
		label.textBox.setParentItem(self)
		label.hide()
		label.textBox.hide()
		return label

	@unitLabel.setter
	def unitLabel(self, value: GaugeUnit):
		self._unitLabel = value

	@unitLabel.decode
	def unitLabel(self, value) -> GaugeUnit:
		return self._buildLabel('_unitLabel', GaugeUnit, value)

	def _buildLabel(self, attr: str, labelType: type, value):
		"""Turn a `value-label`/`unit-label` mapping into a real label.

		Reuses the label already on the gauge when there is one, so a reload
		applies onto the existing item rather than orphaning it and building a
		second.
		"""
		if not isinstance(value, Mapping):
			return value
		label = getattr(self, attr, None)
		if not isinstance(label, labelType):
			label = labelType(self)
			label.textBox.setParentItem(self)
			label.hide()
		try:
			label.state = dict(value)
		except Exception as e:  # noqa: BLE001 - a bad key must not abort the load
			log.warning(f'{self}: could not apply {labelType.__name__} state {value!r}: {e}')
		return label

	@property
	def type(self):
		return DisplayType.Gauge

	@property
	def displayType(self):
		return DisplayType.Gauge

	def __init__(self, parent, *args, **kwargs):
		self.previousParent = None
		super(Gauge, self).__init__(parent, *args, **kwargs)

	@property
	def startAngle(self) -> float:
		return self.arc.startAngle

	@property
	def leading_angle(self) -> float:
		"""Left side of the arc."""
		angle = sorted([self.startAngle, self.endAngle])[1]
		return angle % 360

	@property
	def endAngle(self) -> float:
		return self.arc.endAngle

	@property
	def trailing_angle(self) -> float:
		"""Right side of the arc."""
		angle = sorted([self.startAngle, self.endAngle])[0]
		return angle % 360

	def convert_gradient(self, gradient: 'Gradient') -> QConicalGradient:
		_type = self.valueClass
		rounded_min = self._range.rounded_min
		rounded_max = self._range.rounded_max
		if not issubclass(gradient.itemCls.__item__, _type):
			gradient = gradient.as_type(_type, rounded_min, rounded_max)
		return gradient.toQConicalGradient(
			start_angle=self.startAngle,
			stop_angle=self.endAngle,
			min_value=rounded_min,
			max_value=rounded_max,
		)

	def map_gradient_to(self, gradient: 'Gradient', item: QGraphicsPathItem | Surface = None) -> QConicalGradient:
		gradient = self.convert_gradient(gradient)
		gradient.setCenter(self._center_transform.map(self.mapToItem(item or self, self.center)))
		return gradient

	def _afterSetState(self):
		super()._afterSetState()

		self.refresh()

	_center_transform: QTransform = QTransform()
	#: The shift recenter() last applied to the needle, markers, arc, fills and ticks.
	_recenterTransform: QTransform = QTransform()

	# def paint(self, painter, option, widget):
	# 	super().paint(painter, option, widget)
	#
	# 	if issubclass(self.valueClass, Temperature):
	# 		f = self.get_gradient_for(self)
	# 	else:
	# 		f = QColor(self.defaultColor)
	#
	# 	# shape = self._shape()
	# 	shape = QPainterPath()
	# 	rect = self.gaugeRect
	# 	rect.moveCenter(self.center)
	# 	shape.addEllipse(rect)
	# 	addPath(painter, shape, fill=f)
	# 	addCrosshair(painter, pos=self._shape().boundingRect().center())
	# 	addCrosshair(painter, pos=option.rect.center())

	def recenter(self):

		bounds_rect = self._dialRect()

		# Measure at identity. `full_gauge_path` maps every child through its
		# CURRENT transform, so measuring while a previous centering is still
		# applied reports an already-centred shape, yields ~zero offset, and
		# the `setTransform(t, combine=False)` below then REPLACES the good
		# transform with a near-identity one - snapping the ticks back to
		# their uncentred position while the arc, drawn centred in its own
		# local space, appears to stay put. That is the "correct for a split
		# second, then jump" behaviour: the first pass centres correctly and
		# the second undoes it.
		centred_items = (
			self.needle, self.arc, *self._zoneItems(), *self._markerItems, *self._fillItems(),
			self.major_ticks_surface, self.minor_ticks_surface, self.micro_ticks_surface,
		)
		for item in centred_items:
			item.resetTransform()

		self._update_shape()
		own_shape = self.full_gauge_path
		own_shape_rect = own_shape.boundingRect()

		panel_center = bounds_rect.center()
		shape_center = own_shape_rect.center()
		center_offset = shape_center - panel_center

		t = QTransform()

		alignment = self.alignment

		if alignment.vertical.isCenter:
			t.translate(0, -center_offset.y())
		else:
			if own_shape_rect.height() >= bounds_rect.height():
				t.translate(0, bounds_rect.center().y() - own_shape_rect.center().y())
			elif own_shape_rect.top() <= bounds_rect.top():
				t.translate(0, bounds_rect.top() - own_shape_rect.top())
			elif own_shape_rect.bottom() >= bounds_rect.bottom():
				t.translate(0, bounds_rect.bottom() - own_shape_rect.bottom())

		if alignment.horizontal.isCenter:
			t.translate(-center_offset.x(), 0)
		else:
			if own_shape_rect.width() >= bounds_rect.width():
				t.translate(bounds_rect.center().x() - own_shape_rect.center().x(), 0)
			elif own_shape_rect.left() <= bounds_rect.left():
				t.translate(bounds_rect.left() - own_shape_rect.left(), 0)
			elif own_shape_rect.right() >= bounds_rect.right():
				t.translate(bounds_rect.right() - own_shape_rect.right(), 0)

		if self._anchor is not None:
			# The pivot is already where `anchor` put it; nothing to centre.
			t = QTransform()

		self._center_transform = QTransform()
		self._recenterTransform = QTransform(t)

		self.needle.setTransform(t, combine=False)
		for marker in self._markerItems:
			marker.setTransform(t, combine=False)
		self.arc.setTransform(t, combine=False)
		for item in self._zoneItems():
			item.setTransform(t, combine=False)
		for item in self._fillItems():
			item.setTransform(t, combine=False)

		# TODO: After transformation is set, the labels are not moved
		# correctly thus the 'refresh' method must be called after.
		# This needs to be corrected
		self.major_ticks_surface.setTransform(t, combine=False)
		self.majorDivisions.labels.refresh()
		self.minor_ticks_surface.setTransform(t, combine=False)
		self.minorDivisions.labels.refresh()
		self.micro_ticks_surface.setTransform(t, combine=False)
		self.microDivisions.labels.refresh()

		self.valueLabel.textBox.updateTransform(updatePath=False, reason='recenter')
		if self._valueSide() is None:
			self.valueLabel.textBox.setTransform(t, combine=True)

		self.unitLabel.textBox.updateTransform(updatePath=False, reason='recenter')
		self.unitLabel.textBox.setTransform(t, combine=True)

		self._syncUnitUnderValue()
		self._syncCaptions()

	def _syncUnitUnderValue(self):
		"""Hang a `float-under`/`below` unit under the value's final glyphs.

		The unit places itself from the value's box while both are still being
		laid out, and recenter() then shifts each again, so where it landed
		depended on update order - over the value as often as under it. Run
		last, against the glyphs as drawn: the gauge's version of Realtime's
		_syncFloatUnderPair.
		"""
		unit, value = getattr(self, '_unitLabel', None), getattr(self, '_valueLabel', None)
		if not isinstance(unit, GaugeUnit) or not isinstance(value, GaugeValueLabel):
			return
		ubox, vbox = unit.textBox, value.textBox
		try:
			if not ubox.isVisibleTo(self) or ubox._position not in _UNIT_UNDER_VALUE or ubox._warpActive:
				return
			v = self.mapRectFromScene(vbox.scenePath().boundingRect())
			u = self.mapRectFromScene(ubox.scenePath().boundingRect())
		except Exception as e:  # noqa: BLE001 - layout must never abort a load
			log.warning(f'Gauge {_gaugeKeyName(self)} could not place its unit label: {e!r}')
			return
		if v.isEmpty() or u.isEmpty():
			return
		# A third of the unit's own height: reads as one block, never touches.
		shift = unit.offsetPx()
		dx = v.center().x() - u.center().x() + shift.x()
		dy = v.bottom() + u.height() / 3 - u.top() + shift.y()
		t = ubox.transform()
		# Shift the translation part only, in gauge coordinates.
		ubox.setTransform(QTransform(t.m11(), t.m12(), t.m21(), t.m22(), t.dx() + dx, t.dy() + dy))

	@defer
	def rebuild(self):
		self.major_ticks_surface.rebuild()
		self.minor_ticks_surface.rebuild()
		self.micro_ticks_surface.rebuild()

		self.refresh()

	def refresh(self):
		self.arc.refresh()
		for item in self._zoneItems():
			item.refresh()
		for item in self._fillItems():
			item.refresh()
		self.needle.refresh()
		for marker in self._markerItems:
			marker.refresh()

		self.major_ticks_surface.refresh()
		self.minor_ticks_surface.refresh()
		self.micro_ticks_surface.refresh()

		self._update_shape()
		# Defensive: refresh() runs from _afterSetState, which is inside the
		# dashboard load. Anything raising here aborts the *whole* load, so a
		# single malformed gauge used to leave a board with nothing on it. A
		# label that is not a label is worth a warning, not an empty screen.
		for label in (self.valueLabel, self.unitLabel):
			textBox = getattr(label, 'textBox', None)
			if textBox is None:
				log.warning(f'{self}: {type(label).__name__} has no textBox; skipping its refresh')
				continue
			textBox.refresh()
		self.recenter()

	def _update_shape(self):
		clearCacheAttr(self, 'value_text_box_area_rect', 'full_gauge_path')

	def parentResized(self, arg: Union[QPointF, QSizeF, QRectF]):
		super().parentResized(arg)
		self.refresh()

	_value: GaugeValue = 0

	@property
	def value(self) -> GaugeValue:
		return self._value

	@value.setter
	def value(self, value):
		if isinstance(value, (int, float)):
			self.valueClass = value
			if float(value) == float(self._value):
				return
			self._value = value
			self.valueLabel.textBox.refresh()
			self.unitLabel.textBox.refresh()
			self.needle.refresh()
			for item in self._fillItems():
				item.refresh()
			self._update_shape()

	def _zoneItems(self) -> list:
		item = getattr(self, '_zonesItem', None)
		return [] if item is None else [item]

	def _fillItems(self) -> list:
		item = getattr(self, '_fillItem', None)
		return [] if item is None else [item]

	def value_to_angle(self, value: Numeric) -> Angle:
		angle = float(value - self._range.rounded_min) / self._range.rounded_range * self.fullAngle + self.startAngle
		return Angle(sorted((self.startAngle, angle, self.endAngle))[1])

	@property
	def valueClass(self) -> Type[GaugeValue]:
		return self._valueClass

	@valueClass.setter
	def valueClass(self, value):
		if not isinstance(value, type):
			value = type(value)
		if value is self._valueClass:
			return

		self._valueClass = value

		self.rebuild()

	@Slot(float)
	def updateSlot(self, value: Union[Measurement, Numeric]):
		if isinstance(value, (int, float)):
			self.valueClass = value

	def animateValue(self, start: Numeric, end: Numeric):
		if self._needleAnimation.state() == QtCore.QAbstractAnimation.Running:
			self._needleAnimation.stop()
		self._needleAnimation.setStartValue(float(start))
		self._needleAnimation.setEndValue(float(end))
		self._needleAnimation.start()

	@property
	def pen(self):
		return self._pen

	@StateProperty(key='alignment', allowNone=False, after=rebuild, repr=True)
	def alignment(self) -> Alignment:
		return self._alignment

	@alignment.setter
	def alignment(self, value: Alignment):
		self._alignment = value

	@alignment.item_default
	def alignment(self) -> Alignment:
		return Alignment(AlignmentFlag.Center)

	@alignment.decode
	def alignment(self, value: str | int | tuple[AlignmentFlag, AlignmentFlag] | AlignmentFlag) -> Alignment:
		if isinstance(value, (str, int)):
			alignment = AlignmentFlag[value]
		elif value is None:
			alignment = AlignmentFlag.Center
		elif isinstance(value, tuple):
			return Alignment(*value)
		else:
			alignment = AlignmentFlag.Center
		return Alignment(alignment)

	#: Corner names `anchor` accepts, as the (x, y) share of the box the pivot sits at.
	_ANCHORS = {
		'top-left': (0, 0), 'top-right': (1, 0),
		'bottom-left': (0, 1), 'bottom-right': (1, 1),
	}
	_anchor: Optional[str] = None
	_s_inset = Size.Height(0.0, relative=True)

	@StateProperty(key='anchor', default=None, allowNone=True, after=rebuild, repr=True)
	def anchor(self) -> Optional[str]:
		"""Pin the pivot (the arc centre) to a corner of the box: ``top-left``, ``top-right``,
		``bottom-left`` or ``bottom-right``. ``radius`` then counts from the box's short side, so
		100% is the whole short side minus ``inset``. Use it for a quarter-circle dial that fills
		a card. Without it the dial is centred as before."""
		return self._anchor

	@anchor.setter
	def anchor(self, value: Optional[str]):
		self._anchor = value

	@anchor.decode
	def anchor(self, value) -> Optional[str]:
		if value is None:
			return None
		name = normalizeCorner(value)
		if name not in Gauge._ANCHORS:
			raise ValueError(f'anchor must be one of {sorted(Gauge._ANCHORS)}, got {value!r}')
		return name

	@StateProperty(key='inset', default=Size.Height(0.0, relative=True), allowNone=False, after=rebuild)
	def inset(self) -> Length | Size.Height:
		"""Gap between an `anchor`ed pivot and the box's two edges at that corner."""
		return self._s_inset

	@inset.setter
	def inset(self, value):
		self._s_inset = value

	@inset.decode
	def inset(self, value) -> Length | Size.Height:
		return parseSize(value, allowFloat=False, dimension=DimensionType.height)

	@inset.encode
	def inset(self, value) -> str:
		return str(value)

	@property
	def insetPx(self) -> float:
		if self._anchor is None:
			return 0.0
		return max(size_px(self._s_inset, min(self.height(), self.width())), 0.0)

	def update_center_offset(self, offset: QPointF):
		self._center_offset = offset

	@StateProperty(key='center_offset', allowNone=True, after=rebuild, repr=True)
	def center_offset(self) -> QPointF:
		return getattr(self, '_center_offset', QPointF())

	@center_offset.setter
	def center_offset(self, value: QPointF):
		self._center_offset = value

	@center_offset.decode
	def center_offset(self, value: str | Sequence | dict) -> QPointF:
		if isinstance(value, str):
			value = value.split(',')

		if len(value) != 2:
			raise ValueError(f'center_offset must be a sequence or mapping of length 2, got {len(value)}')

		if isinstance(value, dict):
			x = parseX(value.get('x', 0), 0)
			y = parseY(value.get('y', 0), 0)
		else:
			x = parseX(value[0], 0)
			y = parseY(value[1], 0)
		return QPointF(x, y)

	@center_offset.encode
	def center_offset(self, value: QPointF) -> dict[str, float]:
		return {'x': round(value.x(), 3), 'y': round(value.y(), 3)}

	def _valueSide(self) -> Optional[ValueDisplayPosition]:
		"""`left` or `right` when the value label is set to sit beside the dial, else None."""
		label = getattr(self, '_valueLabel', None)
		position = getattr(label, '_position', None)
		if position in (ValueDisplayPosition.Left, ValueDisplayPosition.Right):
			return position
		return None

	def _sideStripWidth(self) -> float:
		"""Width the box gives a value beside the dial, from the far edge to the dial's."""
		if self._valueSide() is None:
			return 0.0
		width, height = self.width(), self.height()
		# A wide box keeps the dial at full height and gives the value what is left;
		# a narrow one shares the width, the dial taking the larger part.
		return min(width * 0.5, max(width * 0.34, width - height))

	def _dialRect(self) -> QRectF:
		"""The part of the box the dial lives in: all of it, less the strip a side value takes."""
		rect = QRectF(self.rect())
		side = self._valueSide()
		if side is None:
			return rect
		strip = self._sideStripWidth()
		if side is ValueDisplayPosition.Left:
			rect.setLeft(rect.left() + strip)
		else:
			rect.setRight(rect.right() - strip)
		return rect

	def _sideValueRect(self) -> QRectF:
		"""The strip beside the dial a `left`/`right` value is fitted to, in gauge coordinates.
		Centred on the pivot, so a value stays level with it however the sweep is cut."""
		rect = self.rect()
		strip = self._sideStripWidth()
		# A pinned pivot sits in a corner, so level with the box's middle instead.
		pivot_y = self.rect().center().y() if self._anchor is not None else self.center.y() + self._recenterTransform.dy()
		half = max(min(pivot_y - rect.top(), rect.bottom() - pivot_y), 1.0)
		left = rect.left() if self._valueSide() is ValueDisplayPosition.Left else rect.right() - strip
		return QRectF(left, pivot_y - half, strip, half * 2)

	@property
	def center(self) -> QPointF:

		if self._anchor is not None:
			fx, fy = self._ANCHORS[self._anchor]
			rect, inset = self._dialRect(), self.insetPx
			return QPointF(
				rect.left() + inset if fx == 0 else rect.right() - inset,
				rect.top() + inset if fy == 0 else rect.bottom() - inset,
			)

		p = self.alignment.multipliersAlt
		rect = self.boundingRect()
		x = rect.width() * p[0]
		y = rect.height() * p[1]
		p = QPointF(x, y)

		p -= self._center_offset
		if self._valueSide() is not None:
			p.setX(p.x() + self._dialRect().center().x() - self.rect().center().x())
		margin_rect = self.marginRect
		# keep p within the bounding rect
		p.setX(sorted((margin_rect.left(), p.x(), margin_rect.right()))[1])
		p.setY(sorted((margin_rect.top(), p.y(), margin_rect.bottom()))[1])

		return p

	@property
	def scene_center(self) -> QPointF:
		return self.mapToScene(self.center)

	@property
	def baseWidth(self):
		return sqrt(self.height() ** 2 + self.width() ** 2) * INVERSE_GOLDEN_RATIO * 0.01

	@property
	def radius_max(self):
		if self._anchor is not None:
			# The pivot is in a corner, so the dial may reach the whole short side.
			return max(min(self.height(), self._dialRect().width()) - self.insetPx - self.baseWidth, 1)
		return max(min(self.height(), self._dialRect().width()) / 2 - self.baseWidth, 1)

	@property
	def radius(self):
		return min(self.radius_max, self._radius)

	@property
	def radius(self) -> float:
		radius_max = self.radius_max
		return min(size_px(self._radius, radius_max), radius_max * 2)

	@property
	def gaugeRect(self) -> QRectF:
		f = QRectF(0.0, 0.0, self.radius * 2, self.radius * 2)
		f.moveCenter(self.rect().center())
		return f

	@property
	def fullAngle(self):
		return abs(self.endAngle + -self.startAngle)

	@property
	def defaultColor(self):
		return Color.text.QColor

	@property
	def tickFont(self):
		font = QFont()
		font.setPointSizeF(max(self.radius * .1, 18))
		return font

	def setRect(self, *args, **kwargs):
		super().setRect(*args, **kwargs)

	@property
	def duration(self):
		return self._needleAnimation.duration()

	@duration.setter
	def duration(self, value):
		self._needleAnimation.setDuration(value)

	@property
	def easing(self):
		return self._needleAnimation.getEasingCurve()

	@easing.setter
	def easing(self, value: QEasingCurve):
		if isinstance(QEasingCurve, value):
			self._needleAnimation.setEasingCurve(value)
		else:
			print('Not a valid easing curve')

	@property
	def arc_length(self) -> float:
		radius_px = self.radius
		return float(radius_px * self.fullAngle / 180 * pi)

	def sizeAcross(self, value, dimension: Optional[DimensionType] = None):
		"""A relative size resolved across the track - against the dial's radius.

		The reference, not the quantity: `sizeAcross(self.width)` asks how wide
		something is in dial terms. A bar answers the same question with its own
		cross extent, so an element drawn on either asks the meter for this rather
		than reaching for a radius it may not have.
		"""
		return size_px(value, self.radius, dimension=dimension)

	def sizeAlong(self, value, dimension: Optional[DimensionType] = None):
		"""A relative size resolved along the track - against the arc's length."""
		return size_px(value, self.arc_length, dimension=dimension)

	@property
	def value_scale(self) -> Scale:
		"""This gauge's range as fractions - the value→``t`` half of the track's work.

		Not `scale`: `QGraphicsItem` already owns that name for the item's
		transform, and shadowing it would break `item.scale()` calls.
		"""
		_range = self._range
		return Scale.from_span(_range.rounded_min, _range.rounded_range, _range.wrap)

	def value_to_angle(self, value: Numeric) -> float:
		return self.startAngle + self.value_scale.toT(value) * self.fullAngle

	def value_to_angle_degrees(
		self,
		value: Numeric | Percentage | RelativeFloat | Length,
		relative_angle: Angle = None,
		relative_px: float = None,
		radius_px: float = None,
	) -> Angle:
		radius = radius_px or self.radius
		arc_length_px = float(radius * self.fullAngle / 180 * pi)

		if isinstance(value, Percentage):
			if relative_angle is not None:
				return Angle(relative_angle * value)
			elif relative_px is not None:
				return Angle(relative_px * value / arc_length_px * self.fullAngle)
		# elif issubclass(self.valueClass, Percentage):
		# 	value = float(value)

		if isinstance(value, (int, float, self.valueClass)):
			if isinstance(value, Percentage):
				value = float(value)
			value_arc_coverage = float(value / self._range.rounded_range)
			value_deg = value_arc_coverage * self.fullAngle
			return Angle(value_deg)

		elif isinstance(value, Percentage | RelativeFloat):
			# TODO: Add support for custom radius
			return Angle(value * relative_angle or self.fullAngle)
		elif isinstance(value, Length):
			value_px = size_px(value, relative_px or self.gauge.baseWidth)
			value = value_px / radius * 180 / pi
			return Angle(value)
		elif isinstance(value, Angle):
			return value

	def angle_degrees_to_value(
		self,
		angle: Angle | float | int,
		relative_angle: Angle = None,
		relative_px: float = None,
		radius_px: float = None,
	) -> float:

		radius = radius_px or self.radius
		arc_length_px = float(radius * self.fullAngle / 180 * pi)

		if isinstance(angle, Angle):
			angle = float(angle)
		elif isinstance(angle, (int, float)):
			angle = float(angle)
		else:
			raise TypeError(f'Invalid angle type: {type(angle)}')

		if isinstance(angle, (int, float)):
			if relative_angle is not None:
				angle = angle / float(relative_angle)
			elif relative_px is not None:
				angle = angle / relative_px * arc_length_px

			return angle / self.fullAngle * self._range.rounded_range

	def interval_to_count_float(self, interval: GaugeValue) -> float:
		return self._range.rounded_range / interval

	@property
	def safe_radius(self):
		major: Graduations = self.majorDivisions
		minor: Graduations = self.minorDivisions
		micro: Graduations = self.microDivisions

		arc_line_width = self.arc.pen().widthF()

		trim = max(arc_line_width / 2, 0)

		if major.enabled and major.position in {DisplayPosition.Below, DisplayPosition.Inside}:
			trim = max(major.length_px + major.width_px / 2, trim)
		if minor.enabled and minor.position in {DisplayPosition.Below, DisplayPosition.Inside}:
			trim = max(minor.length_px + minor.width_px / 2, trim)
		if micro.enabled and micro.position in {DisplayPosition.Below, DisplayPosition.Inside}:
			trim = max(micro.length_px + micro.width_px / 2, trim)

		return self.radius - trim

	@property
	def exterior_safe_radius(self):
		major: Graduations = self.majorDivisions
		minor: Graduations = self.minorDivisions
		micro: Graduations = self.microDivisions

		arc_line_width = self.arc.pen().widthF()

		extend = max(arc_line_width / 2, 0)

		if major.enabled and major.position in {DisplayPosition.Above, DisplayPosition.Outside}:
			extend = max(major.length_px + major.width_px / 2, extend)
		if minor.enabled and minor.position in {DisplayPosition.Above, DisplayPosition.Outside}:
			extend = max(minor.length_px + minor.width_px / 2, extend)
		if micro.enabled and micro.position in {DisplayPosition.Above, DisplayPosition.Outside}:
			extend = max(micro.length_px + micro.width_px / 2, extend)

		return self.radius + extend

	@property
	def value_safe_radius(self):

		major: Graduations = self.majorDivisions
		minor: Graduations = self.minorDivisions
		micro: Graduations = self.microDivisions

		trim = 0

		safe_radius = self.safe_radius
		if major.labels.enabled:
			labels: GaugeTickTextGroup = major.labels
			trim = max(labels.textSize_px + labels.offset_px, trim)
		if minor.labels.enabled:
			labels: GaugeTickTextGroup = minor.labels
			trim = max(labels.textSize_px + labels.offset_px, trim)
		if micro.labels.enabled:
			labels: GaugeTickTextGroup = micro.labels
			trim = max(labels.textSize_px + labels.offset_px, trim)

		return safe_radius - trim

	@property
	def safe_area(self) -> QPainterPath:
		return self.arc.mapToParent(self.arc.shape())

	def _debug_paint(self, painter: QPainter, option, widget):

		def add_gradient():
			painter.save()
			if (gradient := self.arc.gradient) is not None:
				painter.setBrush(self.map_gradient_to(gradient, self))
				painter.drawRect(option.rect)
			painter.restore()

		self._normal_paint(painter, option, widget)
	# addPath(painter, self.mapFromItem(self.arc, self.arc.shape(z)), type(self)._debug_paint_color, fill=type(self)._debug_paint_color)
	# f = QRadialGradient(rainbow)
	# f.setRadius(max(self.boundingRect().width(), self.boundingRect().height()) / 2)
	# f.setCenter(self.center)
	# f.setFocalPoint(self.center)
	# f.setCoordinateMode(QGradient.CoordinateMode.LogicalMode)
	# p = self._shape()
	# # addRect(painter, self.full_gauge_rect(), fill=f, opacity=.2)
	# p = outline_path(p, 5)
	# # self._normal_paint(painter, option, widget)
	# addPath(painter, p, fill=f)
	# addRect(painter, self.rect(), color=Qt.cyan, offset=-2, width=3)

	def _gauge_path(self) -> QPainterPath:
		"""Returns the path of the gauge, including the arc, ticks, and tick labels"""

		gauge_path = QPainterPath()
		gauge_path.setFillRule(Qt.WindingFill)

		# add arc
		gauge_path.addPath(self.mapFromItem(self.arc, self.arc.shape()))

		# add major ticks
		try:
			gauge_path.addPath(self.mapFromItem(self.major_ticks_surface, self.major_ticks_surface.tick_path))

			# add major tick labels
			if self.majorDivisions.labels.enabled:
				gauge_path.addPath(self.mapFromItem(self.major_ticks_surface, self.majorDivisions.labels.shape()))
		except AttributeError:
			pass

		# add minor ticks
		try:
			gauge_path.addPath(self.mapFromItem(self.minor_ticks_surface, self.minor_ticks_surface.tick_path))

			# add minor tick labels
			if self.minorDivisions.labels.enabled:
				gauge_path.addPath(self.mapFromItem(self.minor_ticks_surface, self.minorDivisions.labels.shape()))
		except AttributeError:
			pass

		# add micro ticks
		try:
			gauge_path.addPath(self.mapFromItem(self.micro_ticks_surface, self.micro_ticks_surface.tick_path))

			# add micro tick labels
			if self.microDivisions.labels.enabled:
				gauge_path.addPath(self.mapFromItem(self.micro_ticks_surface, self.microDivisions.labels.shape()))
		except AttributeError:
			pass

		return gauge_path

	@cached_property
	def full_gauge_path(self) -> QPainterPath:
		path = self._gauge_path()
		path.setFillRule(Qt.WindingFill)
		# Value-independent geometry only: arc, ticks, tick labels. The value
		# and unit labels (and the needle, fills, markers) change shape with
		# the value, and recenter() measures this path - counting them made a
		# partial dial land somewhere different for every value at load.
		return path.simplified()

	def full_gauge_rect(self) -> QRectF:
		return self.full_gauge_path.boundingRect()

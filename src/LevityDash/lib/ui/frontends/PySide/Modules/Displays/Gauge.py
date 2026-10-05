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
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.meter import GaugeRange
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.elements import (
	Arrow, GaugeCaption, GaugeFill, GaugeItem, GaugeLabel, GaugeMarker, GaugePathItem, GaugeText, GaugeTickText,
	GaugeTickTextGroup, GaugeUnit, GaugeValueLabel, GaugeZones, Graduations, Needle, StatefulGaugeItem,
	StatefulGaugePathItem, SubTick, Tick, TickSurface, _UNIT_UNDER_VALUE, gaugeKeyName as _gaugeKeyName,
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


# Unit positions that hang the unit under the value. `float-under` is the
# Realtime text display's name for it; `below` is the gauge's older one.
def _markerText(spec) -> str:
	"""The ``value:`` text of a marker spec, for log messages. Never raises."""
	try:
		return str(spec.get('value'))
	except Exception:
		return str(spec)


@DebugPaint
class Gauge(Display):

	_center_offset: QPointF | QPointF = QPointF(0, 0)

	__value: float = 0.0
	_needleAnimation: QPropertyAnimation
	valueChanged = Signal(float)
	arc: GaugeArc

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
		return GaugeRange(self)

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


# `meter/elements.py` annotates its items with `Gauge` and `GaugeArc`, and
# `typing.get_type_hints` resolves an annotation against the module its class was
# defined in (`Text.surface` asks for them at layout time). Hand the classes over
# now that they exist, so those hints resolve to the real thing.
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter import elements as _meter_elements
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter import meter as _meter_module

_meter_elements.Gauge = Gauge
_meter_elements.GaugeArc = GaugeArc
_meter_module.Gauge = Gauge

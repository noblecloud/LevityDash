"""Where a value sits, as a point: the track a meter's scale runs along.

A track is a one-dimensional path parameterised by ``t`` in 0..1. It knows how
to give back a point, a direction, and a piece of itself as a `QPainterPath`;
it knows nothing about values (that is `Scale`) and nothing about what gets
drawn on it (that is the meter and its elements).

`ArcTrack` is the dial. Its angles are the *dial's* angles, in the same
convention the gauge has always used - ``start-angle`` 0 is up, positive runs
clockwise, and a ``start`` greater than ``end`` is an arc that runs the other
way (``GaugeArc.inverted``) - and the Qt conversion (``-angle + 90``) lives here
and nowhere else, exactly as it always has.

`LineTrack` is the same interface for a straight run, which is what a bar
needs. Both are written so a `PathTrack(QPainterPath)` can join them later.
"""
from math import atan2, cos, degrees, hypot, radians, sin

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath

__all__ = ['ArcTrack', 'LineTrack', 'Track']


class Track:
	"""A path a value moves along, parameterised by ``t`` in 0..1.

	Subclasses implement the geometry; nothing here touches values or painting.
	"""

	def pointAt(self, t: float) -> QPointF:
		"""The point at ``t``. ``t`` outside 0..1 is extrapolated, not clamped."""
		raise NotImplementedError

	def tangentAt(self, t: float) -> QPointF:
		"""A unit vector along the track at ``t``."""
		raise NotImplementedError

	def normalAt(self, t: float) -> QPointF:
		"""A unit vector across the track at ``t`` (the tangent turned 90 clockwise)."""
		tangent = self.tangentAt(t)
		return QPointF(-tangent.y(), tangent.x())

	def angleAt(self, t: float) -> float:
		"""The tangent's direction at ``t``, in degrees, for a Qt rotation."""
		tangent = self.tangentAt(t)
		return degrees(atan2(tangent.y(), tangent.x()))

	def subPath(self, t0: float = 0.0, t1: float = 1.0) -> QPainterPath:
		"""The piece of the track between ``t0`` and ``t1``."""
		raise NotImplementedError

	def distanceAt(self, t: float) -> float:
		"""How far along the track ``t`` is, in px."""
		return self.lengthPx * t

	@property
	def lengthPx(self) -> float:
		"""The track's length, in px."""
		raise NotImplementedError

	@property
	def bounds(self) -> QRectF:
		"""The track's bounding rect."""
		return self.subPath().boundingRect()


class ArcTrack(Track):
	"""An arc of an ellipse, with the dial's angle convention.

	``rect`` is the ellipse's bounding rect in the owning item's coordinates -
	the same rect `QPainterPath.arcTo` wants - and ``start_angle``/``end_angle``
	are dial angles: 0 is up, positive is clockwise, and a larger start than end
	is an arc drawn the other way round.
	"""

	__slots__ = ('rect', 'start_angle', 'end_angle')

	def __init__(self, rect: QRectF, start_angle: float, end_angle: float):
		self.rect = rect
		self.start_angle = float(start_angle)
		self.end_angle = float(end_angle)

	def __repr__(self) -> str:
		return f'ArcTrack({self.start_angle:g}°..{self.end_angle:g}°, r={self.radius:.1f})'

	@property
	def full_angle(self) -> float:
		"""Dial degrees from start to end; negative when the arc runs the other way."""
		return self.end_angle - self.start_angle

	@property
	def radius(self) -> float:
		"""Half the rect's width. A dial's rect is square; see `lengthPx` otherwise."""
		return self.rect.width() / 2

	@property
	def center(self) -> QPointF:
		return self.rect.center()

	@property
	def lengthPx(self) -> float:
		"""Arc length. Exact for a circle; the mean radius approximates an ellipse."""
		radius = (self.rect.width() + self.rect.height()) / 4
		return abs(radius * self.full_angle / 180 * 3.141592653589793)

	def qtAngle(self, t: float) -> float:
		"""The Qt angle (degrees, counter-clockwise from 3 o'clock) at ``t``.

		The whole of the dial's ``-angle + 90`` convention is this one line.
		"""
		return -self.start_angle + 90 - self.full_angle * t

	def dialAngle(self, t: float) -> float:
		"""The dial angle at ``t``: ``start`` at 0, ``end`` at 1, clockwise from up."""
		return self.start_angle + self.full_angle * t

	def markAngle(self, t: float) -> float:
		"""The angle at ``t`` in the convention marks are placed in.

		The dial's own angle less 90 degrees: what `Tick.angle` carries, and what
		`cos`/`sin` want. ``-90`` is up, ``0`` is right, positive runs clockwise
		(y grows downwards).
		"""
		return self.start_angle + self.full_angle * t - 90

	def pointAtAngle(self, angle: float) -> QPointF:
		"""The point at a mark angle (see `markAngle`), by the marks' own arithmetic.

		Deliberately not Qt's arc parameterisation: `QPainterPath` quantises arc
		angles to a 16th of a degree, so `arcMoveTo` lands up to 0.199 px off a
		400 px radius (measured, 2026-10-05), and anything placed through it would
		shift by that much against every render taken so far. `subPath` still
		draws the Qt arc, so the two can disagree by that 0.2 px; making them
		agree is a visible change and belongs in its own task, not this refactor.
		"""
		radians_ = radians(angle)
		center = self.rect.center()
		return QPointF(center.x() + self.radius * cos(radians_), center.y() + self.radius * sin(radians_))

	def normalAtAngle(self, angle: float) -> QPointF:
		"""The outward unit vector at a mark angle: the direction a tick grows in."""
		return QPointF(cos(radians(angle)), sin(radians(angle)))

	def pointAt(self, t: float) -> QPointF:
		return self.pointAtAngle(self.markAngle(t))

	def tangentAt(self, t: float) -> QPointF:
		outward = self.normalAtAngle(self.markAngle(t))
		# A clockwise sweep turns the outward normal a quarter turn backwards.
		sign = -1.0 if self.full_angle < 0 else 1.0
		return QPointF(outward.y() * sign, -outward.x() * sign)

	def subPath(self, t0: float = 0.0, t1: float = 1.0) -> QPainterPath:
		"""The arc between ``t0`` and ``t1``, drawn the way `GaugeArc` always drew it."""
		path = QPainterPath()
		start = self.qtAngle(t0)
		path.arcMoveTo(self.rect, start)
		path.arcTo(self.rect, start, -(self.full_angle * (t1 - t0)))
		return path


class LineTrack(Track):
	"""A straight run from ``start`` to ``end``."""

	__slots__ = ('start', 'end')

	def __init__(self, start: QPointF, end: QPointF):
		self.start = QPointF(start)
		self.end = QPointF(end)

	def __repr__(self) -> str:
		return f'LineTrack({self.start.x():.1f},{self.start.y():.1f} -> {self.end.x():.1f},{self.end.y():.1f})'

	def pointAt(self, t: float) -> QPointF:
		return QPointF(
			self.start.x() + (self.end.x() - self.start.x()) * t,
			self.start.y() + (self.end.y() - self.start.y()) * t,
		)

	def tangentAt(self, t: float) -> QPointF:
		dx, dy = self.end.x() - self.start.x(), self.end.y() - self.start.y()
		length = hypot(dx, dy) or 1.0
		return QPointF(dx / length, dy / length)

	def subPath(self, t0: float = 0.0, t1: float = 1.0) -> QPainterPath:
		path = QPainterPath()
		path.moveTo(self.pointAt(t0))
		path.lineTo(self.pointAt(t1))
		return path

	@property
	def lengthPx(self) -> float:
		return hypot(self.end.x() - self.start.x(), self.end.y() - self.start.y())

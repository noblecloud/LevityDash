from datetime import datetime, timedelta, timezone
from functools import cached_property
from typing import Iterable, Tuple, TYPE_CHECKING

import numpy as np
from pylunar import MoonInfo as _MoonInfo
from PySide2.QtCore import QPointF, Qt, QTimer, Signal
from PySide2.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QTransform
from PySide2.QtWidgets import QGraphicsPathItem, QGraphicsItem, QGraphicsDropShadowEffect
from pysolar import solar
from ephem import previous_new_moon, next_new_moon

from LevityDash.lib.ui.frontends.PySide.utils import colorPalette
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.utils.shared import clearCacheAttr, now
from LevityDash.lib.stateful import StateProperty
from LevityDash.lib.config import userConfig
from LevityDash.lib.ui import UILogger
from WeatherUnits import Angle, Time, Percentage

golden = (1 + np.sqrt(5))/2
dark = QColor(28, 29, 31, 255)

__all__ = ["Moon"]


class MoonInfo(_MoonInfo):
	"""
	Class to provide fractional age until pull request for pylunmar is accepted and merged
	"""

	def fractional_age(self) -> float:
		prev_new = previous_new_moon(self.observer.date)
		next_new = next_new_moon(self.observer.date)
		return (self.observer.date - prev_new)/(next_new - prev_new)


class ThreeDimensionalPoint:
	__slots__ = ["x", "y", "z"]

	def __init__(self, x: float, y: float, z: float):
		self.x = x
		self.y = y
		self.z = z

	def __repr__(self):
		return f'<ThreeDimensionalPoint> x: {self.x}, y: {self.y}, z: {self.z}'

	def __add__(self, other: "ThreeDimensionalPoint") -> "ThreeDimensionalPoint":
		return ThreeDimensionalPoint(self.x + other.x, self.y + other.y, self.z + other.z)

	def __sub__(self, other: "ThreeDimensionalPoint") -> "ThreeDimensionalPoint":
		return ThreeDimensionalPoint(self.x - other.x, self.y - other.y, self.z - other.z)

	def __mul__(self, other: float) -> "ThreeDimensionalPoint":
		return ThreeDimensionalPoint(self.x*other, self.y*other, self.z*other)

	def __truediv__(self, other: float) -> "ThreeDimensionalPoint":
		return ThreeDimensionalPoint(self.x/other, self.y/other, self.z/other)

	def toQPointF(self) -> QPointF:
		return QPointF(self.x, self.y)

	def multipliedQPointF(self, other: float) -> QPointF:
		return QPointF(self.x*other, self.y*other)


class MoonBack(QGraphicsPathItem):
	if TYPE_CHECKING:
		def parentItem(self) -> 'Moon':
			...

	def __init__(self, parent: 'Moon'):
		super().__init__()
		self.setParentItem(parent)
		self.setAcceptHoverEvents(False)
		self.setAcceptedMouseButtons(Qt.NoButton)
		self.setPen(QPen(Qt.NoPen))
		self.setBrush(QBrush(dark))
		self.setZValue(-1)
		self.draw()

	def draw(self):
		bounds = self.parentItem().rect()
		path = QPainterPath()
		radius = min(bounds.width(), bounds.height())/2
		path.addEllipse(QPointF(0, 0), radius, radius)
		self.setPath(path)

	def paint(self, painter: QPainter, option, widget):
		tW = painter.worldTransform()
		painter.setRenderHint(QPainter.Antialiasing)
		scale = min(tW.m11(), tW.m22())
		tW.scale(1/tW.m11(), 1/tW.m22())
		tW.scale(scale, scale)
		painter.setWorldTransform(tW, False)
		super().paint(painter, option, widget)


class MoonFront(QGraphicsPathItem):
	if TYPE_CHECKING:
		def parentItem(self) -> 'Moon':
			...

	def __init__(self, parent: 'Moon'):
		super().__init__()
		self.setParentItem(parent)
		self.setAcceptHoverEvents(False)
		self.setAcceptedMouseButtons(Qt.NoButton)
		self.setPen(QPen(Qt.NoPen))
		self.setBrush(colorPalette.windowText().color())
		self.setZValue(1)
		self.draw()

	def sphericalToCartesian(self, ascension: float, declination: float) -> ThreeDimensionalPoint:
		ascension += 90
		ascension = np.deg2rad(ascension)
		declination = np.deg2rad(declination)
		return ThreeDimensionalPoint(x=float(np.sin(ascension)*np.sin(declination)), y=float(np.cos(declination)), z=float(np.cos(ascension)*np.sin(declination)))

	def sphericalToCartesianArray(self, ascension: float, declination: Iterable) -> ThreeDimensionalPoint:
		values = np.array(list(declination))
		values = np.deg2rad(values)
		ascension = np.deg2rad(ascension + 90)
		x = np.sin(ascension)*np.sin(values)
		y = np.cos(values)
		# z = np.cos(ascension) * np.sin(values)
		return np.array([x, y]).T

	@property
	def pathPoints(self):
		## Todo: try to rewrite this to use an ellipse/curve rather than 240 lines
		phase = self.parentItem().phase
		r1 = range(0, 180, 3)
		r2 = range(180, 360, 3)
		if phase < 180:
			p1 = self.sphericalToCartesianArray(phase, r1)
			p2 = self.sphericalToCartesianArray(180, r2)
		else:
			p1 = self.sphericalToCartesianArray(180, r1)
			p2 = self.sphericalToCartesianArray(phase, r2)

		points = np.concatenate((p1, p2), axis=0)

		return points

	def draw(self):
		path = QPainterPath()
		points = [QPointF(*point) for point in self.pathPoints*self.parentItem().radius]
		path.moveTo(points[0])
		for point in points:
			path.lineTo(point)
		path.closeSubpath()
		t = QTransform()
		t.rotate(self.parentItem().getAngle())
		path = t.map(path)
		self.setPath(path.simplified())
		self.setTransformOriginPoint(self.parentItem().rect().center())

	def paint(self, painter, option, widget):
		tW = painter.worldTransform()
		painter.setRenderHint(QPainter.Antialiasing)
		scale = min(tW.m11(), tW.m22())
		tW.scale(1/tW.m11(), 1/tW.m22())
		tW.scale(scale, scale)
		painter.setWorldTransform(tW, False)
		super().paint(painter, option, widget)


class MoonGlowEffect(QGraphicsDropShadowEffect):
	def __init__(self, parent, strength):
		super().__init__(None)
		self.surface = parent
		self.setBlurRadius(strength)
		self.setColor(QColor(255, 255, 255, 255))
		self.setOffset(QPointF(0, 0))


class Moon(Panel, tag="moon"):
	moonFull: QPainterPath
	moonPath: QPainterPath
	_date: datetime
	_phase: float
	_glow: bool
	_glowStrength: float
	rotation: float
	_interval = timedelta(minutes=5)

	__exclude__ = {..., 'items'}

	valueChanged = Signal(float)

	def __init__(self, *args, **kwargs):
		self.__phase = 0
		self.__rotate = True
		self.lat, self.lon = userConfig.loc
		self._date = datetime.now(userConfig.tz)
		self.refreshData()
		self._glow = True
		self._glowStrength = 0.5
		self.timer = QTimer(interval=1000*60*15)
		self.timer.setTimerType(Qt.VeryCoarseTimer)
		super(Moon, self).__init__(*args, **kwargs)
		self.timer.timeout.connect(self.updateMoon)
		self.setFlag(self.ItemHasNoContents)
		self.moonFull.setParentItem(self)
		self.moonPath.setParentItem(self)
		self.moonPath.setPos(self.boundingRect().center())
		self.scene().view.resizeFinished.connect(self.refresh)

		self.timer.start()
		self._acceptsChildren = False
		self.updateMoon()

	def refresh(self):
		self.setRect(self.rect())

	def __rich_repr__(self):
		yield 'phase', self.phase
		yield 'phaseName', self._moonInfo.phase_name()
		yield 'rotation', Angle(self.getAngle())
		yield 'date', self._date
		yield 'nextRefresh', str(Time.Millisecond(self.timer.remainingTime()).s.auto)
		yield from super().__rich_repr__()

	@property
	def isEmpty(self):
		return False

	@cached_property
	def moonFull(self) -> MoonBack:
		return MoonBack(self)

	@cached_property
	def moonPath(self) -> MoonFront:
		return MoonFront(self)

	@cached_property
	def _moonInfo(self) -> MoonInfo:
		return MoonInfo(self.deg2dms(self.lat), self.deg2dms(self.lon))

	@property
	def visibleWidth(self):
		return self.rect().width()

	@property
	def visibleHeight(self):
		return self.rect().height()

	@property
	def radius(self) -> float:
		return min(self.visibleHeight, self.visibleWidth)/2

	@StateProperty(default=True, allowNone=False, dependencies={'glowStrength'})
	def glow(self) -> bool:
		return self._glow

	@glow.setter
	def glow(self, value):
		self._glow = value
		if moonPath := getattr(self, "moonPath", None):
			if value:
				if effect := moonPath.graphicsEffect():
					effect.setEnabled(True)
				else:
					moonPath.setGraphicsEffect(MoonGlowEffect(self.moonPath, self.glowStrength))
			else:
				if effect := moonPath.graphicsEffect():
					effect.setEnabled(False)

	@StateProperty(default=0.2, allowNone=False)
	def glowStrength(self) -> float:
		return self._glowStrength

	@glowStrength.setter
	def glowStrength(self, value: float):
		self._glowStrength = max(value, 0)
		if not self._glowStrength:
			self.glow = False
			return
		if moonPath := getattr(self, "moonPath", None):
			if effect := moonPath.graphicsEffect():
				effect.setBlurRadius(value*self.radius)

	@glowStrength.condition
	def glowStrength(value: float):
		return value > 0

	@glowStrength.condition
	def glowStrength(self):
		return self._glow

	@StateProperty(default=timedelta(minutes=5), allowNone=False)
	def interval(self) -> timedelta:
		interval = self.timer.interval()
		if interval < 0:
			interval = 0
		return timedelta(seconds=interval/1000)

	@interval.setter
	def interval(self, value: timedelta):
		if timer := getattr(self, "timer", None):
			timer.stop()
			timer.setInterval(1000*value.total_seconds())
			timer.start()

	@interval.decode
	def interval(value: dict | int) -> timedelta:
		match value:
			case dict(value):
				return timedelta(**value)
			case int(value):
				return timedelta(minutes=value)
			case _:
				raise ValueError(f"Invalid interval: {value}")

	@property
	def nextUpdate(self) -> Time:
		return Time.Millisecond(self.timer.remainingTime()).s.auto

	def refreshData(self):
		self._date = now()
		self._moonInfo.update(tuple(self._date.timetuple()[:-3]))
		self._phase = self._moonInfo.fractional_age()*360

	def updateMoon(self):
		self.refreshData()
		self.redrawMoon()
		UILogger.verbose(f"Moon Updated: nextUpdate={self.nextUpdate!s}, phase={Percentage(self._moonInfo.fractional_phase())!s}, angle={Angle(self.getAngle())!s}", verbosity=4)

	def redrawMoon(self):
		self.moonPath.draw()
		self.moonFull.draw()

	@StateProperty(default=True, allowNone=False, after=redrawMoon)
	def rotate(self) -> bool:
		return self.__rotate

	@rotate.setter
	def rotate(self, value: bool):
		self.__rotate = value

	def getAngle(self) -> float:
		"""https://stackoverflow.com/a/45029216/2975046"""

		if not self.__rotate:
			return 0.0

		sunalt = solar.get_altitude_fast(self.lat, self.lon, self._date)
		sunaz = solar.get_azimuth_fast(self.lat, self.lon, self._date)
		moonaz = self._moonInfo.azimuth()
		moonalt = self._moonInfo.altitude()

		dLon = (sunaz - moonaz)
		y = np.sin(np.deg2rad(dLon))*np.cos(np.deg2rad(sunalt))
		x = np.cos(np.deg2rad(moonalt))*np.sin(np.deg2rad(sunalt)) - np.sin(np.deg2rad(moonalt))*np.cos(np.deg2rad(sunalt))*np.cos(np.deg2rad(dLon))
		brng = np.arctan2(y, x)
		brng = np.rad2deg(brng)
		return (brng + 90)%360

	@staticmethod
	def deg2dms(dd: float) -> Tuple[float, float, float]:
		mnt, sec = divmod(dd*3600, 60)
		deg, mnt = divmod(mnt, 60)
		return deg, mnt, sec

	@property
	def phase(self):
		return self._phase

	def setRect(self, rect):
		super().setRect(rect)
		self.moonPath.setPos(rect.center())
		self.moonPath.draw()
		self.moonFull.setPos(rect.center())
		self.moonFull.draw()
		self.setCacheMode(QGraphicsItem.CacheMode.ItemCoordinateCache)
		if self.glow and (effect := self.moonPath.graphicsEffect()):
			effect.setBlurRadius(self.glowStrength*self.radius)
			effect.updateBoundingRect()
			effect.update()

from datetime import datetime, timedelta, timezone
from functools import cached_property
from typing import Iterable, Tuple

import numpy as np
from pylunar import MoonInfo as _MoonInfo
from PySide2.QtCore import QPointF, Qt, QTimer, Signal
from PySide2.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QTransform
from PySide2.QtWidgets import QGraphicsPathItem, QGraphicsItem, QGraphicsDropShadowEffect
from pysolar import solar
from ephem import previous_new_moon, next_new_moon

from LevityDash.lib.ui.frontends.PySide.utils import colorPalette
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.utils.shared import clearCacheAttr
from LevityDash.lib.config import userConfig

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
		scale = min(tW.m11(), tW.m22())
		tW.scale(1/tW.m11(), 1/tW.m22())
		tW.scale(scale, scale)
		painter.setWorldTransform(tW, False)
		super().paint(painter, option, widget)


class MoonFront(QGraphicsPathItem):

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

	@cached_property
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
		scale = min(tW.m11(), tW.m22())
		tW.scale(1/tW.m11(), 1/tW.m22())
		tW.scale(scale, scale)
		painter.setWorldTransform(tW, False)
		super().paint(painter, option, widget)


class MoonGlowEffect(QGraphicsDropShadowEffect):
	def __init__(self, parent):
		super().__init__(None)
		self.surface = parent
		self.setBlurRadius(self.surface.parentItem().radius)
		self.setColor(QColor(255, 255, 255, 255))
		self.setOffset(QPointF(0, 0))

	def draw(self, painter: QPainter):
		painter.setRenderHint(QPainter.Antialiasing, True)
		super().draw(painter)


class Moon(Panel):
	moonFull: QPainterPath
	moonPath: QPainterPath
	_date: datetime
	_phase: float = 0
	rotation: float = 0.0
	_interval = timedelta(minutes=5)

	valueChanged = Signal(float)

	def __init__(self, *args, **kwargs):
		self.__phase = 0
		self.lat, self.lon = userConfig.loc
		self._date = datetime.now(userConfig.tz)
		self.refreshData()
		super(Moon, self).__init__(*args, **kwargs)
		self.setFlag(self.ItemHasNoContents, False)
		self.moonFull.setParentItem(self)
		self.moonPath.setParentItem(self)
		self.moonPath.setPos(self.boundingRect().center())
		self.moonPath.setGraphicsEffect(MoonGlowEffect(self.moonPath))

		# Build timer
		self.timer = QTimer()
		self.timer.setInterval(1000*self._interval.total_seconds())
		# self.timer.setInterval(200)
		self.timer.setTimerType(Qt.VeryCoarseTimer)
		self.timer.timeout.connect(self.updateMoon)
		self.timer.start()
		self.updateFromGeometry()
		self._acceptsChildren = False
		self.updateMoon()

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

	def refreshData(self):
		self._date = datetime.now(timezone.utc)
		self._moonInfo.update(tuple(self._date.timetuple()[:-3]))
		self._phase = self._moonInfo.fractional_age()*360

	def updateMoon(self):
		self.refreshData()
		self.redrawMoon()

	def redrawMoon(self):
		clearCacheAttr(self, 'pathPoints')
		self.moonPath.draw()
		self.moonFull.draw()

	def getAngle(self) -> float:
		"""https://stackoverflow.com/a/45029216/2975046"""

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
		effect = self.moonPath.graphicsEffect()
		self.setCacheMode(QGraphicsItem.CacheMode.ItemCoordinateCache)
		if effect is not None:
			effect.updateBoundingRect()
			effect.update()

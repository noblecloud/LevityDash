"""Dev-only: the stage Gauge Studio draws a gauge on, and the made-up data behind it.

The studio is its own program. It does not boot the dashboard, the central
panel, a plugin, the backend or the Fixture plugin. It builds the real `Gauge`
class from `Gauge.py` and puts it in a plain `QGraphicsScene`, so the drawing is
what the dashboard draws.

`Gauge` touches the app in four places. Each has a small stand-in here, and
`Gauge.py` is unchanged:

- `Gauge._init_defaults_` reads `self.parent.container.value_type` (Gauge.py
  `_init_defaults_`). `StudioStage.container` answers it.
- `GaugeRange.default_range` and `_gaugeKeyName` read `self.parent.key`.
  `StudioStage.key` answers both.
- A marker or fill that names a key (`value: environment.temperature.high`) asks
  `openValueSource`, imported into the Gauge module by name. `installSources()`
  swaps that name for a lookup into the made-up data.
- `Panel` wants a stateful root with an action pool, a scene with `.view` and
  `.base`, and a parent that is a `Panel`. `StudioScene` and `StudioStage` are
  that, minus everything `CentralPanel` does with files, config and the
  `LevityDashboard` globals.

Importing `LevityDash` still builds the `QApplication` and the config object at
import time (`LevityDash/__init__.py`, class body). The studio points both at a
throwaway directory first (`_studio_env.prepare`). That is the only way to keep
the import from creating files in the real config directory.
"""
from dataclasses import dataclass, field
from functools import cached_property
from math import pi, sin
from typing import Any, Callable, Dict, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays import Gauge as _gaugeModule
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Gauge import Gauge
from statekit.actions import ActionPool
from statekit.binding import Constant
from qolkit import Unset
import WeatherUnits as wu

__all__ = ['DataPreset', 'DATA_PRESETS', 'presetForKey', 'StudioScene', 'StudioStage', 'StudioGauge', 'installSources']

STAGE_SIZE = (800, 800)


# Section: made-up data

def _rain(value: float):
	return wu.Precipitation.Hourly(wu.Length.Inch(value), wu.Time.Hour(1))


@dataclass
class DataPreset:
	"""One made-up reading: a value, today's low and high, and where it lives."""
	name: str
	key: str
	make: Callable[[float], Any]
	low: float
	high: float
	value: float
	min: float
	max: float
	#: Extra keys a marker or fill may name, each as a fraction of min..max or an absolute number.
	keys: Dict[str, float] = field(default_factory=dict)

	def measurement(self, value: float):
		return self.make(value)


DATA_PRESETS: Dict[str, DataPreset] = {p.name: p for p in (
	DataPreset('Temperature F', 'environment.temperature.temperature', wu.Temperature.Fahrenheit, 52, 78, 68, 0, 120),
	DataPreset('Humidity %', 'environment.humidity.humidity', lambda v: wu.Humidity(v), 38, 82, 61, 0, 100),
	DataPreset('Pressure inHg', 'environment.pressure.pressure', wu.Pressure.InchOfMercury, 29.7, 30.1, 29.9, 28.5, 31.5),
	DataPreset('Wind mph', 'environment.wind.speed.speed', wu.Wind.MilesPerHour, 3, 18, 11, 0, 40),
	DataPreset('Rain in/hr', 'environment.precipitation.precipitation', _rain, 0.0, 0.8, 0.3, 0, 2),
	DataPreset('Generic 0-100', 'studio.generic', lambda v: float(v), 15, 85, 55, 0, 100),
)}

#: Which preset suits a key in a showcase cell.
_KEY_HINTS = (
	('temperature', 'Temperature F'), ('humidity', 'Humidity %'), ('pressure', 'Pressure inHg'),
	('wind.speed', 'Wind mph'), ('precipitation', 'Rain in/hr'),
)


def presetForKey(key: Optional[str]) -> DataPreset:
	"""The made-up data that fits a key, else the generic 0-100 reading."""
	for hint, name in _KEY_HINTS:
		if key and hint in key:
			return DATA_PRESETS[name]
	return DATA_PRESETS['Generic 0-100']


class _Source:
	"""A value source the studio owns. Satisfies statekit's `ValueSource`."""

	def __init__(self, get: Callable[[], Any]):
		self._get = get
		self._callbacks = []

	def get(self):
		return self._get()

	def subscribe(self, callback):
		self._callbacks.append(callback)

		def unsubscribe():
			if callback in self._callbacks:
				self._callbacks.remove(callback)
		return unsubscribe

	def push(self):
		for callback in tuple(self._callbacks):
			callback(self.get())


# Section: the stage

class StudioScene(QGraphicsScene):
	"""A scene that answers `.view` and `.base` the way `LevityScene` does."""

	def __init__(self, view: QGraphicsView):
		super().__init__(view)
		self._view = view
		self.base = None
		self.setSceneRect(QRectF(0, 0, *STAGE_SIZE))
		self.setBackgroundBrush(Qt.transparent)

	@property
	def view(self) -> QGraphicsView:
		return self._view

	# The members of `LevityScene` that `Geometry` and `Panel` read from a parent scene.

	def rect(self) -> QRectF:
		return self.sceneRect()

	@property
	def marginRect(self) -> QRectF:
		return self.sceneRect()

	def size(self):
		return self.sceneRect().size()

	@property
	def frozen(self) -> bool:
		return False

	@cached_property
	def geometry(self):
		from LevityDash.lib.ui.Geometry import StaticGeometry
		return StaticGeometry(surface=self, position=(0, 0), absolute=True, snapping=False, updateSurface=False)

	def zValue(self) -> int:
		return -1

	def setHighlighted(self, value) -> None:
		pass

	def hasCursor(self) -> bool:
		return True

	def childHasFocus(self) -> bool:
		return False


class _Container:
	"""What `Gauge._init_defaults_` reads from the panel above it."""

	def __init__(self, preset: DataPreset):
		self.value_type = type(preset.make(preset.value))


class StudioStage(Panel, tag='studio-stage'):
	"""The panel the gauge sits in. `CentralPanel` without files, config or globals."""

	_keepInFrame = True
	__exclude__ = {'geometry', 'movable', 'resizable', 'locked', 'frozen'}
	__defaults__ = {
		'movable': False,
		'resizable': False,
		'locked': True,
		'fillParent': True,
		'geometry': {'fillParent': True},
		'margins': ('0px', '0px', '0px', '0px'),
	}

	def prep_init(self, *args, **kwargs):
		self._set_state_items_ = set()
		self.statefulParent = None

	def __init__(self, scene: StudioScene, preset: DataPreset):
		self._parent = scene
		self._action_pool = ActionPool(self, trace='StudioStage')
		self._scene = scene
		self.key = CategoryItem(preset.key)
		self.container = _Container(preset)
		super().__init__(None)
		self.setFlag(self.GraphicsItemFlag.ItemHasNoContents)
		self.resizeHandles.setVisible(False)
		self.resizeHandles.setEnabled(False)
		self.setFlag(self.GraphicsItemFlag.ItemClipsChildrenToShape, False)
		self.setFlag(self.GraphicsItemFlag.ItemIsFocusable, False)
		self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
		self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, False)
		scene.base = self

	def _init_args_(self, *args, **kwargs):
		self._scene.addItem(self)
		super()._init_args_(*args, **kwargs)
		self._parent = self.scene()

	@property
	def parent(self):
		return self.scene()


# Section: stand-in for `openValueSource`

_active: Optional['StudioGauge'] = None


def _openValueSource(value, label: str = '', effect: str = ''):
	"""Replaces `Gauge.openValueSource`. A number is a constant, a key reads the made-up data."""
	if isinstance(value, bool):
		return None
	if isinstance(value, (int, float)):
		return Constant(value)
	if isinstance(value, str) and _active is not None:
		return _active.sourceForKey(value)
	return None


def installSources() -> None:
	"""Point the Gauge module's `openValueSource` at the made-up data. Idempotent."""
	_gaugeModule.openValueSource = _openValueSource


# Section: the gauge and its driver

class StudioGauge:
	"""Builds one real `Gauge` on a `StudioStage` and drives it from made-up data.

	`value` is what the gauge shows. The slider and the sweep both write it
	through `setValue`.
	"""

	def __init__(self, scene: StudioScene, preset: DataPreset):
		self.scene = scene
		self.preset = preset
		self.stage: Optional[StudioStage] = None
		self.gauge: Optional[Gauge] = None
		self.value = preset.value
		self._valueSource = _Source(lambda: self.preset.measurement(self.value))
		installSources()

	# values

	def sourceForKey(self, key: str):
		"""The source for `key` in a marker or fill. High and low are today's; else the live value."""
		tail = key.rsplit('.', 1)[-1]
		preset = self.preset
		if tail == 'high':
			return Constant(preset.measurement(preset.high))
		if tail == 'low':
			return Constant(preset.measurement(preset.low))
		if key == preset.key or tail in {'temperature', 'humidity', 'pressure', 'speed', 'precipitation'}:
			return self._valueSource
		return Constant(preset.measurement(preset.value))

	@property
	def range(self):
		"""The gauge's own min and max, as floats."""
		r = self.gauge._range
		return float(r.min), float(r.max)

	def setValue(self, value: float) -> None:
		self.value = value
		if self.gauge is not None:
			self.gauge.value = self.preset.measurement(value)
		self._valueSource.push()

	# building

	def build(self, display: Optional[dict], preset: Optional[DataPreset] = None) -> Gauge:
		"""Replace the gauge with a new one from a `display:` mapping."""
		global _active
		_active = self
		if preset is not None:
			self.preset = preset
		self.dispose()
		self.stage = StudioStage(self.scene, self.preset)
		display = dict(display or {})
		display.setdefault('geometry', {'x': 0, 'y': 0, 'width': 1, 'height': 1})
		# Inside the stage's action pool: the dashboard builds a gauge while its panel
		# loads state, so every deferred refresh waits until the gauge is complete.
		with self.stage.action_pool:
			self.gauge = Gauge(parent=self.stage, **display)
		self.gauge.show()
		self.stage.setRect(self.scene.sceneRect())
		self.gauge.valueClass = type(self.preset.measurement(self.value))
		self.gauge.value = self.preset.measurement(self.value)
		self.gauge.refresh()
		return self.gauge

	def dispose(self) -> None:
		if self.gauge is not None:
			try:
				self.gauge.releaseSources()
			except Exception:
				pass
		if self.stage is not None:
			self.scene.removeItem(self.stage)
		self.stage = self.gauge = None

	def render(self, size: Optional[tuple] = None) -> QImage:
		"""The scene as an image. For tests and screenshots."""
		rect = self.scene.sceneRect()
		w, h = size or (int(rect.width()), int(rect.height()))
		image = QImage(w, h, QImage.Format.Format_ARGB32)
		image.fill(Qt.black)
		painter = QPainter(image)
		painter.setRenderHint(QPainter.Antialiasing)
		self.scene.render(painter, QRectF(image.rect()), rect)
		painter.end()
		return image

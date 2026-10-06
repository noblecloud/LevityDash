"""Dev-only: structured editors for Gauge Studio. Nothing here asks you to type YAML.

Each editor is a widget with one job: show a value in the form a `.levity` file
holds, and report an edit in the same form (`changed(value)`). `FieldRow`
(`_studio_widgets.py`) picks one by the field's kind (`_studio_schema._refine`).

======== =========================================================================
kind     editor
======== =========================================================================
size     `SizeEdit`: a number and a unit (%, px, mm, cm, in)
color    `ColorEdit`: a swatch, the hex text and a clear button
choice   `ChoiceEdit`: a dropdown
font     `FontEdit`: a dropdown of the installed families that also takes a name
offset   `OffsetEdit`: x and y as a share of the dial's diameter
intset   `IntSetEdit`: numbers with commas, checked as you type
format   `FormatEdit`: decimals, unit shown, compact
gradient `GradientEdit`: a colour band (folded) or a band of draggable nodes and a row per stop (open); each stop has its own unit
textmap  `TextMapEdit`: value to word table, with compass and E/F presets
zones    `ZonesEdit`: a list of bands
markers  `MarkersEdit`: a list of markers with the real needle types
fill     `FillEdit`: the value-driven arc
caption  `CaptionEdit`: text or a key, with format
======== =========================================================================

A value that needs a key (a marker, a fill end, a caption) uses `KeyEdit`, a
dropdown that completes as you type from every key the studio knows.
"""
import re
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QPointF, QRectF, QRegularExpression, QSignalBlocker, Qt, QTime, Signal
from PySide6.QtGui import (
	QBrush, QColor, QFontDatabase, QLinearGradient, QPainter, QPainterPath, QPalette, QPen, QRegularExpressionValidator,
)
from PySide6.QtWidgets import (
	QCheckBox, QColorDialog, QComboBox, QCompleter, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
	QSlider, QSpinBox, QTimeEdit, QToolButton, QVBoxLayout, QWidget,
)

from LevityDash.devtools import _studio_schema as schema
from LevityDash.devtools import _studio_stops as stops
from LevityDash.devtools._studio_stops import niceStep, snapTo
from LevityDash.lib.ui.colors.stopunits import formatStop

__all__ = ['Editor', 'make', 'CONTEXT', 'knownKeys']


@dataclass
class Context:
	"""What the editors need to know about the gauge that is open. The window keeps it current."""
	unit: str = ''
	range: Callable[[], tuple] = lambda: (0.0, 100.0)
	keys: List[str] = field(default_factory=list)
	#: The unit a number is shown in, and the units the data can be shown in: name to (native -> shown, shown -> native).
	shown: str = ''
	units: Dict[str, tuple] = field(default_factory=dict)
	#: Called after the shown unit changes, so every control redraws.
	refresh: Callable[[], None] = lambda: None
	#: Pixels a '%' size is a share of: 'radius' is the dial's radius now, 'full' the radius at 100%.
	ref: Callable[[str], float] = lambda kind='radius': 100.0
	dpi: float = 100.0
	#: The class of the gauge's data (a WeatherUnits unit class), which a stop in another unit converts to.
	valueClass: Callable[[], Optional[type]] = lambda: None
	#: The range the dial spans, in the gauge's own unit.
	span: Callable[[], tuple] = lambda: (0.0, 100.0)
	#: A drag that spans several edits (a node on the band) is one undo step: it starts here and ends here.
	beginDrag: Callable[[], None] = lambda: None
	endDrag: Callable[[bool], None] = lambda changed=True: None
	#: Whether the meter shows the gradient's nodes, and the switch for it.
	gradientMode: Callable[[], bool] = lambda: False
	setGradientMode: Callable[[bool], None] = lambda on: None

	def toShown(self, value: float) -> float:
		fn = self.units.get(self.shown)
		return value if fn is None else fn[0](value)

	def toNative(self, value: float) -> float:
		fn = self.units.get(self.shown)
		return value if fn is None else fn[1](value)

	def symbol(self) -> str:
		return self.shown or self.unit


CONTEXT = Context()

#: The colour of quiet text (hints). The window sets it with the theme.
MUTED = '#8b949e'

_WEATHER_KEYS = [
	'environment.temperature.temperature', 'environment.temperature.high', 'environment.temperature.low',
	'environment.temperature.dewpoint', 'environment.humidity.humidity', 'environment.pressure.pressure',
	'environment.wind.speed.speed', 'environment.wind.speed.gust', 'environment.wind.speed.lull',
	'environment.wind.direction.direction', 'environment.precipitation.precipitation',
	'environment.precipitation.probability', 'environment.light.uvi', 'environment.light.illuminance',
	'environment.light.irradiance.irradiance', 'environment.clouds.cover.cover', 'environment.soil.moisture',
	'environment.soil.temperature', 'environment.visibility', 'indoor.temperature.temperature',
	'indoor.humidity.humidity', 'indoor.battery.battery', 'astronomy.sun.hour', 'time.timer.seconds',
]

_keyCache: List[str] = []


def knownKeys() -> List[str]:
	"""Every key the studio can name: the made-up data's own, the common weather keys and the Mock plugin's."""
	if _keyCache:
		return _keyCache
	keys = list(_WEATHER_KEYS)
	try:
		from LevityDash.devtools._studio_stage import DATA_PRESETS
		keys += [p.key for p in DATA_PRESETS.values()]
	except Exception:  # noqa: BLE001 - a missing list must not stop the studio
		pass
	try:
		from LevityDash.lib.plugins.builtin.Mock import MOCK_KEYS
		keys += list(MOCK_KEYS)
	except Exception:  # noqa: BLE001
		pass
	_keyCache.extend(sorted(set(keys)))
	return _keyCache


SLIDER_STEPS = 1000


class Slide(QSlider):
	"""A slider over real numbers, kept beside a spinbox for the precise value.

	The span is the base span, stretched to hold the value it shows. It stays fixed while the
	handle is down, so a drag does not move the scale under the mouse. `moved(value)` reports
	only a move the user made; `showValue` never reports.
	"""

	moved = Signal(float)

	def __init__(self, lo: float = 0.0, hi: float = 100.0, digits: int = 3):
		super().__init__(Qt.Orientation.Horizontal)
		self.setRange(0, SLIDER_STEPS)
		self.setMinimumWidth(56)
		self.base = (lo, hi)
		self.span = (lo, hi)
		self.digits = digits
		self.valueChanged.connect(self._moved)

	def setBase(self, lo: float, hi: float):
		self.base = (lo, hi) if hi > lo else (lo, lo + 1)
		if not self.isSliderDown():
			self.span = self.base

	def _moved(self, pos: int):
		lo, hi = self.span
		self.moved.emit(round(lo + pos / SLIDER_STEPS * (hi - lo), self.digits))

	def showValue(self, value: Optional[float]):
		if self.isSliderDown():
			return
		lo, hi = self.base
		if value is not None:
			lo, hi = min(lo, value), max(hi, value)
		self.span = (lo, hi)
		with QSignalBlocker(self):
			self.setValue(round((value - lo) / (hi - lo) * SLIDER_STEPS) if value is not None and hi > lo else 0)


_SIZE = re.compile(r'^\s*(-?\d*\.?\d+)\s*(%|px|mm|cm|in)?\s*$')
UNITS = ['%', 'px', 'mm', 'cm', 'in']


def _tool(text: str, tip: str = '') -> QToolButton:
	b = QToolButton()
	b.setText(text)
	b.setAutoRaise(True)
	b.setToolTip(tip)
	return b


class Editor(QWidget):
	"""A control that shows one value and reports edits as `changed(value)`."""

	changed = Signal(object)
	#: A wide editor gets the whole row, with its label on top.
	wide = False

	def setValue(self, value: Any) -> None:
		raise NotImplementedError

	def value(self) -> Any:
		raise NotImplementedError

	def onContext(self) -> None:
		"""The gauge or its unit changed: refresh anything that shows them."""

	def _emit(self, *_):
		self.changed.emit(self.value())


# Section: single values

_LEADING_NUMBER = re.compile(r'^\s*(-?\d+(?:\.\d+)?)')


def _number(value: Any) -> Optional[float]:
	"""A number from a saved value: `10`, `'10'` or `'10°'`; None for anything else."""
	if isinstance(value, bool) or value is None:
		return None
	if isinstance(value, (int, float)):
		return float(value)
	if isinstance(value, str) and (m := _LEADING_NUMBER.match(value)):
		return float(m.group(1))
	return None


def _liveDpi() -> float:
	"""Ask for the dpi each time: it depends on which window is active, and the gauge asks the same way."""
	try:
		from LevityDash.lib.ui.Geometry import getDPI
		return float(getDPI())
	except Exception:  # noqa: BLE001
		return CONTEXT.dpi


class UnitBox(QComboBox):
	"""The unit a measured number is shown in. Choosing one redraws every control; no value changes."""

	def __init__(self):
		super().__init__()
		self.setToolTip('The unit this number is shown in. The gauge keeps its own unit, so nothing moves when you switch.')
		self.activated.connect(self._picked)

	def _picked(self, _):
		CONTEXT.shown = self.currentText()
		CONTEXT.refresh()

	def sync(self):
		with QSignalBlocker(self):
			names = list(CONTEXT.units)
			if [self.itemText(i) for i in range(self.count())] != names:
				self.clear()
				self.addItems(names)
			self.setCurrentText(CONTEXT.symbol())
		self.setVisible(bool(CONTEXT.units))


class NumberEdit(Editor):
	"""A number, with an optional 'off' state (`autoText` names what off means).

	A `measured` number is in the gauge's own unit (degrees F, inHg, mph). It is held in that
	unit and shown in the unit the context names, so a switch from F to C moves no value.
	`unitBox` adds the dropdown; without it the unit shows as a suffix.
	"""

	def __init__(self, autoText: Optional[str] = None, suffix: str = '', lo: float = -1e9, hi: float = 1e9,
	             step: float = 1.0, decimals: int = 3, measured: bool = False, integer: bool = False, slider: bool = True,
	             unitBox: bool = False):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		box.setSpacing(4)
		self.measured = measured
		self.baseSuffix = suffix
		self.native: float = 0.0
		self.auto: Optional[QCheckBox] = None
		if autoText is not None:
			self.auto = QCheckBox(autoText)
			self.auto.setChecked(True)
			self.auto.toggled.connect(self._autoToggled)
			box.addWidget(self.auto)
		self.spin = QSpinBox() if integer else QDoubleSpinBox()
		self.spin.setRange(int(lo) if integer else lo, int(hi) if integer else hi)
		if not integer:
			self.spin.setDecimals(decimals)
		self.spin.setSingleStep(step)
		self.spin.setKeyboardTracking(False)
		self.spin.setMinimumWidth(48)
		self.spin.valueChanged.connect(self._spun)
		self.slide: Optional[Slide] = None
		self.lo, self.hi = lo, hi
		if slider:
			self.slide = Slide(digits=0 if integer else min(decimals, 3))
			self.slide.moved.connect(self._slid)
			self._fitSlider()
			box.addWidget(self.slide, 1)
		box.addWidget(self.spin, 0 if slider else 1)
		self.unitBox: Optional[UnitBox] = None
		if measured and unitBox:
			self.unitBox = UnitBox()
			box.addWidget(self.unitBox)
		self._applySuffix()
		if self.auto is not None:
			self.spin.setEnabled(False)
			if self.slide is not None:
				self.slide.setEnabled(False)

	def _fitSlider(self):
		# The scale: the data range (in the shown unit) for a measured number, else the limits given (0 to 100 when none).
		if self.slide is None:
			return
		if self.measured:
			lo, hi = sorted((CONTEXT.toShown(v) for v in CONTEXT.range()))
		elif abs(self.lo) < 1e6 and abs(self.hi) < 1e6:
			lo, hi = self.lo, self.hi
		else:
			lo, hi = 0.0, 100.0
		self.slide.setBase(lo, hi)

	def _applySuffix(self):
		suffix = self.baseSuffix
		if self.measured and self.unitBox is None and CONTEXT.symbol():
			suffix = f' {CONTEXT.symbol()}'
		self.spin.setSuffix(suffix)
		if self.unitBox is not None:
			self.unitBox.sync()

	def _show(self):
		"""Put the held number on the spinbox and the slider, in the shown unit."""
		shown = CONTEXT.toShown(self.native) if self.measured else self.native
		with QSignalBlocker(self.spin):
			self.spin.setValue(int(round(shown)) if isinstance(self.spin, QSpinBox) else shown)
		if self.slide is not None:
			self._fitSlider()
			self.slide.showValue(float(self.spin.value()) if self.spin.isEnabled() else None)

	def onContext(self):
		self._applySuffix()
		self._show()

	def _spun(self, value):
		self._take(float(value))
		if self.slide is not None:
			self.slide.showValue(float(value))
		self._emit()

	def _slid(self, value: float):
		with QSignalBlocker(self.spin):
			self.spin.setValue(int(round(value)) if isinstance(self.spin, QSpinBox) else value)
		self._take(float(self.spin.value()))
		self._emit()

	def _take(self, shown: float):
		self.native = round(CONTEXT.toNative(shown), 4) if self.measured else shown

	def _autoToggled(self, on: bool):
		self.spin.setEnabled(not on)
		if self.slide is not None:
			self.slide.setEnabled(not on)
		self._emit()

	def setValue(self, value):
		if self.auto is not None:
			with QSignalBlocker(self.auto):
				self.auto.setChecked(value is None)
			self.spin.setEnabled(value is not None)
			if self.slide is not None:
				self.slide.setEnabled(value is not None)
		number = _number(value)
		if number is not None:
			self.native = number
		elif value is not None:
			value = None
		self._show()
		if value is None and self.slide is not None:
			self.slide.showValue(None)

	def value(self):
		if self.auto is not None and self.auto.isChecked():
			return None
		v = self.native
		return int(v) if isinstance(self.spin, QSpinBox) or float(v).is_integer() else round(float(v), 4)

	def isEditing(self) -> bool:
		return self.spin.hasFocus() or (self.slide is not None and self.slide.isSliderDown())


class SizeEdit(Editor):
	"""A size: a number and its unit. `nullable` adds an 'auto' box that unsets it."""

	def __init__(self, nullable: bool = False, autoText: str = 'auto', units: Optional[List[str]] = None, ref: str = 'radius'):
		super().__init__()
		self.ref = ref
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		box.setSpacing(4)
		self.auto: Optional[QCheckBox] = None
		if nullable:
			self.auto = QCheckBox(autoText)
			self.auto.setChecked(True)
			self.auto.toggled.connect(self._autoToggled)
			box.addWidget(self.auto)
		self.spin = QDoubleSpinBox()
		self.spin.setRange(-10000, 10000)
		self.spin.setDecimals(2)
		self.spin.setKeyboardTracking(False)
		self.spin.setMinimumWidth(48)
		self.spin.valueChanged.connect(self._spun)
		self.slide = Slide(digits=2)
		self.slide.moved.connect(self._slid)
		self.unit = QComboBox()
		# Inches are left out of the small sizes (weights, gaps): WeatherUnits calls any inch value
		# within about 0.05 of a default equal to it, so the export drops 0.09 in and the gauge falls back.
		self.unit.addItems(units or (UNITS if ref == 'full' else [u for u in UNITS if u != 'in']))
		self.unit.setToolTip('% is a share of the dial; px is scene pixels; mm, cm and in are physical')
		self.unit.activated.connect(self._unitPicked)
		box.addWidget(self.slide, 1)
		box.addWidget(self.spin)
		box.addWidget(self.unit)
		self._fitSlider()
		if nullable:
			self.spin.setEnabled(False)
			self.unit.setEnabled(False)
			self.slide.setEnabled(False)

	#: The scale of the slider for each unit: a share of the dial, scene pixels, then physical sizes.
	SPANS = {'%': (0.0, 100.0), 'px': (0.0, 500.0), 'mm': (0.0, 50.0), 'cm': (0.0, 5.0), 'in': (0.0, 2.0)}

	def _fitSlider(self):
		self.slide.setBase(*self.SPANS.get(self.unit.currentText(), (0.0, 100.0)))
		self.slide.showValue(float(self.spin.value()))

	def _spun(self, value):
		self.slide.showValue(float(value))
		self._emit()

	def _slid(self, value: float):
		with QSignalBlocker(self.spin):
			self.spin.setValue(value)
		self._emit()

	def _autoToggled(self, on: bool):
		self.spin.setEnabled(not on)
		self.unit.setEnabled(not on)
		self.slide.setEnabled(not on)
		self._emit()

	def pixels(self, value: float, unit: str) -> float:
		"""A size in scene pixels. A '%' is a share of `ref`; physical units go through the dpi the dashboard uses."""
		dpi = _liveDpi()
		return {'%': value / 100 * CONTEXT.ref(self.ref), 'px': value, 'mm': value / 25.4 * dpi, 'cm': value / 2.54 * dpi,
		        'in': value * dpi}.get(unit, value)

	def fromPixels(self, px: float, unit: str) -> float:
		dpi = _liveDpi()
		ref = CONTEXT.ref(self.ref) or 1.0
		return {'%': px / ref * 100, 'px': px, 'mm': px / dpi * 25.4, 'cm': px / dpi * 2.54, 'in': px / dpi}.get(unit, px)

	def _unitPicked(self, _):
		"""Show the same size in the new unit, so the gauge does not jump."""
		new = self.unit.currentText()
		old = self._unit
		if old != new and self.spin.isEnabled():
			value = round(self.fromPixels(self.pixels(self.spin.value(), old), new), 2)
			with QSignalBlocker(self.spin):
				self.spin.setValue(value)
		self._unit = new
		self.spin.setSingleStep(1.0 if new in ('%', 'px') else 0.5)
		self._fitSlider()
		self._emit()

	_unit = '%'

	def setValue(self, value):
		with QSignalBlocker(self.spin), QSignalBlocker(self.unit):
			if self.auto is not None:
				with QSignalBlocker(self.auto):
					self.auto.setChecked(value is None)
				self.spin.setEnabled(value is not None)
				self.unit.setEnabled(value is not None)
				self.slide.setEnabled(value is not None)
			if value is None:
				return
			m = _SIZE.match(str(value))
			if m is None:
				return
			self.spin.setValue(float(m.group(1)))
			i = self.unit.findText(m.group(2) or '%')
			if i < 0:
				self.unit.addItem(m.group(2))
				i = self.unit.count() - 1
			self.unit.setCurrentIndex(i)
			self._unit = self.unit.currentText()
			self._fitSlider()

	def value(self):
		if self.auto is not None and self.auto.isChecked():
			return None
		return f'{self.spin.value():g}{self.unit.currentText()}'

	def isEditing(self) -> bool:
		return self.spin.hasFocus() or self.slide.isSliderDown()


class ColorEdit(Editor):
	"""A swatch that opens the colour dialog, the hex text, and a clear button for a colour that may be unset."""

	def __init__(self, nullable: bool = False):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		box.setSpacing(4)
		self.swatch = QPushButton()
		self.swatch.setFixedSize(28, 20)
		self.swatch.setToolTip('Pick a colour')
		self.swatch.clicked.connect(self._pick)
		self.text = QLineEdit()
		self.text.setPlaceholderText('default' if nullable else '#rrggbb')
		self.text.editingFinished.connect(self._typed)
		box.addWidget(self.swatch)
		box.addWidget(self.text, 1)
		self.clear: Optional[QToolButton] = None
		if nullable:
			self.clear = _tool('×', 'Back to the default colour')
			self.clear.clicked.connect(self._cleared)
			box.addWidget(self.clear)
		self._color: Optional[str] = None

	def _pick(self):
		chosen = QColorDialog.getColor(QColor(self._color or 'white'), self, 'Colour')
		if chosen.isValid():
			self._set(chosen.name())
			self._emit()

	def _typed(self):
		text = self.text.text().strip()
		if text == '':
			self._set(None)
		elif QColor(text).isValid():
			self._set(text)
		else:
			self.text.setText(self._color or '')
			return
		self._emit()

	def _cleared(self):
		self._set(None)
		self._emit()

	def _set(self, value: Optional[str]):
		self._color = value
		with QSignalBlocker(self.text):
			self.text.setText('' if value is None else str(value))
		color = QColor(value) if value else QColor()
		self.swatch.setStyleSheet(f'background: {color.name() if color.isValid() else "transparent"}; border: 1px solid #888;')

	def setValue(self, value):
		self._set(None if value is None else str(value))

	def value(self):
		return self._color

	def isEditing(self) -> bool:
		return self.text.hasFocus()


class ChoiceEdit(Editor):
	"""A dropdown over (label, saved value) pairs."""

	def __init__(self, choices: List[tuple], editable: bool = False):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		self.combo = QComboBox()
		self.combo.setEditable(editable)
		for label, value in choices:
			self.combo.addItem(label, value)
		self.combo.activated.connect(self._emit)
		box.addWidget(self.combo, 1)

	def setValue(self, value):
		if isinstance(value, str) and value.lower() == 'auto':
			value = None
		with QSignalBlocker(self.combo):
			for i in range(self.combo.count()):
				if schema._same(self.combo.itemData(i), value) and (value is not None or self.combo.itemData(i) is None):
					self.combo.setCurrentIndex(i)
					return
			if self.combo.isEditable() and value is not None:
				self.combo.setEditText(str(value))
			else:
				self.combo.setCurrentIndex(-1)

	def value(self):
		i = self.combo.currentIndex()
		if i >= 0 and self.combo.itemText(i) == self.combo.currentText():
			return self.combo.itemData(i)
		return self.combo.currentText() or None

	def isEditing(self) -> bool:
		return self.combo.hasFocus() or self.combo.view().isVisible()


def pickerFamilies() -> list[str]:
	"""Bundled and user-folder families, common families, and `[Fonts] extra`, each only if installed."""
	from LevityDash import LevityDashboard
	from LevityDash.lib.config import userConfig
	from LevityDash.lib.ui.fontlist import curatedFamilies, folderFamilies, parseExtra
	extra = parseExtra(userConfig.get('Fonts', 'extra', fallback=None))
	bundled = folderFamilies(Path(LevityDashboard.resources) / 'fonts', userConfig.userPath.path / 'fonts')
	return curatedFamilies(QFontDatabase.families(), bundled, extra)


class FontEdit(ChoiceEdit):
	"""A short list of fonts, and any other name you type. See `lib/ui/fontlist.py`."""

	def __init__(self):
		super().__init__([(name, name) for name in pickerFamilies()], editable=True)
		self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
		self.combo.lineEdit().editingFinished.connect(self._emit)
		completer = self.combo.completer()
		if completer is not None:
			completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
			completer.setFilterMode(Qt.MatchFlag.MatchContains)


class KeyEdit(Editor):
	"""A key: a dropdown that completes as you type, over every key the studio knows."""

	def __init__(self, placeholder: str = 'environment.temperature.high'):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		self.combo = QComboBox()
		self.combo.setEditable(True)
		self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
		self.combo.addItems(knownKeys())
		self.combo.setCurrentIndex(-1)
		self.combo.lineEdit().setPlaceholderText(placeholder)
		completer = QCompleter(knownKeys(), self.combo)
		completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
		completer.setFilterMode(Qt.MatchFlag.MatchContains)
		self.combo.setCompleter(completer)
		self.combo.activated.connect(self._emit)
		self.combo.lineEdit().editingFinished.connect(self._emit)
		box.addWidget(self.combo, 1)

	def setValue(self, value):
		with QSignalBlocker(self.combo):
			self.combo.setEditText('' if value is None else str(value))

	def value(self):
		return self.combo.currentText().strip() or None

	def isEditing(self) -> bool:
		return self.combo.lineEdit().hasFocus() or self.combo.view().isVisible()


class ValueOrKey(Editor):
	"""A number, or a key, or (when `autoText` is given) nothing: the gauge picks."""

	def __init__(self, autoText: Optional[str] = None):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		box.setSpacing(4)
		self.mode = QComboBox()
		self.modes = ([autoText] if autoText else []) + ['number', 'key']
		self.mode.addItems(self.modes)
		self.mode.activated.connect(self._modeChanged)
		self.number = NumberEdit(measured=True)
		self.number.changed.connect(self._emit)
		self.key = KeyEdit()
		self.key.changed.connect(self._emit)
		box.addWidget(self.mode)
		box.addWidget(self.number, 1)
		box.addWidget(self.key, 1)
		self._showMode()

	def _current(self) -> str:
		text = self.mode.currentText()
		return text if text in ('number', 'key') else 'auto'

	def _showMode(self):
		mode = self._current()
		self.number.setVisible(mode == 'number')
		self.key.setVisible(mode == 'key')

	def _modeChanged(self, _):
		self._showMode()
		if self._current() == 'number':
			lo, hi = CONTEXT.range()
			with QSignalBlocker(self.number):
				if self.number.spin.value() == 0:
					self.number.setValue((lo + hi) / 2)
		self._emit()

	def onContext(self):
		self.number.onContext()

	def setValue(self, value):
		if value is None:
			mode = 'auto' if len(self.modes) == 3 else 'number'
		elif isinstance(value, (int, float)) and not isinstance(value, bool):
			mode = 'number'
		else:
			mode = 'key'
		with QSignalBlocker(self.mode):
			self.mode.setCurrentIndex(0 if mode == 'auto' else self.modes.index(mode))
		if mode == 'number' and value is not None:
			self.number.setValue(value)
		elif mode == 'key':
			self.key.setValue(value)
		self._showMode()

	def value(self):
		mode = self._current()
		if mode == 'number':
			return self.number.value()
		if mode == 'key':
			return self.key.value()
		return None

	def isEditing(self) -> bool:
		return self.number.isEditing() or self.key.isEditing() or self.mode.view().isVisible()


class OffsetEdit(Editor):
	"""Move a label: x and y as a percentage of the dial's diameter. Dragging the label on the preview writes the same value."""

	def __init__(self):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		box.setSpacing(4)
		self.x = QDoubleSpinBox()
		self.y = QDoubleSpinBox()
		self.slides = {}
		for label, spin in (('x', self.x), ('y', self.y)):
			spin.setRange(-100, 100)
			spin.setDecimals(1)
			spin.setSingleStep(0.5)
			spin.setSuffix(' %')
			spin.setKeyboardTracking(False)
			spin.setToolTip(f'{label}: share of the dial\'s diameter; positive is right (x) or down (y)')
			slide = Slide(-50.0, 50.0, digits=1)
			slide.setToolTip(spin.toolTip())
			slide.moved.connect(lambda v, s=spin: self._slid(s, v))
			spin.valueChanged.connect(lambda v, k=label: self._spun(k, v))
			self.slides[label] = slide
			box.addWidget(QLabel(label))
			box.addWidget(slide, 1)
			box.addWidget(spin)
		self.clear = _tool('×', 'Back to the default place')
		self.clear.clicked.connect(self._cleared)
		box.addWidget(self.clear)

	def _cleared(self):
		self.setValue(None)
		self._emit()

	def _spun(self, key: str, value: float):
		self.slides[key].showValue(value)
		self._emit()

	def _slid(self, spin: QDoubleSpinBox, value: float):
		with QSignalBlocker(spin):
			spin.setValue(value)
		self._emit()

	def setValue(self, value):
		x = y = 0.0
		if isinstance(value, dict):
			x, y = float(value.get('x', 0)), float(value.get('y', 0))
		with QSignalBlocker(self.x), QSignalBlocker(self.y):
			self.x.setValue(x * 100)
			self.y.setValue(y * 100)
		self.slides['x'].showValue(self.x.value())
		self.slides['y'].showValue(self.y.value())

	def value(self):
		x, y = round(self.x.value() / 100, 4), round(self.y.value() / 100, 4)
		return None if x == 0 and y == 0 else {'x': x, 'y': y}

	def isEditing(self) -> bool:
		return self.x.hasFocus() or self.y.hasFocus() or any(s.isSliderDown() for s in self.slides.values())


class IntSetEdit(Editor):
	"""A set of whole numbers, picked from boxes. A number the file holds that is not a candidate gets a box too."""

	CANDIDATES = [1, 2, 2.5, 3, 4, 5, 6, 8, 10]

	def __init__(self):
		super().__init__()
		self.grid = QGridLayout(self)
		self.grid.setContentsMargins(0, 0, 0, 0)
		self.grid.setSpacing(4)
		self.boxes: Dict[float, QCheckBox] = {}
		for n in self.CANDIDATES:
			self._box(n)

	def _box(self, n: float) -> QCheckBox:
		box = QCheckBox(f'{n:g}')
		box.toggled.connect(self._emit)
		i = len(self.boxes)
		self.grid.addWidget(box, i // 5, i % 5)
		self.boxes[n] = box
		return box

	def setValue(self, value):
		items = {float(v) for v in (value or [])}
		for n in sorted(items - set(self.boxes)):
			self._box(n)
		for n, box in self.boxes.items():
			with QSignalBlocker(box):
				box.setChecked(n in items)

	def value(self):
		return sorted(int(n) if float(n).is_integer() else n for n, box in self.boxes.items() if box.isChecked())

	def isEditing(self) -> bool:
		return any(b.hasFocus() for b in self.boxes.values())


FORMAT_PRESETS = [
	('auto', None), ('duration (4h 49m)', 'duration'), ('0 decimals', {'precision': 0}), ('1 decimal', {'precision': 1}),
	('2 decimals', {'precision': 2}), ('no unit', {'show_unit': False}),
]


class FormatEdit(Editor):
	"""How a number prints: a preset, or decimals and whether the unit shows."""

	def __init__(self):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		box.setSpacing(4)
		self.decimals = NumberEdit(autoText='auto', integer=True, lo=0, hi=8, step=1, slider=False)
		self.decimals.setToolTip('Digits after the point')
		self.decimals.changed.connect(self._emit)
		self.unit = QComboBox()
		self.unit.addItem('unit: auto', None)
		self.unit.addItem('show unit', True)
		self.unit.addItem('hide unit', False)
		self.unit.activated.connect(self._emit)
		self.compact = QComboBox()
		self.compact.addItem('compact: auto', None)
		self.compact.addItem('compact', True)
		self.compact.addItem('full', False)
		self.compact.activated.connect(self._emit)
		self.duration = QCheckBox('duration')
		self.duration.setToolTip('Show minutes as 4h 49m')
		self.duration.toggled.connect(self._emit)
		for w in (self.duration, self.decimals, self.unit, self.compact):
			box.addWidget(w, 1 if w is self.decimals else 0)
		self._extra: dict = {}

	def setValue(self, value):
		self._extra = {}
		with QSignalBlocker(self.duration), QSignalBlocker(self.unit), QSignalBlocker(self.compact), QSignalBlocker(self.decimals):
			self.duration.setChecked(value == 'duration')
			spec = value if isinstance(value, dict) else {}
			self._extra = {k: v for k, v in spec.items() if k not in ('precision', 'show_unit', 'compact')}
			self.decimals.setValue(spec.get('precision'))
			self.unit.setCurrentIndex(max(self.unit.findData(spec.get('show_unit')), 0))
			self.compact.setCurrentIndex(max(self.compact.findData(spec.get('compact')), 0))
			for w in (self.decimals, self.unit, self.compact):
				w.setEnabled(value != 'duration')

	def value(self):
		if self.duration.isChecked():
			return 'duration'
		out = dict(self._extra)
		if (p := self.decimals.value()) is not None:
			out['precision'] = p
		if (u := self.unit.currentData()) is not None:
			out['show_unit'] = u
		if (c := self.compact.currentData()) is not None:
			out['compact'] = c
		return out or None

	def _emit(self, *_):
		for w in (self.decimals, self.unit, self.compact):
			w.setEnabled(not self.duration.isChecked())
		super()._emit()

	def isEditing(self) -> bool:
		return self.decimals.isEditing()


# Section: lists

class _ItemRow(QFrame):
	"""One entry of a list: its editor and a remove button."""

	removed = Signal(object)

	def __init__(self, item: Editor):
		super().__init__()
		self.item = item
		self.setFrameShape(QFrame.Shape.StyledPanel)
		box = QHBoxLayout(self)
		box.setContentsMargins(4, 3, 2, 3)
		box.addWidget(item, 1)
		remove = _tool('×', 'Remove')
		remove.clicked.connect(lambda: self.removed.emit(self))
		box.addWidget(remove, 0, Qt.AlignmentFlag.AlignTop)


class ListEditor(Editor):
	"""Add and remove entries. Each entry is an `Editor` made by `factory`; `fresh` makes the first value of a new one."""

	wide = True

	def __init__(self, factory: Callable[[], Editor], fresh: Callable[[List[Any]], Any], addText: str = '+ Add', empty: str = '', measured: bool = False):
		super().__init__()
		self.factory, self.fresh = factory, fresh
		box = QVBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		box.setSpacing(3)
		self.hint = QLabel(empty)
		self.hint.setStyleSheet('color: palette(placeholder-text); font-size: 11px;')
		self.hint.setVisible(bool(empty))
		box.addWidget(self.hint)
		self.unitBox: Optional[UnitBox] = None
		if measured:
			header = QHBoxLayout()
			header.addWidget(QLabel('values in'))
			self.unitBox = UnitBox()
			header.addWidget(self.unitBox)
			header.addStretch(1)
			box.addLayout(header)
			self.unitBox.sync()
		self.body = QVBoxLayout()
		self.body.setSpacing(3)
		box.addLayout(self.body)
		self.add = QPushButton(addText)
		self.add.clicked.connect(self._add)
		box.addWidget(self.add)
		self.rows: List[_ItemRow] = []

	def items(self) -> List[Any]:
		return [r.item.value() for r in self.rows]

	def _make(self, value: Any) -> _ItemRow:
		item = self.factory()
		item.setValue(value)
		item.changed.connect(self._emit)
		row = _ItemRow(item)
		row.removed.connect(self._remove)
		self.rows.append(row)
		self.body.addWidget(row)
		return row

	def _add(self):
		self._make(self.fresh(self.items()))
		self._refreshHint()
		self._emit()

	def _remove(self, row: _ItemRow):
		self.rows.remove(row)
		row.setParent(None)
		row.deleteLater()
		self._refreshHint()
		self._emit()

	def _refreshHint(self):
		self.hint.setVisible(bool(self.hint.text()) and not self.rows)

	def setItems(self, values: List[Any]):
		if values == self.items():
			return
		for row in self.rows:
			row.setParent(None)
			row.deleteLater()
		self.rows = []
		for v in values:
			self._make(v)
		self._refreshHint()

	def setValue(self, value):
		self.setItems(list(value or []))

	def value(self):
		return self.items() or None

	def onContext(self):
		if self.unitBox is not None:
			self.unitBox.sync()
		for row in self.rows:
			row.item.onContext()

	def isEditing(self) -> bool:
		return any(w.hasFocus() for w in self.findChildren(QWidget))


def _grid(editor: QWidget) -> QGridLayout:
	g = QGridLayout(editor)
	g.setContentsMargins(0, 0, 0, 0)
	g.setHorizontalSpacing(6)
	g.setVerticalSpacing(3)
	g.setColumnStretch(1, 1)
	return g


class _Form(Editor):
	"""A dict editor: labelled sub-editors in a grid. Keys it does not know are kept as they were."""

	def __init__(self):
		super().__init__()
		self.grid = _grid(self)
		self.parts: Dict[str, Editor] = {}
		self.labels: Dict[str, QLabel] = {}
		self._extra: dict = {}
		self._known: set = set()
		self._r = 0

	def part(self, key: str, label: str, editor: Editor, tip: str = '', span: bool = False):
		editor.changed.connect(self._emit)
		self.parts[key] = editor
		self._known.add(key)
		name = QLabel(label)
		name.setToolTip(tip)
		self.labels[key] = name
		self.grid.addWidget(name, self._r, 0)
		self.grid.addWidget(editor, self._r, 1)
		self._r += 1
		return editor

	def showPart(self, key: str, on: bool):
		self.parts[key].setVisible(on)
		self.labels[key].setVisible(on)

	def onContext(self):
		for p in self.parts.values():
			p.onContext()

	def isEditing(self) -> bool:
		return any(w.hasFocus() for w in self.findChildren(QWidget))


class ZoneItem(_Form):
	def __init__(self):
		super().__init__()
		self.part('from', 'from', NumberEdit(autoText='range start', measured=True), 'Where the band starts. Unticked is a number.')
		self.part('to', 'to', NumberEdit(autoText='range end', measured=True), 'Where the band ends.')
		self.part('color', 'colour', ColorEdit())
		self.part('weight', 'weight', SizeEdit(nullable=True, autoText='arc'), 'Band thickness; by default the arc\'s.')
		self.mark = QCheckBox('tick across the arc at each cutoff')
		self.mark.toggled.connect(self._emit)
		self.grid.addWidget(self.mark, self._r, 1)

	def setValue(self, value):
		spec = dict(value or {})
		self._extra = {k: v for k, v in spec.items() if k not in self._known and k != 'mark'}
		for key, p in self.parts.items():
			with QSignalBlocker(p):
				p.setValue(spec.get(key))
		with QSignalBlocker(self.mark):
			self.mark.setChecked(bool(spec.get('mark')))

	def value(self):
		out = dict(self._extra)
		for key, p in self.parts.items():
			v = p.value()
			if v is not None:
				out[key] = v
		if self.mark.isChecked():
			out['mark'] = True
		return out


class ZonesEdit(ListEditor):
	def __init__(self):
		super().__init__(ZoneItem, self._fresh, '+ Add zone', 'No zones. The track is one colour.', measured=True)

	@staticmethod
	def _fresh(items):
		lo, hi = CONTEXT.range()
		last = next((i.get('to') for i in reversed(items) if i.get('to') is not None), lo)
		start = last if last < hi else lo
		return {'from': round(start, 3), 'to': round(min(hi, start + (hi - lo) / 4), 3), 'color': '#f5a524'}


def pickColor(parent: QWidget, initial: Optional[str]) -> Optional[str]:
	"""The colour the user picks, as `#rrggbb`, or None for cancel. `PICKER` stands in for the dialog in a scripted run."""
	if PICKER is not None:
		return PICKER(initial)
	chosen = QColorDialog.getColor(QColor(initial or 'white'), parent, 'Colour')
	return chosen.name() if chosen.isValid() else None


PICKER: Optional[Callable[[Optional[str]], Optional[str]]] = None


def _spanOf(unit: Optional[str]) -> float:
	"""The width of the gauge's range in `unit` (the shown unit when there is none)."""
	lo, hi = sorted(CONTEXT.span())
	vc = CONTEXT.valueClass()
	if unit:
		return abs(stops.fromNative(hi, unit, vc) - stops.fromNative(lo, unit, vc))
	return abs(CONTEXT.toShown(hi) - CONTEXT.toShown(lo))


class StopRow(Editor):
	"""One gradient stop: its colour, and its value with a unit of its own.

	A stop written with a unit (`99°F`) holds the number in that unit. Another unit in the box
	converts the number and keeps the reading, so nothing moves on the meter. A bare number (no
	unit) is in the gauge's own unit and shows in the unit the context names, as a zone does.
	"""

	def __init__(self):
		super().__init__()
		grid = QGridLayout(self)
		grid.setContentsMargins(0, 0, 0, 0)
		grid.setHorizontalSpacing(4)
		grid.setVerticalSpacing(3)
		self.color = ColorEdit()
		self.color.changed.connect(self._emit)
		grid.addWidget(self.color, 0, 0, 1, 3)
		self.slide = Slide(digits=3)
		self.slide.moved.connect(self._slid)
		self.spin = QDoubleSpinBox()
		self.spin.setRange(-1e9, 1e9)
		self.spin.setDecimals(3)
		self.spin.setKeyboardTracking(False)
		self.spin.setMinimumWidth(80)
		self.spin.valueChanged.connect(self._spun)
		self.unitCombo = QComboBox()
		self.unitCombo.setToolTip('The unit this stop is written in. A different unit converts the number; the colour stays at the same reading.')
		self.unitCombo.activated.connect(self._unitPicked)
		grid.addWidget(self.slide, 1, 0)
		grid.addWidget(self.spin, 1, 1)
		grid.addWidget(self.unitCombo, 1, 2)
		grid.setColumnStretch(0, 1)
		self.number = 0.0
		self.unit: Optional[str] = None

	# the value

	def stop(self) -> 'stops.Stop':
		return stops.Stop(self.number, self.unit, self.color.value() or '#ffffff')

	def native(self) -> Optional[float]:
		return stops.native(self.stop(), CONTEXT.valueClass())

	def _shown(self) -> float:
		return self.number if self.unit else CONTEXT.toShown(self.number)

	def _take(self, shown: float):
		self.number = round(shown if self.unit else CONTEXT.toNative(shown), 4)

	def _fit(self):
		lo, hi = sorted(CONTEXT.span())
		vc = CONTEXT.valueClass()
		a, b = (stops.fromNative(v, self.unit, vc) for v in (lo, hi)) if self.unit else (CONTEXT.toShown(lo), CONTEXT.toShown(hi))
		self.slide.setBase(min(a, b), max(a, b))

	def _names(self) -> List[str]:
		names = list(CONTEXT.units)
		if self.unit and self.unit not in names:
			names.append(self.unit)
		return names

	def _show(self):
		names = self._names()
		with QSignalBlocker(self.unitCombo):
			if [self.unitCombo.itemText(i) for i in range(self.unitCombo.count())] != names:
				self.unitCombo.clear()
				self.unitCombo.addItems(names)
			self.unitCombo.setCurrentText(self.unit or CONTEXT.symbol())
		self.unitCombo.setVisible(bool(names))
		self.spin.setSuffix('' if names else (f' {CONTEXT.symbol()}' if CONTEXT.symbol() else ''))
		self._fit()
		with QSignalBlocker(self.spin):
			self.spin.setValue(self._shown())
		self.slide.showValue(self._shown())

	def onContext(self):
		self._show()

	def _spun(self, value):
		self._take(float(value))
		self.slide.showValue(float(value))
		self._emit()

	def _slid(self, value: float):
		with QSignalBlocker(self.spin):
			self.spin.setValue(value)
		self._take(float(self.spin.value()))
		self._emit()

	def _unitPicked(self, i: int):
		new = self.unitCombo.itemText(i)
		if new == (self.unit or CONTEXT.symbol()):
			return
		native = self.native()
		if native is not None:
			self.number = round(stops.fromNative(native, new, CONTEXT.valueClass()), 4)
		self.unit = new
		self._show()
		self._emit()

	def setNative(self, native: float, fine: bool = False):
		"""Put the stop at `native` (in the gauge's own unit), snapped to a round step in the stop's own unit unless `fine`."""
		lo, hi = sorted(CONTEXT.span())
		self.number = stops.place(self.stop(), native, CONTEXT.valueClass(), lo, hi, fine).number
		self._show()
		self._emit()

	# the editor protocol

	def setValue(self, value):
		value = value or {}
		self.number = float(value.get('value') or 0.0)
		self.unit = value.get('unit') or None
		with QSignalBlocker(self.color):
			self.color.setValue(value.get('color') or '#ffffff')
		self._show()

	def value(self):
		return {'value': self.number, 'unit': self.unit, 'color': self.color.value() or '#ffffff'}

	def isEditing(self) -> bool:
		return self.spin.hasFocus() or self.slide.isSliderDown() or self.color.isEditing()


class GradientBar(QWidget):
	"""The gradient across the gauge's range, with a mark for each stop.

	Folded, it is one thin band with a tick at each stop; a click opens the stops. Open, each stop
	is a node you can drag (the value snaps to a round step; shift snaps finely), a click on the
	band adds a stop with the colour that is there, a double click on a node picks its colour, and a node dragged off
	the band, or Delete with a node chosen, removes it.
	"""

	PAD = 10
	NODE = 7

	def __init__(self, owner: 'GradientEdit'):
		super().__init__()
		self.owner = owner
		self.open = False
		self.drag: Optional[int] = None
		self.selected: Optional[int] = None
		self.removing = False
		self._moved = False
		self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
		self.setMouseTracking(True)
		self.setFixedHeight(24)

	def setOpen(self, on: bool):
		self.open = on
		self.setFixedHeight(64 if on else 24)
		self.setCursor(Qt.CursorShape.ArrowCursor if on else Qt.CursorShape.PointingHandCursor)
		self.setToolTip('' if on else 'Click to show the stops')
		self.update()

	# geometry

	def _span(self):
		lo, hi = sorted(CONTEXT.span())
		return lo, (hi if hi > lo else lo + 1)

	def _band(self) -> QRectF:
		top = 22 if self.open else 5
		return QRectF(self.PAD, top, max(self.width() - 2 * self.PAD, 1), 14)

	def xOf(self, value: float) -> float:
		lo, hi = self._span()
		band = self._band()
		return band.left() + (value - lo) / (hi - lo) * band.width()

	def valueAt(self, x: float) -> float:
		lo, hi = self._span()
		band = self._band()
		return lo + (x - band.left()) / band.width() * (hi - lo)

	def _nodeAt(self, pos) -> Optional[int]:
		best, found = 11.0, None
		cy = self._band().center().y()
		for index, value, _ in self.owner.points():
			if abs(pos.y() - cy) > 13:
				continue
			d = abs(pos.x() - self.xOf(value))
			if d < best:
				best, found = d, index
		return found

	# painting

	def paintEvent(self, event):
		p = QPainter(self)
		p.setRenderHint(QPainter.RenderHint.Antialiasing)
		pal = self.palette()
		band = self._band()
		points = self.owner.points()
		colors = [(v, c) for _, v, c in points]
		lo, hi = self._span()
		path = QPainterPath()
		path.addRoundedRect(band, 4, 4)
		if colors:
			grad = QLinearGradient(band.left(), 0, band.right(), 0)
			grad.setColorAt(0, QColor(stops.sample(colors, lo)))
			grad.setColorAt(1, QColor(stops.sample(colors, hi)))
			for _, v, c in sorted(points, key=lambda t: t[1]):
				if lo < v < hi:
					grad.setColorAt((v - lo) / (hi - lo), QColor(c))
			p.fillPath(path, QBrush(grad))
		else:
			p.fillPath(path, pal.alternateBase())
			p.setPen(pal.color(QPalette.ColorRole.PlaceholderText))
			p.drawText(band, Qt.AlignmentFlag.AlignCenter, 'No gradient')
		edge = QColor(pal.color(QPalette.ColorRole.Mid))
		p.setPen(QPen(edge, 1))
		p.drawPath(path)
		cy = band.center().y()
		for index, value, color in points:
			x = self.xOf(value)
			if not self.open:
				# a tick that reads on any colour and either theme: a dark line under a light one
				p.setPen(QPen(QColor(0, 0, 0, 210), 3))
				p.drawLine(QPointF(x, band.top() - 3), QPointF(x, band.bottom() + 3))
				p.setPen(QPen(QColor(255, 255, 255, 240), 1.2))
				p.drawLine(QPointF(x, band.top() - 3), QPointF(x, band.bottom() + 3))
			else:
				hot = index in (self.drag, self.selected)
				r = self.NODE + (2 if hot else 0)
				fade = self.removing and index == self.drag
				p.setOpacity(0.4 if fade else 1.0)
				p.setPen(QPen(QColor(0, 0, 0, 220), 4))
				p.setBrush(Qt.BrushStyle.NoBrush)
				p.drawEllipse(QPointF(x, cy), r, r)
				p.setPen(QPen(QColor(255, 255, 255), 2))
				p.setBrush(QBrush(QColor(color)))
				p.drawEllipse(QPointF(x, cy), r, r)
				p.setOpacity(1.0)
		if self.open:
			# the range ends, in the unit the panel shows
			p.setPen(pal.color(QPalette.ColorRole.WindowText))
			small = p.font()
			small.setPointSizeF(max(small.pointSizeF() - 1, 7))
			p.setFont(small)
			lo_, hi_ = self._span()
			sym = CONTEXT.symbol()
			p.drawText(QRectF(self.PAD, band.bottom() + 6, 140, 16), Qt.AlignmentFlag.AlignLeft, f'{CONTEXT.toShown(lo_):g} {sym}'.strip())
			p.drawText(QRectF(self.width() - self.PAD - 140, band.bottom() + 6, 140, 16), Qt.AlignmentFlag.AlignRight,
			           f'{CONTEXT.toShown(hi_):g} {sym}'.strip())
			if self.drag is not None:
				self._label(p, self.drag)

	def _label(self, p: QPainter, index: int):
		"""The value and unit of the dragged node, over it."""
		match = [(v, c) for i, v, c in self.owner.points() if i == index]
		if not match:
			return
		text = 'release to remove' if self.removing else self.owner.labelFor(index)
		pal = self.palette()
		fm = p.fontMetrics()
		w = fm.horizontalAdvance(text) + 14
		x = min(max(self.xOf(match[0][0]) - w / 2, 1), self.width() - w - 1)
		box = QRectF(x, 2, w, 18)
		p.setPen(QPen(pal.color(QPalette.ColorRole.WindowText), 1))
		p.setBrush(pal.base())
		p.drawRoundedRect(box, 4, 4)
		p.setPen(pal.color(QPalette.ColorRole.Text))
		p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

	# the mouse

	def mousePressEvent(self, event):
		if event.button() != Qt.MouseButton.LeftButton:
			return
		if not self.open:
			self.owner.setOpen(True)
			return
		self.setFocus()
		hit = self._nodeAt(event.position())
		self._moved = False
		if hit is None and self._band().adjusted(0, -4, 0, 4).contains(event.position()):
			CONTEXT.beginDrag()
			hit = self.owner.addAt(self.valueAt(event.position().x()))
			self._moved = True
		elif hit is not None:
			CONTEXT.beginDrag()
		if hit is None:
			self.selected = None
			self.update()
			return
		self.drag = self.selected = hit
		self.removing = False
		self.update()

	def mouseMoveEvent(self, event):
		if self.drag is None:
			if self.open:
				self.setCursor(Qt.CursorShape.OpenHandCursor if self._nodeAt(event.position()) is not None else Qt.CursorShape.ArrowCursor)
			return
		self._moved = True
		off = abs(event.position().y() - self._band().center().y()) > 34
		self.removing = off
		if not off:
			fine = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
			self.owner.moveStop(self.drag, self.valueAt(event.position().x()), fine)
		self.update()

	def mouseReleaseEvent(self, event):
		if self.drag is None:
			return
		index, removing, moved = self.drag, self.removing, self._moved
		self.drag, self.removing = None, False
		if removing:
			self.selected = None
			self.owner.removeStop(index)
		self.update()
		CONTEXT.endDrag(moved or removing)

	def mouseDoubleClickEvent(self, event):
		if self.open and (hit := self._nodeAt(event.position())) is not None:
			self.owner.recolor(hit)

	def keyPressEvent(self, event):
		if self.open and self.selected is not None and event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
			index, self.selected = self.selected, None
			CONTEXT.beginDrag()
			self.owner.removeStop(index)
			CONTEXT.endDrag(True)
			return
		super().keyPressEvent(event)


METER_GRADIENT = ('arc', 'gradient')


class GradientEdit(Editor):
	"""A colour pinned to each reading. Folded it is one band; open it is the band with a node per stop, and a row per stop."""

	wide = True
	#: Whether the stops are open. One answer for every gradient editor in the session.
	opened = False
	_all: 'weakref.WeakSet' = weakref.WeakSet()

	def __init__(self, path: tuple = ()):
		super().__init__()
		self.path = tuple(path)
		outer = QVBoxLayout(self)
		outer.setContentsMargins(0, 0, 0, 0)
		outer.setSpacing(3)
		top = QHBoxLayout()
		top.setSpacing(4)
		self.arrow = QToolButton()
		self.arrow.setAutoRaise(True)
		self.arrow.clicked.connect(lambda: self.setOpen(not GradientEdit.opened))
		top.addWidget(self.arrow)
		self.bar = GradientBar(self)
		top.addWidget(self.bar, 1)
		self.meterToggle: Optional[QCheckBox] = None
		if self.path == METER_GRADIENT:
			self.meterToggle = QCheckBox('Edit gradient')
			self.meterToggle.setToolTip('Drag the stops as nodes on the meter itself')
			self.meterToggle.toggled.connect(lambda on: CONTEXT.setGradientMode(on))
			top.addWidget(self.meterToggle)
		outer.addLayout(top)
		self.detail = QWidget()
		inner = QVBoxLayout(self.detail)
		inner.setContentsMargins(0, 0, 0, 0)
		inner.setSpacing(3)
		self.presets = QComboBox()
		self.presets.addItem('Preset…', None)
		from LevityDash.lib.ui.colors import Gradient
		for name in Gradient.presets():
			self.presets.addItem(name, name)
		self.presets.activated.connect(self._preset)
		inner.addWidget(self.presets)
		self.list = ListEditor(StopRow, self._fresh, '+ Add stop', 'No gradient. The arc keeps its colour.')
		self.list.changed.connect(self._listChanged)
		inner.addWidget(self.list)
		outer.addWidget(self.detail)
		GradientEdit._all.add(self)
		self._apply()

	# fold

	def setOpen(self, on: bool):
		GradientEdit.opened = on
		for editor in list(GradientEdit._all):
			try:
				editor._apply()
			except RuntimeError:  # the widget is gone; Python still holds its wrapper
				GradientEdit._all.discard(editor)

	def _apply(self):
		on = GradientEdit.opened
		self.arrow.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
		self.arrow.setToolTip('Hide the stops' if on else 'Show the stops')
		self.detail.setVisible(on)
		self.bar.setOpen(on)

	# the stops

	def stopList(self) -> List['stops.Stop']:
		return [row.item.stop() for row in self.list.rows]

	def points(self) -> List[tuple]:
		"""(row, native value, colour) for each stop that sits on this data."""
		out = []
		for i, row in enumerate(self.list.rows):
			value = row.item.native()
			if value is not None:
				out.append((i, value, row.item.color.value() or '#ffffff'))
		return out

	def labelFor(self, index: int) -> str:
		"""The number and unit of stop `index`, as the stop shows them."""
		item = self.list.rows[index].item
		if item.unit:
			return formatStop(item.number, item.unit)
		return f'{CONTEXT.toShown(item.number):.4g} {CONTEXT.symbol()}'.strip()

	def _unitForNew(self) -> Optional[str]:
		"""A new stop is written in the unit of the highest stop, so a gradient in one unit stays in one."""
		ordered = sorted(self.points(), key=lambda t: t[1])
		return self.list.rows[ordered[-1][0]].item.unit if ordered else None

	def _fresh(self, items):
		lo, hi = sorted(CONTEXT.span())
		natives = sorted(v for _, v, _ in self.points())
		if not natives:
			where = lo + (hi - lo) * 0.25
		elif natives[-1] + (hi - lo) / 4 <= hi:
			where = natives[-1] + (hi - lo) / 4
		else:
			edges = [lo, *natives, hi]
			gap = max(zip(edges, edges[1:]), key=lambda g: g[1] - g[0])
			where = (gap[0] + gap[1]) / 2
		unit = self._unitForNew()
		vc = CONTEXT.valueClass()
		number = stops.fromNative(where, unit, vc) if unit else where
		span = _spanOf(unit) if unit else hi - lo
		number = round(snapTo(number, niceStep(span / 50)), 4)
		color = stops.freshColor([i['color'] for i in items])
		return {'value': number, 'unit': unit, 'color': color}

	def addAt(self, native: float) -> int:
		"""Add a stop at `native` with the colour the gradient has there. Returns its row."""
		color = stops.sample([(v, c) for _, v, c in self.points()], native) if self.points() else stops.freshColor([])
		unit = self._unitForNew()
		row = self.list._make({'value': 0.0, 'unit': unit, 'color': color})
		self.list._refreshHint()
		row.item.setNative(native)
		return len(self.list.rows) - 1

	def moveStop(self, index: int, native: float, fine: bool = False):
		if 0 <= index < len(self.list.rows):
			self.list.rows[index].item.setNative(native, fine)

	def removeStop(self, index: int):
		if 0 <= index < len(self.list.rows):
			self.list._remove(self.list.rows[index])

	def recolor(self, index: int):
		if not 0 <= index < len(self.list.rows):
			return
		item = self.list.rows[index].item
		CONTEXT.beginDrag()
		chosen = pickColor(self, item.color.value())
		if chosen is not None:
			with QSignalBlocker(item.color):
				item.color.setValue(chosen)
			item._emit()
		CONTEXT.endDrag(chosen is not None)

	def _preset(self, _):
		name = self.presets.currentData()
		if name is None:
			return
		from LevityDash.lib.ui.colors import Gradient
		self.setValue(schema.gradientText(Gradient.decode(name)))
		with QSignalBlocker(self.presets):
			self.presets.setCurrentIndex(0)
		self._emit()

	def _listChanged(self, _=None):
		self.bar.update()
		self.changed.emit(self.value())

	# the editor protocol

	def setValue(self, value):
		wanted = [{'value': s.number, 'unit': s.unit, 'color': s.color} for s in stops.decode(value)]
		have = self.list.items()
		same = len(wanted) == len(have) and all(
			abs(a['value'] - b['value']) < 1e-9 and a['unit'] == b['unit'] and a['color'].lower() == b['color'].lower()
			for a, b in zip(wanted, have))
		if not same:
			self.list.setItems(wanted)
		self.bar.update()

	def value(self):
		vc = CONTEXT.valueClass()
		ordered = sorted(self.stopList(), key=lambda s: (v if (v := stops.native(s, vc)) is not None else float('inf')))
		return stops.encode(ordered)

	def onContext(self):
		self.list.onContext()
		if self.meterToggle is not None:
			with QSignalBlocker(self.meterToggle):
				self.meterToggle.setChecked(CONTEXT.gradientMode())
		self.bar.update()

	def isEditing(self) -> bool:
		return self.bar.drag is not None or self.list.isEditing()


class WordItem(_Form):
	def __init__(self):
		super().__init__()
		self.part('value', 'at', NumberEdit(measured=True))
		self.word = QLineEdit()
		self.word.setPlaceholderText('E')
		self.word.editingFinished.connect(self._emit)
		self.grid.addWidget(QLabel('word'), self._r, 0)
		self.grid.addWidget(self.word, self._r, 1)

	def setValue(self, value):
		value = value or {}
		with QSignalBlocker(self.parts['value']):
			self.parts['value'].setValue(value.get('value'))
		with QSignalBlocker(self.word):
			self.word.setText(str(value.get('word', '')))

	def value(self):
		return {'value': self.parts['value'].value() or 0, 'word': self.word.text()}


class TextMapEdit(ListEditor):
	"""Words in place of numbers on the tick labels. Presets for a compass and for E, half, F."""

	PRESETS = ['custom', 'compass', 'compass-16', 'E ½ F']

	def __init__(self):
		super().__init__(WordItem, self._fresh, '+ Add word', '', measured=True)
		self.preset = QComboBox()
		self.preset.addItems(self.PRESETS)
		self.preset.activated.connect(self._preset)
		box = QHBoxLayout()
		box.addWidget(QLabel('words'))
		box.addWidget(self.preset, 1)
		self.layout().insertLayout(0, box)
		self._named: Optional[str] = None

	@staticmethod
	def _fresh(items):
		lo, hi = CONTEXT.range()
		top = max((i['value'] for i in items), default=lo - (hi - lo) / 4)
		return {'value': min(hi, top + (hi - lo) / 4), 'word': ''}

	def _preset(self, i: int):
		name = self.PRESETS[i]
		if name in ('compass', 'compass-16'):
			self._named = name
			self.setItems([])
		else:
			self._named = None
			if name == 'E ½ F':
				lo, hi = CONTEXT.range()
				self.setItems([{'value': lo, 'word': 'E'}, {'value': (lo + hi) / 2, 'word': '½'}, {'value': hi, 'word': 'F'}])
		self._showRows()
		self._emit()

	def _showRows(self):
		named = self._named is not None
		for row in self.rows:
			row.setVisible(not named)
		self.add.setVisible(not named)

	def setValue(self, value):
		if isinstance(value, str):
			self._named = value
			with QSignalBlocker(self.preset):
				self.preset.setCurrentIndex(self.PRESETS.index(value) if value in self.PRESETS else 0)
			self.setItems([])
		else:
			self._named = None
			with QSignalBlocker(self.preset):
				self.preset.setCurrentIndex(0)
			self.setItems([{'value': float(k), 'word': str(v)} for k, v in sorted((value or {}).items(), key=lambda kv: float(kv[0]))])
		self._showRows()

	def value(self):
		if self._named is not None:
			return self._named
		return {i['value']: i['word'] for i in self.items() if i['word'] != ''} or None

	def _add(self):
		super()._add()
		self._showRows()


# Section: markers

def _needleTypes() -> List[str]:
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Gauge import Needle
	return [t.value for t in Needle.Type]


CLOCK_HANDS = ['hour', 'minute', 'second', 'day']


class MarkerValue(Editor):
	"""A marker's place: a number, a key, or a hand of the clock."""

	def __init__(self):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		box.setSpacing(4)
		self.mode = QComboBox()
		self.mode.addItems(['number', 'key', 'clock'])
		self.mode.activated.connect(self._modeChanged)
		self.number = NumberEdit(measured=True)
		self.number.changed.connect(self._emit)
		self.key = KeyEdit()
		self.key.changed.connect(self._emit)
		self.hand = QComboBox()
		self.hand.addItems(CLOCK_HANDS)
		self.hand.activated.connect(self._emit)
		self.at = QTimeEdit()
		self.at.setDisplayFormat('HH:mm')
		self.at.setToolTip('A fixed time such as 10:09. Untick "fixed" to follow the clock.')
		self.at.timeChanged.connect(self._emit)
		self.fixed = QCheckBox('fixed')
		self.fixed.setToolTip('Hold the hand at this time instead of following the clock')
		self.fixed.toggled.connect(self._fixedToggled)
		self.at.setEnabled(False)
		for w in (self.mode, self.number, self.key, self.hand, self.fixed, self.at):
			box.addWidget(w, 0 if w is self.mode else 1)
		self._show()

	def _show(self):
		mode = self.mode.currentText()
		self.number.setVisible(mode == 'number')
		self.key.setVisible(mode == 'key')
		self.hand.setVisible(mode == 'clock')
		self.fixed.setVisible(mode == 'clock')
		self.at.setVisible(mode == 'clock')

	def _fixedToggled(self, on: bool):
		self.at.setEnabled(on)
		self._emit()

	def _modeChanged(self, _):
		self._show()
		self._emit()

	def onContext(self):
		self.number.onContext()

	def setValue(self, spec):
		spec = spec or {}
		if spec.get('time') is not None:
			mode = 'clock'
		elif isinstance(spec.get('value'), str):
			mode = 'key'
		else:
			mode = 'number'
		with QSignalBlocker(self.mode):
			self.mode.setCurrentText(mode)
		with QSignalBlocker(self.number), QSignalBlocker(self.key), QSignalBlocker(self.hand), QSignalBlocker(self.at), QSignalBlocker(self.fixed):
			if mode == 'number':
				v = spec.get('value')
				self.number.setValue(v if isinstance(v, (int, float)) else sum(CONTEXT.range()) / 2)
			elif mode == 'key':
				self.key.setValue(spec.get('value'))
			else:
				self.hand.setCurrentText(str(spec.get('time')))
				held = spec.get('at') is not None
				with QSignalBlocker(self.fixed):
					self.fixed.setChecked(held)
				self.at.setEnabled(held)
				if held:
					self.at.setTime(QTime.fromString(str(spec.get('at')), 'H:mm'))
		self._show()

	def value(self):
		mode = self.mode.currentText()
		if mode == 'number':
			return {'value': self.number.value()}
		if mode == 'key':
			return {'value': self.key.value() or ''}
		out = {'time': self.hand.currentText()}
		if self.fixed.isChecked():
			out['at'] = self.at.time().toString('H:mm')
		return out

	def isEditing(self) -> bool:
		return self.number.isEditing() or self.key.isEditing() or self.at.hasFocus() or self.fixed.hasFocus()


_MARKER_SIZES = [('width', 'width'), ('length', 'length'), ('offset', 'offset'), ('tail', 'tail'), ('tail-dot', 'tail dot'),
                 ('head', 'head'), ('hub', 'hub'), ('halo', 'halo')]
_MARKER_COLORS = [('hub-color', 'hub colour'), ('halo-color', 'halo colour')]


class MarkerItem(_Form):
	"""A marker: its type, where it sits, its colour, and the options its type uses."""

	def __init__(self):
		super().__init__()
		self.type = ChoiceEdit([(t, t) for t in _needleTypes()])
		self.part('type', 'type', self.type, 'The needle design this marker uses.')
		self.type.changed.connect(self._typeChanged)
		self.where = MarkerValue()
		self.where.changed.connect(self._emit)
		self.grid.addWidget(QLabel('where'), self._r, 0)
		self.grid.addWidget(self.where, self._r, 1)
		self._r += 1
		self.part('color', 'colour', ColorEdit(nullable=True))
		for key, label in _MARKER_SIZES:
			self.part(key, label, SizeEdit(nullable=True))
		for key, label in _MARKER_COLORS:
			self.part(key, label, ColorEdit(nullable=True))
		self.part('hub-hole', 'hub hole', NumberEdit(autoText='auto', lo=0, hi=1, step=0.05, decimals=2))
		self.part('point', 'point', ChoiceEdit([('out', None), ('in', 'in')]))
		self._known |= {'time', 'at', 'value'}

	def _typeChanged(self, *_):
		self._rules()

	def _rules(self):
		kind = self.type.value() or 'marker'
		for key in list(self.parts):
			uses = schema.NEEDLE_USES.get(key)
			if uses is not None:
				self.showPart(key, kind in uses)

	def setValue(self, spec):
		spec = dict(spec or {})
		self._extra = {k: v for k, v in spec.items() if k not in self._known}
		for key, p in self.parts.items():
			with QSignalBlocker(p):
				p.setValue(spec.get(key) if key != 'type' else spec.get('type', 'marker'))
		self.where.setValue(spec)
		self._rules()

	def value(self):
		out = dict(self._extra)
		kind = self.type.value() or 'marker'
		out['type'] = kind
		out.update(self.where.value())
		for key, p in self.parts.items():
			if key == 'type':
				continue
			uses = schema.NEEDLE_USES.get(key)
			if uses is not None and kind not in uses:
				continue
			v = p.value()
			if v is not None:
				out[key] = v
		return out


class MarkersEdit(ListEditor):
	def __init__(self):
		super().__init__(MarkerItem, self._fresh, '+ Add marker', 'No markers.', measured=True)

	@staticmethod
	def _fresh(items):
		lo, hi = CONTEXT.range()
		return {'type': 'marker', 'value': round(lo + (hi - lo) * 0.75, 3), 'color': '#f5a524'}


# Section: fill and captions

class _Toggled(Editor):
	"""A form behind an 'on' box. Off is `None`."""

	wide = True

	def __init__(self, label: str, form: _Form):
		super().__init__()
		self.form = form
		box = QVBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		box.setSpacing(3)
		self.on = QCheckBox(label)
		self.on.toggled.connect(self._toggled)
		box.addWidget(self.on)
		box.addWidget(form)
		form.changed.connect(self._emit)
		form.setVisible(False)

	def _toggled(self, on: bool):
		self.form.setVisible(on)
		if on and not self.form.value():
			self.form.setValue(self.fresh())
		self._emit()

	def fresh(self) -> Any:
		return {}

	def onContext(self):
		self.form.onContext()

	def setValue(self, value):
		on = value not in (None, '', {})
		with QSignalBlocker(self.on):
			self.on.setChecked(on)
		self.form.setVisible(on)
		if on:
			self.form.setValue(value)

	def value(self):
		return self.form.value() if self.on.isChecked() else None

	def isEditing(self) -> bool:
		return self.form.isEditing()


class FillForm(_Form):
	def __init__(self):
		super().__init__()
		self.part('from', 'from', ValueOrKey(autoText='range minimum'), 'Where the fill starts: a number or a key.')
		self.part('to', 'to', ValueOrKey(autoText='the gauge value'), 'Where the fill ends. Left alone it follows the value.')
		self.color = self.part('color', 'colour', ColorEdit(nullable=True))
		self.zone = QCheckBox('use the zone colour')
		self.zone.setToolTip('Take the colour of the zone the value is in')
		self.zone.toggled.connect(self._zone)
		self.grid.addWidget(self.zone, self._r, 1)
		self._r += 1
		self.part('weight', 'weight', SizeEdit(nullable=True, autoText='arc'))
		self.part('segments', 'segments', NumberEdit(autoText='solid', integer=True, lo=1, hi=200, step=1), 'Break the fill into this many pieces.')
		self.part('gap', 'gap', SizeEdit(nullable=True, autoText='auto'), 'Space between segments.')
		self.part('glow', 'glow', GlowEdit(), 'A halo around the fill. Left off, the fill takes the gauge glow.')

	def _zone(self, on: bool):
		self.color.setEnabled(not on)
		self._emit()

	def setValue(self, value):
		spec = dict(value or {})
		self._extra = {k: v for k, v in spec.items() if k not in self._known}
		zone = isinstance(spec.get('color'), str) and spec['color'].strip().lower() == 'zone'
		for key, p in self.parts.items():
			with QSignalBlocker(p):
				p.setValue(None if key == 'color' and zone else spec.get(key))
		with QSignalBlocker(self.zone):
			self.zone.setChecked(zone)
		self.color.setEnabled(not zone)

	def value(self):
		out = dict(self._extra)
		for key, p in self.parts.items():
			v = p.value()
			if key == 'color' and self.zone.isChecked():
				v = 'zone'
			if v is not None:
				out[key] = v
		return out


class FillEdit(_Toggled):
	def __init__(self):
		super().__init__('Fill the track up to a value', FillForm())

	def fresh(self):
		return {'color': '#2f81f7'}


class CaptionForm(_Form):
	def __init__(self):
		super().__init__()
		self.part('text', 'text', LineText('Humidity  (use {} where the value goes)'))
		self.part('value', 'value', KeyEdit(), 'A key whose value shows in the text.')
		self.part('format', 'format', ChoiceEdit([(n, v) for n, v in FORMAT_PRESETS]), 'How the value prints.')
		self.part('size', 'size', SizeEdit(nullable=True, autoText='7%'), 'Text height as a share of the dial\'s diameter.')
		self.part('gap', 'gap', SizeEdit(nullable=True, autoText='2%'), 'Distance from the value.')
		self.part('color', 'colour', ColorEdit(nullable=True))
		self.bold = QCheckBox('bold')
		self.bold.toggled.connect(self._emit)
		self.grid.addWidget(self.bold, self._r, 1)
		self._r += 1
		self.part('offset', 'offset', OffsetEdit(), 'Move the text. Dragging it on the preview writes this.')
		self.part('warp', 'warp', WarpEdit(), 'Bend the text along a circle.')
		self.part('glow', 'glow', GlowEdit(), 'A halo around the text.')
		self._known |= {'weight'}

	def setValue(self, value):
		spec = {'text': value} if isinstance(value, str) else dict(value or {})
		self._extra = {k: v for k, v in spec.items() if k not in self._known}
		for key, p in self.parts.items():
			with QSignalBlocker(p):
				p.setValue(spec.get(key))
		fmt = self.parts['format']
		if spec.get('format') is not None and fmt.combo.currentIndex() < 0:
			with QSignalBlocker(fmt.combo):
				fmt.combo.addItem('custom', spec['format'])
				fmt.combo.setCurrentIndex(fmt.combo.count() - 1)
		with QSignalBlocker(self.bold):
			self.bold.setChecked(str(spec.get('weight', '')).lower() == 'bold')

	def value(self):
		out = dict(self._extra)
		for key, p in self.parts.items():
			v = p.value()
			if v not in (None, ''):
				out[key] = v
		if self.bold.isChecked():
			out['weight'] = 'bold'
		if set(out) == {'text'}:
			return out['text']
		return out


class LineText(Editor):
	"""A line of text. Reports on Return or when the box loses focus."""

	def __init__(self, placeholder: str = ''):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		self.edit = QLineEdit()
		self.edit.setPlaceholderText(placeholder)
		self.edit.editingFinished.connect(self._emit)
		box.addWidget(self.edit, 1)

	def setValue(self, value):
		with QSignalBlocker(self.edit):
			self.edit.setText('' if value is None else str(value))

	def value(self):
		return self.edit.text() or None

	def isEditing(self) -> bool:
		return self.edit.hasFocus()


class WarpForm(_Form):
	"""The pieces of `warp:`. Only what differs from the defaults is written; all default is `true`."""

	CENTERS = ['dial', 'card', 'top-left', 'top', 'top-right', 'left', 'center', 'right', 'bottom-left', 'bottom',
	           'bottom-right']

	def __init__(self):
		super().__init__()
		self.centre = QComboBox()
		self.centre.addItems(self.CENTERS + ['custom'])
		self.centre.setToolTip('The middle of the circle: the dial\'s pivot, the card, a corner or edge, or a point you set')
		self.centre.activated.connect(self._centreChanged)
		self.grid.addWidget(QLabel('centre'), self._r, 0)
		self.grid.addWidget(self.centre, self._r, 1)
		self._r += 1
		self.cx = NumberEdit(lo=-100, hi=200, step=1, decimals=1, suffix=' %')
		self.cy = NumberEdit(lo=-100, hi=200, step=1, decimals=1, suffix=' %')
		for k, e in (('x', self.cx), ('y', self.cy)):
			e.setToolTip(f'{k} as a share of the card')
			e.changed.connect(self._emit)
			self.grid.addWidget(QLabel(f'  {k}'), self._r, 0)
			self.grid.addWidget(e, self._r, 1)
			self.labels[f'c{k}'] = self.grid.itemAtPosition(self._r, 0).widget()
			self._r += 1
		self.radius = self.part('radius', 'radius', SizeEdit(units=['%', 'px', 'in'], ref='full'),
		                        'Distance from the centre to the middle of the text; % is a share of the dial\'s diameter')
		self.angle = self.part('angle', 'angle', NumberEdit(lo=-180, hi=180, step=1, decimals=1, suffix='\u00b0'),
		                       'Where on the circle the text sits, degrees clockwise from the top')
		self.bend = self.part('bend', 'bend', NumberEdit(lo=0, hi=100, step=1, decimals=0, suffix=' %'),
		                      '0 % turns each rigid letter to the circle; 100 % bends the letters with it. Around 60 % keeps letters readable')
		self.mode = QComboBox()
		self.mode.addItems(['warp', 'glyphs'])
		self.mode.setToolTip('warp is bend 100 %; glyphs is bend 0 %. Use bend for anything between')
		self.mode.activated.connect(self._emit)
		self.grid.addWidget(QLabel('mode'), self._r, 0)
		self.grid.addWidget(self.mode, self._r, 1)
		self._r += 1
		self.flip = QComboBox()
		self.flip.addItems(['auto', 'true', 'false'])
		self.flip.setToolTip('auto turns text in the lower half so it reads left to right')
		self.flip.activated.connect(self._emit)
		self.grid.addWidget(QLabel('flip'), self._r, 0)
		self.grid.addWidget(self.flip, self._r, 1)
		self._r += 1
		self._known |= {'center', 'mode', 'flip', 'bend'}
		self.setValue(True)

	def _showCustom(self, on: bool):
		for k in ('cx', 'cy'):
			(self.cx if k == 'cx' else self.cy).setVisible(on)
			self.labels[k].setVisible(on)

	def _centreChanged(self, _=None):
		self._showCustom(self.centre.currentText() == 'custom')
		self._emit()

	def setValue(self, value):
		spec = dict(value) if isinstance(value, dict) else {}
		self._extra = {k: v for k, v in spec.items() if k not in self._known}
		centre = spec.get('center', 'dial')
		with QSignalBlocker(self.centre), QSignalBlocker(self.mode), QSignalBlocker(self.flip):
			if isinstance(centre, dict):
				self.centre.setCurrentText('custom')
				for e, k in ((self.cx, 'x'), (self.cy, 'y')):
					with QSignalBlocker(e):
						e.setValue(_number(centre.get(k, '50%')))
			else:
				self.centre.setCurrentText(str(centre) if str(centre) in self.CENTERS else 'dial')
			self.mode.setCurrentText(str(spec.get('mode', 'warp')))
			flip = spec.get('flip', 'auto')
			self.flip.setCurrentText('auto' if flip == 'auto' else str(bool(flip)).lower())
		self._showCustom(self.centre.currentText() == 'custom')
		self.radius.setValue(spec.get('radius', '40%'))
		self.angle.setValue(spec.get('angle', 0))
		bend = spec.get('bend')
		if bend is None:
			bend = 0 if str(spec.get('mode', 'warp')) == 'glyphs' else 100
		self.bend.setValue(_number(bend))

	def value(self):
		out = dict(self._extra)
		if self.centre.currentText() == 'custom':
			out['center'] = {'x': f'{self.cx.value():g}%', 'y': f'{self.cy.value():g}%'}
		elif self.centre.currentText() != 'dial':
			out['center'] = self.centre.currentText()
		if (r := self.radius.value()) not in (None, '40%'):
			out['radius'] = r
		if (a := self.angle.value()):
			out['angle'] = a
		if self.mode.currentText() != 'warp':
			out['mode'] = self.mode.currentText()
		bend = self.bend.value()
		if bend is not None and not (bend == 0 and out.get('mode') == 'glyphs') and bend != 100:
			out['bend'] = f'{bend:g}%'
		if self.flip.currentText() != 'auto':
			out['flip'] = self.flip.currentText() == 'true'
		return out or True

	def isEditing(self) -> bool:
		return super().isEditing() or self.centre.view().isVisible()


class WarpEdit(_Toggled):
	"""`warp:` as a structured editor: off, or the circle the text bends along."""

	def __init__(self):
		super().__init__('Bend along a circle', WarpForm())

	def fresh(self):
		return True


class GlowForm(_Form):
	"""The pieces of `glow:`. Only what differs from the defaults is written; all default is `true`."""

	DEFAULTS = {'strength': 1.0, 'reach': 0.6, 'passes': 4, 'bloom': 0.04}

	def __init__(self):
		super().__init__()
		self.part('strength', 'strength', NumberEdit(lo=0, hi=3, step=0.05, decimals=2),
		          'How bright the halo is. 0 draws no glow, which also turns off a glow the item inherits')
		self.part('reach', 'reach', NumberEdit(lo=0, hi=2, step=0.05, decimals=2),
		          'How far the halo reaches past the object, as a share of its width')
		self.part('passes', 'passes', NumberEdit(lo=1, hi=8, step=1, integer=True),
		          'How many layers the halo has. More is smoother and costs a little more to draw')
		self.part('bloom', 'bloom', NumberEdit(lo=0, hi=0.2, step=0.005, decimals=3),
		          'Cap on the extra light added to the core. 0 turns it off. Too much washes colours out to white')
		self.setValue(True)

	def setValue(self, value):
		spec = dict(value) if isinstance(value, dict) else {}
		self._extra = {k: v for k, v in spec.items() if k not in self._known}
		for key, p in self.parts.items():
			with QSignalBlocker(p):
				p.setValue(spec.get(key, self.DEFAULTS[key]))

	def value(self):
		out = dict(self._extra)
		for key, p in self.parts.items():
			v = p.value()
			if v is not None and v != self.DEFAULTS[key]:
				out[key] = int(v) if key == 'passes' else v
		return out or True


class GlowEdit(_Toggled):
	"""`glow:` as a structured editor: off, or the halo settings. Every number keeps its slider."""

	def __init__(self):
		super().__init__('Glow', GlowForm())

	def fresh(self):
		return True


class CaptionEdit(_Toggled):
	def __init__(self):
		super().__init__('Show small text', CaptionForm())

	def fresh(self):
		return 'Label'


class ConditionEdit(Editor):
	"""`when:` and a beam's `active:` and `sweep:`: nothing, a bool, or a key or an expression."""

	MODES = [('not set', None), ('always (true)', True), ('never (false)', False), ('key or expression', '')]

	def __init__(self, unsetText: str = 'not set', placeholder: str = 'environment.wind.speed.speed > 25 mph'):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		box.setSpacing(4)
		self.mode = QComboBox()
		for i, (label, _) in enumerate(self.MODES):
			self.mode.addItem(unsetText if i == 0 else label)
		self.mode.activated.connect(self._modeChanged)
		self.text = KeyEdit(placeholder)
		self.text.changed.connect(self._emit)
		box.addWidget(self.mode)
		box.addWidget(self.text, 1)
		self._showMode()

	def _showMode(self):
		self.text.setVisible(self.mode.currentIndex() == 3)

	def _modeChanged(self, _):
		self._showMode()
		if self.mode.currentIndex() == 3:
			self.text.setFocus()
		self._emit()

	def setValue(self, value):
		if value is None or value == '':
			index = 0
		elif isinstance(value, bool):
			index = 1 if value else 2
		else:
			index = 3
		with QSignalBlocker(self.mode):
			self.mode.setCurrentIndex(index)
		self.text.setValue(str(value) if index == 3 else None)
		self._showMode()

	def value(self):
		index = self.mode.currentIndex()
		if index == 3:
			return self.text.value()
		return self.MODES[index][1]

	def isEditing(self) -> bool:
		return self.text.isEditing() or self.mode.view().isVisible()


class BeamForm(_Form):
	"""The keys of `beam:`. Only what differs from the defaults is written."""

	DEFAULTS = {'size': 'md', 'variant': 'colorful', 'theme': None, 'color-space': 'hsv', 'strength': 1.0}

	def __init__(self):
		super().__init__()
		self.part('active', 'active', ConditionEdit(unsetText='off'), 'Runs while true: a bool, a key or an expression.')
		self.part('sweep', 'sweep', ConditionEdit(unsetText='off', placeholder='environment.temperature.temperature'),
		          'Runs once each time a new value arrives. A key or an expression.')
		self.part('path', 'outline', ChoiceEdit([('panel rectangle', None)] + [(n, n) for n in ('circle', 'diamond', 'triangle', 'arc', 'wave', 'heart')], editable=True),
		          'What the beam follows. A shape name, or SVG path data such as M 0 0 L 100 0 L 50 100 Z, scaled to fill the panel.')
		self.part('size', 'size', ChoiceEdit([(n, n) for n in ('sm', 'md', 'line', 'pulse-inner', 'pulse-outside')]), 'The shape and motion.')
		self.part('variant', 'variant', ChoiceEdit([(n, n) for n in ('colorful', 'mono', 'ocean', 'sunset')]))
		self.part('theme', 'theme', ChoiceEdit([('auto', None), ('dark', 'dark'), ('light', 'light')]))
		self.part('color-space', 'colour space', ChoiceEdit([('hsv (upstream)', 'hsv'), ('oklch (palette ring)', 'oklch')]))
		self.part('duration', 'duration', NumberEdit(autoText='default', suffix=' s', lo=0.2, hi=20, step=0.1, decimals=2),
		          'Seconds for one cycle. 1.96 for sm and md, 3.1 for line, 2.3 for the pulses.')
		self.part('strength', 'strength', NumberEdit(lo=0, hi=1, step=0.05, decimals=2), 'How strong the beam is, 0 to 1.')
		self.part('radius', 'radius', NumberEdit(autoText='default', suffix=' px', lo=0, hi=200, step=1, decimals=0),
		          'Corner radius in pixels. 32 for sm, 16 for the others.')
		self.part('fill', 'fill', ColorEdit(nullable=True), 'A card colour under the content. pulse-outside needs one.')
		self.part('phase', 'hold at', NumberEdit(autoText='run', suffix=' s', lo=0, hi=20, step=0.05, decimals=2),
		          'Freeze the beam at this time in seconds. For renders; leave it on run for a real dashboard.')

	def setValue(self, value):
		spec = dict(value) if isinstance(value, dict) else {}
		self._extra = {k: v for k, v in spec.items() if k not in self._known}
		for key, p in self.parts.items():
			with QSignalBlocker(p):
				p.setValue(spec.get(key, self.DEFAULTS.get(key)))

	def value(self):
		out = dict(self._extra)
		for key, p in self.parts.items():
			v = p.value()
			if v is not None and v != self.DEFAULTS.get(key):
				out[key] = v
		return out


class _Popover(Editor):
	"""A button that shows a summary and opens its form in a small floating panel.

	The panel is a tool window, not a popup: a popup closes when the colour dialog opens.
	"""

	title = ''

	def __init__(self, form: Editor):
		super().__init__()
		self.form = form
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		self.button = QPushButton()
		self.button.setCheckable(True)
		self.button.setStyleSheet('text-align: left; padding: 3px 8px;')
		self.button.toggled.connect(self._toggle)
		box.addWidget(self.button, 1)
		self.panel = QFrame(self, Qt.WindowType.Tool)
		self.panel.setWindowTitle(self.title)
		inner = QVBoxLayout(self.panel)
		inner.setContentsMargins(10, 10, 10, 10)
		inner.addWidget(form)
		self.panel.setMinimumWidth(420)
		form.changed.connect(self._formChanged)
		self._value: Any = None
		self._summarize()

	def _toggle(self, on: bool):
		if on:
			self.form.setValue(self._value)
			corner = self.button.mapToGlobal(self.button.rect().bottomLeft())
			self.panel.move(corner)
			self.panel.show()
			self.panel.raise_()
		else:
			self.panel.hide()

	def _formChanged(self, value):
		self._value = self._tidy(value)
		self._summarize()
		self.changed.emit(self._value)

	def _tidy(self, value):
		return value or None

	def summary(self) -> str:
		return 'set' if self._value is not None else 'not set'

	def _summarize(self):
		self.button.setText(self.summary() + '  \u25be')

	def setValue(self, value):
		self._value = value
		self._summarize()
		if self.panel.isVisible():
			self.form.setValue(value)

	def value(self):
		return self._value

	def onContext(self):
		self.form.onContext()

	def isEditing(self) -> bool:
		return self.panel.isVisible() and self.form.isEditing()


class BeamEdit(_Popover):
	"""`beam:` as a popover. Off when it has no `active` or `sweep`."""

	title = 'Beam'

	def __init__(self):
		super().__init__(BeamForm())

	def _tidy(self, value):
		return value or None

	def summary(self) -> str:
		spec = self._value if isinstance(self._value, dict) else {}
		if not spec:
			return 'Beam: off'
		running = spec.get('active') not in (None, False) or spec.get('sweep') not in (None, False)
		bits = [spec.get('size', 'md'), spec.get('variant', 'colorful')]
		return 'Beam: ' + ' \u00b7 '.join(bits) + ('' if running else ' (not triggered)')


class WhenEdit(_Popover):
	"""`when:` as a popover: the form is a mode and a key or expression, with hints."""

	title = 'When'

	def __init__(self):
		form = _Form()
		self.condition = form.part('when', 'when', ConditionEdit(unsetText='always shown'),
		                           'Show this panel only while the condition holds. In a switch the slot picks among its children by it.')
		hint = QLabel('A key is true when its value is not zero. An expression can use units: '
		              'environment.temperature.temperature < 32\u00b0F. A missing value counts as false.')
		hint.setWordWrap(True)
		hint.setStyleSheet('color: palette(placeholder-text); font-size: 11px;')
		form.grid.addWidget(hint, 1, 0, 1, 2)
		form.setValue = lambda value: self.condition.setValue(value)
		form.value = lambda: self.condition.value()
		super().__init__(form)

	def _tidy(self, value):
		return None if value is None or value == '' else value

	def summary(self) -> str:
		v = self._value
		if v is None:
			return 'When: always shown'
		if isinstance(v, bool):
			return 'When: ' + ('true' if v else 'false')
		return f'When: {v}'


# Section: the factory

def make(field: 'schema.Field') -> Optional[Editor]:
	"""The editor for a field's kind, or None when the plain control will do."""
	kind = field.kind
	if kind == 'size':
		return SizeEdit(nullable=field.nullable, ref='full' if field.key in ('radius', 'inset') else 'radius')
	if kind == 'number' and field.measured:
		return NumberEdit(autoText='auto' if field.nullable else None, measured=True, step=field.step, unitBox=True,
		                  integer=field.integer)
	if kind == 'choice':
		return ChoiceEdit(field.choices)
	if kind == 'font':
		return FontEdit()
	if kind == 'offset':
		return OffsetEdit()
	if kind == 'intset':
		return IntSetEdit()
	if kind == 'format':
		return FormatEdit()
	if kind == 'gradient':
		return GradientEdit(field.path)
	if kind == 'textmap':
		return TextMapEdit()
	if kind == 'zones':
		return ZonesEdit()
	if kind == 'markers':
		return MarkersEdit()
	if kind == 'fill':
		return FillEdit()
	if kind == 'caption':
		return CaptionEdit()
	if kind == 'warp':
		return WarpEdit()
	if kind == 'glow':
		return GlowEdit()
	if kind == 'beam':
		return BeamEdit()
	if kind == 'when':
		return WhenEdit()
	return None

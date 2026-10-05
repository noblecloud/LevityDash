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
gradient `GradientEdit`: a list of stops, each a value and a colour swatch
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
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QRegularExpression, QSignalBlocker, Qt, QTime, Signal
from PySide6.QtGui import QColor, QFontDatabase, QRegularExpressionValidator
from PySide6.QtWidgets import (
	QCheckBox, QColorDialog, QComboBox, QCompleter, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
	QSlider, QSpinBox, QTimeEdit, QToolButton, QVBoxLayout, QWidget,
)

from LevityDash.devtools import _studio_schema as schema

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


class FontEdit(ChoiceEdit):
	"""The installed font families, and any other name you type."""

	def __init__(self):
		super().__init__([(name, name) for name in QFontDatabase.families()], editable=True)
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


class StopItem(_Form):
	def __init__(self):
		super().__init__()
		self.part('value', 'value', NumberEdit(measured=True))
		self.part('color', 'colour', ColorEdit())

	def setValue(self, value):
		value = value or {}
		for key, p in self.parts.items():
			with QSignalBlocker(p):
				p.setValue(value.get(key))

	def value(self):
		return {'value': self.parts['value'].value() or 0, 'color': self.parts['color'].value() or '#ffffff'}


class GradientEdit(ListEditor):
	"""A colour at each value; the arc blends between them."""

	def __init__(self):
		super().__init__(StopItem, self._fresh, '+ Add stop', 'No gradient. The arc keeps its colour.', measured=True)
		from LevityDash.lib.ui.colors import Gradient
		self.presets = QComboBox()
		self.presets.addItem('Preset…', None)
		for name in Gradient.presets():
			self.presets.addItem(name, name)
		self.presets.activated.connect(self._preset)
		self.layout().insertWidget(1, self.presets)

	@staticmethod
	def _fresh(items):
		lo, hi = CONTEXT.range()
		top = max((i['value'] for i in items), default=lo - (hi - lo) / 4)
		return {'value': min(hi, top + (hi - lo) / 4), 'color': '#2f81f7'}

	def _preset(self, _):
		name = self.presets.currentData()
		if name is None:
			return
		from LevityDash.lib.ui.colors import Gradient
		self.setValue(schema.gradientText(Gradient.decode(name)))
		with QSignalBlocker(self.presets):
			self.presets.setCurrentIndex(0)
		self._emit()

	def setValue(self, value):
		stops = [{'value': k, 'color': v} for k, v in sorted((value or {}).items(), key=lambda kv: float(kv[0]))]
		self.setItems(stops)

	def value(self):
		stops = self.items()
		return {s['value']: s['color'] for s in sorted(stops, key=lambda s: s['value'])} or None

	def setItems(self, values):
		current = self.items()
		if [(float(a['value']), a['color'].lower()) for a in values] == [(float(a['value']), a['color'].lower()) for a in current]:
			return
		super().setItems(values)


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


class CaptionEdit(_Toggled):
	def __init__(self):
		super().__init__('Show small text', CaptionForm())

	def fresh(self):
		return 'Label'


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
		return GradientEdit()
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
	return None

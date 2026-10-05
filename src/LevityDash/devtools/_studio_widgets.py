"""Dev-only: the Qt widgets Gauge Studio builds its panel from.

One `FieldRow` per `_studio_schema.Field`. A row holds a label, the control
that fits the field's kind, a reset button and a line for the reason a value
was rejected. A `Section` is a collapsible box. `build` turns a `Group` tree
into nested sections.

No widget here knows about gauges. A row reports `edited(path, value)` in the
same form a `.levity` file holds, and the window decides what to do with it.
"""
import re
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
	QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
	QPushButton, QSlider, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from LevityDash.devtools import _studio_editors as editors
from LevityDash.devtools._studio_schema import Field, Group, fromText, toYaml

_NUMBER = re.compile(r'^\s*(-?\d+(?:\.\d+)?)')
SLIDER_STEPS = 1000
ERROR_COLOR = '#e5484d'


def toNumber(value: Any) -> Optional[float]:
	"""A number from a saved value: `10`, `'10'` or `'10°'`."""
	if isinstance(value, bool):
		return None
	if isinstance(value, (int, float)):
		return float(value)
	if isinstance(value, str) and (match := _NUMBER.match(value)):
		return float(match.group(1))
	return None


def labelFor(key: str) -> str:
	return key.replace('-', ' ').replace('_', ' ')


class Section(QWidget):
	"""A header you click to fold, over a body that holds rows and child sections."""

	userToggled = Signal(bool)  # a click on the header, not a change the filter made

	def __init__(self, title: str, expanded: bool = False, parent: Optional[QWidget] = None):
		super().__init__(parent)
		self.key = ''  # names the section in the saved fold state
		self._preFilter: Optional[bool] = None
		outer = QVBoxLayout(self)
		outer.setContentsMargins(0, 0, 0, 0)
		outer.setSpacing(0)
		self.header = QToolButton()
		self.header.setText(title[:1].upper() + title[1:])
		self.header.setCheckable(True)
		self.header.setChecked(expanded)
		self.header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
		self.header.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
		self.header.setStyleSheet('QToolButton { border: none; font-weight: 600; padding: 6px 4px; text-align: left; color: palette(window-text); }')
		self.header.setSizePolicy(self.header.sizePolicy().horizontalPolicy(), self.header.sizePolicy().verticalPolicy())
		self.header.toggled.connect(self._toggled)
		self.header.clicked.connect(self.userToggled)
		self.headerBar = QHBoxLayout()
		self.headerBar.setContentsMargins(0, 0, 0, 0)
		self.headerBar.setSpacing(4)
		self.headerBar.addWidget(self.header, 1)
		outer.addLayout(self.headerBar)
		self.body = QFrame()
		self.body.setVisible(expanded)
		self.grid = QGridLayout(self.body)
		self.grid.setContentsMargins(14, 0, 0, 6)
		self.grid.setHorizontalSpacing(6)
		self.grid.setVerticalSpacing(3)
		self.grid.setColumnStretch(1, 1)
		outer.addWidget(self.body)
		self._row = 0
		self.path: tuple = ()

	def _toggled(self, on: bool):
		self.header.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
		self.body.setVisible(on)

	def setExpanded(self, on: bool):
		self.header.setChecked(on)

	def addRow(self, widget: QWidget):
		self.grid.addWidget(widget, self._row, 0, 1, 3)
		self._row += 1

	def addHeaderWidget(self, widget: QWidget):
		self.headerBar.addWidget(widget)

	def clear(self):
		while self.grid.count():
			w = self.grid.takeAt(0).widget()
			if w is not None:
				w.setParent(None)
				w.deleteLater()
		self._row = 0

	def setFiltered(self, text: str) -> bool:
		"""Show only rows whose label contains `text`. True when anything matches."""
		anything = False
		for i in range(self.grid.count()):
			w = self.grid.itemAt(i).widget()
			if isinstance(w, FieldRow):
				hit = w.matches(text) and not w.ruledOut
				w.setVisible(hit)
				anything |= hit
			elif isinstance(w, Section):
				hit = w.setFiltered(text)
				w.setVisible(hit)
				anything |= hit
		if text:
			if self._preFilter is None:
				self._preFilter = self.header.isChecked()
			self.setExpanded(anything)
		elif self._preFilter is not None:
			self.setExpanded(self._preFilter)
			self._preFilter = None
		return anything or not text


class FieldRow(QWidget):
	"""One property: label, control, reset, and the reason a value was rejected."""

	edited = Signal(tuple, object)  # path, value in `.levity` form
	pinToggled = Signal(tuple, bool)

	def __init__(self, field: Field, saved: Any, parent: Optional[QWidget] = None):
		super().__init__(parent)
		self.field = field
		self.baseline = saved
		self._stepping = False
		self.ruledOut = False  # hidden because the needle type does not use it
		self.editor: Optional[editors.Editor] = editors.make(field)
		if self.editor is None and field.kind == 'color':
			self.editor = editors.ColorEdit(nullable=field.nullable)
		grid = QGridLayout(self)
		grid.setContentsMargins(0, 0, 0, 0)
		grid.setHorizontalSpacing(6)
		grid.setVerticalSpacing(0)
		self.label = QLabel(labelFor(field.key))
		self.label.setMinimumWidth(96)
		self.label.setToolTip((field.doc + '\n\n' if field.doc else '') + '.'.join(field.path))
		grid.addWidget(self.label, 0, 0)
		self.control = QWidget()
		box = QHBoxLayout(self.control)
		box.setContentsMargins(0, 0, 0, 0)
		box.setSpacing(4)
		if self.editor is not None:
			self.editor.setToolTip(field.doc)
			self.editor.changed.connect(self._emit)
			box.addWidget(self.editor, 1)
		else:
			self._build(box)
		if self.editor is not None and self.editor.minimumSizeHint().width() > 300:
			self.editor.wide = True  # too wide to sit beside the label: it would force the panel to scroll sideways
		if self.editor is not None and self.editor.wide:
			grid.addWidget(self.control, 2, 0, 1, 4)
		else:
			grid.addWidget(self.control, 0, 1)
		self.reset = QToolButton()
		self.reset.setText('↺')
		self.reset.setToolTip('Back to the value it had when this template loaded')
		self.reset.setAutoRaise(True)
		self.reset.clicked.connect(self.resetToBaseline)
		self.reset.setEnabled(False)
		grid.addWidget(self.reset, 0, 2)
		self.reset.setVisible(saved is not None or self.editor is not None)
		self.pin = QToolButton()
		self.pin.setCheckable(True)
		self.pin.setAutoRaise(True)
		self.pin.setText('☆')
		self.pin.setToolTip('Pin this property to the top of the panel')
		keep = self.pin.sizePolicy()
		keep.setRetainSizeWhenHidden(True)
		self.pin.setSizePolicy(keep)
		self.pin.setVisible(False)
		self.pin.toggled.connect(self._pinned)
		grid.addWidget(self.pin, 0, 3)
		self.error = QLabel()
		self.error.setWordWrap(True)
		self.error.setStyleSheet(f'color: {ERROR_COLOR}; font-size: 11px;')
		self.error.setVisible(False)
		grid.addWidget(self.error, 1, 0, 1, 4)
		grid.setColumnStretch(1, 1)
		self.setSaved(saved)

	# pinning

	def _pinned(self, on: bool):
		self.pin.setText('★' if on else '☆')
		self.pinToggled.emit(self.field.path, on)

	def setPinned(self, on: bool):
		"""Show the pin state without reporting a toggle."""
		with QSignalBlocker(self.pin):
			self.pin.setChecked(on)
		self.pin.setText('★' if on else '☆')
		self.pin.setVisible(on)

	def enterEvent(self, event):
		self.pin.setVisible(True)
		super().enterEvent(event)

	def leaveEvent(self, event):
		self.pin.setVisible(self.pin.isChecked())
		super().leaveEvent(event)

	# building

	def _build(self, box: QHBoxLayout):
		kind = self.field.kind
		f = self.field
		if kind == 'bool':
			self.check = QCheckBox()
			self.check.toggled.connect(lambda on: self._emit(bool(on)))
			box.addWidget(self.check)
			box.addStretch(1)
		elif kind == 'enum':
			self.combo = QComboBox()
			for name, text in f.choices:
				self.combo.addItem(name, text)
			self.combo.activated.connect(lambda i: self._emit(self.combo.itemData(i)))
			box.addWidget(self.combo, 1)
		elif kind == 'color':
			self.swatch = QPushButton()
			self.swatch.setFixedSize(28, 20)
			self.swatch.clicked.connect(self._pickColor)
			self.colorText = QLineEdit()
			self.colorText.editingFinished.connect(lambda: self._emit(self.colorText.text().strip()))
			box.addWidget(self.swatch)
			box.addWidget(self.colorText, 1)
		elif kind == 'number':
			self.slider = QSlider(Qt.Orientation.Horizontal)
			self.slider.setRange(0, SLIDER_STEPS)
			self.spin = QSpinBox() if f.integer else QDoubleSpinBox()
			self.spin.setRange(-1e6, 1e6)
			if not f.integer:
				self.spin.setDecimals(3 if f.step < 0.1 else 2)
			self.spin.setSingleStep(f.step)
			self.spin.setMinimumWidth(72)
			self._suffix()
			self.spin.setKeyboardTracking(False)
			self.slider.valueChanged.connect(self._sliderMoved)
			self.spin.valueChanged.connect(self._spinChanged)
			box.addWidget(self.slider, 1)
			box.addWidget(self.spin)
		elif kind == 'percent':
			self.slider = QSlider(Qt.Orientation.Horizontal)
			self.slider.setRange(0, SLIDER_STEPS)
			self.text = QLineEdit()
			self.text.setMaximumWidth(80)
			self.slider.valueChanged.connect(self._sliderMoved)
			self.text.editingFinished.connect(self._textEdited)
			box.addWidget(self.slider, 1)
			box.addWidget(self.text)
		else:  # text, yaml
			self.text = QLineEdit()
			self.text.setPlaceholderText('flow YAML: {a: 1}' if kind == 'yaml' else 'unset')
			self.text.editingFinished.connect(self._textEdited)
			box.addWidget(self.text, 1)

	def _suffix(self):
		f = self.field
		text = f.suffix
		if f.measured and editors.CONTEXT.unit:
			text = f' {editors.CONTEXT.unit}'
		self.spin.setSuffix(text)

	def onContext(self):
		if self.editor is not None:
			self.editor.onContext()
		elif self.field.kind == 'number':
			self._suffix()

	# slider mapping: the slider spans lo..hi, stretched when the value is outside it

	def _span(self, value: Optional[float]):
		lo, hi = self.field.lo, self.field.hi
		if self.field.kind == 'percent':
			lo, hi = 0.0, max(100.0, abs(value or 0) * 1.5)
		if value is not None:
			lo, hi = min(lo, value), max(hi, value)
		return lo, hi

	def _toSlider(self, value: float) -> int:
		lo, hi = self._span(value)
		return round((value - lo) / (hi - lo) * SLIDER_STEPS) if hi > lo else 0

	def _fromSlider(self, pos: int) -> float:
		lo, hi = self._span(self._current)
		value = lo + pos / SLIDER_STEPS * (hi - lo)
		return round(value) if self.field.integer else round(value, 3)

	_current: Optional[float] = None

	def _sliderMoved(self, pos: int):
		if self._stepping:
			return
		value = self._fromSlider(pos)
		self._current = value
		if self.field.kind == 'percent':
			self.text.setText(f'{value:g}%')
			self._emit(f'{value:g}%')
		else:
			with QSignalBlocker(self.spin):
				self.spin.setValue(value)
			self._emit(int(value) if self.field.integer else value)

	def _spinChanged(self, value):
		self._current = float(value)
		with QSignalBlocker(self.slider):
			self.slider.setValue(self._toSlider(float(value)))
		self._emit(int(value) if self.field.integer else float(value))

	def _textEdited(self):
		text = self.text.text().strip()
		if self.field.kind == 'percent':
			if (n := toNumber(text)) is not None and text.rstrip().endswith('%'):
				self._current = n
				with QSignalBlocker(self.slider):
					self.slider.setValue(self._toSlider(n))
			self._emit(text)
		else:
			self._emit(fromText(text) if self.field.kind == 'yaml' else _plain(text))

	def _pickColor(self):
		start = QColor(self.colorText.text() or 'white')
		chosen = QColorDialog.getColor(start, self, labelFor(self.field.key))
		if chosen.isValid():
			self._emit(chosen.name())

	# in and out

	def _emit(self, value: Any):
		self.setError(None)
		self.reset.setEnabled(True)
		self.edited.emit(self.field.path, value)

	def setError(self, reason: Optional[str]):
		self.error.setText(reason or '')
		self.error.setVisible(bool(reason))
		self.label.setStyleSheet(f'color: {ERROR_COLOR};' if reason else '')

	def hasError(self) -> bool:
		return self.error.isVisible()

	def resetToBaseline(self):
		self.setSaved(self.baseline)
		self.reset.setEnabled(False)
		self.setError(None)
		self.edited.emit(self.field.path, self.baseline if self.baseline is not None else None)

	def setSaved(self, saved: Any):
		"""Show a value without reporting it as an edit."""
		kind = self.field.kind
		if self.editor is not None:
			with QSignalBlocker(self.editor):
				self.editor.setValue(saved)
			return
		if kind == 'bool':
			with QSignalBlocker(self.check):
				self.check.setChecked(bool(saved))
		elif kind == 'enum':
			with QSignalBlocker(self.combo):
				i = self.combo.findData(saved)
				if i < 0:
					i = self.combo.findText(str(saved), Qt.MatchFlag.MatchFixedString)
				self.combo.setCurrentIndex(max(i, 0) if i >= 0 else -1)
		elif kind == 'color':
			text = '' if saved is None else str(saved)
			with QSignalBlocker(self.colorText):
				self.colorText.setText(text)
			color = QColor(text)
			self.swatch.setStyleSheet(f'background: {color.name() if color.isValid() else "transparent"}; border: 1px solid #888;')
		elif kind == 'number':
			n = toNumber(saved)
			self._current = n
			with QSignalBlocker(self.spin), QSignalBlocker(self.slider):
				self.spin.setValue(n if n is not None else 0)
				self.slider.setValue(self._toSlider(n) if n is not None else 0)
				self.slider.setEnabled(n is not None)
		elif kind == 'percent':
			text = '' if saved is None else str(saved)
			n = toNumber(text)
			self._current = n
			with QSignalBlocker(self.text), QSignalBlocker(self.slider):
				self.text.setText(text)
				self.slider.setValue(self._toSlider(n) if n is not None else 0)
		else:
			with QSignalBlocker(self.text):
				self.text.setText(toYaml(saved) if self.field.kind == 'yaml' else ('' if saved is None else str(saved)))

	def isEditing(self) -> bool:
		return any(w.hasFocus() or (isinstance(w, QComboBox) and w.view().isVisible()) for w in self.control.findChildren(QWidget)) or self.slider_down()

	def slider_down(self) -> bool:
		slider = getattr(self, 'slider', None)
		return slider is not None and slider.isSliderDown()

	def matches(self, text: str) -> bool:
		text = text.strip().lower()
		return not text or text in self.field.key.lower() or text in '.'.join(self.field.path).lower()


def _plain(text: str) -> Any:
	"""A text field's content as a `.levity` scalar: numbers stay numbers, `5mm` stays text."""
	if text == '':
		return None
	try:
		return int(text)
	except ValueError:
		pass
	try:
		return float(text)
	except ValueError:
		return text


def build(group: Group, read: Callable[[tuple], Any], rows: Dict[tuple, FieldRow], expanded: bool = False,
          top: bool = True) -> Section:
	"""Nested sections for a `Group`. Every row it makes lands in `rows`, keyed by path."""
	section = Section(group.title if not top else 'Gauge', expanded=expanded)
	section.path = group.path
	for field in group.fields:
		row = FieldRow(field, read(field.path))
		rows[field.path] = row
		section.addRow(row)
	for sub in group.groups:
		section.addRow(build(sub, read, rows, expanded=False, top=False))
	return section


def fieldsOf(group: Group, found: Optional[Dict[tuple, Field]] = None) -> Dict[tuple, Field]:
	"""Every field under `group`, keyed by path."""
	found = {} if found is None else found
	for field in group.fields:
		found[field.path] = field
	for sub in group.groups:
		fieldsOf(sub, found)
	return found

"""Dev-only: the Studio's controls for a graph's plots.

A graph holds `figures:`, each figure holds series keyed by data key, and each series has a `plot:`.
Until now that whole tree sat in the "More properties" YAML box. `GraphPlotsEdit` is one editor for
the whole `figures:` list: pick a series, then set its plot with the controls its type reads
(a line, a fill under it, a band to another series, a strip of glyphs, pins on the line).
It emits the whole list on every edit, because a series key such as `environment.temperature.temperature`
has dots in it and cannot be a field path.

The first half of this file has no Qt: finding the series in a figures list and writing a plot back
into it. The second half is the widgets, built from the editors the gauge panel already has, so every
number has a slider and a spin box, complex settings sit in popovers and a setting a plot type does
not read is hidden.
"""
import copy
from dataclasses import dataclass
from typing import Any, List, Optional

import yaml
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from LevityDash.devtools import _studio_editors as editors
from LevityDash.devtools._studio_editors import (
	ChoiceEdit, ColorEdit, Editor, GlowEdit, KeyEdit, NumberEdit, SizeEdit, _Form, _Popover, _Toggled,
)

__all__ = ['GraphPlotsEdit', 'Ref', 'series', 'plotOf', 'withPlot', 'withFigure', 'plotTypes']

#: Keys of a figure that are not series.
FIGURE_FIELDS = ('figure', 'margins', 'min', 'max', 'scale', 'height', 'width')

#: The plot types, with the label the Studio shows.
TYPES = [('line', 'plot'), ('bar', 'bar'), ('area', 'area'), ('band', 'band'), ('strip', 'strip'), ('violin', 'violin')]

#: Which settings each plot type reads. A type that is not here reads all of them.
USED = {
	'plot': {'color', 'gradient', 'weight', 'opacity', 'glow', 'fill', 'pins'},
	'bar': {'color', 'gradient', 'opacity'},
	'area': {'color', 'gradient', 'opacity', 'glow', 'base', 'pins'},
	'band': {'color', 'gradient', 'opacity', 'glow', 'to'},
	'strip': {'pins'},
	'violin': {'color', 'gradient', 'opacity'},
}

GRADIENTS = ['TemperatureGradient', 'WindSpeedGradient', 'PrecipitationRateGradient', 'UVIndexGradient', '$temperature', '$load']

GLYPHS = ['wi:direction-up', 'wi:direction-up-right', 'fa:arrow-up', 'mdi:navigation']


# Section: the data

@dataclass(frozen=True)
class Ref:
	"""One series of a graph: which figure and which key."""
	figure: int
	key: str
	name: str = ''

	def label(self) -> str:
		short = self.key.rsplit('.', 1)[-1] if '.' in self.key else self.key
		return f'{self.name or f"figure {self.figure + 1}"} · {short}'


def series(figures: Any) -> List[Ref]:
	"""Every series of a figures list, in order. Anything that is not a list of mappings has none."""
	out = []
	if not isinstance(figures, list):
		return out
	for i, figure in enumerate(figures):
		if not isinstance(figure, dict):
			continue
		for key, value in figure.items():
			if key not in FIGURE_FIELDS and isinstance(value, dict):
				out.append(Ref(i, str(key), str(figure.get('figure') or '')))
	return out


def plotOf(figures: list, ref: Ref) -> dict:
	"""The series' plot as a mapping. A bare type name (`plot: bar`) is `{type: bar}`; none is `{}`."""
	plot = figures[ref.figure][ref.key].get('plot')
	if isinstance(plot, str):
		return {'type': plot}
	return copy.deepcopy(plot) if isinstance(plot, dict) else {}


def withPlot(figures: list, ref: Ref, plot: Optional[dict]) -> list:
	"""A copy of `figures` with the series' plot replaced. An empty plot removes it."""
	out = copy.deepcopy(figures)
	holder = out[ref.figure][ref.key]
	if plot:
		holder['plot'] = plot
	else:
		holder.pop('plot', None)
	return out


def withFigure(figures: list, index: int, fields: dict) -> list:
	"""A copy with figure `index` set to `fields` for each name given; a value of None removes the field."""
	out = copy.deepcopy(figures)
	figure = out[index]
	for name, value in fields.items():
		if name == 'margins.top' or name == 'margins.bottom':
			margins = dict(figure.get('margins') or {})
			side = name.split('.')[1]
			if value is None:
				margins.pop(side, None)
			else:
				margins[side] = value
			if margins:
				figure['margins'] = margins
			else:
				figure.pop('margins', None)
		elif value is None:
			figure.pop(name, None)
		else:
			figure[name] = value
	return out


def plotTypes() -> List[str]:
	return [value for _, value in TYPES]


# Section: the widgets

def narrow(widget: QWidget) -> None:
	"""Let every dropdown under `widget` be as narrow as the panel needs, not as wide as its longest key."""
	for combo in widget.findChildren(QComboBox):
		combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
		combo.setMinimumContentsLength(8)


def _number(label: str = 'default', lo: float = 0.0, hi: float = 1.0, step: float = 0.05, decimals: int = 2, integer: bool = False) -> NumberEdit:
	return NumberEdit(autoText=label, lo=lo, hi=hi, step=step, decimals=decimals, integer=integer)


class _Choice(ChoiceEdit):
	"""A dropdown whose choices can be replaced, for the series a band can follow."""

	def setChoices(self, values: List[str]):
		current = self.value()
		with QSignalBlocker(self.combo):
			self.combo.clear()
			for v in values:
				self.combo.addItem(v, v)
		self.setValue(current)
		narrow(self)


class RotateEdit(Editor):
	"""`rotate:` of a pin: off, turn by the value (`true`), or by the value plus some degrees."""

	def __init__(self):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		self.mode = QComboBox()
		for text in ('off', 'by the value', 'by the value plus'):
			self.mode.addItem(text)
		self.mode.activated.connect(self._moded)
		self.turn = NumberEdit(lo=-360, hi=360, step=5, decimals=1, suffix='°')
		self.turn.changed.connect(self._emit)
		box.addWidget(self.mode)
		box.addWidget(self.turn, 1)
		self.turn.setVisible(False)

	def _moded(self, *_):
		self.turn.setVisible(self.mode.currentIndex() == 2)
		if self.mode.currentIndex() == 2 and not self.turn.value():
			self.turn.setValue(180)
		self._emit()

	def setValue(self, value):
		if value in (None, False):
			index = 0
		elif value is True or value == 0:
			index = 1
		else:
			index = 2
		with QSignalBlocker(self.mode):
			self.mode.setCurrentIndex(index)
		self.turn.setVisible(index == 2)
		if index == 2:
			self.turn.setValue(float(value))

	def value(self):
		index = self.mode.currentIndex()
		if index == 0:
			return None
		if index == 1:
			return True
		return self.turn.value() or True


class _YamlBox(Editor):
	"""A text box that holds a mapping as YAML. A text that does not parse keeps the last good value and says so."""

	def __init__(self):
		super().__init__()
		box = QVBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		self.text = QPlainTextEdit()
		self.text.setMinimumHeight(120)
		self.text.setPlaceholderText("steps:\n- [0, 'wi:day-sunny']\n- [0.1, 'wi:showers']")
		self.note = QLabel()
		self.note.setStyleSheet('color: #e5534b; font-size: 11px;')
		self.note.setVisible(False)
		box.addWidget(self.text)
		box.addWidget(self.note)
		self._value: dict = {}
		self.text.textChanged.connect(self._edited)

	def _edited(self):
		try:
			parsed = yaml.safe_load(self.text.toPlainText()) if self.text.toPlainText().strip() else {}
			if not isinstance(parsed, dict):
				raise ValueError('write a mapping, such as steps: or map:')
		except (yaml.YAMLError, ValueError) as error:
			self.note.setText(str(error).splitlines()[0])
			self.note.setVisible(True)
			return
		self.note.setVisible(False)
		self._value = parsed
		self.changed.emit(parsed)

	def setValue(self, value):
		self._value = dict(value or {})
		with QSignalBlocker(self.text):
			self.text.setPlainText(yaml.safe_dump(self._value, default_flow_style=None, sort_keys=False).strip() if self._value else '')
		self.note.setVisible(False)

	def value(self):
		return dict(self._value)

	def isEditing(self) -> bool:
		return self.text.hasFocus()


class SymbolsEdit(_Popover):
	"""The `steps:` and `map:` of pins, as YAML in a popover: a list of rows has no control worth building."""

	title = 'Pin symbols'

	def __init__(self):
		super().__init__(_YamlBox())

	def _tidy(self, value):
		return value or None

	def summary(self) -> str:
		spec = self._value or {}
		if not spec:
			return 'Symbols: none (the value is printed)'
		bits = []
		if spec.get('steps'):
			bits.append(f'{len(spec["steps"])} steps')
		if spec.get('map'):
			bits.append(f'{len(spec["map"])} mapped')
		return 'Symbols: ' + ', '.join(bits)


class _Holding:
	"""Keeps a value a control cannot show. A preset's template holds `$name` where a control wants a number, so
	a part that reads back differently from what it was given is held as written and written back until the user
	touches it. Without this, editing one setting would erase every reference beside it."""

	_held: dict

	def _put(self, key: str, part: Editor, value: Any):
		if not hasattr(self, '_held'):
			self._held = {}
		with QSignalBlocker(part):
			part.setValue(value)
		shown = part.value()
		if value is not None and shown != value:
			self._held[key] = (value, shown)
		else:
			self._held.pop(key, None)

	def _get(self, key: str, part: Editor) -> Any:
		value = part.value()
		held = getattr(self, '_held', {}).get(key)
		return held[0] if held is not None and value == held[1] else value


class PinsForm(_Holding, _Form):
	"""`pins:` of a line, an area or a strip."""

	def __init__(self):
		super().__init__()
		self.part('key', 'key', KeyEdit('environment.precipitation.precipitation'), 'The key whose value picks each pin')
		self.part('size', 'size', _number('default 14', 6, 80, 1, 0, True), 'Pixels across a pin')
		self.part('at', 'height', _number('on the line', 0, 1, 0.05, 2), 'Put every pin at one height: 0 is the bottom of the figure, 1 the top. A strip uses 0.5')
		self.part('offset', 'offset', _number('default -1.2', -4, 4, 0.1, 1), 'Distance from the line in pin sizes. Negative is above')
		self.part('spacing', 'spacing', _number('default 1.6', 0, 6, 0.1, 1), 'The smallest gap between two pins, in pin sizes')
		self.part('only', 'where', ChoiceEdit([('every sample', None), ('peaks', 'peaks'), ('troughs', 'troughs'), ('peaks and troughs', 'extremes')]),
		          'Pins only where the line turns')
		self.part('prominence', 'prominence', _number('default 0.15', 0.01, 1, 0.01, 2), 'How far a turn must stand out, as a share of the line\'s range')
		self.part('glyph', 'glyph', ChoiceEdit([('from the value', None)] + [(g, g) for g in GLYPHS], editable=True), 'One icon for every pin, such as an arrow')
		self.part('rotate', 'turn', RotateEdit(), 'Turn each pin by its value, in degrees clockwise. Wind direction needs 180 for an arrow that points downwind')
		self.part('color', 'colour', ColorEdit(nullable=True), 'Left alone the pins are painted like the line')
		self.symbols = SymbolsEdit()
		self.symbols.changed.connect(self._emit)
		self.grid.addWidget(QLabel('symbols'), self._r, 0)
		self.grid.addWidget(self.symbols, self._r, 1)
		self._r += 1

	def setValue(self, value):
		spec = dict(value) if isinstance(value, dict) else {}
		self._extra = {k: v for k, v in spec.items() if k not in self._known and k not in ('steps', 'map')}
		for key, p in self.parts.items():
			v = spec.get(key)
			if key == 'size' and v is not None and not isinstance(v, (int, float)):
				self._extra['size'] = v  # a length such as 5mm: kept as written
				v = None
			self._put(key, p, v)
		self.symbols.setValue({k: spec[k] for k in ('steps', 'map') if k in spec})

	def value(self):
		out = dict(self._extra)
		for key, p in self.parts.items():
			v = self._get(key, p)
			if v is not None:
				out[key] = v
		out.update(self.symbols.value() or {})
		return out


class PinsEdit(_Toggled):
	def __init__(self):
		super().__init__('Pins: a mark on the line for each value of a key', PinsForm())

	def fresh(self):
		return {'key': 'environment.precipitation.precipitation', 'size': 22}


class FillForm(_Holding, _Form):
	"""`fill:` of a line: how strong, and the value it reaches."""

	def __init__(self):
		super().__init__()
		self.part('opacity', 'opacity', _number('default 0.25', 0, 1, 0.05, 2), 'How strong the fill is')
		self.part('base', 'down to', NumberEdit(autoText='the bottom', lo=-100, hi=200, step=1, decimals=1),
		          'The value the fill reaches, in the unit of the data. The axis always includes it')

	def setValue(self, value):
		spec = {'opacity': value} if isinstance(value, (int, float)) and not isinstance(value, bool) else (dict(value) if isinstance(value, dict) else {})
		self._extra = {k: v for k, v in spec.items() if k not in self._known}
		for key, p in self.parts.items():
			self._put(key, p, spec.get(key))

	def value(self):
		out = dict(self._extra)
		for key, p in self.parts.items():
			v = self._get(key, p)
			if v is not None:
				out[key] = v
		return out or True


class FillEdit(_Toggled):
	def __init__(self):
		super().__init__('Fill the space under the line', FillForm())

	def fresh(self):
		return True


class PlotForm(_Holding, _Form):
	"""One series' `plot:`."""

	def __init__(self):
		super().__init__()
		self.type = self.part('type', 'type', ChoiceEdit(TYPES), 'What the series draws')
		self.part('color', 'colour', ColorEdit(nullable=True))
		self.part('gradient', 'gradient', ChoiceEdit([('none', None)] + [(g, g) for g in GRADIENTS], editable=True), 'A named scale that colours the plot by value')
		self.part('weight', 'weight', _number('default', 0.1, 6, 0.1, 2), 'Thickness of the line')
		self.part('opacity', 'opacity', _number('default', 0, 1, 0.05, 2))
		self.to = self.part('to', 'to', _Choice([]), 'The other series the band reaches. Both are read at the band\'s own sample times')
		self.part('base', 'base', NumberEdit(autoText='default 0', lo=-100, hi=200, step=1, decimals=1), 'The value an area fills down to')
		self.part('glow', 'glow', GlowEdit())
		self.part('fill', 'fill', FillEdit())
		self.part('pins', 'pins', PinsEdit())
		self.type.changed.connect(self._shown)
		self._shown()

	def setSeries(self, keys: List[str]):
		self.to.setChoices(keys)

	def _shown(self, *_):
		kind = self.type.value() or 'plot'
		used = USED.get(kind, set(self.parts) - {'type'})
		for key in self.parts:
			if key != 'type':
				self.showPart(key, key in used)

	def setValue(self, value):
		spec = dict(value or {})
		self._extra = {k: v for k, v in spec.items() if k not in self._known}
		for key, p in self.parts.items():
			self._put(key, p, spec.get(key, 'plot' if key == 'type' else None))
		self._shown()

	def value(self):
		out = dict(self._extra)
		kind = self.type.value() or 'plot'
		used = USED.get(kind, set(self.parts))
		out['type'] = kind
		for key, p in self.parts.items():
			if key == 'type' or key not in used:
				continue
			v = self._get(key, p)
			if v is not None:
				out[key] = v
		return out


class FigureForm(_Holding, _Form):
	"""What a figure sets for all its series: the range and the band of the graph it sits in."""

	def __init__(self):
		super().__init__()
		self.part('min', 'min', NumberEdit(autoText='fit the data', lo=-100, hi=200, step=1, decimals=2), 'The bottom of the scale, in the unit of the data')
		self.part('max', 'max', NumberEdit(autoText='fit the data', lo=-100, hi=200, step=1, decimals=2), 'The top of the scale')
		self.part('margins.top', 'space above', SizeEdit(nullable=True, autoText='default', ref='full'), 'Space above this figure. A strip or a ribbon takes a band of its own')
		self.part('margins.bottom', 'space below', SizeEdit(nullable=True, autoText='default', ref='full'), 'Space below this figure')

	def setFigure(self, figure: dict):
		margins = figure.get('margins') if isinstance(figure.get('margins'), dict) else {}
		values = {'min': figure.get('min'), 'max': figure.get('max'), 'margins.top': margins.get('top'), 'margins.bottom': margins.get('bottom')}
		for key, p in self.parts.items():
			self._put(key, p, values[key])

	def setValue(self, value):
		self.setFigure(value or {})

	def value(self):
		return {key: self._get(key, p) for key, p in self.parts.items()}


class GraphPlotsEdit(Editor):
	"""The `figures:` of a graph: a series picker, the figure's range and margins, and the series' plot."""

	wide = True

	def __init__(self):
		super().__init__()
		box = QVBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		box.setSpacing(4)
		self.picker = QComboBox()
		self.picker.activated.connect(self._picked)
		self.note = QLabel()
		self.note.setWordWrap(True)
		self.note.setStyleSheet('color: palette(placeholder-text);')
		self.figure = FigureForm()
		self.plot = PlotForm()
		for title, widget in (('series', self.picker), ('figure', self.figure), ('plot', self.plot)):
			row = QWidget()
			line = QVBoxLayout(row)
			line.setContentsMargins(0, 0, 0, 0)
			line.setSpacing(2)
			head = QLabel(title)
			head.setStyleSheet('font-weight: 600;')
			line.addWidget(head)
			line.addWidget(widget)
			box.addWidget(row)
		box.addWidget(self.note)
		narrow(self)
		self.figure.changed.connect(self._figureEdited)
		self.plot.changed.connect(self._plotEdited)
		self._figures: Any = None
		self._refs: List[Ref] = []

	def _current(self) -> Optional[Ref]:
		i = self.picker.currentIndex()
		return self._refs[i] if 0 <= i < len(self._refs) else None

	def _load(self):
		ref = self._current()
		on = ref is not None
		for w in (self.figure, self.plot):
			w.parentWidget().setVisible(on)
		self.picker.parentWidget().setVisible(on)
		if ref is None:
			self.note.setText('No plots to edit here.' if isinstance(self._figures, list) else 'The figures come from a preset property; edit them in the preset.')
			self.note.setVisible(True)
			return
		self.note.setVisible(False)
		self.plot.setSeries([r.key for r in self._refs if r != ref])
		self.figure.setFigure(self._figures[ref.figure])
		self.plot.setValue(plotOf(self._figures, ref))

	def _picked(self, *_):
		self._load()

	def _figureEdited(self, fields: dict):
		ref = self._current()
		if ref is None:
			return
		self._figures = withFigure(self._figures, ref.figure, fields)
		self.changed.emit(copy.deepcopy(self._figures))

	def _plotEdited(self, plot: dict):
		ref = self._current()
		if ref is None:
			return
		self._figures = withPlot(self._figures, ref, plot)
		self.changed.emit(copy.deepcopy(self._figures))

	def setValue(self, value):
		keep = self._current()
		self._figures = copy.deepcopy(value)
		self._refs = series(self._figures)
		with QSignalBlocker(self.picker):
			self.picker.clear()
			for ref in self._refs:
				self.picker.addItem(ref.label())
			if keep in self._refs:
				self.picker.setCurrentIndex(self._refs.index(keep))
		self._load()

	def value(self):
		return copy.deepcopy(self._figures)

	def isEditing(self) -> bool:
		return self.figure.isEditing() or self.plot.isEditing()

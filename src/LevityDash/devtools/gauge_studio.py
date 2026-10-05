#!/usr/bin/env python
"""Dev-only: Gauge Studio. Design one gauge live, with controls, on made-up data.

    poetry run python src/LevityDash/devtools/gauge_studio.py [fragment.levity]

A standalone program. It does not start the dashboard, a plugin, the backend or
the Fixture plugin. It draws the real `Gauge` class on its own scene and feeds
it a value the studio owns (see `_studio_stage.py`).

- Left: the gauge, on a dark stage.
- Right: one control per StateProperty on the gauge and every part of it
  (see `_studio_schema.py`). A property added to `Gauge.py` shows up here with no
  edit. A value the gauge rejects shows its reason under the control.
- Value: a slider over the gauge's range, or an animated sweep.
- Templates: every file in `docs/design-references/presets/`, every gauge cell in
  `docs/design-references/gauge-showcase.levity`, and any file you open.
- Copy code / Save as: the gauge's `.levity` YAML, only the properties that
  differ from the defaults.
- With a fragment path, the studio reloads it whenever the file changes on disk.

Importing `LevityDash` builds the config object, so the studio points every
LevityDash directory at a throwaway temp directory first. It never reads or
writes the real config.
"""
import argparse
import copy
import math
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _studio_env

_studio_env.prepare()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import yaml
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
	QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGraphicsView, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
	QPushButton, QScrollArea, QSlider, QSplitter, QToolButton, QVBoxLayout, QWidget,
)

from LevityDash.devtools import _studio_schema as schema
from LevityDash.devtools import _studio_stage as _stage
from LevityDash.devtools._studio_stage import DATA_PRESETS, DataPreset, StudioGauge, StudioScene, presetForKey
from LevityDash.devtools import _studio_editors as editors
from LevityDash.devtools._studio_handles import HandleLayer
from LevityDash.devtools._studio_widgets import FieldRow, Section, build

StatefulDumper = schema.StudioDumper

REPO = Path(__file__).resolve().parents[3]
PRESET_DIR = REPO / 'docs' / 'design-references' / 'presets'
SHOWCASE = REPO / 'docs' / 'design-references' / 'gauge-showcase.levity'

#: Runtime-computed state the dumper reports but a file should not hold.
EXPORT_DROP = {('center_offset',), ('unit-label', 'text'), ('value-label', 'text')}

#: How long input must be quiet before the gauge is rebuilt from its saved form.
SETTLE_MS = 400

STAGES = {'Square 800x800': (800, 800), 'Wide 1200x700': (1200, 700), 'Tall 600x900': (600, 900)}
MOTIONS = {
	'sine': lambda p: math.sin(2 * math.pi * p),
	'triangle': lambda p: 4 * abs(((p + 0.75) % 1) - 0.5) - 1,
	'sawtooth': lambda p: 2 * (p % 1) - 1,
}


_DEGREES = re.compile(r'^(-?\d+(?:\.\d+)?)\s*\u00b0$')


def _plainNumbers(node: Any) -> Any:
	"""Write `60\u00b0` as `60`. The dumper writes a temperature that way, and the loader
	(`decode_measurement` -> `auto_wu`) cannot read it back; a bare number it can."""
	if isinstance(node, dict):
		return {k: _plainNumbers(v) for k, v in node.items()}
	if isinstance(node, list):
		return [_plainNumbers(v) for v in node]
	if isinstance(node, str) and (m := _DEGREES.match(node)):
		n = float(m.group(1))
		return int(n) if n.is_integer() else n
	return node


def _expandSingles(node: dict, owner) -> dict:
	"""Write `labels: outside` as `labels: {position: outside}`.

	`getItemState` collapses a part with one key to that key's bare value. The
	loader cannot read the collapsed form back when the value is an enum
	(`TypeError: Unable to set state for [] with outside`), so the export spells it out.
	"""
	out = {}
	for key, value in node.items():
		prop = schema.findProp(owner, key)
		try:
			part = prop.fget(owner) if prop is not None else None
		except Exception:
			part = None
		if isinstance(part, schema.Stateful):
			if isinstance(value, dict):
				value = _expandSingles(value, part)
			else:
				singles = [p for p in type(part).statefulItems.values() if p.singleVal]
				match = [p for p in singles if schema._same(schema.saved(p, _get(p, part), part), value)]
				pick = (match or singles or [None])[0]
				if pick is not None:
					value = {pick.key: value}
		out[key] = value
	return out


def _get(prop, owner):
	try:
		return prop.fget(owner)
	except Exception:
		return None


def _without(node: Any, base: Any) -> Any:
	"""`node` minus every leaf that equals the same leaf in `base`."""
	if isinstance(node, dict) and isinstance(base, dict):
		out = {}
		for k, v in node.items():
			kept = _without(v, base.get(k))
			if kept not in ({}, None):
				out[k] = kept
		return out
	return None if node == base else node


# Section: reading templates

def readEntries(path: Path) -> List[dict]:
	"""The gauges in a `.levity` fragment, each as the `realtime.gauge` mapping."""
	with open(path, 'r', encoding='utf-8') as file:
		data = yaml.safe_load(file)
	found: List[dict] = []
	_collect(data, found)
	return found


def _collect(node: Any, found: List[dict]):
	if isinstance(node, list):
		for item in node:
			_collect(item, found)
	elif isinstance(node, dict):
		if node.get('type') == 'realtime.gauge':
			found.append(node)
		else:
			_collect(node.get('items'), found)


def showcaseCells() -> List[Tuple[str, dict]]:
	"""Every gauge cell of the showcase, labelled with the caption written beside it."""
	with open(SHOWCASE, 'r', encoding='utf-8') as file:
		data = yaml.safe_load(file)
	cells: List[Tuple[str, dict]] = []

	def visit(node):
		if isinstance(node, list):
			for item in node:
				visit(item)
		elif isinstance(node, dict):
			items = node.get('items')
			if isinstance(items, list):
				gauges = [i for i in items if isinstance(i, dict) and i.get('type') == 'realtime.gauge']
				captions = [i['text'] for i in items if isinstance(i, dict) and i.get('type') == 'text' and 'text' in i]
				if gauges:
					label = (captions[0] if captions else node.get('name', 'gauge')).removeprefix('gauge-ui: ')
					cells.append((label, gauges[0]))
				else:
					visit(items)

	visit(data)
	return cells


# Section: the preview

class Preview(QGraphicsView):
	"""The gauge scene, scaled to fit, on a dark stage."""

	def __init__(self):
		super().__init__()
		self.setBackgroundBrush(QColor('#0b0d10'))
		self.setFrameShape(QFrame.Shape.NoFrame)
		self.setRenderHints(self.renderHints() | self.renderHints().Antialiasing | self.renderHints().TextAntialiasing)
		self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
		self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
		self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
		self.setMinimumSize(320, 320)
		self.setMouseTracking(True)
		self.viewport().setMouseTracking(True)
		self.layer: Optional[HandleLayer] = None

	def enterEvent(self, event):
		super().enterEvent(event)
		if self.layer is not None:
			self.layer.setInside(True)

	def leaveEvent(self, event):
		super().leaveEvent(event)
		if self.layer is not None:
			self.layer.setInside(False)

	def refit(self):
		self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

	def resizeEvent(self, event):
		super().resizeEvent(event)
		self.refit()


# Section: the window

def _pruned(node):
	"""A copy of a mapping without empty branches."""
	if not isinstance(node, dict):
		return node
	pruned = {k: _pruned(v) for k, v in node.items()}
	return {k: v for k, v in pruned.items() if v not in ({}, None)}


class Studio(QWidget):
	"""Preview on the left, controls on the right."""

	def __init__(self, fragment: Optional[Path] = None):
		super().__init__()
		self.setWindowTitle('Gauge Studio')
		self.resize(1280, 860)
		self.preview = Preview()
		self.scene = StudioScene(self.preview)
		self.preview.setScene(self.scene)
		self.studio: Optional[StudioGauge] = None
		self.key: Optional[str] = None
		self.title = 'Gauge'
		self.rows: Dict[tuple, FieldRow] = {}
		self._group: Optional[schema.Group] = None
		self.pending: Dict[tuple, Any] = {}
		self.dragActive = False
		self.history: List[dict] = []
		self.hpos = -1
		self.fragment = fragment
		self.fragmentMtime = fragment.stat().st_mtime if fragment else None
		self.animStart = time.monotonic()

		self._buildChrome()

		self.flushTimer = QTimer(self, singleShot=True, interval=8, timeout=self._flush)
		self.syncTimer = QTimer(self, singleShot=True, interval=60, timeout=self._syncIdle)
		# An edit applies in place at once. A moment after the input goes quiet the gauge is
		# rebuilt from its own saved form, so the preview is what a reload of the exported file
		# draws. In-place edits can leave a gauge laid out a little differently from a fresh one
		# (the centre offset the value label asks for builds up). The rebuild is the slow step,
		# so it waits for the mouse button to come up: dragging a slider only pays for the
		# in-place edit.
		self.settleTimer = QTimer(self, singleShot=True, interval=SETTLE_MS, timeout=self.settle)
		self.animTimer = QTimer(self, interval=16, timeout=self._tick)
		self.watchTimer = QTimer(self, interval=500, timeout=self._checkFile)

		self.studio = StudioGauge(self.scene, DATA_PRESETS['Temperature F'])
		editors.CONTEXT.range = lambda: self.studio.range if self.studio.gauge is not None else (0.0, 100.0)
		self.layer = HandleLayer(self)
		self.preview.layer = self.layer
		for keys in (QKeySequence.StandardKey.Undo, 'Ctrl+Z'):
			QShortcut(QKeySequence(keys), self, activated=self.undo)
		for keys in (QKeySequence.StandardKey.Redo, 'Ctrl+Shift+Z', 'Ctrl+Y'):
			QShortcut(QKeySequence(keys), self, activated=self.redo)
		if fragment is not None:
			self.loadFile(fragment)
			self.watchTimer.start()
		else:
			self.loadDisplay({'arc': {'weight': '5%'}, 'major': {'labels': {'position': 'outside'}}, 'value-label': {'position': 'below'}},
			                 'environment.temperature.temperature', 'Default dial')

	# chrome

	def _buildChrome(self):
		outer = QHBoxLayout(self)
		outer.setContentsMargins(0, 0, 0, 0)
		split = QSplitter(Qt.Orientation.Horizontal)
		outer.addWidget(split)
		split.addWidget(self.preview)

		side = QWidget()
		side.setMinimumWidth(400)
		side.setMaximumWidth(520)
		box = QVBoxLayout(side)
		box.setContentsMargins(8, 8, 8, 8)

		bar = QHBoxLayout()
		self.templates = QToolButton()
		self.templates.setText('Templates')
		self.templates.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
		self.templates.setMenu(self._templateMenu())
		bar.addWidget(self.templates)
		self.themeButton = QPushButton('Light')
		self.themeButton.setCheckable(True)
		self.themeButton.toggled.connect(self._setTheme)
		bar.addWidget(self.themeButton)
		reset = QPushButton('Reset')
		reset.setToolTip('Reload the current template and drop every change')
		reset.clicked.connect(self.resetAll)
		bar.addWidget(reset)
		bar.addStretch(1)
		box.addLayout(bar)

		bar3 = QHBoxLayout()
		self.undoButton = QPushButton('Undo')
		self.undoButton.setToolTip('Undo the last edit (Cmd+Z)')
		self.undoButton.clicked.connect(self.undo)
		self.redoButton = QPushButton('Redo')
		self.redoButton.setToolTip('Redo (Shift+Cmd+Z)')
		self.redoButton.clicked.connect(self.redo)
		self.handlesBox = QCheckBox('Handles')
		self.handlesBox.setChecked(True)
		self.handlesBox.setToolTip('Drag handles on the preview: angles, radius, weight, markers, zones, labels, anchor corner')
		self.handlesBox.toggled.connect(lambda on: self.layer.setEnabled(on))
		self.snapBox = QCheckBox('Snap')
		self.snapBox.setChecked(True)
		self.snapBox.setToolTip('Snap dragged values to round steps. Hold Shift while dragging for fine control.')
		self.snapBox.toggled.connect(lambda on: setattr(self.layer, 'snap', on))
		for w in (self.undoButton, self.redoButton, self.handlesBox, self.snapBox):
			bar3.addWidget(w)
		bar3.addStretch(1)
		box.addLayout(bar3)

		bar2 = QHBoxLayout()
		copy_ = QPushButton('Copy code')
		copy_.clicked.connect(self.copyCode)
		bar2.addWidget(copy_)
		save = QPushButton('Save as…')
		save.clicked.connect(self.saveAs)
		bar2.addWidget(save)
		bar2.addStretch(1)
		box.addLayout(bar2)

		self.status = QLabel('')
		self.status.setStyleSheet('color: #8b949e; font-size: 11px;')
		box.addWidget(self.status)

		self.search = QLineEdit()
		self.search.setPlaceholderText('Filter controls (arc, label, angle…)')
		self.search.setClearButtonEnabled(True)
		self.search.textChanged.connect(self._filter)
		box.addWidget(self.search)

		self.scroll = QScrollArea()
		self.scroll.setWidgetResizable(True)
		self.scroll.setFrameShape(QFrame.Shape.NoFrame)
		self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
		self.holder = QWidget()
		self.holderLayout = QVBoxLayout(self.holder)
		self.holderLayout.setContentsMargins(0, 0, 4, 0)
		self.holderLayout.setSpacing(2)
		self.holderLayout.addStretch(1)
		self.scroll.setWidget(self.holder)
		box.addWidget(self.scroll, 1)
		split.addWidget(side)
		split.setStretchFactor(0, 1)
		split.setStretchFactor(1, 0)
		split.setSizes([860, 460])

		self.valueSection = self._buildValueSection()
		self.stageSection = self._buildStageSection()
		self.tree: Optional[Section] = None

	def _templateMenu(self) -> QMenu:
		menu = QMenu(self)
		presets = menu.addMenu('Presets')
		for path in sorted(PRESET_DIR.glob('*.levity')):
			presets.addAction(path.stem.replace('-', ' '), lambda p=path: self.loadFile(p))
		showcase = menu.addMenu('Showcase')
		try:
			for label, entry in showcaseCells():
				showcase.addAction(label, lambda e=entry, l=label: self.loadEntry(e, l))
		except Exception as e:  # noqa: BLE001 - a missing showcase must not stop the studio
			showcase.addAction(f'unavailable: {e}').setEnabled(False)
		menu.addSeparator()
		menu.addAction('Open file…', self._openFile)
		return menu

	def _buildValueSection(self) -> Section:
		section = Section('Value', expanded=True)
		w = QWidget()
		g = QVBoxLayout(w)
		g.setContentsMargins(0, 0, 0, 0)
		row = QHBoxLayout()
		self.mode = QComboBox()
		self.mode.addItems(['Manual', 'Animate'])
		self.mode.currentTextChanged.connect(self._modeChanged)
		row.addWidget(QLabel('mode'))
		row.addWidget(self.mode, 1)
		g.addLayout(row)
		row = QHBoxLayout()
		self.data = QComboBox()
		self.data.addItems(list(DATA_PRESETS))
		self.data.activated.connect(lambda _: self._dataChanged())
		row.addWidget(QLabel('data  '))
		row.addWidget(self.data, 1)
		g.addLayout(row)
		row = QHBoxLayout()
		self.valueSlider = QSlider(Qt.Orientation.Horizontal)
		self.valueSlider.setRange(0, 1000)
		self.valueSlider.valueChanged.connect(self._sliderValue)
		self.valueSpin = QDoubleSpinBox()
		self.valueSpin.setRange(-1e6, 1e6)
		self.valueSpin.setDecimals(2)
		self.valueSpin.setKeyboardTracking(False)
		self.valueSpin.valueChanged.connect(self._spinValue)
		row.addWidget(QLabel('value'))
		row.addWidget(self.valueSlider, 1)
		row.addWidget(self.valueSpin)
		g.addLayout(row)
		grid = QGridLayout()
		self.period = QDoubleSpinBox()
		self.period.setRange(0.5, 60)
		self.period.setValue(4.0)
		self.period.setSuffix(' s')
		self.amplitude = QDoubleSpinBox()
		self.amplitude.setRange(1, 100)
		self.amplitude.setDecimals(0)
		self.amplitude.setValue(100)
		self.amplitude.setSuffix(' %')
		self.motion = QComboBox()
		self.motion.addItems(list(MOTIONS))
		grid.addWidget(QLabel('period'), 0, 0)
		grid.addWidget(self.period, 0, 1)
		grid.addWidget(QLabel('amplitude'), 0, 2)
		grid.addWidget(self.amplitude, 0, 3)
		grid.addWidget(QLabel('motion'), 1, 0)
		grid.addWidget(self.motion, 1, 1)
		g.addLayout(grid)
		section.addRow(w)
		self.holderLayout.insertWidget(self.holderLayout.count() - 1, section)
		return section

	def _buildStageSection(self) -> Section:
		section = Section('Stage', expanded=False)
		w = QWidget()
		g = QHBoxLayout(w)
		g.setContentsMargins(0, 0, 0, 0)
		self.stageCombo = QComboBox()
		self.stageCombo.addItems(list(STAGES))
		self.stageCombo.activated.connect(lambda _: self._stageChanged())
		g.addWidget(QLabel('size'))
		g.addWidget(self.stageCombo, 1)
		section.addRow(w)
		self.holderLayout.insertWidget(self.holderLayout.count() - 1, section)
		return section

	# loading

	def loadFile(self, path: Path):
		entries = readEntries(path)
		if not entries:
			self.status.setText(f'{path.name}: no realtime.gauge found')
			return
		self.fragment = path if self.fragment is None or path == self.fragment else self.fragment
		self.loadEntry(entries[0], path.stem.replace('-', ' '))

	def loadEntry(self, entry: dict, label: str):
		self.loadDisplay(copy.deepcopy(entry.get('display') or {}), entry.get('key'), label)

	def loadDisplay(self, display: dict, key: Optional[str], label: str):
		self.key = key
		self.label = label
		self.template = copy.deepcopy(display)
		preset = presetForKey(key)
		self.data.setCurrentText(preset.name)
		self.studio.value = preset.value
		self.studio.build(copy.deepcopy(display), preset)
		self._afterBuild()
		self.history, self.hpos = [], -1
		self._commit(self.exportDisplay())
		self.status.setText(f'{label} on {preset.name}')

	def resetAll(self):
		preset = DATA_PRESETS[self.data.currentText()]
		self.studio.value = preset.value
		self.studio.build(copy.deepcopy(self.template), preset)
		self._afterBuild()
		self._commit(self.exportDisplay())

	def _afterBuild(self):
		self.scene.invalidate()
		self.preview.viewport().update()
		self.preview.refit()
		self._rebuildPanel()
		self._syncValueControls()
		self.layer.rebuild()

	def _openFile(self):
		name, _ = QFileDialog.getOpenFileName(self, 'Open a .levity fragment', str(PRESET_DIR), 'Levity (*.levity *.yaml)')
		if name:
			self.loadFile(Path(name))

	# the controls

	def _read(self, path: tuple) -> Any:
		"""What a row shows for `path`. An unset range end shows the range the gauge is using."""
		value = schema.read(self.studio.gauge, path)
		if value is None and path in (('range', 'min'), ('range', 'max')):
			lo, hi = self.studio.range
			return lo if path[-1] == 'min' else hi
		return value

	def _applyContext(self):
		"""Tell the editors which unit and range the open gauge has."""
		editors.CONTEXT.unit = self.studio.preset.symbol
		for row in self.rows.values():
			row.onContext()

	def _applyRules(self):
		"""Hide the needle options the current needle type does not use."""
		kind = schema.read(self.studio.gauge, ('needle', 'type'))
		for row in self.rows.values():
			if row.field.types is not None:
				row.ruledOut = kind not in row.field.types
				row.setVisible(not row.ruledOut)

	def _rebuildPanel(self):
		gauge = self.studio.gauge
		group = schema.describe(gauge)
		if self.tree is not None and group == self._group:
			# The same controls as before (a data or stage change keeps them): show the new
			# values in the widgets that exist. Building the tree again costs about 100 ms.
			self._applyContext()
			for path, row in self.rows.items():
				value = self._read(path)
				row.baseline = schema.read(gauge, path)
				row.setSaved(value)
				row.setError(None)
				row.reset.setEnabled(False)
			self._applyRules()
			self._filter(self.search.text())
			return
		self._group = group
		open_paths = set()
		if self.tree is not None:
			open_paths = {s.path for s in self.tree.findChildren(Section) if s.header.isChecked()} | (
				{self.tree.path} if self.tree.header.isChecked() else set())
			self.tree.setParent(None)
			self.tree.deleteLater()
		self.rows = {}
		self.tree = build(group, self._read, self.rows, expanded=not open_paths or () in open_paths)
		for s in self.tree.findChildren(Section):
			if s.path in open_paths:
				s.setExpanded(True)
		for row in self.rows.values():
			row.edited.connect(self._edited)
		self.holderLayout.insertWidget(self.holderLayout.count() - 1, self.tree)
		self._applyContext()
		self._applyRules()
		self._filter(self.search.text())

	def _edited(self, path: tuple, value: Any):
		row = self.rows.get(path)
		if value is None and row is not None and row.field.kind not in ('text', 'yaml') and row.editor is None:
			return
		self.pending[path] = value
		self.flushTimer.start()

	def handleEdit(self, path: tuple, value: Any):
		"""A drag handle wrote `value` to the property at `path`."""
		self._edited(path, value)

	def beginDrag(self):
		self.dragActive = True
		self.settleTimer.stop()

	def endDrag(self, changed: bool):
		"""The mouse came up on a handle: apply what is waiting, rebuild the gauge from its saved form, record one undo step."""
		self.dragActive = False
		if self.pending or self.flushTimer.isActive():
			self.flushTimer.stop()
			self._flush()
		if changed:
			self.settleTimer.stop()
			self.settle()

	def setValueFromDrag(self, value: float):
		if self.mode.currentText() != 'Manual':
			self.mode.setCurrentText('Manual')
		self.setValue(value)

	def _flush(self):
		pending, self.pending = self.pending, {}
		gauge = self.studio.gauge
		for path, value in pending.items():
			reason = schema.write(gauge, path, value)
			row = self.rows.get(path)
			if row is not None:
				row.setError(reason)
				if reason is None and not row.isEditing():
					row.setSaved(self._read(path))
					row.reset.setEnabled(True)
		gauge.refresh()
		if ('needle', 'type') in pending:
			self._applyRules()
		self.scene.invalidate()
		self.preview.viewport().update()
		self.layer.refresh()
		self.syncTimer.start()
		self.settleTimer.start()

	def _dragging(self) -> bool:
		"""True while a mouse button is down (a slider is being dragged), a handle is held, or an edit waits to apply."""
		return self.dragActive or self.flushTimer.isActive() or QApplication.mouseButtons() != Qt.MouseButton.NoButton

	def _syncIdle(self):
		if self._dragging():
			self.syncTimer.start()
			return
		self.syncRows()

	def settle(self):
		"""Rebuild the gauge from its saved form. The controls keep what they show."""
		if self._dragging():
			self.settleTimer.start()
			return
		started = time.monotonic()
		display = self.exportDisplay()
		self.studio.build(display)
		self.scene.invalidate()
		self.preview.viewport().update()
		self.syncRows()
		self.layer.rebuild()
		self._commit(display)
		self.lastSettle = time.monotonic() - started

	# history

	def _commit(self, display: dict):
		"""Record the gauge's saved form as an undo step, unless nothing changed."""
		if 0 <= self.hpos < len(self.history) and self.history[self.hpos] == display:
			self._historyButtons()
			return
		del self.history[self.hpos + 1:]
		self.history.append(copy.deepcopy(display))
		del self.history[:-200]
		self.hpos = len(self.history) - 1
		self._historyButtons()

	def _historyButtons(self):
		self.undoButton.setEnabled(self.hpos > 0)
		self.redoButton.setEnabled(self.hpos < len(self.history) - 1)

	def undo(self):
		self._step(-1)

	def redo(self):
		self._step(1)

	def _step(self, by: int):
		target = self.hpos + by
		if self._dragging() or not 0 <= target < len(self.history):
			return
		self.settleTimer.stop()
		self.syncTimer.stop()
		self.hpos = target
		self.studio.build(copy.deepcopy(self.history[self.hpos]))
		self.scene.invalidate()
		self.preview.viewport().update()
		group = schema.describe(self.studio.gauge)
		if group == self._group:
			for row in self.rows.values():
				row.setError(None)
			self.syncRows()
			self._applyRules()
		else:
			self._rebuildPanel()
		self._syncValueControls(keepValue=True)
		self.layer.rebuild()
		self._historyButtons()
		self.status.setText(f'{"Undid" if by < 0 else "Redid"} to step {self.hpos + 1} of {len(self.history)}')

	def syncRows(self):
		"""Show what the gauge holds now. One edit can move others (a range change moves the ticks)."""
		gauge = self.studio.gauge
		for path, row in self.rows.items():
			if row.isEditing() or row.hasError():
				continue
			row.setSaved(self._read(path))
		self._applyRules()
		self._syncValueControls(keepValue=True)

	def _filter(self, text: str):
		if self.tree is not None:
			self.tree.setFiltered(text.strip().lower())

	# value

	def _syncValueControls(self, keepValue: bool = False):
		lo, hi = self.studio.range
		value = self.studio.value if keepValue else min(max(self.studio.value, lo), hi)
		for w in (self.valueSlider, self.valueSpin):
			w.blockSignals(True)
		self.valueSpin.setRange(lo, hi)
		self.valueSpin.setSingleStep((hi - lo) / 100 or 1)
		self.valueSpin.setValue(value)
		self.valueSlider.setValue(round((value - lo) / (hi - lo) * 1000) if hi > lo else 0)
		for w in (self.valueSlider, self.valueSpin):
			w.blockSignals(False)
		self.studio.setValue(value)

	def _sliderValue(self, pos: int):
		lo, hi = self.studio.range
		self.setValue(lo + pos / 1000 * (hi - lo))

	def _spinValue(self, value: float):
		self.setValue(value)

	def setValue(self, value: float):
		self.studio.setValue(value)
		if self.layer.shown:
			self.layer.reposition()
		self.valueSpin.blockSignals(True)
		self.valueSpin.setValue(value)
		self.valueSpin.blockSignals(False)
		lo, hi = self.studio.range
		self.valueSlider.blockSignals(True)
		self.valueSlider.setValue(round((value - lo) / (hi - lo) * 1000) if hi > lo else 0)
		self.valueSlider.blockSignals(False)

	def _modeChanged(self, mode: str):
		animate = mode == 'Animate'
		self.valueSlider.setEnabled(not animate)
		self.valueSpin.setEnabled(not animate)
		if animate:
			self.animStart = time.monotonic()
			self.animTimer.start()
		else:
			self.animTimer.stop()

	def _tick(self):
		lo, hi = self.studio.range
		phase = (time.monotonic() - self.animStart) / self.period.value()
		wave = MOTIONS[self.motion.currentText()](phase)
		self.setValue(lo + (hi - lo) * (0.5 + 0.5 * wave * self.amplitude.value() / 100))

	def _dataChanged(self):
		"""Swap the made-up data. The gauge keeps its settings and takes the new unit's range."""
		preset = DATA_PRESETS[self.data.currentText()]
		display = self.exportDisplay()
		display.pop('range', None)
		self.template.pop('range', None)
		self.key = preset.key
		self.studio.value = preset.value
		self.studio.build(display, preset)
		self._afterBuild()
		self._commit(self.exportDisplay())
		self.status.setText(f'{self.label} on {preset.name}')

	def _stageChanged(self):
		width, height = STAGES[self.stageCombo.currentText()]
		display = self.exportDisplay()
		self.scene.setSceneRect(QRectF(0, 0, width, height))
		self.studio.build(display)
		self._afterBuild()
		self._commit(self.exportDisplay())

	# export

	def exportDisplay(self) -> dict:
		"""The gauge's `display:` mapping: only what differs from the defaults."""
		gauge = self.studio.gauge
		text = yaml.dump(gauge.state, Dumper=StatefulDumper, default_flow_style=False, allow_unicode=True, sort_keys=False)
		display = yaml.safe_load(text) or {}
		for path in EXPORT_DROP:
			node = display
			for key in path[:-1]:
				node = node.get(key, {}) if isinstance(node, dict) else {}
			if isinstance(node, dict):
				node.pop(path[-1], None)
		display = _without(display, self._pristine())
		display = _expandSingles(display, gauge)
		return _plainNumbers(_pruned(display))

	def _pristine(self) -> dict:
		"""What a gauge with no settings dumps for this data: the noise to leave out of an export."""
		preset = self.studio.preset
		size = self.scene.sceneRect().size().toTuple()
		cache = self.__dict__.setdefault('_pristineCache', {})
		key = (preset.name, size)
		if key not in cache:
			previous = _stage._active
			scratch = StudioGauge(StudioScene(QGraphicsView()), preset)
			scratch.scene.setSceneRect(self.scene.sceneRect())
			scratch.build({}, preset)
			text = yaml.dump(scratch.gauge.state, Dumper=StatefulDumper, default_flow_style=False, allow_unicode=True, sort_keys=False)
			cache[key] = yaml.safe_load(text) or {}
			scratch.dispose()
			_stage._active = previous  # the scratch build claims the value sources; give them back
		return cache[key]

	def exportLevity(self) -> str:
		key = self.key or self.studio.preset.key
		entry = {'type': 'realtime.gauge', 'name': 'gauge', 'key': key, 'title': False, 'display': self.exportDisplay()}
		body = yaml.dump([entry], Dumper=StatefulDumper, default_flow_style=False, allow_unicode=True, sort_keys=False)
		return f'# Made with Gauge Studio ({self.label}).\n{body}'

	def copyCode(self):
		text = self.exportLevity()
		QApplication.clipboard().setText(text)
		self.status.setText(f'Copied {len(text.splitlines())} lines of .levity to the clipboard')

	def saveAs(self):
		name, _ = QFileDialog.getSaveFileName(self, 'Save the gauge as', 'gauge.levity', 'Levity (*.levity)')
		if name:
			Path(name).write_text(self.exportLevity(), encoding='utf-8')
			self.status.setText(f'Saved {name}')

	# file watch

	def _checkFile(self):
		try:
			mtime = self.fragment.stat().st_mtime
		except (OSError, AttributeError):
			return
		if mtime != self.fragmentMtime:
			self.fragmentMtime = mtime
			self.loadFile(self.fragment)
			self.status.setText(f'{self.fragment.name} changed on disk; reloaded')

	# theme

	def _setTheme(self, light: bool):
		self.themeButton.setText('Dark' if light else 'Light')
		app = QApplication.instance()
		palette = QPalette()
		if light:
			palette = app.style().standardPalette()
		else:
			palette.setColor(QPalette.ColorRole.Window, QColor('#161b22'))
			palette.setColor(QPalette.ColorRole.WindowText, QColor('#e6edf3'))
			palette.setColor(QPalette.ColorRole.Base, QColor('#0d1117'))
			palette.setColor(QPalette.ColorRole.AlternateBase, QColor('#161b22'))
			palette.setColor(QPalette.ColorRole.Text, QColor('#e6edf3'))
			palette.setColor(QPalette.ColorRole.Button, QColor('#21262d'))
			palette.setColor(QPalette.ColorRole.ButtonText, QColor('#e6edf3'))
			palette.setColor(QPalette.ColorRole.Highlight, QColor('#2f81f7'))
			palette.setColor(QPalette.ColorRole.HighlightedText, QColor('#ffffff'))
			palette.setColor(QPalette.ColorRole.PlaceholderText, QColor('#7d8590'))
			palette.setColor(QPalette.ColorRole.ToolTipBase, QColor('#21262d'))
			palette.setColor(QPalette.ColorRole.ToolTipText, QColor('#e6edf3'))
		app.setPalette(palette)


def main(argv: Optional[List[str]] = None) -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('fragment', nargs='?', help='a .levity fragment to open; reloaded when it changes on disk')
	args = parser.parse_args(argv)
	fragment = Path(args.fragment).expanduser().resolve() if args.fragment else None
	if fragment is not None and not fragment.exists():
		parser.error(f'no such file: {fragment}')
	app = QApplication.instance() or QApplication(sys.argv)
	app.setStyle('Fusion')
	window = Studio(fragment)
	window._setTheme(False)
	window.show()
	app.lastWindowClosed.connect(app.quit)
	return app.exec()


if __name__ == '__main__':
	raise SystemExit(main())

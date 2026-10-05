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
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _studio_env

_studio_env.prepare()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import yaml
from PySide6.QtCore import QEvent, QObject, QRectF, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPalette, QPen, QPixmap, QShortcut, QTransform
from PySide6.QtWidgets import (
	QApplication, QCheckBox, QPinchGesture, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGraphicsView, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
	QPushButton, QScrollArea, QSlider, QSpinBox, QSplitter, QToolButton, QVBoxLayout, QWidget,
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

STAGES = {'Card 320x240': (320, 240), '2x1 640x240': (640, 240), '2x2 640x480': (640, 480), 'Square 320x320': (320, 320), 'Custom': None}
STAGE_MIN, STAGE_MAX = 80, 1600
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


def identify(app: QApplication) -> None:
	"""Name the program and give it an icon, so the Dock and the window show Gauge Studio and not the Python rocket."""
	app.setApplicationName('Gauge Studio')
	app.setApplicationDisplayName('Gauge Studio')
	icon = QIcon(str(REPO / 'src' / 'LevityDash' / 'resources' / 'ui-elements' / 'icon512.png'))
	if icon.isNull():
		pixmap = QPixmap(256, 256)
		pixmap.fill(Qt.GlobalColor.transparent)
		painter = QPainter(pixmap)
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		painter.setPen(QPen(QColor('#2f81f7'), 22))
		painter.drawArc(QRectF(30, 30, 196, 196), 225 * 16, -270 * 16)
		painter.setPen(QPen(QColor('#e6edf3'), 14))
		painter.drawLine(128, 128, 178, 78)
		painter.end()
		icon = QIcon(pixmap)
	app.setWindowIcon(icon)


def _dpi() -> float:
	"""The dpi the dashboard turns a physical size (mm, in) into pixels with."""
	try:
		from LevityDash.lib.ui.Geometry import getDPI
		return float(getDPI())
	except Exception:  # noqa: BLE001
		return 100.0


# Section: themes
#
# Both themes set every colour role the widgets read, so no role falls back to the platform's
# own palette (a dark system gave the light theme a mixed palette). The sheet covers what a
# palette cannot reach: combo popups, tooltips, menus and disabled text.

THEMES = {
	'dark': {
		'window': '#161b22', 'text': '#e6edf3', 'base': '#0d1117', 'alt': '#161b22', 'button': '#21262d', 'highlight': '#2f81f7',
		'highlightText': '#ffffff', 'muted': '#8b949e', 'placeholder': '#7d8590', 'disabled': '#6e7681', 'border': '#30363d',
		'tipBase': '#21262d',
	},
	'light': {
		'window': '#f6f8fa', 'text': '#1f2328', 'base': '#ffffff', 'alt': '#eef0f3', 'button': '#e6e9ed', 'highlight': '#0969da',
		'highlightText': '#ffffff', 'muted': '#59636e', 'placeholder': '#6e7781', 'disabled': '#8c959f', 'border': '#d0d7de',
		'tipBase': '#ffffff',
	},
}


def themePalette(t: Dict[str, str]) -> QPalette:
	p = QPalette()
	Role, Group = QPalette.ColorRole, QPalette.ColorGroup
	for role, key in ((Role.Window, 'window'), (Role.WindowText, 'text'), (Role.Base, 'base'), (Role.AlternateBase, 'alt'),
	                  (Role.Text, 'text'), (Role.Button, 'button'), (Role.ButtonText, 'text'), (Role.Highlight, 'highlight'),
	                  (Role.HighlightedText, 'highlightText'), (Role.PlaceholderText, 'placeholder'), (Role.ToolTipBase, 'tipBase'),
	                  (Role.ToolTipText, 'text'), (Role.BrightText, 'text'), (Role.Link, 'highlight')):
		p.setColor(role, QColor(t[key]))
	for role in (Role.WindowText, Role.Text, Role.ButtonText):
		p.setColor(Group.Disabled, role, QColor(t['disabled']))
	p.setColor(Group.Disabled, Role.Base, QColor(t['alt']))
	p.setColor(Group.Disabled, Role.Button, QColor(t['window']))
	for role in (Role.Light, Role.Midlight, Role.Mid, Role.Dark, Role.Shadow):
		p.setColor(role, QColor(t['border']))
	return p


def themeSheet(t: Dict[str, str]) -> str:
	return f"""
QToolTip {{ color: {t['text']}; background-color: {t['tipBase']}; border: 1px solid {t['border']}; padding: 3px; }}
QComboBox QAbstractItemView, QCompleter QAbstractItemView {{ color: {t['text']}; background-color: {t['base']};
	selection-color: {t['highlightText']}; selection-background-color: {t['highlight']}; outline: 0; }}
QMenu {{ color: {t['text']}; background-color: {t['base']}; border: 1px solid {t['border']}; }}
QMenu::item:selected {{ color: {t['highlightText']}; background-color: {t['highlight']}; }}
QMenu::item:disabled {{ color: {t['disabled']}; }}
QToolButton {{ color: {t['text']}; }}
QToolButton:disabled, QLabel:disabled, QCheckBox:disabled {{ color: {t['disabled']}; }}
QLineEdit, QAbstractSpinBox {{ color: {t['text']}; background-color: {t['base']}; selection-color: {t['highlightText']};
	selection-background-color: {t['highlight']}; }}
QLineEdit:disabled, QAbstractSpinBox:disabled {{ color: {t['disabled']}; background-color: {t['alt']}; }}
"""


# Section: the preview

class Preview(QGraphicsView):
	"""The gauge scene on a dark stage, with a zoom that is only the view's transform.

	The gauge is laid out at the stage's real size in pixels. Zoom never changes that: it scales
	what the view draws. `fit` (the default) keeps the whole stage in view as the window or the
	stage changes. Ctrl or Cmd with the wheel, a trackpad pinch and the zoom slider switch it off.
	Drag empty stage, or use the scrollbars, to pan.
	"""

	zoomChanged = Signal(float)
	MARGIN = 24
	ZOOM_MIN, ZOOM_MAX = 0.25, 4.0

	def __init__(self):
		super().__init__()
		self.setBackgroundBrush(QColor('#0b0d10'))
		self.setFrameShape(QFrame.Shape.NoFrame)
		self.setRenderHints(self.renderHints() | self.renderHints().Antialiasing | self.renderHints().TextAntialiasing)
		self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
		self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
		self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
		self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
		self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
		self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
		self.setMinimumSize(320, 320)
		self.setMouseTracking(True)
		self.viewport().setMouseTracking(True)
		self.layer: Optional[HandleLayer] = None
		self.fitting = True
		self.viewport().grabGesture(Qt.GestureType.PinchGesture)

	@property
	def zoom(self) -> float:
		return self.transform().m11()

	def setZoom(self, zoom: float, fit: bool = False):
		"""Scale the view. `fit` keeps the stage fitted as things change."""
		self.fitting = fit
		zoom = min(max(zoom, self.ZOOM_MIN), self.ZOOM_MAX)
		self.setTransform(QTransform.fromScale(zoom, zoom))
		self.viewport().update()
		self.zoomChanged.emit(self.zoom)

	def fit(self):
		self.refit(force=True)

	def refit(self, force: bool = False):
		"""Fit the whole stage in the view, when fitting is on."""
		if self.scene() is None or not (self.fitting or force):
			return
		self.fitting = True
		rect = self.scene().sceneRect().adjusted(-self.MARGIN, -self.MARGIN, self.MARGIN, self.MARGIN)
		self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
		if not self.ZOOM_MIN <= self.zoom <= self.ZOOM_MAX:
			self.setZoom(self.zoom, fit=True)
		self.zoomChanged.emit(self.zoom)

	def wheelEvent(self, event):
		if event.modifiers() & Qt.KeyboardModifier.ControlModifier or event.modifiers() & Qt.KeyboardModifier.MetaModifier:
			delta = event.angleDelta().y() or event.pixelDelta().y()
			self.setZoom(self.zoom * 1.0015 ** delta)
			event.accept()
			return
		super().wheelEvent(event)

	def viewportEvent(self, event):
		if event.type() == QEvent.Type.NativeGesture and event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
			self.setZoom(self.zoom * (1 + event.value()))
			return True
		if event.type() == QEvent.Type.Gesture:
			pinch = event.gesture(Qt.GestureType.PinchGesture)
			if pinch is not None and pinch.changeFlags() & QPinchGesture.ChangeFlag.ScaleFactorChanged:
				self.setZoom(self.zoom * pinch.scaleFactor() / max(pinch.lastScaleFactor(), 1e-6))
				return True
		return super().viewportEvent(event)

	def enterEvent(self, event):
		super().enterEvent(event)
		if self.layer is not None:
			self.layer.setInside(True)

	def leaveEvent(self, event):
		super().leaveEvent(event)
		if self.layer is not None:
			self.layer.setInside(False)

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


class _UndoKeys(QObject):
	"""Keeps text fields from swallowing Undo and Redo."""

	def __init__(self, studio):
		super().__init__(studio)
		self.studio = studio

	def eventFilter(self, obj, event):
		if event.type() == QEvent.Type.ShortcutOverride and isinstance(obj, QWidget) and obj.window() is self.studio:
			if event.matches(QKeySequence.StandardKey.Undo) or event.matches(QKeySequence.StandardKey.Redo):
				event.ignore()
				return True
		return False


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
		# Each key sequence is bound once. On macOS the standard Undo key is Ctrl+Z in Qt's terms,
		# and two shortcuts on the same sequence make it ambiguous: neither fires.
		taken = set()
		for action, keys in ((self.undo, (QKeySequence.StandardKey.Undo, 'Ctrl+Z')),
		                     (self.redo, (QKeySequence.StandardKey.Redo, 'Ctrl+Shift+Z', 'Ctrl+Y'))):
			for key in keys:
				for seq in (QKeySequence.keyBindings(key) if isinstance(key, QKeySequence.StandardKey) else [QKeySequence(key)]):
					if seq.toString() in taken:
						continue
					taken.add(seq.toString())
					QShortcut(seq, self, activated=action).setContext(Qt.ShortcutContext.ApplicationShortcut)
		# A focused line edit or spinbox accepts the shortcut-override event for Undo and Redo and
		# keeps the keys for its own text history. The studio's undo covers every control, so the
		# filter lets the shortcut through.
		self._keys = _UndoKeys(self)
		QApplication.instance().installEventFilter(self._keys)
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
		side.setMinimumWidth(460)
		side.setMaximumWidth(720)
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
		self.status.setStyleSheet('color: palette(placeholder-text); font-size: 11px;')
		box.addWidget(self.status)

		self.search = QLineEdit()
		self.search.setPlaceholderText('Filter controls (arc, label, angle…)')
		self.search.setClearButtonEnabled(True)
		self.search.textChanged.connect(self._filter)
		box.addWidget(self.search)

		self.scroll = QScrollArea()
		self.scroll.setWidgetResizable(True)
		self.scroll.setFrameShape(QFrame.Shape.NoFrame)
		self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
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
		split.setSizes([820, 560])

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
		self.valueUnit = editors.UnitBox()
		row.addWidget(QLabel('value'))
		row.addWidget(self.valueSlider, 1)
		row.addWidget(self.valueSpin)
		row.addWidget(self.valueUnit)
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
		section = Section('Stage', expanded=True)
		w = QWidget()
		g = QGridLayout(w)
		g.setContentsMargins(0, 0, 0, 0)
		g.setColumnStretch(1, 1)
		self.stageCombo = QComboBox()
		self.stageCombo.addItems(list(STAGES))
		self.stageCombo.setToolTip('The gauge\'s real box in pixels. 320x240 is one cell of the 8x6 showcase grid at 2560x1440.')
		self.stageCombo.activated.connect(self._stagePicked)
		g.addWidget(QLabel('card'), 0, 0)
		g.addWidget(self.stageCombo, 0, 1, 1, 2)
		self.stageSize = {}
		for row, (name, value) in enumerate((('width', STAGES['Card 320x240'][0]), ('height', STAGES['Card 320x240'][1])), start=1):
			slide = QSlider(Qt.Orientation.Horizontal)
			slide.setRange(STAGE_MIN, STAGE_MAX)
			spin = QSpinBox()
			spin.setRange(STAGE_MIN, STAGE_MAX)
			spin.setSuffix(' px')
			spin.setKeyboardTracking(False)
			slide.setValue(value)
			spin.setValue(value)
			slide.valueChanged.connect(lambda v, s=spin: (s.blockSignals(True), s.setValue(v), s.blockSignals(False), self._stageEdited()))
			spin.valueChanged.connect(lambda v, s=slide: (s.blockSignals(True), s.setValue(v), s.blockSignals(False), self._stageEdited()))
			self.stageSize[name] = (slide, spin)
			g.addWidget(QLabel(name), row, 0)
			g.addWidget(slide, row, 1)
			g.addWidget(spin, row, 2)
		self.stageTimer = QTimer(self, singleShot=True, interval=120, timeout=self._stageChanged)
		self.zoomSlider = QSlider(Qt.Orientation.Horizontal)
		self.zoomSlider.setRange(25, 400)
		self.zoomSlider.setValue(100)
		self.zoomSlider.setToolTip('View zoom only. The gauge keeps its real size. Ctrl/Cmd+scroll or pinch also zoom; Ctrl+0 fits.')
		self.zoomSlider.valueChanged.connect(lambda v: self.preview.setZoom(v / 100))
		self.zoomLabel = QLabel('100%')
		self.zoomLabel.setMinimumWidth(48)
		g.addWidget(QLabel('zoom'), 3, 0)
		g.addWidget(self.zoomSlider, 3, 1)
		g.addWidget(self.zoomLabel, 3, 2)
		buttons = QHBoxLayout()
		fit = QPushButton('Fit')
		fit.clicked.connect(self.preview.fit)
		actual = QPushButton('100%')
		actual.setToolTip('Actual pixels')
		actual.clicked.connect(lambda: self.preview.setZoom(1.0))
		buttons.addWidget(fit)
		buttons.addWidget(actual)
		buttons.addStretch(1)
		g.addLayout(buttons, 4, 1, 1, 2)
		self.preview.zoomChanged.connect(self._zoomShown)
		QShortcut(QKeySequence('Ctrl+0'), self, activated=self.preview.fit)
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
		"""Back to the template, as one undoable step. What was on screen is recorded first."""
		self.commitPending()
		preset = DATA_PRESETS[self.data.currentText()]
		self.studio.value = preset.value
		self.studio.build(copy.deepcopy(self.template), preset)
		self._afterBuild()
		self._commit(self.exportDisplay())
		self.status.setText('Reset to the template. Undo brings back what was there.')

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
		ctx = editors.CONTEXT
		preset = self.studio.preset
		ctx.unit = preset.symbol
		ctx.units = preset.units
		if ctx.shown not in ctx.units:
			ctx.shown = preset.symbol
		ctx.refresh = self._unitChanged
		ctx.ref = self._sizeRef
		ctx.dpi = _dpi()
		self.valueUnit.sync()
		self.valueSpin.setSuffix('' if ctx.units else (f' {ctx.symbol()}' if ctx.symbol() else ''))
		self._syncValueControls(keepValue=True)
		for row in self.rows.values():
			row.onContext()

	def _unitChanged(self):
		"""A unit dropdown changed the unit numbers are shown in: redraw every control that shows one."""
		self._applyContext()

	def _sizeRef(self, kind: str = 'radius') -> float:
		"""Pixels that 100% means for a size: the dial's radius now, or (for the radius itself) the radius at 100%."""
		gauge = self.studio.gauge
		if gauge is None:
			return 100.0
		now = float(gauge.radius)
		if kind == 'radius':
			return now
		frac = schema.read(gauge, ('radius',))
		if isinstance(frac, str) and frac.strip().endswith('%'):
			try:
				return now / (float(frac.strip()[:-1]) / 100)
			except (ValueError, ZeroDivisionError):
				pass
		return min(self.scene.sceneRect().width(), self.scene.sceneRect().height()) / 2

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
		# Not `QApplication.mouseButtons()`: it can still report the button just after the release that ended a drag.
		return self.dragActive or self.flushTimer.isActive() or any(s.isSliderDown() for s in self.findChildren(QSlider))

	def commitPending(self):
		"""Apply any edit that is still waiting and record it, so the step that follows (undo, redo, reset) starts from what is on screen."""
		self.dragActive = False
		self.flushTimer.stop()
		if self.pending:
			self._flush()
		self.settleTimer.stop()
		self.syncTimer.stop()
		if self.studio.gauge is not None:
			self._commit(self.exportDisplay())

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
		if any(s.isSliderDown() for s in self.findChildren(QSlider)):
			return
		self.commitPending()
		target = self.hpos + by
		if not 0 <= target < len(self.history):
			return
		self.hpos = target
		self.studio.build(copy.deepcopy(self.history[self.hpos]))
		self.scene.invalidate()
		self.preview.viewport().update()
		group = schema.describe(self.studio.gauge)
		if group == self._group:
			for row in self.rows.values():
				row.setError(None)
			self.syncRows(force=True)
			self._applyRules()
		else:
			self._rebuildPanel()
		self._syncValueControls(keepValue=True)
		self.layer.rebuild()
		self._historyButtons()
		self.status.setText(f'{"Undid" if by < 0 else "Redid"} to step {self.hpos + 1} of {len(self.history)}')

	def syncRows(self, force: bool = False):
		"""Show what the gauge holds now. One edit can move others (a range change moves the ticks).

		`force` (undo, redo) also replaces the row that has focus: its text would otherwise keep the edit that was undone.
		"""
		gauge = self.studio.gauge
		for path, row in self.rows.items():
			if not force and (row.isEditing() or row.hasError()):
				continue
			row.setSaved(self._read(path))
			if force:
				row.reset.setEnabled(not schema._same(schema.read(gauge, path), row.baseline))
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
		shown = sorted(editors.CONTEXT.toShown(v) for v in (lo, hi))
		self.valueSpin.setRange(*shown)
		self.valueSpin.setSingleStep((shown[1] - shown[0]) / 100 or 1)
		self.valueSpin.setValue(editors.CONTEXT.toShown(value))
		self.valueSlider.setValue(round((value - lo) / (hi - lo) * 1000) if hi > lo else 0)
		for w in (self.valueSlider, self.valueSpin):
			w.blockSignals(False)
		self.studio.setValue(value)

	def _sliderValue(self, pos: int):
		lo, hi = self.studio.range
		self.setValue(lo + pos / 1000 * (hi - lo))

	def _spinValue(self, value: float):
		"""The value box shows the unit chosen in the unit dropdown; the gauge takes its own."""
		self.setValue(editors.CONTEXT.toNative(value))

	def setValue(self, value: float):
		self.studio.setValue(value)
		if self.layer.shown:
			self.layer.reposition()
		self.valueSpin.blockSignals(True)
		self.valueSpin.setValue(editors.CONTEXT.toShown(value))
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

	def _zoomShown(self, zoom: float):
		self.zoomLabel.setText(f'{zoom * 100:.0f}%')
		with QSignalBlocker(self.zoomSlider):
			self.zoomSlider.setValue(round(min(max(zoom * 100, 25), 400)))

	def _stagePicked(self, _=None):
		size = STAGES.get(self.stageCombo.currentText())
		if size is None:
			return
		for name, value in zip(('width', 'height'), size):
			for w in self.stageSize[name]:
				with QSignalBlocker(w):
					w.setValue(value)
		self._stageChanged()

	def _stageEdited(self):
		"""A width or height control moved: the card becomes Custom, and the gauge is laid out again once the input is quiet."""
		w, h = (self.stageSize[n][1].value() for n in ('width', 'height'))
		match = next((n for n, s in STAGES.items() if s == (w, h)), 'Custom')
		with QSignalBlocker(self.stageCombo):
			self.stageCombo.setCurrentText(match)
		self.stageTimer.start()

	def stageSizePx(self) -> Tuple[int, int]:
		return tuple(self.stageSize[n][1].value() for n in ('width', 'height'))

	def setStageSize(self, width: int, height: int):
		for name, value in (('width', width), ('height', height)):
			for w in self.stageSize[name]:
				with QSignalBlocker(w):
					w.setValue(value)
		self._stageEdited()
		self._stageChanged()

	def _stageChanged(self):
		"""Lay the gauge out again at the stage's real size. The saved form (and so the export) is unchanged."""
		self.stageTimer.stop()
		self.commitPending()
		width, height = self.stageSizePx()
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
		theme = THEMES['light' if light else 'dark']
		app = QApplication.instance()
		app.setPalette(themePalette(theme))
		app.setStyleSheet(themeSheet(theme))




def main(argv: Optional[List[str]] = None) -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('fragment', nargs='?', help='a .levity fragment to open; reloaded when it changes on disk')
	args = parser.parse_args(argv)
	fragment = Path(args.fragment).expanduser().resolve() if args.fragment else None
	if fragment is not None and not fragment.exists():
		parser.error(f'no such file: {fragment}')
	app = QApplication.instance() or QApplication(sys.argv)
	app.setStyle('Fusion')
	identify(app)
	window = Studio(fragment)
	window._setTheme(False)
	window.show()
	app.lastWindowClosed.connect(app.quit)
	# Quit through Qt on SIGTERM/SIGINT, so macOS drops the Dock tile. The timer wakes Python
	# so it can run the handlers while Qt's loop is busy.
	signal.signal(signal.SIGTERM, lambda *_: app.quit())
	signal.signal(signal.SIGINT, lambda *_: app.quit())
	wake = QTimer()
	wake.start(200)
	wake.timeout.connect(lambda: None)
	return app.exec()


if __name__ == '__main__':
	raise SystemExit(main())

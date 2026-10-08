"""Dev-only: the polar panel of Gauge Studio. Design one `type: polar` plot live, with controls.

    poetry run python src/LevityDash/devtools/gauge_studio.py --polar [fragment.levity]
    (or "Polar…" in the Gauge Studio toolbar)

The real `Polar` item on a `StudioScene`, drawn from made-up series: four days of hourly temperature,
dewpoint and wind around now, so every window (`today`, `24h`, `+24h`, `3d`) has something in it.
Nothing here starts the dashboard, a plugin or the backend; `feed.installStandIn` answers every plain
key from the made-up data, and an expression key (`temperature - dewpoint`) is evaluated over it by the
same `DerivedFeed` the dashboard uses.

The controls come from `StateProperty` introspection (`_studio_schema.describe`), as for the gauge: a
property added to `polar/item.py` shows up with no edit here, in a "More" section, until it is placed.
What this module adds is the part introspection cannot know: which settings belong to which plot, a
slider for every number (a discrete one for the sets `sectors`, `compass` and `span` take), and a
popover for a data key, which may be an expression.

Undo and redo (`Cmd+Z`, `Shift+Cmd+Z`) cover every edit; a slider drag is one step.
"""
import copy
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
import WeatherUnits as wu
from PySide6.QtCore import QEvent, QRectF, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
	QApplication, QComboBox, QFileDialog, QFrame, QGraphicsView, QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QPushButton,
	QScrollArea, QSizePolicy, QSlider, QSplitter, QToolButton, QVBoxLayout, QWidget,
)

from LevityDash.devtools import _studio_editors as editors
from LevityDash.devtools import _studio_schema as schema
from LevityDash.devtools._studio_stage import DATA_PRESETS, StudioScene, StudioStage
from LevityDash.devtools._studio_themes import ThemePicker
from LevityDash.devtools._studio_widgets import FieldRow, Section, fieldsOf
from LevityDash.lib.plugins.expressions import Expression, ExpressionError
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar import feed
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.item import Polar
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar.series import Series
from LevityDash.lib.utils.shared import now as localNow

__all__ = ['PolarStudio', 'StudioPolar', 'madeUpData', 'DATA_KEYS']

REPO = Path(__file__).resolve().parents[3]
PRESET_DIR = REPO / 'docs' / 'design-references' / 'presets'

STAGES = {'Square 480': (480, 480), 'Card 320x240': (320, 240), 'Wide 640x360': (640, 360), 'Tall 360x480': (360, 480)}
SETTLE_MS = 350

#: The settings each plot reads. `plot`, `window`, `beam` and `when` apply to all of them.
USED = {
	'rose': {'direction', 'speed', 'sectors', 'rings', 'max', 'compass', 'gradient', 'legend'},
	'trail': {'direction', 'speed', 'rings', 'max', 'compass', 'gradient', 'stamps'},
	'clock': {'key', 'rings', 'max', 'min', 'gradient', 'accent', 'span', 'top', 'smooth', 'marks'},
}
ALWAYS = {'plot', 'window', 'beam', 'when'}

#: Where each setting sits in the panel. A property not named here lands in "More".
SECTIONS = (
	('Plot', ('plot', 'window')),
	('Data', ('key', 'direction', 'speed')),
	('Scale', ('max', 'min', 'rings', 'sectors', 'compass', 'span', 'top')),
	('Look', ('gradient', 'accent', 'smooth', 'legend', 'marks', 'stamps')),
	('Panel', ('beam', 'when')),
)

#: What a plot reads when it has no key yet, so a change of plot draws something.
DEFAULT_KEYS = {
	'key': 'environment.temperature.temperature',
	'direction': 'environment.wind.direction.direction',
	'speed': 'environment.wind.speed.speed',
}
#: The feed a property opens, where the name differs.
FEEDS = {'key': 'value'}
NEEDS = {'rose': ('direction', 'speed'), 'trail': ('direction', 'speed'), 'clock': ('key',)}

STEPS = {'sectors': (4, 8, 12, 16, 24, 32), 'compass': (4, 8, 16), 'span': (12, 24)}
CHOICES = {'plot': ('rose', 'trail', 'clock'), 'top': ('noon', 'midnight')}
WINDOWS = ('today', '24h', '+24h', '3d')
#: Slider limits for the two numbers that mean a different thing in each plot (percent, speed, a reading).
LIMITS = {'max': (0.0, 100.0, 0.5), 'min': (-40.0, 100.0, 0.5)}
INTEGERS = {'rings': (1, 12), 'stamps': (0, 24)}


# Section: made-up data

_TEMPERATURE = [52, 51, 50, 49, 48, 48, 49, 52, 56, 60, 64, 67, 69, 70, 71, 71, 70, 68, 64, 60, 57, 55, 54, 53]
_DEWPOINT = [47, 47, 46, 46, 46, 45, 45, 46, 47, 48, 49, 49, 50, 50, 51, 52, 52, 52, 52, 51, 50, 50, 49, 48]
_DIRECTION = [318, 322, 330, 338, 345, 352, 4, 12, 20, 34, 52, 78, 102, 126, 148, 164, 176, 184, 190, 196, 204, 214, 226, 236]
_SPEED = [4, 3, 3, 5, 6, 8, 9, 10, 9, 8, 7, 9, 12, 15, 18, 21, 22, 19, 16, 14, 11, 9, 7, 6]
#: Day offset from today -> (degrees warmer, degrees of wind turned, wind scale): the days differ.
_DAYS = {-2: (-3, 40, 0.8), -1: (-1, -25, 1.1), 0: (0, 0, 1.0), 1: (2, 30, 0.9)}

DATA_KEYS = (
	'environment.temperature.temperature', 'environment.temperature.dewpoint',
	'environment.wind.direction.direction', 'environment.wind.speed.speed', 'environment.wind.speed.gust',
)


def _series(times, raw) -> Series:
	first = raw[0]
	return Series(times, [float(r) for r in raw], str(getattr(first, 'unit', '') or ''), None, type(first), raw)


def madeUpData(now=None) -> Dict[str, Series]:
	"""Hourly series for `DATA_KEYS` from two days ago to the end of tomorrow, in the local zone.

	`Series.now` is the last sample at or before `now`, as the live feed reports the current value.
	"""
	from datetime import timedelta
	now = now or localNow()
	midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
	times, columns = [], {key: [] for key in DATA_KEYS}
	for offset, (warmer, turn, scale) in _DAYS.items():
		for hour in range(24):
			times.append(midnight + timedelta(days=offset, hours=hour))
			columns['environment.temperature.temperature'].append(wu.Temperature.Fahrenheit(_TEMPERATURE[hour] + warmer))
			columns['environment.temperature.dewpoint'].append(wu.Temperature.Fahrenheit(_DEWPOINT[hour] + warmer * 0.5))
			columns['environment.wind.direction.direction'].append(wu.Direction((_DIRECTION[hour] + turn) % 360))
			columns['environment.wind.speed.speed'].append(wu.Wind.MilesPerHour(round(_SPEED[hour] * scale, 1)))
			columns['environment.wind.speed.gust'].append(wu.Wind.MilesPerHour(round(_SPEED[hour] * scale * 1.45, 1)))
	data = {key: _series(times, raw) for key, raw in columns.items()}
	for series in data.values():
		past = [v for t, v in zip(series.times, series.values) if t <= now]
		series.now = past[-1] if past else None
	return data


class _Input:
	"""What `feed.openFeed` gets back for a key in the studio: a series that does not change."""

	def __init__(self, key: str, series: Series):
		self.key = key
		self.series = series

	def close(self):
		pass


# Section: the stage

class StudioPolar:
	"""Builds one real `Polar` on a `StudioStage` from a `display:` mapping, over the made-up data."""

	def __init__(self, scene: StudioScene, install: bool = True):
		self.scene = scene
		self.stage: Optional[StudioStage] = None
		self.polar: Optional[Polar] = None
		self.data = madeUpData()
		self._good: Optional[dict] = None
		self.opener = lambda key, onChange: _Input(key, self.data.get(key, Series()))
		self.install = install
		if install:
			feed.installStandIn(self.opener)

	def build(self, display: Optional[dict]) -> Polar:
		"""Replace the plot with a new one. A mapping the plot rejects keeps the last one that built, and raises."""
		if self.install:
			feed.installStandIn(self.opener)  # another window may have taken it since this one last built
		view = self.scene.view
		saved = view.transform()
		view.resetTransform()  # an item built under a scaled view lays its text out doubled
		self.dispose()
		self.stage = StudioStage(self.scene, DATA_PRESETS['Generic 0-100'])
		display = copy.deepcopy(dict(display or {}))  # the loader edits the mappings it is given
		display.setdefault('geometry', {'x': 0, 'y': 0, 'width': 1, 'height': 1})
		try:
			with self.stage.action_pool:
				self.polar = Polar(parent=self.stage, **display)
		except Exception:
			view.setTransform(saved)
			self.dispose()
			good, self._good = self._good, None
			if good is not None:
				self.build(good)
			raise
		self._good = copy.deepcopy(display)
		self.polar.show()
		flags = self.polar.GraphicsItemFlag
		for flag in (flags.ItemIsMovable, flags.ItemIsSelectable, flags.ItemIsFocusable):
			self.polar.setFlag(flag, False)
		self.polar.resizeHandles.setEnabled(False)
		self.polar.resizeHandles.setVisible(False)
		self.polar.setAcceptHoverEvents(False)
		self.stage.setRect(self.scene.sceneRect())
		view.setTransform(saved)
		return self.polar

	def dispose(self) -> None:
		if self.polar is not None:
			try:
				self.polar.release()
			except Exception:  # noqa: BLE001 - a half-built item must not stop the next build
				pass
		if self.stage is not None and self.stage.scene() is not None:
			self.scene.removeItem(self.stage)
		self.stage = self.polar = None

	def render(self, size: Optional[tuple] = None) -> QImage:
		"""The scene as an image. For tests and screenshots."""
		rect = self.scene.sceneRect()
		w, h = size or (int(rect.width()), int(rect.height()))
		image = QImage(w, h, QImage.Format.Format_ARGB32)
		image.fill(ThemePicker.stageColor())
		painter = QPainter(image)
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		self.scene.render(painter, QRectF(image.rect()), rect)
		painter.end()
		return image

	def dataRange(self) -> tuple:
		"""The span of the series the plot colours by: speed for a rose or trail, the reading for a clock."""
		polar = self.polar
		if polar is None:
			return (0.0, 100.0)
		series = polar._series('value' if polar._plot == 'clock' else 'speed')
		return (min(series.values), max(series.values)) if len(series) else (0.0, 100.0)

	def valueClass(self):
		polar = self.polar
		return polar._series('value' if polar._plot == 'clock' else 'speed').cls if polar is not None else None


# Section: editors

class StepEdit(editors.Editor):
	"""A slider over a short list of allowed numbers, with the number beside it."""

	def __init__(self, values):
		super().__init__()
		self.values = list(values)
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		self.slider = QSlider(Qt.Orientation.Horizontal)
		self.slider.setRange(0, len(self.values) - 1)
		self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
		self.slider.setTickInterval(1)
		self.slider.setPageStep(1)
		self.label = QLabel('')
		self.label.setMinimumWidth(32)
		self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
		self.slider.valueChanged.connect(self._moved)
		box.addWidget(self.slider, 1)
		box.addWidget(self.label)

	def _moved(self, index: int):
		self.label.setText(str(self.values[index]))
		self._emit()

	def setValue(self, value):
		try:
			index = min(range(len(self.values)), key=lambda i: abs(self.values[i] - float(value)))
		except (TypeError, ValueError):
			index = 0
		with QSignalBlocker(self.slider):
			self.slider.setValue(index)
		self.label.setText(str(self.values[index]))

	def value(self):
		return self.values[self.slider.value()]

	def isEditing(self) -> bool:
		return self.slider.isSliderDown()


class _ExpressionForm(editors.Editor):
	"""The text of a key or an expression over keys, with the keys it reads checked as it is typed."""

	wide = True
	HINT = ('A key, or maths over keys: temperature - dewpoint, max(speed, 24h), speed * 0.868976, wind > 15mph. '
	        'It is worked out at every sample, so the plot gets a whole series.')

	def __init__(self):
		super().__init__()
		box = QVBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		self.text = QPlainTextEdit()
		self.text.setFixedHeight(64)
		self.text.setPlaceholderText('environment.temperature.temperature')
		self.text.textChanged.connect(self._check)
		self.text.installEventFilter(self)
		box.addWidget(self.text)
		row = QHBoxLayout()
		self.insert = QComboBox()
		self.insert.addItem('Insert a key…', None)
		for key in DATA_KEYS:
			self.insert.addItem(key, key)
		self.insert.activated.connect(self._insert)
		self.apply = QPushButton('Apply')
		self.apply.setToolTip('Apply (Cmd+Return, or click away)')
		self.apply.clicked.connect(self._apply)
		row.addWidget(self.insert, 1)
		row.addWidget(self.apply)
		box.addLayout(row)
		self.status = QLabel('')
		self.status.setWordWrap(True)
		box.addWidget(self.status)
		hint = QLabel(self.HINT)
		hint.setWordWrap(True)
		hint.setStyleSheet('color: palette(placeholder-text); font-size: 11px;')
		box.addWidget(hint)
		self._applied: Optional[str] = None

	def eventFilter(self, obj, event):
		if obj is self.text:
			if event.type() == QEvent.Type.FocusOut:
				self._apply()
			elif event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) \
					and event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
				self._apply()
				return True
		return super().eventFilter(obj, event)

	def _insert(self, index: int):
		key = self.insert.itemData(index)
		if key:
			self.text.insertPlainText(key)
			self.text.setFocus()
		self.insert.setCurrentIndex(0)

	def _apply(self):
		value = self.value()
		if value != self._applied:
			self._applied = value
			self.changed.emit(value)

	def _check(self):
		text = self.value()
		if text is None:
			self.status.setText('No key: nothing is drawn.')
			self.status.setStyleSheet(f'color: {editors.MUTED};')
			return
		try:
			expression = Expression.parse(text)
		except ExpressionError as error:
			self.status.setText(str(error))
			self.status.setStyleSheet('color: #e5484d;')
			return
		keys = sorted(str(k) for k in expression.inputKeys)
		unknown = [k for k in keys if k not in DATA_KEYS]
		kind = 'a key' if expression.plainKey is not None else 'an expression'
		note = f'{kind} reading {len(keys)} key{"" if len(keys) == 1 else "s"}: {", ".join(keys)}'
		if unknown:
			note += f'\nNo made-up data for {", ".join(unknown)}: it draws nothing here.'
		self.status.setText(note)
		self.status.setStyleSheet(f'color: {"#d29922" if unknown else editors.MUTED};')

	def setValue(self, value):
		text = '' if value is None else str(value)
		with QSignalBlocker(self.text):
			self.text.setPlainText(text)
		self._applied = text.strip() or None
		self._check()

	def value(self):
		return self.text.toPlainText().strip() or None

	def isEditing(self) -> bool:
		return self.text.hasFocus()


class ExpressionEdit(editors._Popover):
	"""A data key as a popover: the summary shows the text, the panel edits it."""

	title = 'Data key'

	def __init__(self):
		super().__init__(_ExpressionForm())

	def _tidy(self, value):
		return value or None

	def summary(self) -> str:
		text = ' '.join(str(self._value).split()) if self._value else ''
		if not text:
			return 'not set'
		return text if len(text) <= 44 else text[:43] + '…'


def _windowEdit(field) -> editors.Editor:
	return editors.ChoiceEdit([(w, w) for w in WINDOWS], editable=True)


def _numberEdit(field) -> editors.Editor:
	lo, hi, step = LIMITS[field.key]
	edit = editors.NumberEdit(autoText='auto', lo=lo, hi=hi, step=step, decimals=2)
	edit.spin.setRange(-1e5, 1e5)  # the slider covers the usual span and stretches to hold a value outside it
	return edit


editors.EXTRA.update({
	'polar-step': lambda field: StepEdit(STEPS[field.key]),
	'polar-window': _windowEdit,
	'polar-number': _numberEdit,
	'polar-key': lambda field: ExpressionEdit(),
})


def refine(group: schema.Group) -> Dict[str, schema.Field]:
	"""Give each polar field the control that fits it. Returns the fields by key."""
	found = {}
	for field in fieldsOf(group).values():
		key = field.key
		found[key] = field
		if key in CHOICES:
			field.kind, field.choices = 'choice', [(c, c) for c in CHOICES[key]]
		elif key in STEPS:
			field.kind = 'polar-step'
		elif key == 'window':
			field.kind = 'polar-window'
		elif key in LIMITS:
			field.kind = 'polar-number'
		elif key in DEFAULT_KEYS:
			field.kind = 'polar-key'
		elif key in INTEGERS:
			field.lo, field.hi = map(float, INTEGERS[key])
	return found


# Section: the preview

class _View(QGraphicsView):
	"""The stage, fitted to the window."""
	MARGIN = 24

	def __init__(self):
		super().__init__()
		self.setBackgroundBrush(ThemePicker.stageColor())
		self.setFrameShape(QFrame.Shape.NoFrame)
		self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
		self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
		self.setMinimumSize(320, 320)
		self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
		self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

	def refit(self):
		if self.scene() is not None:
			rect = self.scene().sceneRect().adjusted(-self.MARGIN, -self.MARGIN, self.MARGIN, self.MARGIN)
			self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

	def resizeEvent(self, event):
		super().resizeEvent(event)
		self.refit()


# Section: the window

class PolarStudio(QWidget):
	"""Preview on the left, controls on the right."""

	def __init__(self, fragment: Optional[Path] = None, standalone: bool = False):
		super().__init__()
		self.setWindowTitle('Gauge Studio: Polar')
		self.resize(1280, 860)
		self.view = _View()
		self.scene = StudioScene(self.view)
		self.scene.setSceneRect(QRectF(0, 0, *STAGES['Square 480']))
		self.view.setScene(self.scene)
		self.studio = StudioPolar(self.scene)
		self.rows: Dict[tuple, FieldRow] = {}
		self.sections: List[Section] = []
		self.fields: Dict[str, schema.Field] = {}
		self.history: List[dict] = []
		self.hpos = -1
		self.label = 'Default'
		self.display: dict = {'plot': 'rose', 'direction': DEFAULT_KEYS['direction'], 'speed': DEFAULT_KEYS['speed']}
		self.fragment = fragment
		self.fragmentMtime = fragment.stat().st_mtime if fragment else None
		self._pristine: Optional[Dict[str, Any]] = None
		self._buildChrome()
		self.settleTimer = QTimer(self, singleShot=True, interval=SETTLE_MS, timeout=self._remember)
		self.watchTimer = QTimer(self, interval=500, timeout=self._checkFile)
		taken = set()
		for action, keys in ((self.undo, (QKeySequence.StandardKey.Undo, 'Ctrl+Z')),
		                     (self.redo, (QKeySequence.StandardKey.Redo, 'Ctrl+Shift+Z', 'Ctrl+Y'))):
			for key in keys:
				for seq in (QKeySequence.keyBindings(key) if isinstance(key, QKeySequence.StandardKey) else [QKeySequence(key)]):
					if seq.toString() in taken:
						continue
					taken.add(seq.toString())
					QShortcut(seq, self, activated=action).setContext(Qt.ShortcutContext.WindowShortcut)
		self._installContext()
		if fragment is not None:
			self.loadFile(fragment)
			self.watchTimer.start()
		else:
			self.load(self.display, 'Default')

	# chrome

	def _buildChrome(self):
		outer = QHBoxLayout(self)
		outer.setContentsMargins(0, 0, 0, 0)
		split = QSplitter(Qt.Orientation.Horizontal)
		outer.addWidget(split)
		split.addWidget(self.view)
		side = QWidget()
		side.setMinimumWidth(520)
		side.setMaximumWidth(720)
		box = QVBoxLayout(side)
		box.setContentsMargins(8, 8, 8, 8)

		bar = QHBoxLayout()
		self.templates = QToolButton()
		self.templates.setText('Templates')
		self.templates.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
		self.templates.setMenu(self._templateMenu())
		bar.addWidget(self.templates)
		self.themePicker = ThemePicker()
		self.themePicker.picked.connect(self._themePicked)
		bar.addWidget(self.themePicker)
		self.stageBox = QComboBox()
		self.stageBox.setToolTip('Stage size in pixels')
		self.stageBox.addItems(STAGES)
		self.stageBox.activated.connect(self._stagePicked)
		bar.addWidget(self.stageBox)
		reset = QPushButton('Reset')
		reset.setToolTip('Reload the current template and drop every change')
		reset.clicked.connect(self.resetAll)
		bar.addWidget(reset)
		bar.addStretch(1)
		box.addLayout(bar)

		bar2 = QHBoxLayout()
		self.undoButton = QPushButton('Undo')
		self.undoButton.setToolTip('Undo the last edit (Cmd+Z)')
		self.undoButton.clicked.connect(self.undo)
		self.redoButton = QPushButton('Redo')
		self.redoButton.setToolTip('Redo (Shift+Cmd+Z)')
		self.redoButton.clicked.connect(self.redo)
		copy_ = QPushButton('Copy code')
		copy_.clicked.connect(self.copyCode)
		save = QPushButton('Save as…')
		save.clicked.connect(self.saveAs)
		for w in (self.undoButton, self.redoButton, copy_, save):
			bar2.addWidget(w)
		bar2.addStretch(1)
		box.addLayout(bar2)

		self.status = QLabel('')
		self.status.setWordWrap(True)
		self.status.setStyleSheet('color: palette(placeholder-text); font-size: 11px;')
		box.addWidget(self.status)
		self.dataLine = QLabel('')
		self.dataLine.setWordWrap(True)
		self.dataLine.setStyleSheet('color: palette(placeholder-text); font-size: 11px;')
		self.dataLine.setToolTip('Made-up data for: ' + ', '.join(DATA_KEYS))
		box.addWidget(self.dataLine)

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
		split.setSizes([700, 480])

	def _templateMenu(self) -> QMenu:
		menu = QMenu(self)
		for path in sorted(PRESET_DIR.glob('polar-*.levity')):
			menu.addAction(path.stem.replace('-', ' '), lambda p=path: self.loadFile(p))
		menu.addSeparator()
		menu.addAction('Open…', self._openFile)
		return menu

	def _installContext(self):
		"""Point the shared editor context at this plot. The gradient editor reads its range and unit from it."""
		ctx = editors.CONTEXT
		ctx.range = self.studio.dataRange
		ctx.span = self.studio.dataRange
		ctx.valueClass = self.studio.valueClass
		ctx.unit, ctx.shown, ctx.units = '', '', {}
		feed.installStandIn(self.studio.opener)

	def changeEvent(self, event):
		if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
			self._installContext()
		super().changeEvent(event)

	def closeEvent(self, event):
		if feed.standIn() is self.studio.opener:
			feed.installStandIn(None)
		self.studio.dispose()
		super().closeEvent(event)

	# loading

	def loadFile(self, path: Path):
		try:
			display = self._displayIn(yaml.safe_load(Path(path).read_text(encoding='utf-8')))
			if display is None:
				raise ValueError('it has no type: polar item')
			self.load(display, Path(path).stem.replace('-', ' '))
		except Exception as error:  # noqa: BLE001 - a bad file must not close the window
			self.status.setText(f'Could not load {Path(path).name}: {error}')

	@staticmethod
	def _displayIn(node: Any) -> dict:
		"""The settings of the first `type: polar` item in a document."""
		if isinstance(node, dict):
			if node.get('type') == 'polar':
				return {k: v for k, v in node.items() if k not in ('type', 'name', 'geometry')}
			for child in node.values():
				if (found := PolarStudio._displayIn(child)) is not None:
					return found
		elif isinstance(node, list):
			for child in node:
				if (found := PolarStudio._displayIn(child)) is not None:
					return found
		return {} if node is not None and not isinstance(node, (dict, list)) else None

	def load(self, display: Optional[dict], label: str):
		self.display = copy.deepcopy(display or {})
		self.label = label
		self.studio.build(self.display)
		self._buildRows()
		self.history, self.hpos = [], -1
		self._remember()
		self.status.setText(f'Loaded {label}')
		self._afterEdit()

	def resetAll(self):
		self.load(self.display, self.label)

	def _openFile(self):
		name, _ = QFileDialog.getOpenFileName(self, 'Open a polar plot', str(PRESET_DIR), 'Levity (*.levity)')
		if name:
			self.loadFile(Path(name))

	def _checkFile(self):
		try:
			mtime = self.fragment.stat().st_mtime
		except (OSError, AttributeError):
			return
		if mtime != self.fragmentMtime:
			self.fragmentMtime = mtime
			self.loadFile(self.fragment)
			self.status.setText(f'{self.fragment.name} changed on disk; reloaded')

	# rows

	@property
	def polar(self) -> Polar:
		return self.studio.polar

	def _buildRows(self):
		for section in self.sections:
			section.setParent(None)
			section.deleteLater()
		self.sections, self.rows = [], {}
		self.fields = refine(schema.describe(self.polar, title='Polar'))
		placed = set()
		layout = [*SECTIONS]
		extra = tuple(k for k in self.fields if not any(k in keys for _, keys in SECTIONS))
		if extra:
			layout.append(('More', extra))
		for title, keys in layout:
			section = Section(title, expanded=title != 'Panel')
			section.keys = keys
			for key in keys:
				field = self.fields.get(key)
				if field is None:
					continue
				row = FieldRow(field, schema.read(self.polar, field.path))
				row.edited.connect(self._edited)
				self.rows[field.path] = row
				section.addRow(row)
				placed.add(key)
			if section._row:
				self.holderLayout.insertWidget(len(self.sections), section)
				self.sections.append(section)
			else:
				section.deleteLater()
		self._applyRules()

	def _applyRules(self):
		"""Show the settings the current plot reads."""
		plot = self.polar._plot
		for path, row in self.rows.items():
			key = path[-1]
			known = key in ALWAYS or any(key in used for used in USED.values())
			row.ruledOut = known and key not in ALWAYS and key not in USED[plot]
			row.setVisible(not row.ruledOut)
		for section in self.sections:
			section.setVisible(any(not self.rows[(k,)].ruledOut for k in section.keys if (k,) in self.rows))

	def syncRows(self):
		for path, row in self.rows.items():
			if row.isEditing() or row.hasError():
				continue
			saved = schema.read(self.polar, path)
			row.setSaved(saved)
			row.reset.setEnabled(not schema._same(saved, row.baseline))
		self._applyRules()

	# editing

	def _edited(self, path: tuple, value: Any):
		row = self.rows.get(path)
		reason = self._invalid(path, value) or schema.write(self.polar, path, value)
		if row is not None:
			row.setError(reason)
		if reason is not None:
			return
		if path == ('plot',):
			self._fillKeys()
			self.syncRows()
		self._afterEdit()

	def _invalid(self, path: tuple, value: Any) -> Optional[str]:
		"""Why the plot's own decoder refuses `value`, or None. `schema.write` sets the raw value, which a file load would have decoded first."""
		prop = schema.findProp(self.polar, path[-1])
		if prop is None or value is None:
			return None
		try:
			prop.decodeValue(value, self.polar)
		except Exception as error:  # noqa: BLE001 - whatever the decoder says is the reason
			return str(error) or type(error).__name__
		return None

	def _fillKeys(self):
		"""A plot that reads a key it has none for gets the made-up one, so a change of plot draws something."""
		for key in NEEDS[self.polar._plot]:
			if schema.read(self.polar, (key,)) is None and (key,) in self.rows:
				schema.write(self.polar, (key,), DEFAULT_KEYS[key])
				self.rows[(key,)].setSaved(DEFAULT_KEYS[key])

	def _afterEdit(self):
		self.settleTimer.start()
		self._reportData()
		self.scene.update()

	def _reportData(self):
		polar = self.polar
		parts = []
		for name, text in polar._feedText.items():
			count = len(polar._series(name))
			parts.append(f'{name}: {count} samples' if count else f'{name}: no samples for {text!r}')
		for prop in NEEDS[polar._plot]:
			name, text = FEEDS.get(prop, prop), getattr(polar, f'_{prop}')
			if text and name not in polar._feedText:
				parts.append(f'{name}: could not open {text!r}')
		self.dataLine.setText('Data: ' + ('; '.join(parts) if parts else 'no key set'))

	# history

	def _snapshot(self) -> Dict[tuple, Any]:
		return {path: schema.read(self.polar, path) for path in self.rows}

	def _remember(self):
		snap = self._snapshot()
		if self.hpos >= 0 and snap == self.history[self.hpos]:
			return
		del self.history[self.hpos + 1:]
		self.history.append(snap)
		self.hpos = len(self.history) - 1
		self._historyButtons()

	def _historyButtons(self):
		self.undoButton.setEnabled(self.hpos > 0)
		self.redoButton.setEnabled(self.hpos < len(self.history) - 1)

	def _step(self, by: int):
		self.settleTimer.stop()
		self._remember()
		target = self.hpos + by
		if not 0 <= target < len(self.history):
			return
		self.hpos = target
		for path, value in self.history[target].items():
			if not schema._same(schema.read(self.polar, path), value):
				schema.write(self.polar, path, value)
		for row in self.rows.values():
			row.setError(None)
		for path, row in self.rows.items():
			row.setSaved(schema.read(self.polar, path))
			row.reset.setEnabled(not schema._same(schema.read(self.polar, path), row.baseline))
		self._applyRules()
		self._historyButtons()
		self._reportData()

	def undo(self):
		self._step(-1)

	def redo(self):
		self._step(+1)

	# stage and theme

	def _stagePicked(self, _=None):
		width, height = STAGES[self.stageBox.currentText()]
		self.setStageSize(width, height)

	def setStageSize(self, width: int, height: int):
		self.settleTimer.stop()
		display = self.exportDisplay()
		self.scene.setSceneRect(QRectF(0, 0, width, height))
		self.studio.build(display)
		self.view.refit()
		self._afterRebuild()

	def _themePicked(self, name: str):
		"""Draw the plot in another colour theme: the stage takes its ground and the plot is built again from its saved form."""
		self.settleTimer.stop()
		self.view.setBackgroundBrush(ThemePicker.stageColor())
		self.studio.build(self.exportDisplay())
		self._afterRebuild()
		self.status.setText(f'Drawn in the {name} theme')

	def _afterRebuild(self):
		for row in self.rows.values():
			row.setError(None)
		self.syncRows()
		self._afterEdit()

	# export

	def _defaults(self) -> Dict[str, Any]:
		"""What a plot with no settings holds, for each setting: the noise to leave out of an export."""
		if self._pristine is None:
			scratch = StudioPolar(StudioScene(QGraphicsView()), install=False)
			scratch.build({})
			self._pristine = {path[-1]: schema.read(scratch.polar, path) for path in self.rows}
			scratch.dispose()
		return self._pristine

	def exportDisplay(self) -> dict:
		"""The plot's settings that differ from the defaults, as a `.levity` item holds them."""
		defaults = self._defaults()
		display, plot = {}, self.polar._plot
		for path in self.rows:
			key = path[-1]
			value = schema.read(self.polar, path)
			if value is None or key == 'plot' or (key not in ALWAYS and key not in USED[plot] and any(key in u for u in USED.values())):
				continue
			if not schema._same(value, defaults.get(key)):
				display[key] = value
		return {'plot': self.polar._plot, **display}

	def exportLevity(self) -> str:
		entry = {'type': 'polar', 'name': 'polar', **self.exportDisplay()}
		body = yaml.dump([entry], Dumper=schema.StudioDumper, default_flow_style=False, allow_unicode=True, sort_keys=False)
		return f'# Made with Gauge Studio ({self.label}).\n{body}'

	def copyCode(self):
		text = self.exportLevity()
		QApplication.clipboard().setText(text)
		self.status.setText(f'Copied {len(text.splitlines())} lines of .levity to the clipboard')

	def saveAs(self):
		name, _ = QFileDialog.getSaveFileName(self, 'Save the plot as', 'polar.levity', 'Levity (*.levity)')
		if name:
			Path(name).write_text(self.exportLevity(), encoding='utf-8')
			self.status.setText(f'Saved {name}')

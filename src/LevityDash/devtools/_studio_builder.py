"""Dev-only: the Studio builder. Compose an item from sub-items, give it properties, preview it, save it.

    poetry run python src/LevityDash/devtools/gauge_studio.py --build [preset.yaml] [--scenario NAME]

The gauge editor edits one display. The builder edits a *preset*: a template of items (containers and
displays) plus the properties the template exposes. It writes the format in `_studio_preset.py`
(`props:` and `template:`) and an instance stores only what differs from the preset's defaults.

- Left: the template as a tree. Add, duplicate, delete and reorder items.
- Middle: the preview, a real dashboard drawn offscreen on the Fixture scenario's data. Click an item to select
  it; drag it, or drag a corner, to set its geometry (a share of its parent).
- Right, four tabs.
  Item: the selected item's fields. Each field has a `$` button that binds it to a preset property.
  Properties: the preset's own properties: name, type, default, limits.
  Instance: a value for every property, drawn live, and the few lines a dashboard would store.
  YAML: the preset file as saved, and what the dashboard sees once expanded.

Every number has a slider; a size has a unit selector. Text is fitted by the dashboard against its format hint,
never against the live value, so a preview with a different value changes no layout.

Like the gauge editor, this never reads or writes the real config: the dashboard it draws on is a disposable
copy of `devtools/design-seed`.
"""
import copy
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml
from PySide6.QtCore import QPointF, QRectF, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
	QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu,
	QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QTabWidget, QToolButton, QTreeWidget, QTreeWidgetItem,
	QVBoxLayout, QWidget,
)

from LevityDash.devtools import _studio_editors as editors
from LevityDash.devtools import _studio_layout as layout
from LevityDash.lib import presets as lib
from LevityDash.devtools import _studio_preset as model
from LevityDash.devtools import _studio_state as state
from LevityDash.devtools._studio_stage import presetForKey
from LevityDash.devtools._studio_chrome import THEMES, themePalette, themeSheet
from LevityDash.devtools._studio_themes import ThemePicker
from LevityDash.devtools._studio_widgets import Section

Editor = editors.Editor
REPO = Path(__file__).resolve().parents[3]

CONTAINERS = ['group', 'stack', 'grid', 'value-stack', 'titled-group', 'switch']
DISPLAYS = ['realtime.text', 'realtime.gauge', 'realtime.bar', 'text', 'label', 'graph', 'mini-graph', 'polar', 'clock', 'moon', 'spacer']
LAYOUT_PARENTS = ('stack', 'value-stack', 'grid', 'switch')
STAGES = {'Card 640x400': (640, 400), 'Wide 960x400': (960, 400), 'Tall 400x640': (400, 640), 'Board 1280x800': (1280, 800)}
SETTLE_MS = 350

#: The fields the Item tab edits, in order: (field, label, kind). `kind` picks the editor and the property type a `$` binds to.
GEOMETRY = [('geometry.x', 'x', 'w'), ('geometry.y', 'y', 'h'), ('geometry.width', 'width', 'w'), ('geometry.height', 'height', 'h')]
BINDABLE = {
	'display.range.min': ('any', ('number', 'any')), 'display.range.max': ('any', ('number', 'any')),
	'display.arc.gradient': ('text', ('text', 'color')),
	'key': ('key', ('key', 'text')), 'text': ('text', ('text', 'key')), 'color': ('color', ('color', 'text')),
	'direction': ('text', ('text',)), 'spacing': ('size', ('size',)),
	**{f: ('size', ('size',)) for f, _, _ in GEOMETRY},
}


#: Fields the Item tab has a control for. Everything else an item holds goes to the "more properties" popover.
OWNED = {'type', model.PRESET_KEY, 'name', 'key', 'text', 'color', 'direction', 'spacing', 'flex', 'grid', 'when', model.ITEMS_KEY}
OWNED_PATHS = ['geometry.x', 'geometry.y', 'geometry.width', 'geometry.height', 'display.range.min', 'display.range.max', 'display.arc.gradient']


#: What a new property of each type starts as.
PROP_DEFAULTS = {'number': 50, 'size': '50%', 'text': 'text', 'color': '#2f81f7', 'key': 'environment.temperature.temperature', 'bool': True, 'any': []}
#: What a property made from an unset field starts as.
FIELD_DEFAULTS = {'display.arc.gradient': '$temperature', 'display.range.min': 0, 'display.range.max': 100}


def restOf(node: dict) -> dict:
	"""The node without the fields the Item tab owns."""
	rest = {k: copy.deepcopy(v) for k, v in node.items() if k not in OWNED}
	for path in OWNED_PATHS:
		if model.getField(rest, path) is not None:
			model.setField(rest, path, None)
	return rest


def newItem(kind: str, parentType: str, n: int) -> dict:
	"""A fresh item of `kind`, ready to see on the stage."""
	if kind.startswith('preset:'):
		item = {model.PRESET_KEY: kind.split(':', 1)[1]}
		if parentType not in LAYOUT_PARENTS:
			item['geometry'] = {'x': '4%', 'y': '4%', 'width': '44%', 'height': '44%'}
		return item
	item: Dict[str, Any] = {'type': kind}
	if kind in ('realtime.text', 'realtime.gauge', 'realtime.bar', 'graph', 'mini-graph'):
		item['key'] = 'environment.temperature.temperature'
	elif kind in ('text', 'label'):
		item['text'] = 'Label'
	if kind == 'realtime.bar':
		# A bar with no fill draws only its track.
		item['title'] = False
		item['display'] = {'range': {'min': 0, 'max': 100}, 'fill': {'color': '$accent'}}
	elif kind in ('stack', 'value-stack'):
		item['direction'] = 'Vertical'
		item['items'] = []
	elif kind in ('group', 'titled-group', 'switch', 'grid'):
		item['items'] = []
	if parentType not in LAYOUT_PARENTS and kind != 'spacer':
		off = 8 * (n % 5)
		item['geometry'] = {'x': f'{4 + off}%', 'y': f'{4 + off}%', 'width': '44%', 'height': '44%'}
	return item


# Section: small editors the shared set lacks

class TextEdit(Editor):
	def __init__(self, placeholder: str = ''):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		self.line = QLineEdit()
		self.line.setPlaceholderText(placeholder)
		self.line.editingFinished.connect(self._emit)
		box.addWidget(self.line, 1)

	def setValue(self, value):
		with QSignalBlocker(self.line):
			self.line.setText('' if value is None else str(value))

	def value(self):
		return self.line.text() or None

	def isEditing(self) -> bool:
		return self.line.hasFocus()


class BoolEdit(Editor):
	def __init__(self):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		self.check = QCheckBox()
		self.check.toggled.connect(self._emit)
		box.addWidget(self.check)
		box.addStretch(1)

	def setValue(self, value):
		with QSignalBlocker(self.check):
			self.check.setChecked(bool(value))

	def value(self):
		return self.check.isChecked()


_MEASURED = re.compile(r'^\s*(-?\d+(?:\.\d+)?)\s*(.*?)\s*$')


class MeasuredEdit(Editor):
	"""A number on a data key's scale, with the unit selector the key allows.

	With no unit chosen it writes a bare number, which the gauge reads in the unit it shows. With one chosen it writes
	`32\u00b0F`, which it converts, so the file says what it means.
	"""

	def __init__(self, key: Optional[str] = None):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		self.number = numberEdit(0)
		self.number.changed.connect(self._emit)
		self.unit = QComboBox()
		self.unit.setToolTip('The unit this number is in. "as shown" is a bare number, read in the unit the display shows.')
		self.unit.activated.connect(self._emit)
		box.addWidget(self.number, 1)
		box.addWidget(self.unit)
		self.setKey(key)

	def setKey(self, key: Optional[str]):
		current = self.unit.currentData()
		names = list(presetForKey(key if isinstance(key, str) and '$' not in key else None).units)
		with QSignalBlocker(self.unit):
			self.unit.clear()
			self.unit.addItem('as shown', '')
			for name in names:
				self.unit.addItem(name, name)
			i = self.unit.findData(current or '')
			self.unit.setCurrentIndex(max(i, 0))
		self.unit.setVisible(bool(names))

	def setValue(self, value):
		text = '' if value is None else str(value)
		m = _MEASURED.match(text)
		if not m:
			return
		self.number.setValue(float(m.group(1)))
		unit = m.group(2)
		with QSignalBlocker(self.unit):
			i = self.unit.findData(unit)
			if i < 0 and unit:
				self.unit.addItem(unit, unit)
				i = self.unit.findData(unit)
			self.unit.setCurrentIndex(max(i, 0))
			self.unit.setVisible(self.unit.count() > 1)

	def value(self):
		n = self.number.value()
		unit = self.unit.currentData()
		return f'{n:g}{unit}' if unit else n

	def isEditing(self) -> bool:
		return self.number.isEditing()


class AnyEdit(Editor):
	"""A value that is a list or a mapping (zones, a gradient), as one line of flow YAML, checked as you type."""

	def __init__(self):
		super().__init__()
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		self.line = QLineEdit()
		self.line.setPlaceholderText('[{from: 0, to: 20, color: $bad}]')
		self.line.editingFinished.connect(self._done)
		box.addWidget(self.line, 1)
		self._value: Any = None

	def _done(self):
		try:
			value = yaml.safe_load(self.line.text())
		except yaml.YAMLError:
			self.line.setStyleSheet('color: #e5484d;')
			return
		self.line.setStyleSheet('')
		self._value = value
		self.changed.emit(value)

	def setValue(self, value):
		self._value = value
		with QSignalBlocker(self.line):
			self.line.setText('' if value is None else yaml.safe_dump(value, default_flow_style=True, width=10000).strip().removesuffix('...').strip())
			self.line.setStyleSheet('')

	def value(self):
		return self._value

	def isEditing(self) -> bool:
		return self.line.hasFocus()


class YamlForm(Editor):
	"""The fields an item has that the Item tab has no control for, as YAML, checked as you type."""

	def __init__(self):
		super().__init__()
		box = QVBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		self.edit = QPlainTextEdit()
		self.edit.setMinimumHeight(180)
		self.edit.setPlaceholderText('display:\n  range: {min: 0, max: 100}')
		self.error = QLabel()
		self.error.setWordWrap(True)
		self.error.setStyleSheet('color: #e5484d; font-size: 11px;')
		self.error.setVisible(False)
		self.timer = QTimer(self)
		self.timer.setSingleShot(True)
		self.timer.setInterval(500)
		self.timer.timeout.connect(self._parse)
		self.edit.textChanged.connect(self.timer.start)
		box.addWidget(self.edit)
		box.addWidget(self.error)
		self._data: dict = {}
		self.setMinimumWidth(380)

	def setValue(self, value):
		self._data = value or {}
		with QSignalBlocker(self.edit):
			self.edit.setPlainText(yaml.safe_dump(self._data, sort_keys=False, allow_unicode=True) if self._data else '')
		self.error.setVisible(False)

	def value(self):
		return self._data or None

	def _parse(self):
		try:
			data = yaml.safe_load(self.edit.toPlainText()) or {}
			if not isinstance(data, dict):
				raise ValueError('the top level must be a mapping')
		except (yaml.YAMLError, ValueError) as e:
			self.error.setText(str(e).splitlines()[0] if str(e) else 'not valid YAML')
			self.error.setVisible(True)
			return
		self.error.setVisible(False)
		self._data = data
		self.changed.emit(self.value())

	def isEditing(self) -> bool:
		return self.edit.hasFocus()


class MoreEdit(editors._Popover):
	"""`More properties…` as a popover: everything an item holds that has no control of its own."""

	title = 'More properties'

	def __init__(self):
		super().__init__(YamlForm())

	def summary(self) -> str:
		n = len(self._value or {})
		return f'More properties: {n} set' if n else 'More properties: none'


def numberEdit(value: Any = 0, lo: Optional[float] = None, hi: Optional[float] = None, **kw) -> 'editors.NumberEdit':
	"""A number with a slider. The slider spans the limits when there are some, else a stretch around `value`; the box takes any number inside the limits."""
	v = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0
	low = lo if lo is not None else min(0.0, v * 2)
	high = hi if hi is not None else max(100.0, v * 2)
	edit = editors.NumberEdit(lo=-1e5, hi=1e5, step=max(round((high - low) / 100, 2), 0.01), decimals=3, **kw)
	edit.spin.setRange(lo if lo is not None else -1e5, hi if hi is not None else 1e5)
	edit.lo, edit.hi = low, high
	edit._fitSlider()
	return edit


def editorFor(kind: str, spec: Optional[model.PropSpec] = None, ref: str = 'w', measured: Optional[str] = None) -> Editor:
	"""The editor for a value of `kind`. A number and a size carry a slider; a size also carries its unit."""
	if measured is not None and kind in ('number', 'any'):
		return MeasuredEdit(measured)
	if kind == 'number':
		default = spec.default if spec else 0
		return numberEdit(default, spec.lo if spec else None, spec.hi if spec else None)
	if kind == 'size':
		return editors.SizeEdit(nullable=True, autoText='unset', ref=ref if ref in ('w', 'h') else 'full')
	if kind == 'color':
		return editors.ColorEdit()
	if kind == 'key':
		return editors.KeyEdit()
	if kind == 'bool':
		return BoolEdit()
	if kind == 'any':
		return AnyEdit()
	return TextEdit()


def _label(text: str, tip: str = '') -> QLabel:
	label = QLabel(text)
	label.setToolTip(tip)
	label.setMinimumWidth(70)
	return label


# Section: the preview

def scenarioKeys(name: str) -> List[str]:
	"""The keys a Fixture scenario supplies, so the key menus offer them (rooms included: `...#bedroom`)."""
	path = Path(name)
	if not path.suffix:
		path = REPO / 'docs' / 'design-references' / 'scenarios' / f'{name}.yaml'
	try:
		return [str(k) for k in (yaml.safe_load(path.read_text()) or {}).get('keys', {})]
	except (OSError, yaml.YAMLError, AttributeError):
		return []


class PreviewEngine:
	"""One dashboard, booted once offscreen on the Fixture scenario, that every preview loads into.

	Boot costs seconds; a load costs about one. The dashboard is `devtools/design-seed` copied to a temp
	directory, so nothing here reads or writes a real config.
	"""

	def __init__(self, size: Tuple[int, int]):
		from LevityDash.devtools import _boot
		self._boot = _boot
		self.size = size
		# Boot on an empty board: the seed's own dashboard draws graphs that are still working when the first preview replaces them.
		blank = Path(tempfile.mkdtemp(prefix='levity-builder-')) / 'blank.levity'
		blank.write_text('- type: group\n  name: blank\n')
		self.app, self.dashboard = _boot.boot(levity=str(blank), size=size, settle=2.0, freeze=_boot.FROZEN_TIME)
		panel = self.dashboard.CENTRAL_PANEL
		self.directory = Path(panel.filePath.path).parent
		self.panel = panel
		self.error = ''
		self.scenario = os.environ.get('LEVITYDASH_FIXTURE', '')
		editors.knownKeys()
		editors._keyCache[:] = sorted(set(editors._keyCache) | set(scenarioKeys(self.scenario)))

	def resize(self, size: Tuple[int, int]):
		if size != self.size:
			self.size = size
			self._boot.resizeScene(self.app, size)

	def render(self, items: List[dict], names: Dict[str, tuple]) -> Tuple[QImage, Dict[tuple, QRectF]]:
		"""Draw `items` (a dashboard's item list, each carrying a `name` from `names`) and return the image and each item's rectangle."""
		# A changed path makes the dashboard clear the old items first; the same path reconciles them in place, and an item
		# whose key changed then fails to disconnect from its old value. So the two names take turns.
		self._turn = not getattr(self, '_turn', False)
		target = self.directory / ('_preview-a.levity' if self._turn else '_preview-b.levity')
		target.write_text(yaml.safe_dump(items, sort_keys=False, allow_unicode=True), encoding='utf-8')
		self.panel._load(target)
		self._boot.pump(self.app, 0.5)
		self.app.processEvents()
		self._boot.pump(self.app, 0.4)
		scene = self.dashboard.scene
		rect = scene.sceneRect()
		image = self._boot.render_image(scene, rect)
		found = {}
		for name, item in self._boot.named_items(scene).items():
			if name in names:
				found[names[name]] = item.sceneBoundingRect().translated(-rect.topLeft())
		return image, found

	def stop(self):
		self._boot.shutdown(self.dashboard)


def previewDocument(piece: model.Piece, given: Dict[str, Any], fields: Optional[dict] = None) -> Tuple[List[dict], Dict[str, tuple]]:
	"""The dashboard item list for the stage, and the temporary names that find each item again."""
	root = lib.merge(piece.expanded(given), fields) if fields else piece.expanded(given)
	names: Dict[str, tuple] = {}

	def tag(node: dict, path: tuple):
		name = '_n' + '_'.join(map(str, path)) if path else '_n'
		node['name'] = name
		names[name] = path
		for i, kid in enumerate(node.get(model.ITEMS_KEY) or []):
			if isinstance(kid, dict):
				tag(kid, path + (i,))

	tag(root, ())
	root.setdefault('geometry', {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'})
	stage = {'type': 'group', 'name': '_stage', 'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'}, 'items': [root]}
	return [stage], names


class Stage(QWidget):
	"""The picture, with the selected item outlined. Click selects; a drag moves or resizes it."""

	selected = Signal(tuple)
	dragged = Signal(tuple, dict)  # path, geometry in % of the parent
	dragDone = Signal()

	HANDLE = 9

	def __init__(self):
		super().__init__()
		self.image: Optional[QImage] = None
		self.rects: Dict[tuple, QRectF] = {}
		self.path: Optional[tuple] = None
		self.movable = False
		self._drag: Optional[tuple] = None
		self.setMinimumSize(320, 220)
		self.setMouseTracking(True)

	def show_(self, image: QImage, rects: Dict[tuple, QRectF]):
		self.image, self.rects = image, rects
		self.update()

	def select(self, path: Optional[tuple], movable: bool):
		self.path, self.movable = path, movable
		self.update()

	def _fit(self) -> Tuple[float, QPointF]:
		if self.image is None:
			return 1.0, QPointF()
		scale = min(self.width() / self.image.width(), self.height() / self.image.height())
		return scale, QPointF((self.width() - self.image.width() * scale) / 2, (self.height() - self.image.height() * scale) / 2)

	def _toScene(self, pos: QPointF) -> QPointF:
		scale, off = self._fit()
		return QPointF((pos.x() - off.x()) / scale, (pos.y() - off.y()) / scale)

	def _toView(self, rect: QRectF) -> QRectF:
		scale, off = self._fit()
		return QRectF(off.x() + rect.x() * scale, off.y() + rect.y() * scale, rect.width() * scale, rect.height() * scale)

	def paintEvent(self, _):
		p = QPainter(self)
		p.fillRect(self.rect(), self.palette().window())
		if self.image is None:
			return
		scale, off = self._fit()
		p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
		p.drawImage(QRectF(off.x(), off.y(), self.image.width() * scale, self.image.height() * scale), self.image)
		if self.path is not None and self.path in self.rects:
			r = self._toView(self.rects[self.path])
			p.setPen(QPen(QColor('#2f81f7'), 2))
			p.setBrush(Qt.BrushStyle.NoBrush)
			p.drawRect(r)
			if self.movable:
				p.setBrush(QColor('#2f81f7'))
				for c in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
					p.drawRect(QRectF(c.x() - self.HANDLE / 2, c.y() - self.HANDLE / 2, self.HANDLE, self.HANDLE))

	def _corner(self, pos: QPointF) -> Optional[str]:
		if self.path is None or self.path not in self.rects or not self.movable:
			return None
		r = self._toView(self.rects[self.path])
		for name, c in (('tl', r.topLeft()), ('tr', r.topRight()), ('bl', r.bottomLeft()), ('br', r.bottomRight())):
			if abs(pos.x() - c.x()) <= self.HANDLE and abs(pos.y() - c.y()) <= self.HANDLE:
				return name
		return None

	def hit(self, point: QPointF) -> Optional[tuple]:
		"""The smallest item under the point."""
		best = None
		for path, rect in self.rects.items():
			if path and rect.contains(point) and (best is None or rect.width() * rect.height() <= self.rects[best].width() * self.rects[best].height()):
				best = path
		return best if best is not None else (() if () in self.rects and self.rects[()].contains(point) else None)

	def mousePressEvent(self, event):
		pos = event.position()
		corner = self._corner(pos)
		if corner:
			self._drag = ('resize', corner, pos, QRectF(self.rects[self.path]))
			return
		if self.path in self.rects and self.movable and self._toView(self.rects[self.path]).contains(pos):
			self._drag = ('move', None, pos, QRectF(self.rects[self.path]))
			return
		hit = self.hit(self._toScene(pos))
		if hit is not None:
			self.selected.emit(hit)

	def mouseMoveEvent(self, event):
		pos = event.position()
		if self._drag is None:
			corner = self._corner(pos)
			self.setCursor(Qt.CursorShape.SizeFDiagCursor if corner in ('tl', 'br') else Qt.CursorShape.SizeBDiagCursor if corner else Qt.CursorShape.ArrowCursor)
			return
		mode, corner, start, rect = self._drag
		scale, _ = self._fit()
		dx, dy = (pos.x() - start.x()) / scale, (pos.y() - start.y()) / scale
		new = QRectF(rect)
		if mode == 'move':
			new.translate(dx, dy)
		else:
			if 'l' in corner:
				new.setLeft(rect.left() + dx)
			if 'r' in corner:
				new.setRight(rect.right() + dx)
			if 't' in corner:
				new.setTop(rect.top() + dy)
			if 'b' in corner:
				new.setBottom(rect.bottom() + dy)
			new = new.normalized()
		parent = self.rects.get(self.path[:-1]) if self.path else None
		if parent is None:
			parent = QRectF(0, 0, self.image.width(), self.image.height()) if self.image else QRectF(0, 0, 1, 1)
		if parent.width() <= 0 or parent.height() <= 0:
			return
		geometry = {
			'x': f'{(new.x() - parent.x()) / parent.width() * 100:.1f}%', 'y': f'{(new.y() - parent.y()) / parent.height() * 100:.1f}%',
			'width': f'{new.width() / parent.width() * 100:.1f}%', 'height': f'{new.height() / parent.height() * 100:.1f}%',
		}
		if mode == 'move':
			geometry = {k: geometry[k] for k in ('x', 'y')}  # a move keeps the size the item already has
		self.rects[self.path] = new
		self.update()
		self.dragged.emit(self.path, geometry)

	def mouseReleaseEvent(self, _):
		if self._drag is not None:
			self._drag = None
			self.dragDone.emit()


# Section: the Item tab

class FieldRow(QWidget):
	"""One field of the selected item: label, editor, and the `$` that binds it to a preset property."""

	edited = Signal(str, object)
	bindClicked = Signal(str, QWidget)
	unbound = Signal(str)

	def __init__(self, field: str, label: str, editor: Editor, bindable: bool = True, tip: str = ''):
		super().__init__()
		self.field = field
		self.editor = editor
		box = QHBoxLayout(self)
		box.setContentsMargins(0, 0, 0, 0)
		box.setSpacing(4)
		box.addWidget(_label(label, tip or field))
		box.addWidget(editor, 1)
		self.chip = QLabel()
		self.chip.setStyleSheet('font-weight: 700; padding: 2px 6px; border: 1px solid palette(mid); border-radius: 8px;')
		self.chip.setVisible(False)
		box.addWidget(self.chip, 1)
		self.bind = QToolButton()
		self.bind.setText('$')
		self.bind.setToolTip('Bind this field to a preset property')
		self.bind.setVisible(bindable)
		self.bind.clicked.connect(lambda: self.bindClicked.emit(field, self.bind))
		box.addWidget(self.bind)
		editor.changed.connect(lambda v: self.edited.emit(field, v))

	def show_(self, value: Any, bound: Optional[str]):
		"""`bound` is the `$name` text when the field holds a reference."""
		self.editor.setVisible(bound is None)
		self.chip.setVisible(bound is not None)
		if bound is not None:
			self.chip.setText(bound)
		else:
			self.editor.setValue(value)


class ItemTab(QWidget):
	"""The selected item's fields."""

	def __init__(self, builder: 'Builder'):
		super().__init__()
		self.builder = builder
		self.rows: Dict[str, FieldRow] = {}
		self.outer = QVBoxLayout(self)
		self.outer.setContentsMargins(8, 8, 8, 8)
		self.holder = QWidget()
		self.layout_ = QVBoxLayout(self.holder)
		self.layout_.setContentsMargins(0, 0, 0, 0)
		scroll = QScrollArea()
		scroll.setWidgetResizable(True)
		scroll.setFrameShape(QFrame.Shape.NoFrame)
		scroll.setWidget(self.holder)
		self.outer.addWidget(scroll)

	def clear(self):
		self.rows.clear()
		while self.layout_.count():
			w = self.layout_.takeAt(0).widget()
			if w is not None:
				w.setParent(None)
				w.deleteLater()

	def load(self, path: Optional[tuple]):
		self.clear()
		piece = self.builder.piece
		node = piece.node(path) if path is not None else None
		if node is None:
			self.layout_.addWidget(QLabel('Select an item in the tree or on the preview.'))
			self.layout_.addStretch(1)
			return
		kind = str(node.get('type') or '')
		parent = piece.node(path[:-1]) if path else None
		inLayout = parent is not None and str(parent.get('type')) in LAYOUT_PARENTS

		head = Section('Item', expanded=True)
		self.layout_.addWidget(head)
		if model.PRESET_KEY in node:
			self._row(head, model.PRESET_KEY, 'preset', editors.ChoiceEdit([(n, n) for n in lib.available()], editable=True), bindable=False, value=node[model.PRESET_KEY])
		else:
			type_ = editors.ChoiceEdit([(k, k) for k in CONTAINERS + DISPLAYS], editable=True)
			self._row(head, 'type', 'type', type_, bindable=False, value=kind)
		self._row(head, 'name', 'name', TextEdit('optional'), bindable=False, value=node.get('name'))
		if kind in ('realtime.text', 'realtime.gauge', 'realtime.bar', 'graph', 'mini-graph'):
			self._row(head, 'key', 'key', editors.KeyEdit(), value=node.get('key'))
		if kind in ('text', 'label'):
			self._row(head, 'text', 'text', TextEdit(), value=node.get('text'))
		if kind in ('realtime.gauge', 'realtime.bar'):
			scale = Section('Scale', expanded=True)
			self.layout_.addWidget(scale)
			for field, label in (('display.range.min', 'min'), ('display.range.max', 'max')):
				self._row(scale, field, label, MeasuredEdit(self._keyOf(node)), value=model.getField(node, field))
			if kind == 'realtime.gauge':
				self._row(scale, 'display.arc.gradient', 'gradient', editors.ChoiceEdit([('$temperature', '$temperature'), ('$load', '$load')], editable=True),
				          value=model.getField(node, 'display.arc.gradient'))
		if kind in ('text', 'label'):
			color = editors.ColorEdit(nullable=True)
			self._row(head, 'color', 'color', color, value=node.get('color'))
		if kind in ('stack', 'value-stack'):
			self._row(head, 'direction', 'direction', editors.ChoiceEdit([('Vertical', 'Vertical'), ('Horizontal', 'Horizontal')]), value=node.get('direction'))
			self._row(head, 'spacing', 'spacing', editors.SizeEdit(nullable=True, ref='full'), value=node.get('spacing'))
		if kind == layout.GRID_KIND:
			self._row(head, 'spacing', 'spacing', editors.SizeEdit(nullable=True, ref='full'), value=node.get('spacing'))
		parentKind = str(parent.get('type')) if parent is not None else ''
		flexContainer, flexItem = kind in layout.STACK_KINDS, parentKind in layout.STACK_KINDS
		gridContainer, gridItem = kind == layout.GRID_KIND, parentKind == layout.GRID_KIND
		if flexContainer or flexItem or gridContainer or gridItem:
			arrange = Section('Layout (CSS flex and grid)', expanded=True)
			self.layout_.addWidget(arrange)
			if flexContainer or flexItem:
				edit = layout.FlexEdit()
				edit.setRoles(flexContainer, flexItem)
				self._row(arrange, 'flex', 'flex', edit, bindable=False, value=node.get('flex'))
			if gridContainer or gridItem:
				edit = layout.GridEdit()
				edit.setRoles(gridContainer, gridItem)
				self._row(arrange, 'grid', 'grid', edit, bindable=False, value=node.get('grid'))

		where = Section('Geometry' + (' (a share of its parent; in a stack it sets the size)' if inLayout else ' (a share of its parent)'), expanded=True)
		self.layout_.addWidget(where)
		for field, label, ref in GEOMETRY:
			self._row(where, field, label, editors.SizeEdit(nullable=True, ref=ref), value=model.getField(node, field))

		more = Section('When and more', expanded=True)
		self.layout_.addWidget(more)
		self._row(more, 'when', 'when', editors.WhenEdit(), bindable=False, value=node.get('when'))
		rest = restOf(node)
		self._row(more, '*', 'more', MoreEdit(), bindable=False, value=rest)
		self.layout_.addStretch(1)

	def _keyOf(self, node: dict) -> Optional[str]:
		key = node.get('key')
		ref = model.wholeRef(key)
		if ref is None:
			return key if isinstance(key, str) else None
		given = self.builder.given.get(ref)
		spec = self.builder.piece.props.get(ref)
		return str(given if given is not None else spec.default if spec else '')

	def _row(self, section: Section, field: str, label: str, editor: Editor, bindable: bool = True, value: Any = None):
		row = FieldRow(field, label, editor, bindable)
		bound = value if isinstance(value, str) and model.wholeRef(value) else None
		row.show_(value, bound)
		row.edited.connect(self.builder.editField)
		row.bindClicked.connect(self.builder.bindMenu)
		row.chip.mousePressEvent = lambda e, f=field: self.builder.unbind(f)
		row.chip.setToolTip('Click to unbind: the field takes the property\'s default as a plain value')
		section.addRow(row)
		self.rows[field] = row
		return row


# Section: the Properties tab

class PropRow(QFrame):
	"""One property the preset declares."""

	changed = Signal(str)  # the property's name
	removed = Signal(str)
	renamed = Signal(str, str)
	typed = Signal(str)

	def __init__(self, spec: model.PropSpec, measured: Optional[str] = None):
		super().__init__()
		self.spec = spec
		self.setFrameShape(QFrame.Shape.StyledPanel)
		box = QVBoxLayout(self)
		box.setContentsMargins(8, 6, 8, 6)
		top = QHBoxLayout()
		self.name = QLineEdit(spec.name)
		self.name.setStyleSheet('font-weight: 700;')
		self.name.editingFinished.connect(self._renamed)
		self.type = QComboBox()
		self.type.addItems(model.TYPES)
		self.type.setCurrentText(spec.type)
		self.type.activated.connect(self._typed)
		gone = QToolButton()
		gone.setText('Remove')
		gone.clicked.connect(lambda: self.removed.emit(self.spec.name))
		top.addWidget(self.name, 1)
		top.addWidget(self.type)
		top.addWidget(gone)
		box.addLayout(top)
		self.default = editorFor(spec.kind(), spec, 'full', measured)
		self.default.setValue(spec.default)
		self.default.changed.connect(self._default)
		line = QHBoxLayout()
		line.addWidget(_label('default'))
		line.addWidget(self.default, 1)
		box.addLayout(line)
		if spec.type == 'number':
			for attr, text in (('lo', 'min'), ('hi', 'max')):
				edit = numberEdit(getattr(spec, attr), autoText='none')
				edit.setValue(getattr(spec, attr))
				edit.changed.connect(lambda v, a=attr: self._limit(a, v))
				row = QHBoxLayout()
				row.addWidget(_label(text))
				row.addWidget(edit, 1)
				box.addLayout(row)
		self.doc = QLineEdit(spec.doc)
		self.doc.setPlaceholderText('what it does (shown as a tooltip)')
		self.doc.editingFinished.connect(self._doc)
		row = QHBoxLayout()
		row.addWidget(_label('note'))
		row.addWidget(self.doc, 1)
		box.addLayout(row)

	def _renamed(self):
		new = re.sub(r'[^\w-]+', '-', self.name.text()).strip('-')
		if new and new != self.spec.name:
			self.renamed.emit(self.spec.name, new)

	def _typed(self, _):
		self.spec.type = self.type.currentText()
		self.typed.emit(self.spec.name)

	def _default(self, value):
		self.spec.default = value
		self.changed.emit(self.spec.name)

	def _limit(self, attr: str, value):
		setattr(self.spec, attr, value)
		self.changed.emit(self.spec.name)

	def _doc(self):
		self.spec.doc = self.doc.text()
		self.changed.emit(self.spec.name)


class PropsTab(QWidget):
	def __init__(self, builder: 'Builder'):
		super().__init__()
		self.builder = builder
		outer = QVBoxLayout(self)
		outer.setContentsMargins(8, 8, 8, 8)
		bar = QHBoxLayout()
		add = QToolButton()
		add.setText('Add property')
		add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
		menu = QMenu(add)
		for kind in model.TYPES:
			menu.addAction(kind, lambda k=kind: builder.addProp(k))
		add.setMenu(menu)
		bar.addWidget(add)
		bar.addWidget(QLabel('A field uses one with the $ button in the Item tab.'))
		bar.addStretch(1)
		outer.addLayout(bar)
		doc = QHBoxLayout()
		doc.addWidget(_label('note'))
		self.doc = QLineEdit()
		self.doc.setPlaceholderText('what the preset is, in a line')
		self.doc.editingFinished.connect(self._doc)
		doc.addWidget(self.doc, 1)
		outer.addLayout(doc)
		self.holder = QWidget()
		self.list = QVBoxLayout(self.holder)
		self.list.setContentsMargins(0, 0, 0, 0)
		scroll = QScrollArea()
		scroll.setWidgetResizable(True)
		scroll.setFrameShape(QFrame.Shape.NoFrame)
		scroll.setWidget(self.holder)
		outer.addWidget(scroll)

	def _doc(self):
		if self.doc.text() != self.builder.piece.doc:
			self.builder.push()
			self.builder.piece.doc = self.doc.text()
			self.builder.refreshYaml()

	def load(self):
		with QSignalBlocker(self.doc):
			self.doc.setText(self.builder.piece.doc)
		while self.list.count():
			w = self.list.takeAt(0).widget()
			if w is not None:
				w.setParent(None)
				w.deleteLater()
		for spec in self.builder.piece.props.values():
			row = PropRow(spec, self.builder.piece.measuredKey(spec.name, self.builder.given))
			row.changed.connect(self.builder.propChanged)
			row.removed.connect(self.builder.removeProp)
			row.renamed.connect(self.builder.renameProp)
			row.typed.connect(self.builder.retypeProp)
			self.list.addWidget(row)
		if not self.builder.piece.props:
			self.list.addWidget(QLabel('No properties yet. Bind a field with its $ button, or add one here.'))
		self.list.addStretch(1)


# Section: the Instance tab

class InstanceTab(QWidget):
	"""A value for every property, and what a dashboard would store for it."""

	def __init__(self, builder: 'Builder'):
		super().__init__()
		self.builder = builder
		self.editors: Dict[str, Editor] = {}
		outer = QVBoxLayout(self)
		outer.setContentsMargins(8, 8, 8, 8)
		self.holder = QWidget()
		self.list = QVBoxLayout(self.holder)
		self.list.setContentsMargins(0, 0, 0, 0)
		scroll = QScrollArea()
		scroll.setWidgetResizable(True)
		scroll.setFrameShape(QFrame.Shape.NoFrame)
		scroll.setWidget(self.holder)
		outer.addWidget(scroll, 1)
		outer.addWidget(QLabel('A dashboard stores:'))
		self.out = QPlainTextEdit()
		self.out.setReadOnly(True)
		self.out.setMaximumHeight(150)
		outer.addWidget(self.out)

	def load(self):
		while self.list.count():
			w = self.list.takeAt(0).widget()
			if w is not None:
				w.setParent(None)
				w.deleteLater()
		self.editors.clear()
		piece = self.builder.piece
		for name, spec in piece.props.items():
			row = QWidget()
			box = QHBoxLayout(row)
			box.setContentsMargins(0, 0, 0, 0)
			label = _label(name, spec.doc or name)
			editor = editorFor(spec.kind(), spec, 'full', piece.measuredKey(name, self.builder.given))
			editor.setToolTip(spec.doc)
			editor.setValue(self.builder.given.get(name, spec.default))
			editor.changed.connect(lambda v, n=name: self.builder.setGiven(n, v))
			reset = QToolButton()
			reset.setText('↺')
			reset.setToolTip('Back to the preset\'s default')
			reset.clicked.connect(lambda _=False, n=name: self.builder.resetGiven(n))
			box.addWidget(label)
			box.addWidget(editor, 1)
			box.addWidget(reset)
			self.list.addWidget(row)
			self.editors[name] = editor
		if not piece.props:
			self.list.addWidget(QLabel('The preset has no properties, so an instance is just its name.'))
		use = Section('This use: fields beyond the properties', expanded=True)
		self.list.addWidget(use)
		self.useEditors: Dict[str, Editor] = {}
		for field, label, ref in GEOMETRY:
			editor = editors.SizeEdit(nullable=True, ref=ref)
			editor.setValue(model.getField(self.builder.fields, field))
			editor.changed.connect(lambda v, f=field: self.builder.setUseField(f, v))
			row = QWidget()
			box = QHBoxLayout(row)
			box.setContentsMargins(0, 0, 0, 0)
			box.addWidget(_label(label, f'{field} on the instance, merged over the preset'))
			box.addWidget(editor, 1)
			use.addRow(row)
			self.useEditors[field] = editor
		self.list.addStretch(1)
		self.refresh()

	def sync(self):
		piece = self.builder.piece
		for name, editor in self.editors.items():
			if isinstance(editor, MeasuredEdit):
				editor.setKey(piece.measuredKey(name, self.builder.given))
			if name in piece.props and not editor.isEditing():
				editor.setValue(self.builder.given.get(name, piece.props[name].default))
		self.refresh()

	def refresh(self):
		piece = self.builder.piece
		text = yaml.safe_dump([piece.instance(self.builder.given, self.builder.fields)], sort_keys=False, allow_unicode=True)
		bad = piece.problems(self.builder.given)
		self.out.setPlainText(text + ''.join(f'# {b}\n' for b in bad))


# Section: the window

class Builder(QWidget):
	"""The builder window. `piece` is the preset being built; `given` is the instance the stage draws."""

	def __init__(self, path: Optional[Path] = None, engine: Optional[PreviewEngine] = None, size: Tuple[int, int] = (640, 400)):
		super().__init__()
		self.setWindowTitle('Studio builder')
		self.engine = engine or PreviewEngine(size)
		self.piece = model.Piece()
		self.given: Dict[str, Any] = {}
		self.fields: Dict[str, Any] = {}  # the fields the instance sets beyond its properties (geometry, name)
		self.path: Optional[Path] = None
		self.selection: Optional[tuple] = ()
		self.history: List[Tuple[model.Piece, Dict[str, Any]]] = []
		self.future: List[Tuple[model.Piece, Dict[str, Any]]] = []
		self.light = False
		self._bindSource: Optional[str] = None
		self.timer = QTimer(self)
		self.timer.setSingleShot(True)
		self.timer.setInterval(SETTLE_MS)
		self.timer.timeout.connect(self.redraw)
		self._build()
		self.resize(1500, 860)
		if path is not None:
			self.openFile(path)
		else:
			self.loadPiece(model.Piece(), {})
		QShortcut(QKeySequence.StandardKey.Undo, self, self.undo)
		QShortcut(QKeySequence.StandardKey.Redo, self, self.redo)
		QShortcut(QKeySequence.StandardKey.Save, self, self.save)

	# layout

	def _build(self):
		outer = QVBoxLayout(self)
		outer.setContentsMargins(0, 0, 0, 0)
		bar = QHBoxLayout()
		bar.setContentsMargins(8, 6, 8, 0)
		self.name = QLineEdit()
		self.name.setMaximumWidth(220)
		self.name.setPlaceholderText('preset name')
		self.name.editingFinished.connect(self._named)
		bar.addWidget(QLabel('Preset'))
		bar.addWidget(self.name)
		new = QPushButton('New')
		new.clicked.connect(self.newPiece)
		bar.addWidget(new)
		self.openButton = QToolButton()
		self.openButton.setText('Open')
		self.openButton.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
		self.openMenu = QMenu(self.openButton)
		self.openMenu.aboutToShow.connect(self._fillOpenMenu)
		self.openButton.setMenu(self.openMenu)
		bar.addWidget(self.openButton)
		for text, fn, tip in (
			('Save', self.save, 'Write the preset file'),
			('Save as…', self.saveAs, ''), ('Copy preset', self.copyPreset, 'Copy the preset file\'s YAML'), ('Copy instance', self.copyInstance, 'Copy what a dashboard stores for this instance'),
		):
			button = QPushButton(text)
			button.setToolTip(tip)
			button.clicked.connect(lambda _=False, f=fn: f())
			bar.addWidget(button)
		self.undoButton = QPushButton('Undo')
		self.undoButton.clicked.connect(self.undo)
		self.redoButton = QPushButton('Redo')
		self.redoButton.clicked.connect(self.redo)
		bar.addWidget(self.undoButton)
		bar.addWidget(self.redoButton)
		bar.addStretch(1)
		self.stageBox = QComboBox()
		self.stageBox.addItems(list(STAGES))
		self.stageBox.setToolTip('The size of the area the preset is drawn in')
		self.stageBox.activated.connect(lambda _: self.schedule())
		bar.addWidget(self.stageBox)
		self.themePicker = ThemePicker()
		self.themePicker.setToolTip('The colour theme the preview is drawn in')
		self.themePicker.picked.connect(lambda _: self.schedule())
		bar.addWidget(self.themePicker)
		self.themeButton = QPushButton('Light')
		self.themeButton.setCheckable(True)
		self.themeButton.toggled.connect(self.setLight)
		bar.addWidget(self.themeButton)
		outer.addLayout(bar)

		split = QSplitter(Qt.Orientation.Horizontal)
		outer.addWidget(split, 1)

		left = QWidget()
		lbox = QVBoxLayout(left)
		lbox.setContentsMargins(8, 8, 4, 8)
		tools = QHBoxLayout()
		self.addButton = QToolButton()
		self.addButton.setText('Add item')
		self.addButton.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
		menu = QMenu(self.addButton)
		menu.addSection('Containers')
		for kind in CONTAINERS:
			menu.addAction(kind, lambda k=kind: self.addItem(k))
		menu.addSection('Displays')
		for kind in DISPLAYS:
			menu.addAction(kind, lambda k=kind: self.addItem(k))
		menu.addSection('Presets')
		for name in lib.available():
			menu.addAction(name, lambda n=name: self.addItem(f'preset:{n}'))
		self.addButton.setMenu(menu)
		tools.addWidget(self.addButton)
		for text, fn, tip in (('Duplicate', self.duplicateItem, ''), ('Delete', self.deleteItem, 'Remove the selected item and what is inside it'),
		                      ('▲', lambda: self.moveItem(-1), 'Earlier'), ('▼', lambda: self.moveItem(1), 'Later')):
			b = QToolButton()
			b.setText(text)
			b.setToolTip(tip)
			b.clicked.connect(lambda _=False, f=fn: f())
			tools.addWidget(b)
		tools.addStretch(1)
		lbox.addLayout(tools)
		self.tree = QTreeWidget()
		self.tree.setHeaderHidden(True)
		self.tree.setMinimumWidth(240)
		self.tree.currentItemChanged.connect(self._treePicked)
		lbox.addWidget(self.tree, 1)
		split.addWidget(left)

		middle = QWidget()
		mbox = QVBoxLayout(middle)
		mbox.setContentsMargins(4, 8, 4, 8)
		self.stage = Stage()
		self.stage.selected.connect(self.select)
		self.stage.dragged.connect(self._dragged)
		self.stage.dragDone.connect(self._dragDone)
		mbox.addWidget(self.stage, 1)
		self.status = QLabel()
		self.status.setWordWrap(True)
		self.status.setStyleSheet('color: palette(placeholder-text);')
		mbox.addWidget(self.status)
		split.addWidget(middle)

		self.tabs = QTabWidget()
		self.itemTab = ItemTab(self)
		self.propsTab = PropsTab(self)
		self.instanceTab = InstanceTab(self)
		self.yamlView = QPlainTextEdit()
		self.yamlView.setReadOnly(True)
		self.tabs.addTab(self.itemTab, 'Item')
		self.tabs.addTab(self.propsTab, 'Properties')
		self.tabs.addTab(self.instanceTab, 'Instance')
		self.tabs.addTab(self.yamlView, 'YAML')
		self.tabs.setMinimumWidth(440)
		split.addWidget(self.tabs)
		split.setStretchFactor(1, 1)
		split.setSizes([260, 700, 540])

	# loading

	def loadPiece(self, piece: model.Piece, given: Dict[str, Any], path: Optional[Path] = None):
		self.piece, self.given, self.path = piece, dict(given), path
		self.fields = {}
		self._searchPath()
		self.history.clear()
		self.future.clear()
		with QSignalBlocker(self.name):
			self.name.setText(piece.name)
		self.selection = ()
		self.rebuildAll()
		self.redraw()

	def rebuildAll(self):
		self.rebuildTree()
		self.propsTab.load()
		self.instanceTab.load()
		self.itemTab.load(self.selection)
		self._updateHistory()
		self.refreshYaml()

	def _searchPath(self):
		"""Let the library find the presets this Studio saves, so a nested use and the Open menu see them."""
		if not Builder._searching:
			Builder._searching = True
			lib.add_search_path(lambda: [state.stateDir() / 'presets'])

	_searching = False

	def newPiece(self):
		self.loadPiece(model.Piece(), {})

	def _fillOpenMenu(self):
		self.openMenu.clear()
		for name in lib.available():
			self.openMenu.addAction(name, lambda n=name: self.openNamed(n))
		self.openMenu.addSeparator()
		self.openMenu.addAction('File\u2026', self.openDialog)

	def openDialog(self):
		start = str(state.stateDir() / 'presets')
		name, _ = QFileDialog.getOpenFileName(self, 'Open a preset', start, 'Preset (*.yaml *.yml *.levity)')
		if name:
			self.openFile(Path(name))

	def openFile(self, path: Path):
		try:
			text = path.read_text()
			data = yaml.safe_load(text) or {}
		except (OSError, yaml.YAMLError) as e:
			self.status.setText(f'Could not read {path.name}: {e}')
			return
		try:
			if isinstance(data, dict) and model.TEMPLATE_KEY in data:
				piece = model.Piece.fromText(path.stem, text)
			else:
				# A plain item file (a gauge fragment, a levityPanel): a preset with no properties.
				items = data if isinstance(data, list) else data.get('items') if isinstance(data, dict) else None
				template = items[0] if isinstance(items, list) and len(items) == 1 else {'type': 'group', 'items': items or []}
				piece = model.Piece(path.stem, {}, template)
		except lib.PresetError as e:
			self.status.setText(f'{path.name} is not a usable preset: {e}')
			return
		self.loadPiece(piece, {}, path if path.parent == state.stateDir() / 'presets' else None)
		self.status.setText(f'Opened {path.name}')

	def openNamed(self, name: str):
		"""Open a preset the library finds by name: the user's, then the ones that ship."""
		lib.clear_cache()
		try:
			preset = lib.load(name)
		except lib.PresetError as e:
			self.status.setText(str(e))
			return
		if preset is None:
			self.status.setText(f'No preset called {name}')
			return
		source = Path(preset.source) if preset.source else None
		self.loadPiece(model.Piece.fromPreset(preset), {}, source if source and source.parent == state.stateDir() / 'presets' else None)
		self.status.setText(f'Opened {name}' + ('' if self.path else ' (a shipped preset: Save writes your own copy, which takes its place)'))

	# saving

	def presetText(self) -> str:
		return yaml.safe_dump(self.piece.asData(), sort_keys=False, allow_unicode=True, width=120)

	def defaultPath(self) -> Path:
		return state.stateDir() / 'presets' / f'{self.piece.name}.yaml'

	def save(self):
		path = self.path or self.defaultPath()
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(self.presetText())
		lib.clear_cache()
		self.path = path
		self.status.setText(f'Saved {path}')

	def saveAs(self):
		name, _ = QFileDialog.getSaveFileName(self, 'Save the preset', str(self.path or self.defaultPath()), 'Preset (*.yaml)')
		if name:
			self.path = Path(name)
			self.save()

	def copyPreset(self):
		QApplication.clipboard().setText(self.presetText())
		self.status.setText('Copied the preset file')

	def copyInstance(self):
		QApplication.clipboard().setText(yaml.safe_dump([self.piece.instance(self.given, self.fields)], sort_keys=False, allow_unicode=True))
		self.status.setText('Copied the instance')

	def _named(self):
		name = re.sub(r'[^\w-]+', '-', self.name.text()).strip('-') or 'new-preset'
		if name != self.piece.name:
			self.push()
			self.piece.name = name
			self.path = None
			self.refreshYaml()
		with QSignalBlocker(self.name):
			self.name.setText(name)

	# history

	def push(self):
		self.history.append((self.piece.copy(), dict(self.given)))
		del self.history[:-100]
		self.future.clear()
		self._updateHistory()

	def _updateHistory(self):
		self.undoButton.setEnabled(bool(self.history))
		self.redoButton.setEnabled(bool(self.future))

	def undo(self):
		if self.history:
			self.future.append((self.piece.copy(), dict(self.given)))
			self.piece, self.given = self.history.pop()
			self._restored()

	def redo(self):
		if self.future:
			self.history.append((self.piece.copy(), dict(self.given)))
			self.piece, self.given = self.future.pop()
			self._restored()

	def _restored(self):
		if self.piece.node(self.selection or ()) is None:
			self.selection = ()
		with QSignalBlocker(self.name):
			self.name.setText(self.piece.name)
		self.rebuildAll()
		self.schedule()

	# the tree

	def rebuildTree(self):
		with QSignalBlocker(self.tree):
			self.tree.clear()

			def add(parent, node, path):
				label = str(node.get('type') or (f"preset: {node[model.PRESET_KEY]}" if model.PRESET_KEY in node else '?'))
				detail = node.get('name') or node.get('key') or node.get('text')
				row = QTreeWidgetItem([f'{label}  ·  {detail}' if detail else label])
				row.setData(0, Qt.ItemDataRole.UserRole, path)
				(parent.addChild if parent is not None else self.tree.addTopLevelItem)(row)
				for i, kid in enumerate(node.get(model.ITEMS_KEY) or []):
					add(row, kid, path + (i,))
				row.setExpanded(True)

			add(None, self.piece.template, ())
		self._selectRow()

	def _selectRow(self):
		it = self.tree.invisibleRootItem()
		stack = [it.child(i) for i in range(it.childCount())]
		while stack:
			row = stack.pop()
			if row.data(0, Qt.ItemDataRole.UserRole) == self.selection:
				with QSignalBlocker(self.tree):
					self.tree.setCurrentItem(row)
				return
			stack += [row.child(i) for i in range(row.childCount())]

	def _treePicked(self, row, _):
		if row is not None:
			self.select(row.data(0, Qt.ItemDataRole.UserRole), fromTree=True)

	def select(self, path: tuple, fromTree: bool = False):
		while path and self.piece.node(path) is None:
			path = path[:-1]  # the stage can show items a nested preset makes; the tree holds only this preset's own
		self.selection = path
		if not fromTree:
			self._selectRow()
		self.itemTab.load(path)
		self._syncStage()

	def _movable(self) -> bool:
		if not self.selection:
			return False
		parent = self.piece.node(self.selection[:-1])
		return parent is not None and str(parent.get('type')) not in LAYOUT_PARENTS

	def _syncStage(self):
		self.stage.select(self.selection, self._movable())
		editors.CONTEXT.ref = self._refPixels

	def _refPixels(self, kind: str = 'w') -> float:
		"""The pixels a '%' of the selected item's parent spans, for the size editors' unit switch."""
		parent = self.stage.rects.get(self.selection[:-1]) if self.selection else None
		size = self.engine.size
		if kind == 'h':
			return parent.height() if parent is not None else float(size[1])
		return parent.width() if parent is not None else float(size[0])

	# editing items

	def addItem(self, kind: str):
		self.push()
		target = self.selection if self.selection is not None else ()
		node = self.piece.node(target)
		if node is None or str(node.get('type')) not in CONTAINERS:
			target = target[:-1]
			node = self.piece.node(target)
		count = len(node.get(model.ITEMS_KEY) or [])
		path = self.piece.add(target, newItem(kind, str(node.get('type')), count))
		self.selection = path
		self.rebuildAll()
		self._syncStage()
		self.schedule()

	def duplicateItem(self):
		if self.selection:
			self.push()
			self.selection = self.piece.duplicate(self.selection)
			self.rebuildAll()
			self._syncStage()
			self.schedule()

	def deleteItem(self):
		if self.selection:
			self.push()
			self.piece.remove(self.selection)
			self.selection = self.selection[:-1]
			self.rebuildAll()
			self._syncStage()
			self.schedule()

	def moveItem(self, by: int):
		if self.selection:
			self.push()
			self.selection = self.piece.move(self.selection, by)
			self.rebuildAll()
			self._syncStage()
			self.schedule()

	def editField(self, field: str, value: Any):
		"""A field of the selected item changed."""
		node = self.piece.node(self.selection) if self.selection is not None else None
		if node is None:
			return
		self.push()
		if field == '*':
			self._replaceRest(node, value or {})
		elif field == 'type':
			node['type'] = value or node.get('type')
			if node['type'] in CONTAINERS:
				node.setdefault(model.ITEMS_KEY, [])
			self.rebuildTree()
			self.itemTab.load(self.selection)
		else:
			model.setField(node, field, value if value not in ('', None) else None)
			if field == 'name':
				self.rebuildTree()
		self.afterEdit()

	def _replaceRest(self, node: dict, rest: dict):
		"""Swap the fields the popover holds for the ones it now reports; the fields the Item tab owns stay."""
		owned = {p: model.getField(node, p) for p in OWNED_PATHS}
		for k in [k for k in node if k not in OWNED]:
			del node[k]
		for k, v in rest.items():
			if k not in OWNED:
				node[k] = copy.deepcopy(v)
		for p, v in owned.items():
			if v is not None:
				model.setField(node, p, v)

	def _dragged(self, path: tuple, geometry: dict):
		node = self.piece.node(path)
		if node is None:
			return
		if not getattr(self, '_dragPushed', False):
			self.push()
			self._dragPushed = True
		for k, v in geometry.items():
			model.setField(node, f'geometry.{k}', v)
		self._syncGeometryRows(node)
		self.refreshYaml()
		self.timer.start()

	def _dragDone(self):
		self._dragPushed = False
		self.timer.start(40)

	def _syncGeometryRows(self, node: dict):
		for field, _, _ in GEOMETRY:
			row = self.itemTab.rows.get(field)
			if row is not None:
				row.show_(model.getField(node, field), None)

	def afterEdit(self):
		self.rebuildTree()
		self.refreshYaml()
		self.instanceTab.sync()
		self.schedule()

	# bindings

	def bindMenu(self, field: str, anchor: QWidget):
		node = self.piece.node(self.selection)
		if node is None:
			return
		kind, compatible = BINDABLE.get(field, ('text', ('text',)))
		menu = QMenu(anchor)
		fits = [s for s in self.piece.props.values() if s.type in compatible]
		for spec in fits:
			menu.addAction(f'${spec.name}', lambda s=spec: self.bind(field, s.name))
		if fits:
			menu.addSeparator()
		menu.addAction('New property from this field…', lambda: self.newPropFrom(field, kind))
		menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

	def bind(self, field: str, name: str):
		node = self.piece.node(self.selection)
		self.push()
		model.setField(node, field, f'${name}')
		self.itemTab.load(self.selection)
		self.afterEdit()

	def unbind(self, field: str):
		node = self.piece.node(self.selection)
		current = model.getField(node, field)
		name = model.wholeRef(current) if isinstance(current, str) else None
		self.push()
		spec = self.piece.props.get(name) if name else None
		model.setField(node, field, copy.deepcopy(spec.default) if spec else None)
		self.itemTab.load(self.selection)
		self.afterEdit()

	def newPropFrom(self, field: str, kind: str):
		node = self.piece.node(self.selection)
		current = model.getField(node, field)
		last = field.split('.')[-1]
		name, ok = QInputDialog.getText(self, 'New property', 'Name', text=self.piece.uniqueName(last))
		if not ok or not name.strip():
			return
		self.push()
		name = self.piece.uniqueName(name.strip())
		default = current if current is not None else FIELD_DEFAULTS.get(field, PROP_DEFAULTS.get(kind, ''))
		spec = model.PropSpec(name, kind, default)
		self.piece.props[name] = spec
		model.setField(node, field, f'${name}')
		self.propsTab.load()
		self.instanceTab.load()
		self.itemTab.load(self.selection)
		self.afterEdit()

	# properties

	def addProp(self, kind: str):
		self.push()
		name = self.piece.uniqueName(kind)
		self.piece.props[name] = model.PropSpec(name, kind, PROP_DEFAULTS[kind])
		self.propsTab.load()
		self.instanceTab.load()
		self.refreshYaml()

	def propChanged(self, name: str):
		spec = self.piece.props.get(name)
		if spec is not None:
			self.history.append((self.piece.copy(), dict(self.given)))
			self.future.clear()
			self._updateHistory()
		self.instanceTab.sync()
		self.refreshYaml()
		self.schedule()

	def removeProp(self, name: str):
		self.push()
		self.piece.drop(name)
		self.given.pop(name, None)
		self.propsTab.load()
		self.instanceTab.load()
		self.itemTab.load(self.selection)
		self.afterEdit()

	def renameProp(self, old: str, new: str):
		new = self.piece.uniqueName(new) if new in self.piece.props else new
		self.push()
		self.piece.rename(old, new)
		if old in self.given:
			self.given[new] = self.given.pop(old)
		self.propsTab.load()
		self.instanceTab.load()
		self.itemTab.load(self.selection)
		self.afterEdit()

	def retypeProp(self, name: str):
		spec = self.piece.props[name]
		spec.default = copy.deepcopy(PROP_DEFAULTS[spec.type])
		self.given.pop(name, None)
		self.propsTab.load()
		self.instanceTab.load()
		self.afterEdit()

	def setGiven(self, name: str, value: Any):
		spec = self.piece.props.get(name)
		if spec is None:
			return
		if value == spec.default:
			self.given.pop(name, None)
		else:
			self.given[name] = value
		self.instanceTab.refresh()
		self.schedule()

	def setUseField(self, field: str, value: Any):
		model.setField(self.fields, field, value)
		self.instanceTab.refresh()
		self.schedule()

	def resetGiven(self, name: str):
		self.given.pop(name, None)
		self.instanceTab.sync()
		self.schedule()

	# drawing

	def schedule(self):
		self.timer.start()

	def stageSize(self) -> Tuple[int, int]:
		return STAGES[self.stageBox.currentText()]

	def redraw(self):
		self.timer.stop()
		problems = self.piece.problems(self.given)
		self.engine.resize(self.stageSize())
		items, names = previewDocument(self.piece, self.given, self.fields)
		try:
			image, rects = self.engine.render(items, names)
		except Exception as e:  # noqa: BLE001 - a bad preset must not close the builder
			self.status.setText(f'The preview failed: {type(e).__name__}: {e}')
			return
		self.stage.show_(image, rects)
		self._syncStage()
		self.status.setText(('; '.join(problems) + '. ') if problems else '')
		self.refreshYaml()

	def refreshYaml(self):
		piece = self.piece
		self.yamlView.setPlainText(
			f'# {piece.name}.yaml\n{self.presetText()}\n# What the dashboard sees for the instance on the Instance tab:\n'
			+ yaml.safe_dump([piece.expanded(self.given)], sort_keys=False, allow_unicode=True, width=120))
		self.instanceTab.refresh()

	def setLight(self, on: bool):
		self.themeButton.setText('Dark' if on else 'Light')
		self.light = on
		theme = THEMES['light' if on else 'dark']
		app = QApplication.instance()
		app.setPalette(themePalette(theme))
		app.setStyleSheet(themeSheet(theme))
		editors.MUTED = theme['muted']

	def closeEvent(self, event):
		self.timer.stop()
		super().closeEvent(event)

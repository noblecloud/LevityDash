"""Dev-only: the Studio builder's Keys tab: every key the loaded plugins publish, searchable, with its source, place,
unit, shape and live value; an expression box that checks what you type and shows what it works out to; and a way to
put either on the selected item's `key:`. Drag a row onto the preview, the item tree or a key field to set it there.
Data and checks are in `_studio_keys.py`.
"""
from typing import List, Optional

from PySide6.QtCore import QMimeData, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
	QAbstractItemView, QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QPlainTextEdit, QPushButton,
	QStyledItemDelegate, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from LevityDash.devtools import _studio_keys as keys
from LevityDash.lib.plugins import periods, places

KEY_MIME = 'application/x-levity-key'
#: The items whose `key:` the tab can set.
KEYED = ('realtime.text', 'realtime.gauge', 'realtime.bar', 'graph', 'mini-graph')
COLUMNS = ['Key', 'Source', 'Place', 'Unit', 'Shape', 'Value']
REFRESH_MS = 1500
BAD, WARN = '#e5484d', '#d29922'

HELP = ('Type words to search the key and its title. Filters: source:Govee place:upstairs unit:f shape:enum state:live. '
        'Double-click a row to set it on the selected item; drag it onto the preview, a tree row or a key field.')


class MiddleElide(QStyledItemDelegate):
	"""Cut a long key in the middle, so both the section it starts with and the name it ends with show."""

	def initStyleOption(self, option, index):
		super().initStyleOption(option, index)
		option.textElideMode = Qt.TextElideMode.ElideMiddle


class KeyTree(QTreeWidget):
	"""The key list. A row dragged out carries its key as text."""

	def mimeData(self, items):
		mime = QMimeData()
		texts = [i.data(0, Qt.ItemDataRole.UserRole) for i in items if i.data(0, Qt.ItemDataRole.UserRole)]
		if texts:
			mime.setText(texts[0])
			mime.setData(KEY_MIME, texts[0].encode())
		return mime


class KeysTab(QWidget):
	"""The key browser. `builder` is the Studio builder this tab edits through."""

	def __init__(self, builder):
		super().__init__()
		self.builder = builder
		self.infos: List[keys.KeyInfo] = []
		self._shown: List[str] = []
		box = QVBoxLayout(self)
		box.setContentsMargins(8, 8, 8, 8)

		self.search = QLineEdit()
		self.search.setPlaceholderText('Search keys…  source:Fixture  place:upstairs  shape:enum')
		self.search.setClearButtonEnabled(True)
		self.search.setToolTip(HELP)
		self.search.textChanged.connect(lambda _: self._fill())
		box.addWidget(self.search)

		filters = QHBoxLayout()
		self.sourceBox = QComboBox()
		self.sourceBox.setToolTip('Only the keys this plugin has')
		self.shapeBox = QComboBox()
		self.shapeBox.setToolTip('Only keys of this shape: number, enum, text, time')
		for combo in (self.sourceBox, self.shapeBox):
			combo.activated.connect(lambda _: self._fill())
			filters.addWidget(combo)
		self.liveOnly = QCheckBox('Live')
		self.liveOnly.setToolTip('Only keys that have a value now')
		self.liveOnly.toggled.connect(lambda _: self._fill())
		filters.addWidget(self.liveOnly)
		filters.addStretch(1)
		box.addLayout(filters)

		self.tree = KeyTree()
		self.tree.setHeaderLabels(COLUMNS)
		self.tree.setRootIsDecorated(True)
		self.tree.setAlternatingRowColors(True)
		self.tree.setUniformRowHeights(True)
		self.tree.setDragEnabled(True)
		self.tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
		header = self.tree.header()
		header.setStretchLastSection(False)
		header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
		for column, width in enumerate((0, 88, 130, 44, 66, 70)):
			if column:
				header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
				self.tree.setColumnWidth(column, width)
		self.tree.setItemDelegateForColumn(0, MiddleElide(self.tree))
		self.tree.currentItemChanged.connect(lambda *_: self._status())
		self.tree.itemDoubleClicked.connect(lambda row, _c: self.useRow(row))
		self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
		self.tree.customContextMenuRequested.connect(self._menu)
		box.addWidget(self.tree, 3)

		self.target = QLabel()
		self.target.setWordWrap(True)
		self.target.setStyleSheet('color: palette(placeholder-text);')
		box.addWidget(self.target)

		row = QHBoxLayout()
		self.useButton = QPushButton('Set on item')
		self.useButton.setToolTip('Put the selected row on the selected item as its `key:`')
		self.useButton.clicked.connect(lambda: self.useRow(self.tree.currentItem()))
		self.insertButton = QPushButton('Add to expression')
		self.insertButton.setToolTip('Put the selected row into the expression below, where the cursor is')
		self.insertButton.clicked.connect(lambda: self.insertKey(self.tree.currentItem()))
		row.addWidget(self.useButton)
		row.addWidget(self.insertButton)
		row.addStretch(1)
		box.addLayout(row)

		self.pin = QGroupBox('Pin the selected item to a place or a period')
		form = QFormLayout(self.pin)
		self.placeBox = QComboBox()
		self.placeBox.setEditable(True)
		self.placeBox.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
		self.placeBox.lineEdit().setPlaceholderText('any device')
		self.placeBox.setToolTip('`where:` the one device at this place (home.upstairs.bedroom). A key that already names a device (#bedroom) or an expression ignores it.')
		self.placeBox.activated.connect(lambda _: self._pinned())
		self.placeBox.lineEdit().editingFinished.connect(self._pinned)
		form.addRow('Place', self.placeBox)
		window = QHBoxLayout()
		self.periodBox = QComboBox()
		self.periodBox.setEditable(True)
		self.periodBox.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
		self.periodBox.addItems(['', *periods.PERIODS, '1h', '3h', '6h', '24h', '7d'])
		self.periodBox.lineEdit().setPlaceholderText('now')
		self.periodBox.setToolTip('`period:` the window the reading covers: today, yesterday or a duration such as 3h')
		self.periodBox.activated.connect(lambda _: self._pinned())
		self.periodBox.lineEdit().editingFinished.connect(self._pinned)
		self.usingBox = QComboBox()
		self.usingBox.addItems(['max', 'min', 'avg'])
		self.usingBox.setToolTip('`using:` how the window is summed up')
		self.usingBox.activated.connect(lambda _: self._pinned())
		window.addWidget(self.periodBox, 1)
		window.addWidget(self.usingBox)
		form.addRow('Period', window)
		self.pinNote = QLabel()
		self.pinNote.setWordWrap(True)
		form.addRow('', self.pinNote)
		box.addWidget(self.pin)

		box.addWidget(QLabel('Expression'))
		self.text = QPlainTextEdit()
		self.text.setFixedHeight(64)
		self.text.setPlaceholderText('environment.temperature.temperature - environment.temperature.dewpoint')
		self.text.textChanged.connect(self._check)
		box.addWidget(self.text)
		tools = QHBoxLayout()
		self.snippets = QToolButton()
		self.snippets.setText('Insert…')
		self.snippets.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
		menu = QMenu(self.snippets)
		for label, snippet in keys.SNIPPETS:
			menu.addAction(f'{label}    {snippet}', lambda s=snippet: self.insertText(s))
		self.snippets.setMenu(menu)
		self.useExpression = QPushButton('Set expression on item')
		self.useExpression.clicked.connect(lambda: self.useText(self.value()))
		tools.addWidget(self.snippets)
		tools.addWidget(self.useExpression)
		tools.addStretch(1)
		box.addLayout(tools)
		self.report = QLabel()
		self.report.setWordWrap(True)
		box.addWidget(self.report)
		self.result = QLabel()
		self.result.setWordWrap(True)
		box.addWidget(self.result)

		self.timer = QTimer(self)
		self.timer.setInterval(REFRESH_MS)
		self.timer.timeout.connect(self.refresh)
		self.timer.start()
		self.refresh()
		self.selectionChanged()

	# the list

	def _readDashboard(self) -> List[keys.KeyInfo]:
		from LevityDash import LevityDashboard
		try:
			return keys.collectKeys(LevityDashboard.dispatcher, LevityDashboard.plugins)
		except Exception:  # noqa: BLE001 - a dashboard that is still booting has no keys yet
			return []

	def setInfos(self, infos: List[keys.KeyInfo]):
		"""Replace what the tab lists (the Studio reads the dashboard; a test passes its own)."""
		self.infos = infos
		sources = sorted({s for i in infos for s in i.sourceNames})
		shapes = sorted({i.shape for i in infos})
		for combo, first, names in ((self.sourceBox, 'Any source', sources), (self.shapeBox, 'Any shape', shapes)):
			current = combo.currentData()
			with QSignalBlocker(combo):
				combo.clear()
				combo.addItem(first, None)
				for name in names:
					combo.addItem(name, name)
				at = combo.findData(current)
				combo.setCurrentIndex(max(at, 0))
		self._fill()
		self._check()

	def refresh(self):
		"""Read the dashboard again: new rows rebuild the list, a changed value only changes its cell."""
		if not self.isVisible() and self.infos:
			return
		infos = self._readDashboard()
		if [i.key for i in infos] != [i.key for i in self.infos] or \
				[[s.name for s in i.sources] for i in infos] != [[s.name for s in i.sources] for i in self.infos]:
			self.setInfos(infos)
			return
		self.infos = infos
		self._values()

	def _query(self) -> str:
		parts = [self.search.text()]
		if (source := self.sourceBox.currentData()):
			parts.append(f'source:{source}')
		if (shape := self.shapeBox.currentData()):
			parts.append(f'shape:{shape}')
		if self.liveOnly.isChecked():
			parts.append('state:live')
		return ' '.join(parts)

	def _fill(self):
		query = self._query()
		keep = self._currentKey()
		self.tree.setUpdatesEnabled(False)
		self.tree.clear()
		palette = self.palette()
		ink, ground = palette.color(palette.ColorRole.Text), palette.color(palette.ColorRole.Base)
		# Halfway between the text and the ground: plain rows stay clear, rows with no value recede in both themes.
		muted = QBrush(QColor((ink.red() + ground.red()) // 2, (ink.green() + ground.green()) // 2, (ink.blue() + ground.blue()) // 2))
		shown = []
		for info in self.infos:
			if not keys.matches(info, query):
				continue
			shown.append(info.key)
			top = QTreeWidgetItem([info.key, ', '.join(info.sourceNames), info.place, info.unit, info.shape, info.value or info.sources[0].label])
			top.setData(0, Qt.ItemDataRole.UserRole, info.key)
			top.setToolTip(0, info.title or info.key)
			if info.state != keys.LIVE:
				for column in range(len(COLUMNS)):
					top.setForeground(column, muted)
			flags = top.flags() | Qt.ItemFlag.ItemIsDragEnabled
			top.setFlags(flags)
			self.tree.addTopLevelItem(top)
			if len(info.sources) > 1:
				for source in info.sources:
					child = QTreeWidgetItem(['', source.name, '', source.unit, '', source.label])
					child.setData(0, Qt.ItemDataRole.UserRole, info.writtenFor(source.name))
					child.setToolTip(0, f'Read only {source.name}\'s value: {info.writtenFor(source.name)}')
					child.setFlags(child.flags() | Qt.ItemFlag.ItemIsDragEnabled)
					top.addChild(child)
		self._shown = shown
		self.tree.setUpdatesEnabled(True)
		if keep:
			self.selectKey(keep)
		self._status()

	def _values(self):
		"""The value cells, after the live values moved."""
		table = {i.key: i for i in self.infos}
		for n in range(self.tree.topLevelItemCount()):
			row = self.tree.topLevelItem(n)
			info = table.get(row.data(0, Qt.ItemDataRole.UserRole))
			if info is None:
				continue
			row.setText(5, info.value or info.sources[0].label)
			for k in range(row.childCount()):
				child = row.child(k)
				source = next((s for s in info.sources if s.name == child.text(1)), None)
				if source is not None:
					child.setText(5, source.label)

	def _currentKey(self) -> Optional[str]:
		row = self.tree.currentItem()
		return row.data(0, Qt.ItemDataRole.UserRole) if row is not None else None

	def selectKey(self, key: str) -> bool:
		"""Select the row for ``key`` (a plain key, or ``Source:key``), if it is listed."""
		for n in range(self.tree.topLevelItemCount()):
			row = self.tree.topLevelItem(n)
			for candidate in [row, *(row.child(k) for k in range(row.childCount()))]:
				if candidate.data(0, Qt.ItemDataRole.UserRole) == key:
					self.tree.setCurrentItem(candidate)
					self.tree.scrollToItem(candidate)
					return True
		return False

	def _menu(self, point):
		row = self.tree.itemAt(point)
		if row is None:
			return
		menu = QMenu(self.tree)
		menu.addAction('Set on item', lambda: self.useRow(row))
		menu.addAction('Add to expression', lambda: self.insertKey(row))
		info = self._infoFor(row)
		if info is not None and info.identity and info.place:
			menu.addAction(f'Set on item at {info.place}', lambda: self.useAtPlace(info))
		menu.addAction('Copy key', lambda: self.copyKey(row))
		menu.exec(self.tree.viewport().mapToGlobal(point))

	def copyKey(self, row):
		from PySide6.QtWidgets import QApplication
		QApplication.clipboard().setText(row.data(0, Qt.ItemDataRole.UserRole) or '')

	# the item

	def selectionChanged(self):
		"""The builder selected another item."""
		node = self._node()
		kind = str(node.get('type')) if node is not None else ''
		self.keyed = kind in KEYED and 'preset' not in node
		if self.keyed:
			current = node.get('key')
			self.target.setText(f'Selected: {kind}' + (f', key `{current}`' if current else ', no key'))
			if isinstance(current, str):
				self.selectKey(current)
		elif node is not None and 'preset' in node:
			self.target.setText('The selected item is a preset use: set its key in the Instance or Item tab.')
		else:
			self.target.setText('Select a realtime or graph item to set its key.')
		self._loadPin(node if self.keyed else None)
		self._status()

	def _node(self) -> Optional[dict]:
		b = self.builder
		try:
			node = b.piece.node(b.selection) if b.selection is not None else None
		except Exception:  # noqa: BLE001
			node = None
		return node if isinstance(node, dict) else None

	def _status(self):
		row = self.tree.currentItem()
		self.useButton.setEnabled(row is not None and getattr(self, 'keyed', False))
		self.insertButton.setEnabled(row is not None)
		self.useExpression.setEnabled(getattr(self, 'keyed', False) and bool(self.value()))

	def useRow(self, row) -> bool:
		if row is None:
			return False
		key = row.data(0, Qt.ItemDataRole.UserRole)
		if not getattr(self, 'keyed', False):
			return self.insertKey(row)
		return self.useText(key)

	def useText(self, text: Optional[str], path: Optional[tuple] = None) -> bool:
		"""Set ``text`` as the `key:` of the item at ``path`` (the selected item when None). False when that item takes no key."""
		b = self.builder
		if path is not None and path != b.selection:
			b.select(path)
		node = self._node()
		if not text or node is None or str(node.get('type')) not in KEYED or 'preset' in node:
			return False
		b.editField('key', text)
		b.itemTab.load(b.selection)
		self.selectionChanged()
		return True

	# the expression

	def _infoFor(self, row) -> Optional[keys.KeyInfo]:
		key = row.data(0, Qt.ItemDataRole.UserRole) if row is not None else None
		return next((i for i in self.infos if i.key == key), None)

	def useAtPlace(self, info: keys.KeyInfo) -> bool:
		"""Set the device-less key and its place, so the item follows whichever device sits there."""
		if not getattr(self, 'keyed', False):
			return False
		b = self.builder
		b.editField('key', info.path)
		b.editField('where', info.place)
		b.itemTab.load(b.selection)
		self.selectionChanged()
		return True

	# place and period

	def _placeChoices(self) -> List[str]:
		found = {i.place for i in self.infos if i.place}
		with_parents = {'.'.join(p.split('.')[:n]) for p in found for n in range(1, p.count('.') + 2)}
		return sorted(with_parents)

	def _loadPin(self, node: Optional[dict]):
		for widget in (self.placeBox, self.periodBox, self.usingBox):
			widget.blockSignals(True)
		self.pin.setEnabled(node is not None)
		self.placeBox.clear()
		self.placeBox.addItems(['', *self._placeChoices()])
		node = node or {}
		self.placeBox.setCurrentText(str(node.get('where') or ''))
		self.periodBox.setCurrentText(str(node.get('period') or ''))
		self.usingBox.setCurrentText(keys_using(node.get('using')))
		for widget in (self.placeBox, self.periodBox, self.usingBox):
			widget.blockSignals(False)
		self._pinNote(node)

	def _pinNote(self, node: dict):
		where, period = (node.get('where') or ''), (node.get('period') or '')
		text, bad = [], False
		key = node.get('key')
		if where:
			try:
				where = places.normalizePlace(where)
			except ValueError as error:
				text.append(str(error))
				bad = True
			else:
				found = [i.key for i in self.infos if i.place and places.placeContains(where, i.place) and str(key) == i.path]
				if isinstance(key, str) and ('#' in key or keys.isExpression(key)):
					text.append('The key already names a device or is an expression: where is ignored.')
					bad = True
				elif len(found) == 1:
					text.append(f'Reads {found[0]}.')
				elif found:
					text.append(f'{len(found)} devices are at {where}; an item needs one. Name a single place.')
					bad = True
				else:
					text.append(f'No device with {key} is at {where}.')
					bad = True
		if period and isinstance(key, str):
			try:
				known = {i.key for i in self.infos}
				text.append('Reads ' + periods.resolvePeriod(key, period, node.get('using'), lambda k: str(k) in known) + '.')
			except ValueError as error:
				text.append(str(error))
				bad = True
		self.pinNote.setText('\n'.join(text))
		self.pinNote.setStyleSheet(f'color: {WARN if bad else "palette(placeholder-text)"};')

	def _pinned(self):
		"""Place, period or summary edited: write `where`, `period` and `using` on the selected item."""
		node = self._node()
		if node is None or not getattr(self, 'keyed', False):
			return
		b = self.builder
		place = self.placeBox.currentText().strip() or None
		period = self.periodBox.currentText().strip() or None
		using = self.usingBox.currentText() if period else None
		for field, value in (('where', place), ('period', period), ('using', using)):
			if node.get(field) != value:
				b.editField(field, value)
		self._pinNote(self._node() or {})

	def value(self) -> Optional[str]:
		return self.text.toPlainText().strip() or None

	def setValue(self, text: str):
		with QSignalBlocker(self.text):
			self.text.setPlainText(text)
		self._check()

	def insertText(self, snippet: str):
		self.text.insertPlainText(snippet)
		self.text.setFocus()

	def insertKey(self, row) -> bool:
		if row is None:
			return False
		self.insertText(row.data(0, Qt.ItemDataRole.UserRole))
		return True

	def _check(self):
		text = self.value()
		self.useExpression.setEnabled(getattr(self, 'keyed', False) and bool(text))
		if text is None:
			self.report.setText('')
			self.result.setText('')
			return
		report = keys.checkExpression(text, self.infos)
		self.report.setText(keys.describe(report))
		color = BAD if not report.ok else WARN if report.unknown or report.waiting else 'palette(placeholder-text)'
		self.report.setStyleSheet(f'color: {color};')
		self.result.setText(keys.preview(text) if report.ok else '')


def keys_using(value) -> str:
	"""The summary an item's `using:` names, as the menu spells it."""
	return periods.USING.get(str(value or 'max').lower(), 'max')

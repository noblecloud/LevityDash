"""Dev-only: the Studio builder's Size groups tab: every group of the previewed dashboard with its members, the ones that
match no panel flagged, and a form that sets which group the selected item's text joins through the `matchingGroup` and
`shared:` keys the dashboard file already has. Nothing here changes how groups fit; it writes the same keys by hand.
"""
from typing import List, Optional

from PySide6.QtCore import QRectF, QStringListModel, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
	QCheckBox, QComboBox, QCompleter, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QTreeWidget,
	QTreeWidgetItem, QVBoxLayout, QWidget,
)

from LevityDash.devtools import _studio_groups as groups
from LevityDash.devtools import _studio_tiers as tiers
from LevityDash.devtools import _studio_preset as model

WARN = QColor('#ff5c5c')
NOTE = QColor('#e0a526')
HELP = ('A size group makes the text in it agree on one size per tier. Scope decides how far it reaches: '
        '`global.value` the whole dashboard, `title@name` the panel with that `name:`, `group.title` the nearest group.')


def pathText(path: Optional[tuple]) -> str:
	return ''.join(f'[{i}]' for i in path) if path else ('root' if path == () else '?')


class GroupsTab(QWidget):
	"""The groups of the last preview, and the form that moves the selected item's text between them."""

	def __init__(self, builder):
		super().__init__()
		self.builder = builder
		self.found: List[groups.Group] = []
		self.findings: List[tiers.Finding] = []
		box = QVBoxLayout(self)
		box.setContentsMargins(8, 8, 8, 8)
		self.summary = QLabel()
		self.summary.setWordWrap(True)
		box.addWidget(self.summary)
		self.checks = QListWidget()
		self.checks.setMaximumHeight(96)
		self.checks.setWordWrap(True)
		self.checks.setToolTip('Tier order: a header larger than its labels, a label no larger than its value. Click one to outline the text it is about.')
		self.checks.currentItemChanged.connect(self._checked)
		self.checks.hide()
		box.addWidget(self.checks)
		self.only = QCheckBox('Only the selected item')
		self.only.setToolTip('Show the groups that have text in the selected item or inside it')
		self.only.toggled.connect(lambda _: self._fill())
		box.addWidget(self.only)
		self.tree = QTreeWidget()
		self.tree.setHeaderLabels(['Group', 'Reaches', 'Items', 'Tiers (px)'])
		self.tree.setRootIsDecorated(True)
		self.tree.setColumnWidth(0, 190)
		self.tree.currentItemChanged.connect(self._picked)
		box.addWidget(self.tree, 1)

		form = QGroupBox('Group for the selected item')
		fbox = QFormLayout(form)
		self.role = QComboBox()
		for label, _ in groups.ROLES:
			self.role.addItem(label)
		self.role.setToolTip('Which text: the titles or the values of the readings inside the item (written to its `shared:`), or the item\'s own text')
		self.role.currentIndexChanged.connect(lambda _: self.selectionChanged())
		fbox.addRow('Applies to', self.role)
		self.name = QLineEdit()
		self.name.setPlaceholderText('global.value')
		self.names = QStringListModel(self)
		self.completer = QCompleter(self.names, self)
		self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
		self.name.setCompleter(self.completer)
		fbox.addRow('Group', self.name)
		self.matchAll = QCheckBox('Match the whole tier')
		self.matchAll.setToolTip('Everything of a tier in the group shares one size wherever it is. Without it only boxes within 10 px of each other do.')
		self.matchAll.setChecked(True)
		fbox.addRow('', self.matchAll)
		buttons = QHBoxLayout()
		self.apply = QPushButton('Set')
		self.apply.clicked.connect(self._apply)
		self.remove = QPushButton('Remove')
		self.remove.setToolTip('Take the key out of the item; the text is then in whatever group a panel around it sets')
		self.remove.clicked.connect(self._remove)
		buttons.addWidget(self.apply)
		buttons.addWidget(self.remove)
		buttons.addStretch(1)
		fbox.addRow('', buttons)
		self.current = QLabel()
		self.current.setWordWrap(True)
		fbox.addRow('', self.current)
		box.addWidget(form)
		help_ = QLabel(HELP)
		help_.setWordWrap(True)
		help_.setStyleSheet('color: palette(placeholder-text);')
		box.addWidget(help_)

	# the groups

	def load(self, found: List[groups.Group]):
		self.found = found
		self.names.setStringList(sorted({g.label for g in found if not g.unresolved}))
		self._fill()
		self._fillChecks()
		self.selectionChanged()

	def _fillChecks(self):
		self.checks.clear()
		self.findings = tiers.check(found for found in self.found)
		for f in self.findings:
			row = QListWidgetItem(('⚠ ' if f.severity == tiers.WARN else 'ℹ ') + f.message)
			row.setForeground(QBrush(WARN if f.severity == tiers.WARN else NOTE))
			row.setData(Qt.ItemDataRole.UserRole, f)
			self.checks.addItem(row)
		self.checks.setVisible(bool(self.findings))

	def _checked(self, item, _prev=None):
		finding = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
		self.builder.stage.setMarks(finding.rects if finding is not None else [])

	def shown(self) -> List[groups.Group]:
		path = self.builder.selection
		if self.only.isChecked() and path is not None:
			return [g for g in self.found if g.covers(path)]
		return self.found

	def _fill(self):
		self.tree.clear()
		bad = [g for g in self.found if g.unresolved]
		self.summary.setText(f'{len(self.found)} size groups' + (f', {len(bad)} matching no panel' if bad else '') + '.')
		self.summary.setStyleSheet('color: #ff5c5c;' if bad else '')
		for g in self.shown():
			row = QTreeWidgetItem([g.label, g.reach, str(len(g.members)), ', '.join(map(str, g.tiers))])
			row.setData(0, Qt.ItemDataRole.UserRole, g)
			if g.unresolved:
				row.setText(0, f'⚠ {g.label}')
				row.setToolTip(0, f'No panel is named "{g.unresolved}", so this text is in a group of its own. Name a panel around it `name: {g.unresolved}`, or change the scope.')
				row.setForeground(0, QBrush(WARN))
			for m in g.members:
				leaf = QTreeWidgetItem([f'{pathText(m.path)}  {m.text}', '', '', f'{m.tier} → {m.font:.0f}'])
				leaf.setData(0, Qt.ItemDataRole.UserRole, m)
				row.addChild(leaf)
			self.tree.addTopLevelItem(row)
			if len(g.members) <= 6 or g.unresolved:
				row.setExpanded(True)

	def _picked(self, item, _prev=None):
		rects: List[QRectF] = []
		if item is not None:
			data = item.data(0, Qt.ItemDataRole.UserRole)
			if isinstance(data, groups.Group):
				rects = [m.rect for m in data.members]
				if data.unresolved:
					self.name.setText(f'{data.key}@{data.unresolved}')
			elif isinstance(data, groups.Member):
				rects = [data.rect]
		self.builder.stage.setMarks(rects)

	# the form

	def _field(self) -> str:
		return groups.ROLES[self.role.currentIndex()][1]

	def selectionChanged(self):
		"""The selected item changed: show the group it already names, if any."""
		path = self.builder.selection
		node = self.builder.piece.node(path) if path is not None else None
		ok = node is not None
		for w in (self.role, self.name, self.matchAll, self.apply, self.remove):
			w.setEnabled(ok)
		if self.only.isChecked():
			self._fill()
		if not ok:
			self.current.setText('Select an item in the tree.')
			return
		value = model.getField(node, self._field())
		name, matchAll = groups.spec(value)
		if value is None:
			self.current.setText('Not set on this item.')
		else:
			self.current.setText(f'Set here: {name}' + (' (match all)' if matchAll else ''))
			self.name.setText(name)
			self.matchAll.setChecked(matchAll)

	def _apply(self):
		value = groups.written(self.name.text(), self.matchAll.isChecked())
		if value is not None:
			self.builder.editField(self._field(), value)
			self.selectionChanged()

	def _remove(self):
		self.builder.editField(self._field(), None)
		self.name.clear()
		self.selectionChanged()

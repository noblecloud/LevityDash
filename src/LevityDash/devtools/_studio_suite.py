"""Dev-only: the Studio as one window: the dashboard editor, the gauge editor and the polar editor as modes of one
program, with a library of every preset, example and dashboard beside them.

- Top: the mode switch (Dashboard, Gauge, Polar; Ctrl+1, 2, 3). A mode is built the first time it is shown, so
  starting in one costs nothing for the others (the dashboard mode boots a real dashboard offscreen).
- Left: the library (`_studio_library.py`): a search box over every entry, grouped. A double click opens the entry in
  the mode it belongs to and switches to it. File > Open file... opens any `.levity` and picks the mode from what is
  in it.
- Each mode is the editor it was as a window of its own, embedded. Their undo and save keys act on the visible mode.

The gauge editor lives in `studio.py`, which can also be the running script, so the suite does not import it: the
caller passes a `gauge` factory and the `cells` reader (see `studio.makeSuite`).
"""
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
	QApplication, QDockWidget, QFileDialog, QLineEdit, QMainWindow, QStackedWidget, QToolBar, QTreeWidget,
	QTreeWidgetItem, QVBoxLayout, QWidget,
)

from LevityDash.devtools import _studio_library as library
from LevityDash.devtools import _studio_state as state
from LevityDash.devtools._studio_chrome import THEMES, themePalette, themeSheet

MODES = (('dashboard', 'Dashboard'), ('gauge', 'Gauge'), ('polar', 'Polar'))
KIND_MODE = {library.DASHBOARD: 'dashboard', library.PRESET: 'dashboard', library.GAUGE: 'gauge', library.CELL: 'gauge', library.POLAR: 'polar'}


class Library(QWidget):
	"""The searchable, grouped list of everything the Studio can open."""

	def __init__(self, suite: 'Suite'):
		super().__init__()
		self.suite = suite
		box = QVBoxLayout(self)
		box.setContentsMargins(6, 6, 6, 6)
		self.search = QLineEdit()
		self.search.setPlaceholderText('Search presets, examples, dashboards')
		self.search.setClearButtonEnabled(True)
		self.search.textChanged.connect(self.filter)
		box.addWidget(self.search)
		self.tree = QTreeWidget()
		self.tree.setHeaderHidden(True)
		self.tree.setIndentation(14)
		self.tree.itemActivated.connect(self._activated)
		self.tree.itemDoubleClicked.connect(self._activated)
		box.addWidget(self.tree, 1)
		self.entries: List[library.Entry] = []
		self.refresh()

	def refresh(self):
		self.entries = self.suite.listEntries()
		self.tree.clear()
		groups: Dict[str, QTreeWidgetItem] = {}
		for entry in self.entries:
			if entry.group not in groups:
				top = QTreeWidgetItem([entry.group])
				font = top.font(0)
				font.setBold(True)
				top.setFont(0, font)
				top.setFlags(top.flags() & ~Qt.ItemFlag.ItemIsSelectable)
				self.tree.addTopLevelItem(top)
				groups[entry.group] = top
			leaf = QTreeWidgetItem([entry.label])
			leaf.setData(0, Qt.ItemDataRole.UserRole, entry)
			mode = dict(MODES)[KIND_MODE[entry.kind]]
			leaf.setToolTip(0, f'{mode}' + (f' · {entry.path}' if entry.path else ''))
			groups[entry.group].addChild(leaf)
		for top in groups.values():
			top.setExpanded(top.text(0) in ('Dashboards', 'Presets'))
		self.filter(self.search.text())

	def filter(self, text: str):
		words = text.lower().split()
		for i in range(self.tree.topLevelItemCount()):
			top = self.tree.topLevelItem(i)
			shown = 0
			for j in range(top.childCount()):
				leaf = top.child(j)
				entry = leaf.data(0, Qt.ItemDataRole.UserRole)
				hide = not all(word in entry.search for word in words)
				leaf.setHidden(hide)
				shown += not hide
			top.setHidden(not shown)
			if words and shown:
				top.setExpanded(True)

	def _activated(self, item: QTreeWidgetItem, _column: int = 0):
		entry = item.data(0, Qt.ItemDataRole.UserRole)
		if entry is not None:
			self.suite.openEntry(entry)

	def visibleLabels(self) -> List[str]:
		out = []
		for i in range(self.tree.topLevelItemCount()):
			top = self.tree.topLevelItem(i)
			out += [top.child(j).text(0) for j in range(top.childCount()) if not top.child(j).isHidden()]
		return out


class Suite(QMainWindow):
	"""The Studio window."""

	def __init__(self, path: Optional[Path] = None, mode: Optional[str] = None, gauge: Optional[Callable] = None,
	             cells: Optional[Callable] = None, dashboard: Optional[Callable] = None, polar: Optional[Callable] = None):
		super().__init__()
		self.setWindowTitle('LevityDash Studio')
		self.resize(1760, 980)
		self._factories = {'gauge': gauge, 'dashboard': dashboard, 'polar': polar}
		self._cells = cells
		self.modes: Dict[str, QWidget] = {}
		self.light = False
		app = QApplication.instance()
		theme = THEMES['dark']
		app.setPalette(themePalette(theme))
		app.setStyleSheet(themeSheet(theme))
		self.stack = QStackedWidget()
		self.setCentralWidget(self.stack)
		self._buildBar()
		self.library = Library(self)
		dock = QDockWidget('Library', self)
		dock.setWidget(self.library)
		dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
		dock.setMinimumWidth(200)
		self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
		self.dock = dock
		self._buildMenus()
		start = mode or 'dashboard'
		if path is not None:
			self.openPath(path)
		else:
			self.showMode(start)

	# chrome

	def _buildBar(self):
		bar = QToolBar('Mode')
		bar.setMovable(False)
		self.addToolBar(Qt.ToolBarArea.TopToolBarArea, bar)
		self.modeActions: Dict[str, QAction] = {}
		group = QActionGroup(self)
		group.setExclusive(True)
		for i, (key, label) in enumerate(MODES, 1):
			action = QAction(label, self, checkable=True)
			action.setShortcut(QKeySequence(f'Ctrl+{i}'))
			action.triggered.connect(lambda _=False, k=key: self.showMode(k))
			group.addAction(action)
			bar.addAction(action)
			self.modeActions[key] = action

	def _buildMenus(self):
		menus = self.menuBar()
		file = menus.addMenu('File')
		file.addAction('Open file…', self.openDialog, QKeySequence('Ctrl+O'))
		file.addAction('Refresh library', self.library.refresh)
		view = menus.addMenu('View')
		view.addAction(self.dock.toggleViewAction())

	# modes

	def mode(self, key: str) -> QWidget:
		"""The editor for `key`, built on first use."""
		if key not in self.modes:
			widget = self._factories[key]()
			widget.suite = self
			widget.windowTitleChanged.connect(lambda _t, k=key: self._retitle(k))
			self.stack.addWidget(widget)
			self.modes[key] = widget
		return self.modes[key]

	def showMode(self, key: str) -> QWidget:
		previous = self.current()
		if previous not in (None, key) and (leave := getattr(self.modes[previous], '_leave', None)) is not None:
			leave()
		widget = self.mode(key)
		self.stack.setCurrentWidget(widget)
		self.modeActions[key].setChecked(True)
		if (install := getattr(widget, '_installContext', None)) is not None and getattr(widget, 'layer', widget) is not None:
			install()  # the editor binds its undo and key context when its window is activated; do it when it is shown
		self._retitle(key)
		return widget

	def current(self) -> Optional[str]:
		widget = self.stack.currentWidget()
		return next((k for k, w in self.modes.items() if w is widget), None)

	def _retitle(self, key: str):
		if key != self.current():
			return
		label = dict(MODES)[key]
		inner = self.modes[key].windowTitle()
		self.setWindowTitle('LevityDash Studio · ' + (inner if inner and inner != 'Studio' else label))

	# opening

	def listEntries(self) -> List[library.Entry]:
		from LevityDash.lib import presets as lib
		return library.entries(presetNames=lib.available, cells=self._cells)

	def openEntry(self, entry: library.Entry):
		mode = KIND_MODE[entry.kind]
		widget = self.showMode(mode)
		if entry.kind == library.PRESET:
			widget.openNamed(entry.name)
		elif entry.kind == library.CELL:
			widget.loadEntry(entry.payload, entry.label)
		elif entry.kind == library.DASHBOARD:
			widget.openDashboard(entry.path)
		else:
			widget.loadFile(entry.path)

	def openPath(self, path: Path):
		"""Open any file in the mode that suits what is in it."""
		kind = library.classify(path)
		mode = KIND_MODE[kind]
		widget = self.showMode(mode)
		if kind == library.PRESET:
			widget.openFile(path)
		elif kind == library.DASHBOARD:
			widget.openDashboard(path)
		else:
			widget.loadFile(path)

	def openDialog(self):
		name, _ = QFileDialog.getOpenFileName(self, 'Open a .levity file', str(library.REFERENCES), 'Levity (*.levity *.yaml *.yml)')
		if name:
			self.openPath(Path(name))

	def closeEvent(self, event):
		for widget in self.modes.values():
			widget.close()
			# A closed editor keeps its timers (the sweep, the file watch, the settle and render timers) and the
			# application-wide key and wheel filters it installed, for as long as the window object lives. Left running they slow every window
			# that opens after, which a test run or a long session feels as a hang.
			for timer in widget.findChildren(QTimer):
				timer.stop()
			for child in widget.findChildren(QObject):
				QApplication.instance().removeEventFilter(child)
		super().closeEvent(event)

from enum import Enum
from functools import cached_property
from pathlib import Path
from shutil import get_terminal_size
from typing import Any, Type, Union

from PySide2.QtCore import QPointF, Qt, Slot
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

try:
	from PySide2.QtGui import QActionGroup
except ImportError:
	from PySide2.QtWidgets import QActionGroup, QApplication

from PySide2.QtWidgets import QMenu

from LevityDash.lib.log import debug
from LevityDash.lib.config import userConfig
from LevityDash.lib.plugins import Plugins
from LevityDash.lib.EasyPath import EasyPath
from LevityDash.lib.utils.geometry import AlignmentFlag, Position


class BaseContextMenu(QMenu):
	parent: 'Panel'
	position = QPointF(0, 0)

	def __init__(self, parent, title: str = None, *args: Any, **kwargs: Any):
		super().__init__()
		self.debugActions = QActionGroup(self)
		self.parent = parent
		if title is not None:
			self.setTitle(title)
		self.aboutToShow.connect(self.updateItems)
		self.setMinimumWidth(150)
		self.buildMenuItems()

	@Slot()
	def updateItems(self):
		childMenus = [menu for menu in self.children() if isinstance(menu, QMenu)]
		self.debugActions.setVisible(QApplication.queryKeyboardModifiers() & Qt.KeyboardModifier.AltModifier or debug)
		for menu in childMenus:
			menu.update()
		if hasattr(self, 'freeze'):
			self.freeze.setEnabled(self.parent.hasChildren)

	def uniqueItems(self):
		pass

	def buildMenuItems(self):
		self.uniqueItems()
		self.mainChunk()
		# --------------------- #
		if self.parent.hasChildren and self.parent._acceptsChildren:
			self.freezePanelMenuAction()
		if self.parent._acceptsChildren:
			self.addMenu(InsertMenu(self))
			self.saveLoadMenu()
			self.addSeparator()
		self.debugActions.addAction(self.addAction('Print State', self.printState))
		self.debugActions.addAction(self.addAction('Print Repr', self.printRepr))
		if self.parent.deletable:
			self.addAction('Delete', self.delete)

	def freezePanelMenuAction(self):
		self.freeze = self.addAction('Freeze Panel', self.parent.freeze)
		self.freeze.setCheckable(True)
		self.freeze.setChecked(self.parent.frozen)
		self.freeze.setEnabled(self.parent.hasChildren)
		self.locked = self.addAction('Lock Panel', self.parent.setLocked)
		self.locked.setCheckable(True)
		self.locked.setChecked(self.parent.locked)

	def mainChunk(self):
		self.addSeparator()

		resize = self.addAction('Resizable', self.parent.setResizable)
		resize.setCheckable(True)
		resize.setChecked(self.parent.resizable)
		#
		movable = self.addAction('Movable', self.parent.setMovable)
		movable.setCheckable(True)
		movable.setChecked(self.parent.movable)
		self.geometryMenu()

	def printState(self):
		console = Console(
			soft_wrap=True,
			tab_size=2,
			no_color=False,
			force_terminal=True,
			width=get_terminal_size((100, 20)).columns - 5,
			record=False,
			log_time_format="%H:%M:%S",
		)
		pretty = Pretty(self.parent.state)
		panel = Panel(pretty, title=f'{type(self.parent).__name__} - State')
		console.print(panel)

	def printRepr(self):
		console = Console(
			soft_wrap=True,
			tab_size=2,
			no_color=False,
			force_terminal=True,
			width=get_terminal_size((100, 20)).columns - 5,
			log_time_format="%H:%M:%S",
		)
		pretty = Pretty(self.parent)
		panel = Panel(pretty, title=f'{type(self.parent).__name__} - Repr')
		console.print(panel)

	def saveLoadMenu(self):
		saveAct = self.addAction("Save Panel", self.parent.save)
		loadAct = self.addAction("Load Panel")

	def addPanel(self):
		from LevityDash.lib.ui.frontends.PySide.Modules import Panel
		position = Position(self.position)
		item = Panel(self.parent, position=position)
		item.setFocus(Qt.FocusReason.MouseFocusReason)

	def addLabel(self):
		from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import EditableLabel
		item = EditableLabel(self.parent)
		item.setPos(self.position)

	def gridMenu(self):
		self.grid = self.addMenu('Grid')
		show = self.grid.addAction('Show', self.showGrid)
		show.setCheckable(True)
		show.setChecked(self.parent.showGrid)
		# self.grid.addAction('Snapping')
		self.grid.addAction('Static', self.static)

		self.grid.addAction('Reset', self.resetGrid)

	def snappingMenu(self):
		snapping = self.addMenu('Snapping')
		locMag = snapping.addAction('Position', self.locationSnap)
		locMag.setCheckable(True)
		locMag.setChecked(self.parent.geometry.position.snapping)
		sizeMag = snapping.addAction('Size', self.sizeSnap)
		sizeMag.setCheckable(True)
		sizeMag.setChecked(self.parent.geometry.size.snapping)

	def geometryMenu(self):
		self.geometry = self.addMenu('Geometry')
		self.geometry.setMinimumWidth(150)
		size = self.geometry.addMenu('Size')
		# s = size.addAction('Snap to Grid', lambda: self.parent.geometry.size.width.toggleSnapping())
		# s.setCheckable(True)
		# s.setChecked(self.parent.geometry.size.width.snapping)
		a = size.addAction('Relative Width', lambda: self.parent.geometry.toggleRelative('width'))
		a.setCheckable(True)
		a.setChecked(not self.parent.geometry.size.width.absolute)

		# s = size.addAction('Snap to Grid', lambda: self.parent.geometry.size.height.toggleSnapping())
		# s.setCheckable(True)
		# s.setChecked(self.parent.geometry.size.height.snapping)
		a = size.addAction('Relative Height', lambda: self.parent.geometry.toggleRelative('height'))
		a.setCheckable(True)
		a.setChecked(not self.parent.geometry.size.height.absolute)

		pos = self.geometry.addMenu('Position')
		# s = pos.addAction('Snap to Grid', lambda: self.parent.geometry.position.x.toggleSnapping())
		# s.setCheckable(True)
		# s.setChecked(self.parent.geometry.position.x.snapping)
		a = pos.addAction('Relative X', lambda: self.parent.geometry.toggleRelative('x'))
		a.setCheckable(True)
		a.setChecked(not self.parent.geometry.position.x.absolute)

		# s = pos.addAction('Snap to Grid', lambda: self.parent.geometry.position.y.toggleSnapping())
		# s.setCheckable(True)
		# s.setChecked(self.parent.geometry.position.y.snapping)
		a = pos.addAction('Relative Y', lambda: self.parent.geometry.toggleRelative('y'))
		a.setCheckable(True)
		a.setChecked(not self.parent.geometry.position.y.absolute)

		allRelative = self.geometry.addAction('Relative', lambda: self.setRelative(True))
		allRelative.setCheckable(True)
		allRelative.setChecked(self.parent.geometry.relative)
		allAbsolute = self.geometry.addAction('Absolute', lambda: self.setRelative(False))
		allAbsolute.setCheckable(True)
		allAbsolute.setChecked(not self.parent.geometry.relative)

	def setRelative(self, value):
		self.parent.geometry.relative = value

	def alignmentMenu(self):
		self.addSection('Alignment')
		alignment = self.addMenu('Alignment')
		left = alignment.addAction('Left', lambda: self.parent.setAlignment(AlignmentFlag.Left))
		left.setCheckable(True)
		left.setChecked(self.parent.alignment.horizontal.isLeft)

		horizontalCenter = alignment.addAction('Center', lambda: self.parent.setAlignment(AlignmentFlag.HorizontalCenter))
		horizontalCenter.setCheckable(True)
		horizontalCenter.setChecked(self.parent.alignment.horizontal.isCenter)

		right = alignment.addAction('Right', lambda: self.parent.setAlignment(AlignmentFlag.Right))
		right.setCheckable(True)
		right.setChecked(self.parent.alignment.horizontal.isRight)

		horizontalGroup = QActionGroup(alignment)
		horizontalGroup.addAction(left)
		horizontalGroup.addAction(horizontalCenter)
		horizontalGroup.addAction(right)
		horizontalGroup.setExclusive(True)

		alignment.addSeparator()

		top = alignment.addAction('Top', lambda: self.parent.setAlignment(AlignmentFlag.Top))
		top.setCheckable(True)
		top.setChecked(self.parent.alignment.vertical.isTop)

		verticalCenter = alignment.addAction('Center', lambda: self.parent.setAlignment(AlignmentFlag.VerticalCenter))
		verticalCenter.setCheckable(True)
		verticalCenter.setChecked(self.parent.alignment.vertical.isCenter)

		bottom = alignment.addAction('Bottom', lambda: self.parent.setAlignment(AlignmentFlag.Bottom))
		bottom.setCheckable(True)
		bottom.setChecked(self.parent.alignment.vertical.isBottom)

		verticalGroup = QActionGroup(alignment)
		verticalGroup.addAction(top)
		verticalGroup.addAction(verticalCenter)
		verticalGroup.addAction(bottom)
		verticalGroup.setExclusive(True)

	def debugBreak(self):
		self.parent.debugBreak()

	def delete(self):
		if hasattr(self.parent, 'delete'):
			self.parent.delete()
		else:
			self.parent.scene().removeItem(self.parent)
			self.parent.setParentItem(None)
			self.parent.hide()

	@cached_property
	def window(self):
		return self.parent.scene().view

	@cached_property
	def app(self):
		from PySide2.QtWidgets import QApplication
		return QApplication.instance()


class LabelContextMenu(BaseContextMenu):

	def uniqueItems(self):
		self.alignmentMenu()
		# self.textFilterMenu()
		self.addAction('Edit Margins', self.parent.editMargins)

	def textFilterMenu(self):
		filters = self.addMenu('Text Filters')
		for filter in self.parent.filters:
			name = filter[1:]
			filterAction = filters.addAction(name, lambda filter=filter: self.parent.setFilter(filter))
			# filterAction.triggered.connect(lambda value, filter=filter: self.parent.setFilter(filter, value))
			filterAction.setCheckable(True)
			filterAction.setChecked(filter in self.parent.enabledFilters)


class EditableLabelContextMenu(LabelContextMenu):

	def uniqueItems(self):
		self.addAction('Edit', self.parent.edit)
		super().uniqueItems()


class RealtimeContextMenu(BaseContextMenu):

	def uniqueItems(self):
		self.sources = SourceMenu(self)
		self.addMenu(self.sources)
		self.showTitle = self.addAction('Show Title', self.parent.toggleTitle)
		self.showTitle.setCheckable(True)
		self.showTitle.setChecked(self.parent.splitter.enabled)
		showUnit = self.addAction('Show Unit', self.parent.display.toggleUnit)
		showUnit.setCheckable(True)
		showUnit.setChecked(self.parent.display.displayProperties.unitPosition != 'hidden')
		self.addMenu(LabelContextMenu(self.parent.display.valueTextBox, title="Value"))
		self.addMenu(LabelContextMenu(self.parent.display.unitTextBox, title="Unit"))

	def updateItems(self):
		self.sources.update()
		if self.sources.sources:
			self.sources.setEnabled(True)
		else:
			self.sources.setEnabled(False)
		super(RealtimeContextMenu, self).updateItems()


class MenuFromEnum(QMenu):

	def __init__(self, parent, enum: Type[Enum], action=None, title=None):
		super(MenuFromEnum, self).__init__()
		self.setMinimumWidth(150)
		if isinstance(enum, str):
			if '.' in enum:
				enum = enum.split('.')
				result = parent
				for attr in enum:
					result = getattr(result, attr)
				enum = result
			else:
				enum = getattr(parent, enum)
		self.parent = parent
		self.enum = enum
		self.action = action
		self.selection = None
		self.buildActions()

	def buildActions(self):
		actionGroup = QActionGroup(self)
		actionGroup.setExclusive(True)
		for value in type(self.enum):
			action = self.addAction(value, lambda value=value: self.action(value))
			action.setCheckable(True)
			action.setChecked(value == self.selection)
			actionGroup.addAction(action)


class TimeContextMenu(BaseContextMenu):
	parent: 'Clock'

	def uniqueItems(self):
		insert = self.addMenu('Insert')
		insert.addAction('Time', lambda: self.parent.addItem('%-I:%M'))
		insert.addAction('Date', lambda: self.parent.addItem('%A, %B %-d'))
		insert.addAction('AM/PM', lambda: self.parent.addItem('%p'))
		insert.addAction('Day', lambda: self.parent.addItem('%-d'))
		insert.addAction('Day of Week', lambda: self.parent.addItem('%A'))
		insert.addAction('Day of Week [abbreviated]', lambda: self.parent.addItem('%a'))
		insert.addAction('Month', lambda: self.parent.addItem('%B'))
		insert.addAction('Month [abbreviated]', lambda: self.parent.addItem('%b'))
		insert.addAction('Month [numerical]', lambda: self.parent.addItem('%-m'))

		insert.addAction('Year', lambda: self.parent.addItem('%Y'))
		insert.addAction('Year [abbreviated]', lambda: self.parent.addItem('\'%y'))
		insert.addAction('Custom', self.parent.addCustom)
		insert.addAction('Reset')
		super(TimeContextMenu, self).uniqueItems()


class CentralPanelContextMenu(BaseContextMenu):
	parent: 'CentralPanel'

	def buildMenuItems(self):
		self.addMenu(InsertMenu(self))
		self.addSeparator()
		self.saveLoadMenu()
		self.addSeparator()
		self.addAction('Fullscreen', self.fullsceen)
		self.addAction('Quit', self.app.quit)

	def fullsceen(self):
		w = self.window
		if w.isFullScreen():
			w.showNormal()
		else:
			w.showFullScreen()

	def updateItems(self):
		pass

	def saveLoadMenu(self):
		self.addAction('Load Panal', self.parent.loadPanel)
		self.addAction('Save Dashboard', self.parent.save)
		self.addAction('Load Dashboard', self.parent.load)
		self.addAction('Save Dashboard As...', self.parent.saveAs)
		self.addAction('Load Dashboard From File', self.parent.loadFile)


class InsertMenu(QMenu):

	def __init__(self, parent):
		self.parent = parent
		super(InsertMenu, self).__init__(parent)
		self.aboutToShow.connect(self.updateItems)
		self.setMinimumWidth(150)
		self.setTitle('Insert')
		self.addAction('Group/Empty Panel', self.parent.addPanel)
		# self.templates = TemplateMenu(self, EasyPath(userConfig.userPath).templates.panels)
		# self.addMenu(self.templates)
		# if not self.templates.hasTemplates:
		# 	self.templates.setEnabled(False)
		self.addAction('Graph', self.insertGraph)
		self.addAction('Clock', self.insertClock)
		self.addAction('Label', self.parent.addLabel)
		# self.addAction('Split Panel', self.insertSplitPanel)
		self.addAction('Moon')

	def update(self):
		self.setEnabled(not self.parent.parent.frozen)

	def insertClock(self):
		from LevityDash.lib.ui.frontends.PySide.Modules import Clock
		clock = Clock(self.parent.parent, position=self.parent.position)

	def insertMoon(self):
		from LevityDash.lib.ui.frontends.PySide.Modules import Moon
		moon = Moon(self.parent.parent, position=self.parent.position)

	def insertGraph(self):
		from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import GraphPanel
		graph = GraphPanel(self.parent.parent, position=self.parent.position)

	def insertSplitPanel(self):
		from LevityDash.lib.ui.frontends.PySide.Modules.Containers import SplitPanel
		split = SplitPanel(self.parent.parent, position=self.parent.position)

	def updateItems(self):
		pass
	# self.templates.updateItems()


class PlotContextMenu(BaseContextMenu):
	parent: 'PlotPanel'


class SourceMenu(QMenu):

	def __init__(self, parent):
		self.parent = parent
		super(SourceMenu, self).__init__(parent)
		self.aboutToShow.connect(self.updateItems)
		self.setMinimumWidth(150)
		self.setTitle('Source')
		self.addSources()

	def updateItems(self):
		if self.sources:
			self.setEnabled(True)
		else:
			self.setEnabled(False)
		for action in self.actions():
			action.setChecked(action.source == self.parent.parent.currentSource)

	@property
	def sources(self):
		if self.parent.parent.key is not None:
			return [i for i in Plugins if self.parent.parent.key in i]
		return []

	def addSources(self):
		for k in self.sources:
			name = k.name
			if not hasattr(k, 'realtime'):
				name += ' (not realtime)'
			action = self.addAction(name, lambda k=k: self.changeSource(k))
			action.source = k
			action.setCheckable(True)
			action.setChecked(k == self.parent.parent.currentSource)

	def changeSource(self, source):
		for action in self.actions():
			action.setChecked(action.text().startswith(source.name))
		self.parent.parent.changeSource(source)


class TemplateMenu(QMenu):

	def __init__(self, parent, directoryPath: Union[str, Path], *args, **kwargs):
		self.parent = parent
		self.directoryPath = EasyPath(directoryPath)
		super(TemplateMenu, self).__init__(*args, **kwargs)
		self.setMinimumWidth(150)
		self.setTitle('From Template')

	@property
	def hasTemplates(self) -> bool:
		return bool(self.directoryPath.ls())

	def updateItems(self):
		from LevityDash.lib.ui.frontends.PySide.Modules import PanelFromFile
		templates = [file for file in self.directoryPath.ls() if file.path.name.endswith('.yaml') or 'levity' in file.path.name]
		self.clear()
		if len(templates):
			self.setEnabled(True)
			for file in templates:
				name = '.'.join(file.path.name.split('.')[:-1])
				self.addAction(name, lambda file=file: PanelFromFile(self.parent.parent.parent, file.path, self.parent.parent.position))
		else:
			self.setEnabled(False)


class DashboardTemplates(QMenu):

	def __init__(self, parent):
		self.parent = parent
		super(DashboardTemplates, self).__init__(parent)
		self.setTitle('Open Template')
		for file in EasyPath(userConfig.userPath)['templates']['dashboards'].ls():
			if file.path.name.endswith('.yaml') or file.path.name.endswith('.levity'):
				name = file.name.split('.')[0]
				self.addAction(name, lambda file=file: self.parent.centralWidget().base.loadTemplate(file.path))


__all__ = ['BaseContextMenu', 'LabelContextMenu', 'TimeContextMenu', 'CentralPanelContextMenu', 'EditableLabelContextMenu', 'RealtimeContextMenu']

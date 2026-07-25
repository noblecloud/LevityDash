from enum import Enum
from functools import cached_property, partial
from os import environ
from pathlib import Path
from shutil import get_terminal_size
from typing import Any, Type, Union, TYPE_CHECKING

import yaml
from PySide6.QtCore import QPointF, Qt, Slot, QRect
from PySide6.QtGui import QActionGroup, QAction
from PySide6.QtWidgets import QMenu, QApplication
from rich.box import SIMPLE_HEAVY
from rich.console import Console
from rich.highlighter import RegexHighlighter
from rich.panel import Panel as RichPanel
from rich.pretty import Pretty
from rich.syntax import Syntax
from rich.theme import Theme

from LevityDash import LevityDashboard
from LevityDash.lib.stateful import StatefulDumper
from LevityDash.lib.ui.frontends.PySide.utils import DisplayType
from LevityDash.lib.utils import get
from LevityDash.lib.utils.shared import _Panel

if TYPE_CHECKING:
	from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel

from LevityDash.lib.log import debug
from LevityDash.lib.config import userConfig
from LevityDash.lib.EasyPath import EasyPath
from LevityDash.lib.ui.Geometry import Position, LocationFlag, AlignmentFlag


class DimensionFloatHighlighter(RegexHighlighter):
	base_style = "repr."
	highlights = [r"(?P<number>\d+(\.\d+)?)\s?(?P<str>[a-zA-Z]\w*)"]


theme = Theme({'dimension.number': 'bold magenta', 'dimension.unit': 'white'})


class BaseContextMenu(QMenu):
	parent_item: 'Panel'
	position = QPointF(0, 0)

	def __init__(self, parent, title: str = None, *args: Any, **kwargs: Any):
		super().__init__()
		self.debugActions = QActionGroup(self)
		self.parent_item = parent
		if title is not None:
			self.setTitle(title)
		self.aboutToShow.connect(self.updateItems)
		self.setMinimumWidth(150)
		self.buildMenuItems()

	@Slot()
	def updateItems(self):
		self.groupItems.setVisible(len(self.parent_item.scene().selectedItems()) > 1)
		childMenus = [menu for menu in self.children() if isinstance(menu, QMenu)]
		self.debugActions.setVisible((QApplication.queryKeyboardModifiers() & Qt.KeyboardModifier.AltModifier).value or debug)
		for menu in childMenus:
			menu.update()
		if hasattr(self, 'freeze'):
			self.freeze.setEnabled(self.parent_item.hasChildren)

	def uniqueItems(self):
		pass

	def buildMenuItems(self):
		self.uniqueItems()
		self.mainChunk()
		# --------------------- #
		if self.parent_item.hasChildren and self.parent_item._acceptsChildren:
			self.freezePanelMenuAction()
		if self.parent_item._acceptsChildren:
			self.addAction('Edit Margins', self.parent_item.editMargins)
			self.addMenu(InsertMenu(self))
			# self.saveLoadMenu()
			self.addSeparator()
		self.debugActions.addAction(self.addAction('Print State', self.printState))
		self.debugActions.addAction(self.addAction('Print State Dict', partial(self.printState, dict)))
		self.debugActions.addAction(self.addAction('Print Repr', self.printRepr))
		self.debugActions.addAction(self.addAction('Copy Fingerprint', lambda: QApplication.clipboard().setText(f'{id(self.parent_item):x}')))
		self.debugActions.addAction(self.addAction('Breakpoint', lambda: breakpoint()))
		self.debugActions.addAction(self.addMenu(ChildrenMenu(self)))

		if self.parent_item.deletable:
			self.addAction('Delete', self.delete)

	def freezePanelMenuAction(self):
		self.freeze = self.addAction('Freeze Panel', self.parent_item.freeze)
		self.freeze.setCheckable(True)
		self.freeze.setChecked(self.parent_item.frozen)
		self.freeze.setEnabled(self.parent_item.hasChildren)
		self.locked = self.addAction('Lock Panel', self.parent_item.setLocked)
		self.locked.setCheckable(True)
		self.locked.setChecked(self.parent_item.locked)

	def mainChunk(self):
		self.addSeparator()

		self.groupItems = self.addAction('Group Items', self.parent_item.groupItems)

		resize = self.addAction('Resizable', self.parent_item.setResizable)
		resize.setCheckable(True)
		resize.setChecked(self.parent_item.resizable)
		#
		movable = self.addAction('Movable', self.parent_item.setMovable)
		movable.setCheckable(True)
		movable.setChecked(self.parent_item.movable)
		self.geometryMenu()

	def printState(self, type_: Type = str):
		console = Console(
			soft_wrap=True,
			tab_size=2,
			no_color=False,
			force_terminal=True,
			width=get_terminal_size((100, 20)).columns - 5,
		)
		state = self.parent_item.state if type_ is str else self.parent_item.encodedYAMLState(sort=True)
		yamlStr = yaml.dump(state, Dumper=StatefulDumper, default_flow_style=False, allow_unicode=True)
		width = max(len(line) for line in yamlStr.split('\n')) + 2
		pretty = Syntax(yamlStr, 'yaml', tab_size=2, background_color='default')
		panel = RichPanel(pretty, title=f'{type(self.parent_item).__name__} - State', box=SIMPLE_HEAVY, width=width, padding=0)
		console.print(panel)

	def printRepr(self):
		console = Console(
			highlighter=DimensionFloatHighlighter(),
			theme=theme,
			soft_wrap=True,
			tab_size=2,
			no_color=False,
			force_terminal=True,
			width=get_terminal_size((100, 20)).columns - 5,
		)
		pretty = Pretty(self.parent_item, indent_size=2, indent_guides=True, max_depth=4)
		panel = RichPanel(pretty, title=f'{type(self.parent_item).__name__} - Repr', box=SIMPLE_HEAVY, padding=0)
		console.print(panel)

	def saveLoadMenu(self):
		saveAct = self.addAction("Save Panel", self.parent_item.save)
		loadAct = self.addAction("Load Panel")

	def addPanel(self):
		from LevityDash.lib.ui.frontends.PySide.Modules import Panel
		position = Position(self.position, absolute=True)
		item = Panel(self.parent_item, position=position)
		item.geometry.setAbsoluteRect(QRect(0, 0, 150, 150))
		item.borderProp.edges = LocationFlag.Edges
		item.borderProp.enabled = True
		item.setFocus(Qt.FocusReason.MouseFocusReason)

	def addLabel(self):
		from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import EditableLabel
		item = EditableLabel(self.parent_item)
		item.setPos(self.position)

	def gridMenu(self):
		self.grid = self.addMenu('Grid')
		show = self.grid.addAction('Show', self.showGrid)
		show.setCheckable(True)
		show.setChecked(self.parent_item.showGrid)
		# self.grid.addAction('Snapping')
		self.grid.addAction('Static', self.static)

		self.grid.addAction('Reset', self.resetGrid)

	def snappingMenu(self):
		snapping = self.addMenu('Snapping')
		locMag = snapping.addAction('Position', self.locationSnap)
		locMag.setCheckable(True)
		locMag.setChecked(self.parent_item.geometry.position.snapping)
		sizeMag = snapping.addAction('Size', self.sizeSnap)
		sizeMag.setCheckable(True)
		sizeMag.setChecked(self.parent_item.geometry.size.snapping)

	def geometryMenu(self):
		self.geometry = self.addMenu('Geometry')
		self.geometry.setMinimumWidth(150)
		size = self.geometry.addMenu('Size')
		# s = size.addAction('Snap to Grid', lambda: self.parent_item.geometry.size.width.toggleSnapping())
		# s.setCheckable(True)
		# s.setChecked(self.parent_item.geometry.size.width.snapping)
		a = size.addAction('Relative Width', lambda: self.parent_item.geometry.toggleRelative('width'))
		a.setCheckable(True)
		a.setChecked(not self.parent_item.geometry.size.width.absolute)

		# s = size.addAction('Snap to Grid', lambda: self.parent_item.geometry.size.height.toggleSnapping())
		# s.setCheckable(True)
		# s.setChecked(self.parent_item.geometry.size.height.snapping)
		a = size.addAction('Relative Height', lambda: self.parent_item.geometry.toggleRelative('height'))
		a.setCheckable(True)
		a.setChecked(not self.parent_item.geometry.size.height.absolute)

		pos = self.geometry.addMenu('Position')
		# s = pos.addAction('Snap to Grid', lambda: self.parent_item.geometry.position.x.toggleSnapping())
		# s.setCheckable(True)
		# s.setChecked(self.parent_item.geometry.position.x.snapping)
		a = pos.addAction('Relative X', lambda: self.parent_item.geometry.toggleRelative('x'))
		a.setCheckable(True)
		a.setChecked(not self.parent_item.geometry.position.x.absolute)

		# s = pos.addAction('Snap to Grid', lambda: self.parent_item.geometry.position.y.toggleSnapping())
		# s.setCheckable(True)
		# s.setChecked(self.parent_item.geometry.position.y.snapping)
		a = pos.addAction('Relative Y', lambda: self.parent_item.geometry.toggleRelative('y'))
		a.setCheckable(True)
		a.setChecked(not self.parent_item.geometry.position.y.absolute)

		allRelative = self.geometry.addAction('Relative', lambda: self.setRelative(True))
		allRelative.setCheckable(True)
		allRelative.setChecked(self.parent_item.geometry.relative)
		allAbsolute = self.geometry.addAction('Absolute', lambda: self.setRelative(False))
		allAbsolute.setCheckable(True)
		allAbsolute.setChecked(not self.parent_item.geometry.relative)

	def setRelative(self, value):
		self.parent_item.geometry.relative = value

	def alignmentMenu(self):
		self.addSection('Alignment')
		alignment = self.addMenu('Alignment')
		left = alignment.addAction('Left', lambda: self.parent_item.setAlignment(AlignmentFlag.Left))
		left.setCheckable(True)
		left.setChecked(self.parent_item.alignment.horizontal.isLeft)

		horizontalCenter = alignment.addAction('Center', lambda: self.parent_item.setAlignment(AlignmentFlag.HorizontalCenter))
		horizontalCenter.setCheckable(True)
		horizontalCenter.setChecked(self.parent_item.alignment.horizontal.isCenter)

		right = alignment.addAction('Right', lambda: self.parent_item.setAlignment(AlignmentFlag.Right))
		right.setCheckable(True)
		right.setChecked(self.parent_item.alignment.horizontal.isRight)

		horizontalGroup = QActionGroup(alignment)
		horizontalGroup.addAction(left)
		horizontalGroup.addAction(horizontalCenter)
		horizontalGroup.addAction(right)
		horizontalGroup.setExclusive(True)

		alignment.addSeparator()

		top = alignment.addAction('Top', lambda: self.parent_item.setAlignment(AlignmentFlag.Top))
		top.setCheckable(True)
		top.setChecked(self.parent_item.alignment.vertical.isTop)

		verticalCenter = alignment.addAction('Center', lambda: self.parent_item.setAlignment(AlignmentFlag.VerticalCenter))
		verticalCenter.setCheckable(True)
		verticalCenter.setChecked(self.parent_item.alignment.vertical.isCenter)

		bottom = alignment.addAction('Bottom', lambda: self.parent_item.setAlignment(AlignmentFlag.Bottom))
		bottom.setCheckable(True)
		bottom.setChecked(self.parent_item.alignment.vertical.isBottom)

		verticalGroup = QActionGroup(alignment)
		verticalGroup.addAction(top)
		verticalGroup.addAction(verticalCenter)
		verticalGroup.addAction(bottom)
		verticalGroup.setExclusive(True)

	def debugBreak(self):
		self.parent_item.debugBreak()

	def delete(self):
		if hasattr(self.parent_item, 'delete'):
			self.parent_item.delete()
		else:
			self.parent_item.scene().removeItem(self.parent_item)
			self.parent_item.setParentItem(None)
			self.parent_item.hide()

	def addTitleMenu(self):
		title_label = get(self.parent_item, 'title_label', 'title', getter=getattr)
		titleMenu = LabelContextMenu(title_label, title="Title")
		titlePositions = MenuFromEnum(
			self.parent_item.splitter,
			'titlePosition',
			self.parent_item.splitter.setTitlePosition,
			'Position',
			exclude={'auto', 'inline', 'newline', 'floating', 'center'}
		)
		titleMenu.insertMenu(titleMenu.actions()[0], titlePositions)

		# self.showTitle = self.addAction('Show Title', self.parent_item.toggleTitle)
		# self.showTitle.setCheckable(True)
		# self.showTitle.setChecked(self.parent_item.splitter.enabled)
		self.addMenu(titleMenu)

	@cached_property
	def window(self):
		return self.parent_item.scene().view

	@cached_property
	def app(self):
		from PySide6.QtWidgets import QApplication
		return QApplication.instance()


class ChildrenMenu(QMenu):
	parent_item: 'Panel'

	def __init__(self, parent: 'Panel'):
		self.parent_item: 'Panel' = parent
		super().__init__()
		self.setTitle('Children')
		self.aboutToShow.connect(self._aboutToShow)

	def _aboutToShow(self):
		existing = {a.parent_item: a for a in self.actions() if isinstance(a, BaseContextMenu)}
		self.setVisible(True)
		for child in self.parent_item.parent_item.childItems():
			if child in existing:
				continue
			if (childMenu := getattr(child, 'contextMenu', None)) is not None:
				name = getattr(child, 'stateName', None) or type(child).__name__
				m = self.addMenu(childMenu)
				m.setText(name)
			else:
				for grand_child in child.childItems():
					if grand_child in existing:
						continue
					if (childMenu := getattr(grand_child, 'contextMenu', None)) is not None:
						name = getattr(grand_child, 'stateName', None) or type(grand_child).__name__
						m = self.addMenu(childMenu)
						m.setText(name)
		self.adjustSize()
		if len(self.actions()) == 0:
			self.setVisible(False)

	@cached_property
	def parent_item(self):
		return


class LabelContextMenu(BaseContextMenu):
	marginHandleToggle: QAction

	def uniqueItems(self):
		self.alignmentMenu()
		# self.textFilterMenu()
		self.marginHandleToggle = self.addAction('Show Margin Handles', self.parent_item.editMargins)
		fillType = MenuFromEnum(
			self.parent_item,
			'textBox._scaleType',
			self.parent_item.textBox.setScaleType,
			'Scale Type',
		)
		self.addMenu(fillType)

	def textFilterMenu(self):
		filters = self.addMenu('Text Filters')
		for filter in self.parent_item.filters:
			name = filter[1:]
			filterAction = filters.addAction(name, lambda filter=filter: self.parent_item.setFilter(filter))
			# filterAction.triggered.connect(lambda value, filter=filter: self.parent_item.setFilter(filter, value))
			filterAction.setCheckable(True)
			filterAction.setChecked(filter in self.parent_item.enabledFilters)

	def toggleMarginHandles(self):
		shown = self.parent_item.marginHandles.forceDisplay
		self.marginHandleToggle.setText('Hide Margin Handles' if shown else 'Show Margin Handles')
		self.parent_item.editMargins(not shown)


class TitledPanelContextMenu(BaseContextMenu):
	parent_item: 'TitledPanel'

	def uniqueItems(self):
		self.addTitleMenu()
		bodyMenu = self.parent_item.contents.contextMenu
		bodyMenu.setTitle('Body')
		bodyMenu.addAction('Clear', self.parent_item.clear)
		self.addMenu(bodyMenu)


class EditableLabelContextMenu(LabelContextMenu):

	def uniqueItems(self):
		self.addAction('Edit', self.parent_item.edit)
		super().uniqueItems()


class RealtimeContextMenu(BaseContextMenu):
	parent_item: 'Realtime'

	def uniqueItems(self):
		self.sources = SourceMenu(self)
		self.addMenu(self.sources)

		# showUnit = self.addAction('Show Unit', self.parent_item.display.toggleUnit)
		# showUnit.setCheckable(True)
		# showUnit.setChecked(self.parent_item.display.displayProperties.unitPosition != 'hidden')

		if self.parent_item.display.displayType is DisplayType.Text:
			valueContextMenu = self.parent_item.display.valueTextBox.contextMenu
			valueContextMenu.setTitle('Value')

			self.addTitleMenu()
			self.addMenu(valueContextMenu)
			self.addUnitMenu()

	# self.directionItems()

	def addUnitMenu(self):
		unitMenu = self.parent_item.display.unitTextBox.contextMenu
		unitMenu.setTitle('Unit')
		unitPositions = MenuFromEnum(
			self.parent_item.display,
			'displayProperties.unitPosition',
			self.parent_item.display.setUnitPosition,
			'Position',
			exclude={'floating'}
		)
		unitMenu.insertMenu(unitMenu.actions()[0], unitPositions)
		self.addMenu(unitMenu)

	def updateItems(self):
		self.sources.update()
		if self.sources.sources:
			self.sources.setEnabled(True)
		else:
			self.sources.setEnabled(False)
		super(RealtimeContextMenu, self).updateItems()

	def directionItems(self):
		directionMenu = self.addMenu('Direction')
		hor = directionMenu.addAction('Horizontal', lambda: self.setDirection('h'))
		hor.setCheckable(True)
		hor.setChecked(self.parent_item.splitter.location.isHorizontal)
		vert = directionMenu.addAction('Vertical', lambda: self.setDirection('v'))
		vert.setCheckable(True)
		hor.setChecked(self.parent_item.splitter.location.isVertical)
		group = QActionGroup(directionMenu)
		group.addAction(hor)
		group.addAction(vert)
		group.setExclusive(True)

	def setDirection(self, direction: str):
		if direction == 'h':
			self.parent_item.splitter.location = LocationFlag.Horizontal
		else:
			self.parent_item.splitter.location = LocationFlag.Vertical


class MenuFromEnum(QMenu):

	def __init__(self, parent, enum: Type[Enum] | str, action=None, title=None, exclude=None):
		self._exclude = exclude or set()
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
		self.setTitle(title or enum.__name__)
		self.parent_item = parent
		self.enum = enum
		self.action = action
		self.selection = enum
		self.buildActions()

	def buildActions(self):
		actionGroup = QActionGroup(self)
		actionGroup.setExclusive(True)
		for value in type(self.enum):
			if value in self._exclude:
				continue
			action = self.addAction(value.title(), lambda value=value: self.action(value))
			action.setCheckable(True)
			action.setChecked(value == self.selection)
			actionGroup.addAction(action)


class TimeContextMenu(BaseContextMenu):
	parent_item: 'Clock'

	def uniqueItems(self):
		insert = self.addMenu('Insert')
		insert.addAction('Time', lambda: self.parent_item.addItem(f'%-I:%M'))
		insert.addAction('Date', lambda: self.parent_item.addItem('%A, %B %-d'))
		insert.addAction('AM/PM', lambda: self.parent_item.addItem('%p'))
		insert.addAction('Day', lambda: self.parent_item.addItem('%-d'))
		insert.addAction('Day of Week', lambda: self.parent_item.addItem('%A'))
		insert.addAction('Day of Week [abbreviated]', lambda: self.parent_item.addItem('%a'))
		insert.addAction('Month', lambda: self.parent_item.addItem('%B'))
		insert.addAction('Month [abbreviated]', lambda: self.parent_item.addItem('%b'))
		insert.addAction('Month [numerical]', lambda: self.parent_item.addItem('%-m'))

		insert.addAction('Year', lambda: self.parent_item.addItem('%Y'))
		insert.addAction('Year [abbreviated]', lambda: self.parent_item.addItem('\'%y'))
		insert.addAction('Custom', self.parent_item.addCustom)
		insert.addAction('Reset')
		super(TimeContextMenu, self).uniqueItems()


class CentralPanelContextMenu(BaseContextMenu):
	parent_item: 'CentralPanel'

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
		self.addAction('Load Panal', self.parent_item.loadPanel)
		self.addAction('Save Dashboard', self.parent_item.save)
		self.addAction('Load Dashboard', self.parent_item.load)
		self.addAction('Save Dashboard As...', self.parent_item.saveAs)
		self.addAction('Load Dashboard From File', self.parent_item.loadFile)


class InsertMenu(QMenu):

	def __init__(self, parent):
		self.parent_item = parent
		super(InsertMenu, self).__init__(parent)
		self.aboutToShow.connect(self.updateItems)
		self.setMinimumWidth(150)
		self.setTitle('Insert')
		self.addAction('Group/Empty Panel', self.parent_item.addPanel)
		# self.templates = TemplateMenu(self, EasyPath(userConfig.userPath).templates.panels)
		# self.addMenu(self.templates)
		# if not self.templates.hasTemplates:
		# 	self.templates.setEnabled(False)
		self.addAction('Graph', self.insertGraph)
		self.addAction('Clock', self.insertClock)
		self.addAction('Label', self.parent_item.addLabel)
		# self.addAction('Split Panel', self.insertSplitPanel)
		self.addAction('Moon')

	def update(self):
		self.setEnabled(not self.parent_item.parent_item.frozen)

	def insertClock(self):
		from LevityDash.lib.ui.frontends.PySide.Modules import Clock
		clock = Clock(self.parent_item.parent, position=self.parent_item.position)

	def insertMoon(self):
		from LevityDash.lib.ui.frontends.PySide.Modules import Moon
		moon = Moon(self.parent_item.parent, position=self.parent_item.position)

	def insertGraph(self):
		from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import GraphPanel
		graph = GraphPanel(self.parent_item.parent, position=self.parent_item.position)

	def insertSplitPanel(self):
		from LevityDash.lib.ui.frontends.PySide.Modules.Containers import SplitPanel
		split = SplitPanel(self.parent_item.parent, position=self.parent_item.position)

	def updateItems(self):
		pass
	# self.templates.updateItems()


class PlotContextMenu(BaseContextMenu):
	parent_item: 'Plot'


class SourceMenu(QMenu):

	def __init__(self, parent):
		self.parent_menu = parent
		super(SourceMenu, self).__init__(parent)
		self.aboutToShow.connect(self.updateItems)
		self.group = QActionGroup(self)
		self.group.setExclusive(True)
		self.setMinimumWidth(150)
		self.setTitle('Source')
		self.updateItems()

	def updateItems(self):
		if self.sources:
			self.setEnabled(True)
		else:
			self.setEnabled(False)
		self.clear()
		self.addSources()
		# for action in self.actions():
		# 	action.setChecked(action.source == self.parent_item.parent_item.currentSource)

	@property
	def sources(self):
		# See TimeseriesSourceMenu.sources in Displays/Graph.py - same fix:
		# local plugins are loaded but never started in mode=remote, so
		# `key in plugin` was False for all of them and this menu came up
		# empty. The dispatcher's container is populated in both modes.
		key = self.parent_menu.parent_menu.key
		if key is None:
			return []
		container = LevityDashboard.get_container(key, None)
		if container is None:
			return []
		return [c.source for c in container.values()]

	def addSources(self):
		for k in self.sources:
			name = k.name
			if not hasattr(k, 'realtime'):
				name += ' (not realtime)'
			action = self.addAction(name, lambda k=k: self.changeSource(k))
			action.source = k
			action.setCheckable(True)
			action.setChecked(k == self.parent_menu.parent_menu.currentSource)

	def changeSource(self, source):
		for action in self.actions():
			action.setChecked(action.text().startswith(source.name))
		self.parent_menu.parent_menu.changeSource(source)


class TemplateMenu(QMenu):

	def __init__(self, parent, directoryPath: Union[str, Path], *args, **kwargs):
		self.parent_item = parent
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
				self.addAction(name, lambda file=file: PanelFromFile(self.parent_item.parent_menu.parent, file.path, self.parent_item.parent_menu.position))
		else:
			self.setEnabled(False)


class DashboardTemplates(QMenu):

	def __init__(self, parent):
		self.parent_item = parent
		super(DashboardTemplates, self).__init__(parent)
		self.setTitle('Open Template')
		for file in EasyPath(userConfig.userPath)['templates']['dashboards'].ls():
			if file.path.name.endswith('.yaml') or file.path.name.endswith('.levity'):
				name = file.name.split('.')[0]
				self.addAction(name, lambda file=file: self.parent_item.centralWidget().base.loadTemplate(file.path))


__all__ = ['BaseContextMenu', 'LabelContextMenu', 'TimeContextMenu', 'CentralPanelContextMenu', 'EditableLabelContextMenu', 'RealtimeContextMenu']

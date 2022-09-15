from functools import cached_property
from typing import List

from LevityDash.lib.stateful import DefaultGroup, Stateful, StateProperty
from LevityDash.lib.ui.frontends.PySide.Modules import NonInteractivePanel, Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Label import TitleLabel
from LevityDash.lib.ui.frontends.PySide.Modules.Handles.Splitters import TitleValueSplitter
from LevityDash.lib.ui.frontends.PySide.Modules.Menus import TitledPanelContextMenu


class TitledPanel(Panel, tag='titled-group'):
	class ContentsPanel(NonInteractivePanel, tag=...):
		__exclude__ = {'geometry'}
		pass

	title: TitleLabel
	contents: Panel
	splitter: TitleValueSplitter

	@StateProperty(sort=True, sortKey=lambda x: x.geometry.sortValue, default=DefaultGroup(None, []), dependencies={'geometry', 'margins', 'title'})
	def items(self) -> List[Panel]:
		return self.contents.items

	@items.setter
	def items(self, value: List[Panel]):
		self.contents.items = value

	@cached_property
	def contents(self) -> Panel:
		return TitledPanel.ContentsPanel(self)

	@cached_property
	def title(self):
		return TitleLabel(self, stateKey=TitleValueSplitter.title)

	@StateProperty(key='title', sortOrder=1, allowNone=False, default=Stateful, link=TitleValueSplitter)
	def splitter(self) -> TitleValueSplitter:
		return self._splitter

	@splitter.setter
	def splitter(self, value: TitleValueSplitter):
		self._splitter = value
		value.hide()

	@splitter.decode
	def splitter(self, value: dict | bool | float | str) -> dict:
		match value:
			case bool(value):
				value = {'visible': value}
			case float(value):
				value = {'ratio': value}
			case str(value):
				value = {'text': value}
			case _:
				pass
		return value

	@splitter.factory
	def splitter(self) -> TitleValueSplitter:
		return TitleValueSplitter(surface=self, title=self.title, value=self.contents)

	@cached_property
	def contextMenu(self):
		return TitledPanelContextMenu(self)

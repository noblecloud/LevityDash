import re
from functools import cached_property
from platform import system as syscheck
from types import SimpleNamespace
from typing import ClassVar, List

from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import QDialog, QInputDialog
from time import strftime

from LevityDash import LevityDashboard
from LevityDash.lib.stateful import StateProperty
from LevityDash.lib.ui.frontends.PySide import app, UILogger as guiLog
from LevityDash.lib.ui.frontends.PySide.Modules.Displays import Label
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Text import ScaleType, Text
from LevityDash.lib.ui.frontends.PySide.Modules.Menus import TimeContextMenu
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from LevityDash.lib.ui.frontends.PySide.utils import itemLoader
from LevityDash.lib.utils.shared import connectSignal, disconnectSignal, levenshtein

__all__ = ['ClockComponent', 'Clock']
log = guiLog.getChild(__name__)


class ClockComponent(Label, tag=...):
	__hourlyFormats__: ClassVar[set[str]] = {'%h', '%I', '%p'}
	_text: str
	_acceptsChildren = False
	savable = True

	__defaults__ = {
		'format':  '%-I:%M',
		'margins': ('0.25mm', '0.25mm', '0.25mm', '0.25mm'),
		'text-scale-type': ScaleType.fill
	}

	__exclude__ = {'text'}


	class ClockTextBox(Text):
		_scaleType = ScaleType.fill


	def __init__(self, parent: Panel, *args, **kwargs):
		"""
		:param parent:
		:type Clock:
		:param format:
		:type str:
		:param filters:
		:type list[str|Callable]:
		"""
		formatStr = kwargs.pop('format', None)
		if syscheck() == 'Windows':
			formatStr = formatStr.replace('%-', '%#')
		self._format = formatStr

		text = strftime(formatStr)
		super(ClockComponent, self).__init__(parent, text=text, *args, **kwargs)
		self.connectTimer()

	@cached_property
	def textBox(self) -> ClockTextBox:
		box = ClockComponent.ClockTextBox(self)
		box.setParentItem(self)
		return box

	def connectTimer(self):
		connectSignal(self.timer, self.setTime)

	def disconnectTimer(self):
		disconnectSignal(self.timer, self.setTime)

	@property
	def timer(self) -> Signal:
		matches = re.finditer(r"\%-?\w", self._format, re.MULTILINE)
		matches = {x.group().replace('-', '').lower() for x in matches}
		if '%s' in matches:
			return LevityDashboard.clock.second
		elif '%m' in matches:
			return LevityDashboard.clock.minute
		elif self.__hourlyFormats__.intersection(matches):
			return LevityDashboard.clock.hour
		else:
			return LevityDashboard.clock.minute

	def setTime(self, *args):
		self.text = strftime(self.format)

	@StateProperty(sortOrder=0, required=True)
	def format(self) -> str:
		return self._format

	@format.setter
	def format(self, value):
		if self._format != value:
			if syscheck() == "Windows":
				value = value.replace('%-', '%#')
			disconnectSignal(self.timer, self.setTime)
			self._format = value
			self.setTime()
			self.timer.connect(self.setTime)

	def setFormat(self):
		dialog = QInputDialog()
		dialog.setInputMode(QInputDialog.TextInput)
		dialog.setLabelText('Format:')
		dialog.setTextValue(self.format)
		dialog.setWindowTitle('Custom Format')
		dialog.setWindowModality(Qt.WindowModal)
		dialog.setModal(True)
		dialog.exec_()
		if dialog.result() == QDialog.Accepted:
			format = dialog.textValue()
		self.format = format
		self.update()

	@property
	def name(self):
		return self.format


class Clock(Panel, tag='clock'):
	defaultStackType = ClockComponent

	def __init__(self, *args, **kwargs):
		super(Clock, self).__init__(*args, **kwargs)

	@StateProperty
	def items(self) -> List[ClockComponent]:
		pass

	@items.setter
	def items(self, value):
		self.geometry.updateSurface()
		if isinstance(value, dict):
			raise ValueError('Clock items must be a list of dictionaries')
		existing = self.items if 'items' in self._set_state_items_ else []
		existingNonClocks = [x for x in existing if not isinstance(x, ClockComponent)]
		existingClocks = [x for x in existing if isinstance(x, ClockComponent)]
		others = []
		for item in value:
			ns = SimpleNamespace(**item)
			match item:
				case {'format': _, **rest}:
					match existingClocks:
						case []:
							ClockComponent(self, **item)
						case [ClockComponent(format=ns.format) as existingItem, *_]:
							existingClocks.remove(existingItem)
							existingItem.state = item
						case [*_]:
							closestMatch = min(existingClocks, key=lambda x: (
								x.geometry.scoreSimilarity(ns.geometry), levenshtein(x.format, ns.format)
							))
							closestMatch.state = item
							existingClocks.remove(closestMatch)
						case _:
							ClockComponent(self, **item)
				case {'type': _, **rest}:
					others.append(item)
		itemLoader(self, others, existingNonClocks)

	@property
	def name(self):
		if self._name is None:
			return f'ClockPanel 0x{self.uuidShort}'
		return self._name

	@name.setter
	def name(self, value):
		if value is not None:
			self._name = str(value)

	@cached_property
	def contextMenu(self):
		return TimeContextMenu(self)

	def addItem(self, format: str):
		item = ClockComponent(parent=self, format=format)

	def addCustom(self):
		dialog = QInputDialog()
		dialog.setInputMode(QInputDialog.TextInput)
		dialog.setLabelText('Format:')
		dialog.setTextValue('')
		dialog.setWindowTitle('Custom Format')
		dialog.setWindowModality(Qt.WindowModal)
		dialog.setModal(True)
		dialog.exec_()
		if dialog.result() == QDialog.Accepted:
			format = dialog.textValue()
		item = ClockComponent(parent=self, format=format)

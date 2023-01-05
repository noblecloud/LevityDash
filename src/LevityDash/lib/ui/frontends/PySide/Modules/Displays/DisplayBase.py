from abc import abstractmethod

from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.utils import DisplayType


class Display(Panel, tag=...):
	__exclude__ = {'items', 'geometry', 'locked', 'frozen', 'movable', 'resizable', 'text'}

	__defaults__ = {
		'displayType': DisplayType.Text,
		'geometry':    {'x': 0, 'y': 0.2, 'width': 1.0, 'height': 0.8},
		'movable':     False,
		'resizable':   False,
		'locked':      True,
	}

	@property
	@abstractmethod
	def type(self) -> DisplayType: ...

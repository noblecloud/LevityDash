import re
from datetime import datetime, timedelta
from functools import cached_property
from typing import Any, Union

from PySide2.QtCore import QObject, Qt, QTimer, Signal
from PySide2.QtWidgets import QDialog, QInputDialog

from LevityDash.lib.ui.frontends.PySide.Modules import itemLoader
from LevityDash.lib.ui.frontends.PySide.Modules.Label import Label
from LevityDash.lib.ui.frontends.PySide.Modules.Menus import TimeContextMenu
from LevityDash.lib.ui.frontends.PySide.Modules.Panel import Panel
from time import strftime

__all__ = ['ClockComponent', 'Clock', 'baseClock']

from LevityDash.lib.log import LevityGUILog as guiLog

log = guiLog.getChild(__name__)

from LevityDash.lib.utils.shared import disconnectSignal
from LevityDash.lib.utils.geometry import Margins
from platform import system as syscheck

class ClockSignals(QObject):
	second = Signal(int)
	minute = Signal(int)
	hour = Signal(int)
	sync = Signal()

	syncInterval = timedelta(minutes=5)

	def __init__(self):
		super().__init__()
		self.__init_timers_()

	def __init_timers_(self):
		self.__secondTimer = QTimer()
		self.__secondTimer.setTimerType(Qt.PreciseTimer)
		self.__secondTimer.setInterval(1000)
		self.__secondTimer.timeout.connect(self.__emitSecond)

		self.__minuteTimer = QTimer()
		self.__minuteTimer.setInterval(60000)
		self.__minuteTimer.timeout.connect(self.__emitMinute)
		self.__hourTimer = QTimer()
		self.__hourTimer.setInterval(3600000)
		self.__hourTimer.timeout.connect(self.__emitHour)

		self.__syncTimers()

		# Ensures that the timers are synced to the current time every six hours
		self.__syncTimer = QTimer()
		self.__syncTimer.timeout.connect(self.__syncTimers)
		self.__syncTimer.setInterval(1000*60*5)
		self.__syncTimer.setTimerType(Qt.VeryCoarseTimer)
		self.__syncTimer.setSingleShot(False)
		self.__syncTimer.start()

	def __startSeconds(self):
		self.__emitSecond()
		self.__secondTimer.setSingleShot(False)
		self.__secondTimer.start()
		log.verbose('Second timer started')

	def __startMinutes(self):
		self.__emitMinute()
		self.__minuteTimer.setSingleShot(False)
		self.__minuteTimer.start()
		log.verbose('Minute timer started')

	def __startHours(self):
		self.__emitHour()
		self.__hourTimer.setSingleShot(False)
		self.__hourTimer.start()
		log.verbose('Hour timer started')

	def __emitSecond(self):
		# now = datetime.now()
		# diff = now.replace(second=now.second + 1, microsecond=0) - now
		self.second.emit(datetime.now().second)

	def __emitMinute(self):
		minute = datetime.now().minute
		log.verbose(f'Minute timer emitted with value {minute}')
		self.minute.emit(minute)

	def __emitHour(self):
		hour = datetime.now().hour
		log.verbose(f'Hour timer emitted with value {hour}')
		self.hour.emit(hour)

	def __syncTimers(self):
		"""Synchronizes the timers to the current time."""

		self.sync.emit()

		self.__secondTimer.stop()
		self.__minuteTimer.stop()
		self.__hourTimer.stop()

		now = datetime.now()

		# Offset the timers by 10ms to ensure that the timers are synced to the current time
		# otherwise, the time will be announced
		timerOffset = 10

		timeToNextSecond = round((now.replace(second=now.second, microsecond=0) + timedelta(seconds=1) - now).total_seconds()*1000)
		self.__secondTimer.singleShot(timeToNextSecond + timerOffset, self.__startSeconds)

		timeToNextMinute = round((now.replace(minute=now.minute, second=0, microsecond=0) + timedelta(minutes=1) - now).total_seconds()*1000)
		log.verbose(f'Time to next minute: {timeToNextMinute/1000} seconds')
		self.__minuteTimer.singleShot(timeToNextMinute + timerOffset, self.__startMinutes)

		timeToNextHour = round((now.replace(hour=now.hour, minute=0, second=0, microsecond=0) + timedelta(hours=1) - now).total_seconds()*1000)
		log.verbose(f'Time to next hour: {timeToNextHour/1000} seconds')
		self.__hourTimer.singleShot(timeToNextHour + timerOffset, self.__startHours)


baseClock = ClockSignals()


class ClockComponent(Label):
	_format = '%-I:%M'
	_text: str = ''
	__hourlyFormats = {'%h', '%I', '%p'}
	_acceptsChildren = False
	savable = True
	defaultMargins = (0, 0, 0, 0)

	def __init__(self, parent: Union['Panel', 'LevityScene'], format: str = None, *args, **kwargs):
		format = format or self._format
		kwargs.pop('text', None)
		if syscheck() == 'Windows':
			format = format.replace('%-', '%#')
		self._format = format
		text = strftime(format)
		kwargs['margins'] = {'top': 0, 'bottom': 0, 'left': 0, 'right': 0}
		super(ClockComponent, self).__init__(parent, text=text, *args, **kwargs)
		self.updateFromGeometry()
		self.connectTimer()

	def connectTimer(self):
		self.timer.connect(self.setTime)

	@property
	def timer(self) -> Signal:
		matches = re.finditer(r"\%-?\w", self._format, re.MULTILINE)
		matches = {x.group().replace('-', '').lower() for x in matches}
		if '%s' in matches:
			return baseClock.second
		elif '%m' in matches:
			return baseClock.minute
		elif self.__hourlyFormats.intersection(matches):
			return baseClock.hour
		else:
			return baseClock.minute

	def setTime(self, *args):
		self.text = strftime(self.format)

	# self.textBox.value = self.text
	# self.textBox.setPlainText(self.text)
	# self.textBox.updateTransform()

	@property
	def format(self):
		return self._format

	@format.setter
	def format(self, value):
		if self._format != value:
			if syscheck() == "Windows":
				value = value.replace('%-', '%#')
			self._format = value
			self.setTime()
			disconnectSignal(self.timer, self.setTime)
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

	@property
	def state(self):
		state = {
			'format':   self.format.replace('%#', '%-'),
			'geometry': self.geometry,
		}
		if self.filters:
			state['filters'] = tuple(self.filters)
		if self.margins != Margins.zero():
			state['margins'] = self.margins
		if not self.alignment.isDefault():
			state['alignment'] = self.alignment
		return state


class Clock(Panel):
	def __init__(self, *args, **kwargs):
		super(Clock, self).__init__(*args, **kwargs)
		if 'items' not in kwargs:
			time = ClockComponent(self)
			time.setRect(self.parent.rect())
			time.setLocked(True)
		self.neverReleaseChildren = True
		self.updateFromGeometry()

	def _loadChildren(self, childItems: list[dict[str, Any]]):
		if isinstance(childItems, dict):
			for name, item in childItems.items():
				if 'class' in item:
					self.loadChildFromState(item)
				else:
					ClockComponent(self, format=name, **item)
		else:
			for item in childItems:
				if 'type' in item:
					item = itemLoader(self, item)
				else:
					ClockComponent(self, **item)

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

	@property
	def state(self):
		state = super(Clock, self).state
		state.pop('grid', None)
		return state

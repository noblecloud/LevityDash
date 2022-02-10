from src import logging
import re
from datetime import datetime, timedelta
from functools import cached_property

from PySide2.QtCore import QObject, Qt, QTimer, Signal
from PySide2.QtWidgets import QDialog, QInputDialog, QMenu

from time import strftime
from typing import Union

from src.Modules.Panel import Panel
from src.Modules.Label import Label
from src.Modules.Menus import TimeContextMenu

__all__ = ['ClockComponent', 'Clock']

log = logging.getLogger(__name__)

from src.utils import disconnectSignal


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
		self.__syncTimer.setInterval(1000 * 60 * 5)
		self.__syncTimer.setTimerType(Qt.VeryCoarseTimer)
		self.__syncTimer.setSingleShot(False)
		self.__syncTimer.start()

	def __startSeconds(self):
		self.__secondTimer.setSingleShot(False)
		self.__secondTimer.start()

	def __startMinutes(self):
		self.__minuteTimer.setSingleShot(False)
		self.__minuteTimer.start()

	def __startHours(self):
		self.__hourTimer.setSingleShot(False)
		self.__hourTimer.start()

	def __emitSecond(self):
		# now = datetime.now()
		# diff = now.replace(second=now.second + 1, microsecond=0) - now
		self.second.emit(datetime.now().second)

	def __emitMinute(self):
		self.minute.emit(datetime.now().minute)

	def __emitHour(self):
		self.hour.emit(datetime.now().hour)

	def __syncTimers(self):
		'''
			Synchronizes the timers to the current time.
		'''

		self.sync.emit()

		self.__secondTimer.stop()
		self.__minuteTimer.stop()
		self.__hourTimer.stop()

		now = datetime.now()

		timeToNextSecond = round((now.replace(second=now.second, microsecond=0) + timedelta(seconds=1) - now).total_seconds() * 1000)
		self.__secondTimer.singleShot(timeToNextSecond, self.__startSeconds)

		timeToNextMinute = round((now.replace(minute=now.minute, second=0, microsecond=0) + timedelta(minutes=1) - now).total_seconds() * 1000)
		log.info(f'Time to next minute: {timeToNextMinute / 1000} seconds')
		self.__minuteTimer.singleShot(timeToNextMinute, self.__startMinutes)

		timeToNextHour = round((now.replace(hour=now.hour, minute=0, second=0, microsecond=0) + timedelta(hours=1) - now).total_seconds() * 1000)
		log.info(f'Time to next hour: {timeToNextHour / 1000} seconds')
		self.__hourTimer.singleShot(timeToNextHour, self.__startHours)


baseClock = ClockSignals()


class ClockComponent(Label):
	_format = '%-I:%M'
	_text: str = ''
	__hourlyFormats = {'%h', '%I', '%p'}
	_acceptsChildren = False

	def __init__(self, parent: Union['Panel', 'GridScene'], format: str = None, *args, **kwargs):
		if format is not None:
			self._format = format
		else:
			format = self._format
		kwargs.pop('text', None)
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

	@property
	def format(self):
		return self._format

	@format.setter
	def format(self, value):
		if self._format != value:
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
	def state(self):
		state = super(ClockComponent, self).state
		state['format'] = self.format
		return state


class Clock(Panel):
	def __init__(self, *args, **kwargs):
		super(Clock, self).__init__(*args, **kwargs)
		if 'childItems' not in kwargs:
			time = ClockComponent(self)
			time.setRect(self.parent.rect())
			time.setLocked(True)
		self.neverReleaseChildren = True
		self.updateFromGeometry()

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
		return super(Clock, self).state

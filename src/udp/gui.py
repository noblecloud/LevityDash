import json
import logging
from pathlib import Path

from PyQt5.QtWidgets import (QApplication, QDesktopWidget)
from PySide2.QtNetwork import QUdpSocket

from units.defaults.weatherFlow.units import Wind
from widgets.Submodule import windRose, Submodule
from ui.wind_UI import Ui_Frame as windUI


class windSubmodule(windUI, Submodule):

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.setupUi(self)
		self.directionLabel.move(-10, 0)
		self.layout()
		self.windRose = windRose(self.mainFrame)
		self.windRose.setObjectName(u"windRose")
		self.unit.hide()

		rootPath = Path(__file__).parent.parent.parent
		path = rootPath.joinpath('styles/main.qss')
		with open(path, "r") as style:
			self.setStyleSheet(style.read())

		self.udpSocket = QUdpSocket(self)
		self.udpSocket.bind(50224)

		self.udpSocket.readyRead.connect(self.readUDP)

	def readUDP(self):
		while self.udpSocket.hasPendingDatagrams():
			datagram, host, port = self.udpSocket.readDatagram(self.udpSocket.pendingDatagramSize())
			datagram = json.loads(str(datagram, encoding='ascii'))
			if datagram['type'] == 'rapid_wind':
				wind = WF_UDPWind(datagram)
				print('Setting speed to {} and direction to {}'.format(wind.speed.withUnit, wind.direction))
				self.update(wind)
		# print(datagram)

	def update(self, wind: WF_UDPWind):
		self.live = True
		speed = wind.speed.localized
		self.speed = str(speed)
		if speed > 0:
			self.direction = wind.direction
			cardinalDirections = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
			direction = int(((wind.direction + 22.5) % 360) // 45 % 8)
			self.directionLabel.setText(cardinalDirections[direction])

	def resizeEvent(self, event):
		self.windRose.setGeometry(self.mainFrame.geometry())

	def paintEvent(self, event):
		super().paintEvent(event)

	@property
	def speed(self):
		return self.speedLabel.text()

	@speed.setter
	def speed(self, value):
		self.speedLabel.setText(value)

	@property
	def direction(self):
		return self.directionLabel.text()

	@direction.setter
	def direction(self, value):
		self.windRose.animate(value, True, 900)

	@property
	def max(self):
		return self.maxValueLabel.text()

	@max.setter
	def max(self, value):
		self.maxValueLabel.setText(value)

	@property
	def gust(self):
		return self.gustValueLabel.text()

	@gust.setter
	def gust(self, value):
		self.gustValueLabel.setText(value)


class OtherSubmodule(windUI, Submodule):

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.setupUi(self)
		self.directionLabel.move(-10, 0)
		self.layout()
		self.windRose = windRose(self.mainFrame)
		self.windRose.setObjectName(u"windRose")
		self.unit.hide()

		rootPath = Path(__file__).parent.parent.parent
		path = rootPath.joinpath('styles/main.qss')
		with open(path, "r") as style:
			self.setStyleSheet(style.read())

		self.udpSocket = QUdpSocket(self)
		self.udpSocket.bind(50224)

		self.udpSocket.readyRead.connect(self.readUDP)

	def readUDP(self):
		while self.udpSocket.hasPendingDatagrams():
			datagram, host, port = self.udpSocket.readDatagram(self.udpSocket.pendingDatagramSize())
			datagram = json.loads(str(datagram, encoding='ascii'))
			if datagram['type'] == 'rapid_wind':
				wind = WF_UDPWind(datagram)
				print('Setting speed to {} and direction to {}'.format(wind.speed.withUnit, wind.direction))
				self.update(wind)
			else:
				print(datagram)

	def update(self, wind: WF_UDPWind):
		self.live = True
		speed = wind.speed.localized
		self.speed = str(speed)
		if speed > 0:
			self.direction = wind.direction
			cardinalDirections = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
			direction = int(((wind.direction + 22.5) % 360) // 45 % 8)
			self.directionLabel.setText(cardinalDirections[direction])


if __name__ == '__main__':
	import sys

	app = QApplication(sys.argv)

	widget = windSubmodule()
	widget.show()
	widget.setFixedWidth(500)
	widget.setFixedSize(500, 500)
	display_monitor = 0
	monitor = QDesktopWidget().screenGeometry(display_monitor)
	widget.move(monitor.left(), monitor.top())
	sys.exit(app.exec_())

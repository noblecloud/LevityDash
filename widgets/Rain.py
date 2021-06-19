from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Property, QPropertyAnimation, Qt, Signal
from PySide2.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide2.QtWidgets import QApplication, QDesktopWidget, QSlider, QVBoxLayout, QWidget
from pysolar import solar
from ui.rain_UI import Ui_rain as RainWidgetUI


class RainWidget(QtWidgets.QWidget, RainWidgetUI):

	def __init__(self, *args, **kwargs):
		super(RainWidget, self).__init__(*args, **kwargs)
		self.setupUi(self)

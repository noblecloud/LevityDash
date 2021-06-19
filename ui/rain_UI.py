# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'rain.ui'
##
## Created by: Qt User Interface Compiler version 5.15.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from widgets.Complication import Complication


class Ui_rain(object):
	def setupUi(self, rain):
		if not rain.objectName():
			rain.setObjectName(u"rain")
		rain.resize(605, 556)
		self.gridLayout = QGridLayout(rain)
		self.gridLayout.setObjectName(u"gridLayout")
		self.d1 = Complication(rain)
		self.d1.setObjectName(u"d1")
		sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
		sizePolicy.setHorizontalStretch(2)
		sizePolicy.setVerticalStretch(1)
		sizePolicy.setHeightForWidth(self.d1.sizePolicy().hasHeightForWidth())
		self.d1.setSizePolicy(sizePolicy)
		self.d1.setProperty("showUnit", False)

		self.gridLayout.addWidget(self.d1, 0, 0, 1, 1)

		self.d3 = Complication(rain)
		self.d3.setObjectName(u"d3")
		sizePolicy.setHeightForWidth(self.d3.sizePolicy().hasHeightForWidth())
		self.d3.setSizePolicy(sizePolicy)
		self.d3.setProperty("showUnit", False)

		self.gridLayout.addWidget(self.d3, 0, 4, 1, 1)

		self.c1 = Complication(rain)
		self.c1.setObjectName(u"c1")
		sizePolicy.setHeightForWidth(self.c1.sizePolicy().hasHeightForWidth())
		self.c1.setSizePolicy(sizePolicy)
		self.c1.setProperty("showUnit", False)

		self.gridLayout.addWidget(self.c1, 1, 0, 1, 1)

		self.c3 = Complication(rain)
		self.c3.setObjectName(u"c3")
		sizePolicy.setHeightForWidth(self.c3.sizePolicy().hasHeightForWidth())
		self.c3.setSizePolicy(sizePolicy)
		self.c3.setProperty("showUnit", False)

		self.gridLayout.addWidget(self.c3, 1, 4, 1, 1)

		self.b1 = Complication(rain)
		self.b1.setObjectName(u"b1")
		sizePolicy.setHeightForWidth(self.b1.sizePolicy().hasHeightForWidth())
		self.b1.setSizePolicy(sizePolicy)
		self.b1.setProperty("showUnit", False)

		self.gridLayout.addWidget(self.b1, 2, 0, 1, 1)

		self.b3 = Complication(rain)
		self.b3.setObjectName(u"b3")
		sizePolicy.setHeightForWidth(self.b3.sizePolicy().hasHeightForWidth())
		self.b3.setSizePolicy(sizePolicy)
		self.b3.setProperty("showUnit", False)

		self.gridLayout.addWidget(self.b3, 2, 4, 1, 1)

		self.a1 = Complication(rain)
		self.a1.setObjectName(u"a1")
		sizePolicy1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
		sizePolicy1.setHorizontalStretch(4)
		sizePolicy1.setVerticalStretch(1)
		sizePolicy1.setHeightForWidth(self.a1.sizePolicy().hasHeightForWidth())
		self.a1.setSizePolicy(sizePolicy1)
		self.a1.setProperty("showUnit", True)

		self.gridLayout.addWidget(self.a1, 3, 0, 1, 2)

		self.a2 = Complication(rain)
		self.a2.setObjectName(u"a2")
		sizePolicy1.setHeightForWidth(self.a2.sizePolicy().hasHeightForWidth())
		self.a2.setSizePolicy(sizePolicy1)
		self.a2.setProperty("showUnit", True)

		self.gridLayout.addWidget(self.a2, 3, 2, 1, 1)

		self.a3 = Complication(rain)
		self.a3.setObjectName(u"a3")
		sizePolicy1.setHeightForWidth(self.a3.sizePolicy().hasHeightForWidth())
		self.a3.setSizePolicy(sizePolicy1)
		self.a3.setProperty("showUnit", True)

		self.gridLayout.addWidget(self.a3, 3, 3, 1, 2)

		self.main = Complication(rain)
		self.main.setObjectName(u"main")

		self.gridLayout.addWidget(self.main, 0, 1, 3, 3)

		self.gridLayout.setRowStretch(0, 3)
		self.gridLayout.setRowStretch(1, 3)
		self.gridLayout.setRowStretch(2, 3)
		self.gridLayout.setRowStretch(3, 3)
		self.gridLayout.setColumnStretch(0, 2)
		self.gridLayout.setColumnStretch(1, 1)
		self.gridLayout.setColumnStretch(2, 4)
		self.gridLayout.setColumnStretch(3, 1)
		self.gridLayout.setColumnStretch(4, 2)

		self.retranslateUi(rain)

		QMetaObject.connectSlotsByName(rain)

	# setupUi

	def retranslateUi(self, rain):
		rain.setWindowTitle(QCoreApplication.translate("rain", u"Form", None))
	# retranslateUi

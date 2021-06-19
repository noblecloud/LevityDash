# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'Temperature.ui'
##
## Created by: Qt User Interface Compiler version 5.15.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from widgets.DynamicLabel import DynamicLabel
from widgets.Complication import ComplicationArrayHorizontal
from widgets.Complication import Complication
from widgets.Complication import ComplicationArrayVertical


class Ui_ComplicationGroup(object):
	def setupUi(self, ComplicationGroup):
		if not ComplicationGroup.objectName():
			ComplicationGroup.setObjectName(u"ComplicationGroup")
		ComplicationGroup.resize(612, 583)
		sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
		sizePolicy.setHorizontalStretch(1)
		sizePolicy.setVerticalStretch(1)
		sizePolicy.setHeightForWidth(ComplicationGroup.sizePolicy().hasHeightForWidth())
		ComplicationGroup.setSizePolicy(sizePolicy)
		font = QFont()
		font.setFamily(u"SF Compact Rounded")
		ComplicationGroup.setFont(font)
		ComplicationGroup.setStyleSheet(u"")
		self.grid = QGridLayout(ComplicationGroup)
		self.grid.setSpacing(0)
		self.grid.setObjectName(u"grid")
		self.grid.setContentsMargins(0, 0, 0, 0)
		self.topLeft = Complication(ComplicationGroup)
		self.topLeft.setObjectName(u"topLeft")
		sizePolicy1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
		sizePolicy1.setHorizontalStretch(2)
		sizePolicy1.setVerticalStretch(2)
		sizePolicy1.setHeightForWidth(self.topLeft.sizePolicy().hasHeightForWidth())
		self.topLeft.setSizePolicy(sizePolicy1)
		self.topLeft.setStyleSheet(u"background: maroon")

		self.grid.addWidget(self.topLeft, 0, 0, 2, 1)

		self.titleLabel = DynamicLabel(ComplicationGroup)
		self.titleLabel.setObjectName(u"titleLabel")
		sizePolicy2 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
		sizePolicy2.setHorizontalStretch(0)
		sizePolicy2.setVerticalStretch(1)
		sizePolicy2.setHeightForWidth(self.titleLabel.sizePolicy().hasHeightForWidth())
		self.titleLabel.setSizePolicy(sizePolicy2)
		self.titleLabel.setMinimumSize(QSize(0, 30))
		self.titleLabel.setMaximumSize(QSize(16777215, 150))
		self.titleLabel.setStyleSheet(u"background: orange")

		self.grid.addWidget(self.titleLabel, 0, 1, 1, 1)

		self.topRight = Complication(ComplicationGroup)
		self.topRight.setObjectName(u"topRight")
		sizePolicy1.setHeightForWidth(self.topRight.sizePolicy().hasHeightForWidth())
		self.topRight.setSizePolicy(sizePolicy1)
		self.topRight.setStyleSheet(u"background: yellow")

		self.grid.addWidget(self.topRight, 0, 2, 2, 1)

		self.topArray = ComplicationArrayHorizontal(ComplicationGroup)
		self.topArray.setObjectName(u"topArray")
		sizePolicy3 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
		sizePolicy3.setHorizontalStretch(6)
		sizePolicy3.setVerticalStretch(3)
		sizePolicy3.setHeightForWidth(self.topArray.sizePolicy().hasHeightForWidth())
		self.topArray.setSizePolicy(sizePolicy3)
		self.topArray.setStyleSheet(u"background: pink")

		self.grid.addWidget(self.topArray, 1, 1, 1, 1)

		self.leftArray = ComplicationArrayVertical(ComplicationGroup)
		self.leftArray.setObjectName(u"leftArray")
		sizePolicy4 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
		sizePolicy4.setHorizontalStretch(2)
		sizePolicy4.setVerticalStretch(5)
		sizePolicy4.setHeightForWidth(self.leftArray.sizePolicy().hasHeightForWidth())
		self.leftArray.setSizePolicy(sizePolicy4)
		self.leftArray.setStyleSheet(u"background: lime")

		self.grid.addWidget(self.leftArray, 2, 0, 1, 1)

		self.center = Complication(ComplicationGroup)
		self.center.setObjectName(u"center")
		sizePolicy5 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
		sizePolicy5.setHorizontalStretch(6)
		sizePolicy5.setVerticalStretch(8)
		sizePolicy5.setHeightForWidth(self.center.sizePolicy().hasHeightForWidth())
		self.center.setSizePolicy(sizePolicy5)
		self.center.setStyleSheet(u"background: red")

		self.grid.addWidget(self.center, 2, 1, 1, 1)

		self.rightArray = ComplicationArrayVertical(ComplicationGroup)
		self.rightArray.setObjectName(u"rightArray")
		sizePolicy4.setHeightForWidth(self.rightArray.sizePolicy().hasHeightForWidth())
		self.rightArray.setSizePolicy(sizePolicy4)
		self.rightArray.setStyleSheet(u"background: green")

		self.grid.addWidget(self.rightArray, 2, 2, 1, 1)

		self.bottomLeft = Complication(ComplicationGroup)
		self.bottomLeft.setObjectName(u"bottomLeft")
		sizePolicy6 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
		sizePolicy6.setHorizontalStretch(2)
		sizePolicy6.setVerticalStretch(3)
		sizePolicy6.setHeightForWidth(self.bottomLeft.sizePolicy().hasHeightForWidth())
		self.bottomLeft.setSizePolicy(sizePolicy6)
		self.bottomLeft.setStyleSheet(u"background: lightblue")

		self.grid.addWidget(self.bottomLeft, 3, 0, 1, 1)

		self.bottomArray = ComplicationArrayHorizontal(ComplicationGroup)
		self.bottomArray.setObjectName(u"bottomArray")
		sizePolicy3.setHeightForWidth(self.bottomArray.sizePolicy().hasHeightForWidth())
		self.bottomArray.setSizePolicy(sizePolicy3)
		self.bottomArray.setStyleSheet(u"background: blue")

		self.grid.addWidget(self.bottomArray, 3, 1, 1, 1)

		self.bottomRight = Complication(ComplicationGroup)
		self.bottomRight.setObjectName(u"bottomRight")
		sizePolicy6.setHeightForWidth(self.bottomRight.sizePolicy().hasHeightForWidth())
		self.bottomRight.setSizePolicy(sizePolicy6)
		self.bottomRight.setStyleSheet(u"background: purple")

		self.grid.addWidget(self.bottomRight, 3, 2, 1, 1)

		self.grid.setRowStretch(0, 1)
		self.grid.setRowStretch(1, 2)
		self.grid.setRowStretch(2, 6)
		self.grid.setRowStretch(3, 3)
		self.grid.setColumnStretch(0, 2)
		self.grid.setColumnStretch(1, 8)
		self.grid.setColumnStretch(2, 2)

		self.retranslateUi(ComplicationGroup)

		QMetaObject.connectSlotsByName(ComplicationGroup)
    # setupUi

	def retranslateUi(self, ComplicationGroup):
		pass
    # retranslateUi


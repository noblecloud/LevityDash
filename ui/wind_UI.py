# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'wind.ui'
##
## Created by: Qt User Interface Compiler version 5.15.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from widgets.Complication import Complication
from widgets.Wind import windRose


class Ui_wind(object):
    def setupUi(self, wind):
        if not wind.objectName():
            wind.setObjectName(u"wind")
        wind.resize(853, 657)
        font = QFont()
        font.setFamily(u"SF Pro Rounded")
        wind.setFont(font)
        self.rose = windRose(wind)
        self.rose.setObjectName(u"rose")
        self.rose.setGeometry(QRect(89, 49, 571, 391))
        self.topLeft = Complication(wind)
        self.topLeft.setObjectName(u"topLeft")
        self.topLeft.setGeometry(QRect(0, 0, 155, 114))
        font1 = QFont()
        font1.setFamily(u"SF Pro Rounded")
        font1.setPointSize(31)
        self.topLeft.setFont(font1)
        self.topLeft.setProperty("showUnit", False)

        self.bottomLeft = Complication(wind)
        self.bottomLeft.setObjectName(u"bottomLeft")
        self.bottomLeft.setGeometry(QRect(0, 540, 155, 100))
        self.bottomLeft.setFont(font1)
        self.bottomLeft.setProperty("showUnit", False)

        self.topRight = Complication(wind)
        self.topRight.setObjectName(u"topRight")
        self.topRight.setGeometry(QRect(690, 0, 155, 114))
        self.topRight.setFont(font1)
        self.topRight.setProperty("showUnit", False)

        self.bottomRight = Complication(wind)
        self.bottomRight.setObjectName(u"bottomRight")
        self.bottomRight.setGeometry(QRect(690, 530, 155, 116))
        self.bottomRight.setFont(font1)
        self.bottomRight.setProperty("showUnit", False)

        self.retranslateUi(wind)

        QMetaObject.connectSlotsByName(wind)
    # setupUi

    def retranslateUi(self, wind):
        wind.setWindowTitle(QCoreApplication.translate("wind", u"Form", None))
    # retranslateUi


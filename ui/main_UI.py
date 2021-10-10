# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main.ui'
##
## Created by: Qt User Interface Compiler version 5.15.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from widgets.ComplicationArray import MainBox


class Ui_weatherDisplay(object):
    def setupUi(self, weatherDisplay):
        if not weatherDisplay.objectName():
            weatherDisplay.setObjectName(u"weatherDisplay")
        weatherDisplay.resize(1792, 1067)
        font = QFont()
        font.setFamily(u"SF Pro Rounded")
        weatherDisplay.setFont(font)
        weatherDisplay.setUnifiedTitleAndToolBarOnMac(True)
        self.centralwidget = MainBox(weatherDisplay)
        self.centralwidget.setObjectName(u"centralwidget")
        self.centralwidget.setEnabled(True)
        self.centralwidget.setAutoFillBackground(False)
        self.gridLayout_3 = QGridLayout(self.centralwidget)
        self.gridLayout_3.setSpacing(0)
        self.gridLayout_3.setObjectName(u"gridLayout_3")
        self.gridLayout_3.setContentsMargins(10, 10, 10, 10)
        weatherDisplay.setCentralWidget(self.centralwidget)

        self.retranslateUi(weatherDisplay)

        QMetaObject.connectSlotsByName(weatherDisplay)
    # setupUi

    def retranslateUi(self, weatherDisplay):
        weatherDisplay.setWindowTitle(QCoreApplication.translate("weatherDisplay", u"weatherDisplay", None))
    # retranslateUi


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

from widgets.dynamicLabel import DynamicLabel
from widgets.tempWidget import LargeBox
from widgets.tempWidget import GlyphBox
from widgets.complication import Complication


class Ui_weatherDisplay(object):
    def setupUi(self, weatherDisplay):
        if not weatherDisplay.objectName():
            weatherDisplay.setObjectName(u"weatherDisplay")
        weatherDisplay.resize(1920, 1080)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(weatherDisplay.sizePolicy().hasHeightForWidth())
        weatherDisplay.setSizePolicy(sizePolicy)
        weatherDisplay.setMinimumSize(QSize(800, 450))
        weatherDisplay.setBaseSize(QSize(1080, 720))
        font = QFont()
        font.setFamily(u"SF Pro Rounded")
        weatherDisplay.setFont(font)
        self.centralwidget = QWidget(weatherDisplay)
        self.centralwidget.setObjectName(u"centralwidget")
        self.centralwidget.setAutoFillBackground(False)
        self.gridLayout_3 = QGridLayout(self.centralwidget)
        self.gridLayout_3.setObjectName(u"gridLayout_3")
        self.bottom = QFrame(self.centralwidget)
        self.bottom.setObjectName(u"bottom")
        sizePolicy1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(4)
        sizePolicy1.setHeightForWidth(self.bottom.sizePolicy().hasHeightForWidth())
        self.bottom.setSizePolicy(sizePolicy1)
        self.bottom.setFrameShape(QFrame.StyledPanel)
        self.bottom.setFrameShadow(QFrame.Raised)
        self.gridLayout_2 = QGridLayout(self.bottom)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.gridLayout_2.setHorizontalSpacing(1)
        self.gridLayout_2.setVerticalSpacing(0)
        self.gridLayout_2.setContentsMargins(0, 0, 0, 0)
        self.subA = QWidget(self.bottom)
        self.subA.setObjectName(u"subA")
        self.subA.setStyleSheet(u"background-color: #65C8B7;")

        self.gridLayout_2.addWidget(self.subA, 0, 0, 1, 1)

        self.subB = QWidget(self.bottom)
        self.subB.setObjectName(u"subB")
        self.subB.setStyleSheet(u"background-color: #65C8B7;")

        self.gridLayout_2.addWidget(self.subB, 0, 1, 1, 1)

        self.subC = QWidget(self.bottom)
        self.subC.setObjectName(u"subC")
        self.subC.setStyleSheet(u"background-color: #65C8B7;")

        self.gridLayout_2.addWidget(self.subC, 0, 2, 1, 1)

        self.subD = QWidget(self.bottom)
        self.subD.setObjectName(u"subD")
        self.subD.setStyleSheet(u"background-color: #65C8B7;")

        self.gridLayout_2.addWidget(self.subD, 0, 3, 1, 1)

        self.gridLayout_2.setColumnStretch(0, 1)
        self.gridLayout_2.setColumnStretch(1, 1)
        self.gridLayout_2.setColumnStretch(2, 1)
        self.gridLayout_2.setColumnStretch(3, 1)
        self.gridLayout_2.setColumnMinimumWidth(0, 1)
        self.gridLayout_2.setColumnMinimumWidth(1, 1)
        self.gridLayout_2.setColumnMinimumWidth(2, 1)
        self.gridLayout_2.setColumnMinimumWidth(3, 1)

        self.gridLayout_3.addWidget(self.bottom, 1, 0, 1, 2)

        self.forecastGraph = QGraphicsView(self.centralwidget)
        self.forecastGraph.setObjectName(u"forecastGraph")
        sizePolicy2 = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        sizePolicy2.setHorizontalStretch(9)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.forecastGraph.sizePolicy().hasHeightForWidth())
        self.forecastGraph.setSizePolicy(sizePolicy2)

        self.gridLayout_3.addWidget(self.forecastGraph, 0, 1, 1, 1)

        self.topLeft = QFrame(self.centralwidget)
        self.topLeft.setObjectName(u"topLeft")
        sizePolicy3 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        sizePolicy3.setHorizontalStretch(4)
        sizePolicy3.setVerticalStretch(5)
        sizePolicy3.setHeightForWidth(self.topLeft.sizePolicy().hasHeightForWidth())
        self.topLeft.setSizePolicy(sizePolicy3)
        self.topLeft.setFrameShape(QFrame.StyledPanel)
        self.topLeft.setFrameShadow(QFrame.Raised)
        self.verticalLayout = QVBoxLayout(self.topLeft)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.dateFrame = QHBoxLayout()
        self.dateFrame.setSpacing(0)
        self.dateFrame.setObjectName(u"dateFrame")
        self.dateFrame.setContentsMargins(0, 0, -1, -1)
        self.date = QLabel(self.topLeft)
        self.date.setObjectName(u"date")
        sizePolicy4 = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        sizePolicy4.setHorizontalStretch(10)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.date.sizePolicy().hasHeightForWidth())
        self.date.setSizePolicy(sizePolicy4)
        self.date.setMinimumSize(QSize(0, 0))
        font1 = QFont()
        font1.setFamily(u"SF Pro Rounded")
        font1.setPointSize(72)
        font1.setBold(False)
        font1.setWeight(50)
        self.date.setFont(font1)
        self.date.setScaledContents(True)
        self.date.setAlignment(Qt.AlignRight|Qt.AlignTop|Qt.AlignTrailing)
        self.date.setMargin(0)
        self.date.setIndent(0)
        self.date.setTextInteractionFlags(Qt.NoTextInteraction)

        self.dateFrame.addWidget(self.date)

        self.ordinal = QLabel(self.topLeft)
        self.ordinal.setObjectName(u"ordinal")
        sizePolicy5 = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        sizePolicy5.setHorizontalStretch(0)
        sizePolicy5.setVerticalStretch(1)
        sizePolicy5.setHeightForWidth(self.ordinal.sizePolicy().hasHeightForWidth())
        self.ordinal.setSizePolicy(sizePolicy5)
        font2 = QFont()
        font2.setFamily(u"SF Pro Rounded")
        font2.setPointSize(31)
        font2.setBold(False)
        font2.setWeight(50)
        self.ordinal.setFont(font2)
        self.ordinal.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignTop)

        self.dateFrame.addWidget(self.ordinal)

        self.dateFrame.setStretch(0, 1)

        self.verticalLayout.addLayout(self.dateFrame)

        self.timeComplications = QHBoxLayout()
        self.timeComplications.setSpacing(0)
        self.timeComplications.setObjectName(u"timeComplications")
        self.timeComplications.setSizeConstraint(QLayout.SetMinimumSize)
        self.time = DynamicLabel(self.topLeft)
        self.time.setObjectName(u"time")
        sizePolicy6 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy6.setHorizontalStretch(0)
        sizePolicy6.setVerticalStretch(1)
        sizePolicy6.setHeightForWidth(self.time.sizePolicy().hasHeightForWidth())
        self.time.setSizePolicy(sizePolicy6)
        font3 = QFont()
        font3.setFamily(u"SF Pro Rounded")
        font3.setPointSize(140)
        font3.setBold(False)
        font3.setWeight(50)
        self.time.setFont(font3)
        self.time.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)
        self.time.setProperty("maxSize", 180)

        self.timeComplications.addWidget(self.time)

        self.gridLayout = QGridLayout()
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName(u"gridLayout")
        self.gridLayout.setSizeConstraint(QLayout.SetMinimumSize)
        self.moonPhase = GlyphBox(self.topLeft)
        self.moonPhase.setObjectName(u"moonPhase")
        self.moonPhase.setMinimumSize(QSize(50, 50))

        self.gridLayout.addWidget(self.moonPhase, 0, 0, 1, 1)

        self.Un = GlyphBox(self.topLeft)
        self.Un.setObjectName(u"Un")

        self.gridLayout.addWidget(self.Un, 1, 0, 1, 1)

        self.sunRise = Complication(self.topLeft)
        self.sunRise.setObjectName(u"sunRise")
        sizePolicy.setHeightForWidth(self.sunRise.sizePolicy().hasHeightForWidth())
        self.sunRise.setSizePolicy(sizePolicy)

        self.gridLayout.addWidget(self.sunRise, 0, 1, 1, 1)

        self.sunSet = Complication(self.topLeft)
        self.sunSet.setObjectName(u"sunSet")

        self.gridLayout.addWidget(self.sunSet, 1, 1, 1, 1)

        self.gridLayout.setRowStretch(0, 1)
        self.gridLayout.setRowStretch(1, 1)
        self.gridLayout.setColumnStretch(0, 1)
        self.gridLayout.setColumnStretch(1, 1)
        self.gridLayout.setColumnMinimumWidth(0, 1)
        self.gridLayout.setColumnMinimumWidth(1, 1)
        self.gridLayout.setRowMinimumHeight(0, 1)
        self.gridLayout.setRowMinimumHeight(1, 1)

        self.timeComplications.addLayout(self.gridLayout)

        self.timeComplications.setStretch(0, 12)
        self.timeComplications.setStretch(1, 7)

        self.verticalLayout.addLayout(self.timeComplications)

        self.Temps = QHBoxLayout()
        self.Temps.setSpacing(0)
        self.Temps.setObjectName(u"Temps")
        self.indoor = LargeBox(self.topLeft)
        self.indoor.setObjectName(u"indoor")
        sizePolicy7 = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        sizePolicy7.setHorizontalStretch(3)
        sizePolicy7.setVerticalStretch(2)
        sizePolicy7.setHeightForWidth(self.indoor.sizePolicy().hasHeightForWidth())
        self.indoor.setSizePolicy(sizePolicy7)
        self.indoor.setMinimumSize(QSize(0, 100))

        self.Temps.addWidget(self.indoor)

        self.outdoor = LargeBox(self.topLeft)
        self.outdoor.setObjectName(u"outdoor")
        sizePolicy8 = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        sizePolicy8.setHorizontalStretch(1)
        sizePolicy8.setVerticalStretch(1)
        sizePolicy8.setHeightForWidth(self.outdoor.sizePolicy().hasHeightForWidth())
        self.outdoor.setSizePolicy(sizePolicy8)

        self.Temps.addWidget(self.outdoor)

        self.Temps.setStretch(0, 1)
        self.Temps.setStretch(1, 1)

        self.verticalLayout.addLayout(self.Temps)

        self.verticalLayout.setStretch(1, 4)
        self.verticalLayout.setStretch(2, 6)

        self.gridLayout_3.addWidget(self.topLeft, 0, 0, 1, 1)

        # weatherDisplay.setCentralWidget(self.centralwidget)

        self.retranslateUi(weatherDisplay)

        QMetaObject.connectSlotsByName(weatherDisplay)
    # setupUi

    def retranslateUi(self, weatherDisplay):
        weatherDisplay.setWindowTitle(QCoreApplication.translate("weatherDisplay", u"weatherDisplay", None))
        self.date.setText(QCoreApplication.translate("weatherDisplay", u"Mon November 12", None))
        self.ordinal.setText(QCoreApplication.translate("weatherDisplay", u"th", None))
        self.time.setText(QCoreApplication.translate("weatherDisplay", u"12:34", None))
        self.moonPhase.setProperty("charStr", QCoreApplication.translate("weatherDisplay", u"\uf09a", None))
    # retranslateUi


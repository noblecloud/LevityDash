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

from widgets.Graph import Graph
from widgets.DynamicLabel import DynamicLabel
from widgets.Complication import ComplicationArrayHorizontal
from widgets.Complication import ComplicationArrayGrid


class Ui_weatherDisplay(object):
    def setupUi(self, weatherDisplay):
        if not weatherDisplay.objectName():
            weatherDisplay.setObjectName(u"weatherDisplay")
        weatherDisplay.resize(1792, 1067)
        font = QFont()
        font.setFamily(u"SF Pro Rounded")
        weatherDisplay.setFont(font)
        weatherDisplay.setUnifiedTitleAndToolBarOnMac(True)
        self.centralwidget = QWidget(weatherDisplay)
        self.centralwidget.setObjectName(u"centralwidget")
        self.centralwidget.setEnabled(True)
        self.centralwidget.setAutoFillBackground(False)
        self.gridLayout_3 = QGridLayout(self.centralwidget)
        self.gridLayout_3.setSpacing(0)
        self.gridLayout_3.setObjectName(u"gridLayout_3")
        self.gridLayout_3.setContentsMargins(0, 0, 0, 0)
        self.bottom = ComplicationArrayHorizontal(self.centralwidget)
        self.bottom.setObjectName(u"bottom")
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(12)
        sizePolicy.setVerticalStretch(5)
        sizePolicy.setHeightForWidth(self.bottom.sizePolicy().hasHeightForWidth())
        self.bottom.setSizePolicy(sizePolicy)

        self.gridLayout_3.addWidget(self.bottom, 1, 0, 1, 2)

        self.forecastGraph = Graph(self.centralwidget)
        self.forecastGraph.setObjectName(u"forecastGraph")
        sizePolicy1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy1.setHorizontalStretch(7)
        sizePolicy1.setVerticalStretch(6)
        sizePolicy1.setHeightForWidth(self.forecastGraph.sizePolicy().hasHeightForWidth())
        self.forecastGraph.setSizePolicy(sizePolicy1)
        self.forecastGraph.setFont(font)
        self.forecastGraph.setFrameShape(QFrame.StyledPanel)
        self.forecastGraph.setFrameShadow(QFrame.Raised)

        self.gridLayout_3.addWidget(self.forecastGraph, 0, 1, 1, 1)

        self.topLeft = QFrame(self.centralwidget)
        self.topLeft.setObjectName(u"topLeft")
        sizePolicy2 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy2.setHorizontalStretch(4)
        sizePolicy2.setVerticalStretch(6)
        sizePolicy2.setHeightForWidth(self.topLeft.sizePolicy().hasHeightForWidth())
        self.topLeft.setSizePolicy(sizePolicy2)
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
        sizePolicy3 = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        sizePolicy3.setHorizontalStretch(10)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.date.sizePolicy().hasHeightForWidth())
        self.date.setSizePolicy(sizePolicy3)
        self.date.setMinimumSize(QSize(0, 0))
        self.date.setMaximumSize(QSize(16777215, 86))
        font1 = QFont()
        font1.setFamily(u"SF Pro Rounded")
        font1.setPointSize(67)
        font1.setBold(False)
        font1.setWeight(50)
        self.date.setFont(font1)
        self.date.setScaledContents(True)
        self.date.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)
        self.date.setMargin(0)
        self.date.setIndent(0)
        self.date.setTextInteractionFlags(Qt.NoTextInteraction)

        self.dateFrame.addWidget(self.date)

        self.ordinal = QLabel(self.topLeft)
        self.ordinal.setObjectName(u"ordinal")
        sizePolicy4 = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(1)
        sizePolicy4.setHeightForWidth(self.ordinal.sizePolicy().hasHeightForWidth())
        self.ordinal.setSizePolicy(sizePolicy4)
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
        self.timeComplications.setSizeConstraint(QLayout.SetDefaultConstraint)
        self.time = DynamicLabel(self.topLeft)
        self.time.setObjectName(u"time")
        sizePolicy5 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy5.setHorizontalStretch(2)
        sizePolicy5.setVerticalStretch(1)
        sizePolicy5.setHeightForWidth(self.time.sizePolicy().hasHeightForWidth())
        self.time.setSizePolicy(sizePolicy5)
        font3 = QFont()
        font3.setFamily(u"SF Pro Rounded")
        font3.setBold(True)
        font3.setWeight(75)
        self.time.setFont(font3)
        self.time.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)
        self.time.setProperty("textScale", 1.300000000000000)

        self.timeComplications.addWidget(self.time)

        self.complicationMini = ComplicationArrayGrid(self.topLeft)
        self.complicationMini.setObjectName(u"complicationMini")
        sizePolicy6 = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        sizePolicy6.setHorizontalStretch(1)
        sizePolicy6.setVerticalStretch(5)
        sizePolicy6.setHeightForWidth(self.complicationMini.sizePolicy().hasHeightForWidth())
        self.complicationMini.setSizePolicy(sizePolicy6)
        self.complicationMini.setSizeIncrement(QSize(1, 1))
        self.complicationMini.setStyleSheet(u"background: lightblue")

        self.timeComplications.addWidget(self.complicationMini)


        self.verticalLayout.addLayout(self.timeComplications)

        self.temperatures = ComplicationArrayHorizontal(self.topLeft)
        self.temperatures.setObjectName(u"temperatures")
        self.temperatures.setFrameShape(QFrame.StyledPanel)
        self.temperatures.setFrameShadow(QFrame.Raised)
        self.temperatures.setProperty("balanced", True)

        self.verticalLayout.addWidget(self.temperatures)

        self.verticalLayout.setStretch(0, 1)
        self.verticalLayout.setStretch(1, 3)
        self.verticalLayout.setStretch(2, 4)

        self.gridLayout_3.addWidget(self.topLeft, 0, 0, 1, 1)

        self.gridLayout_3.setRowStretch(0, 6)
        self.gridLayout_3.setRowStretch(1, 5)
        self.gridLayout_3.setColumnStretch(0, 1)
        self.gridLayout_3.setColumnStretch(1, 2)
        self.gridLayout_3.setColumnMinimumWidth(0, 1)
        self.gridLayout_3.setColumnMinimumWidth(1, 2)
        self.gridLayout_3.setRowMinimumHeight(0, 1)
        self.gridLayout_3.setRowMinimumHeight(1, 1)
        weatherDisplay.setCentralWidget(self.centralwidget)

        self.retranslateUi(weatherDisplay)

        QMetaObject.connectSlotsByName(weatherDisplay)
    # setupUi

    def retranslateUi(self, weatherDisplay):
        weatherDisplay.setWindowTitle(QCoreApplication.translate("weatherDisplay", u"weatherDisplay", None))
        self.date.setText(QCoreApplication.translate("weatherDisplay", u"Mon November 12", None))
        self.ordinal.setText(QCoreApplication.translate("weatherDisplay", u"th", None))
        self.time.setText(QCoreApplication.translate("weatherDisplay", u"12:34", None))
    # retranslateUi


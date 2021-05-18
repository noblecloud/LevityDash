# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'conditions.ui'
##
## Created by: Qt User Interface Compiler version 5.15.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


class Ui_conditions(object):
    def setupUi(self, conditions):
        if not conditions.objectName():
            conditions.setObjectName(u"conditions")
        conditions.setFrameShape(QFrame.StyledPanel)
        conditions.setFrameShadow(QFrame.Raised)
        self.verticalLayout_2 = QVBoxLayout(conditions)
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 10)
        self.glyphLabel = QLabel(conditions)
        self.glyphLabel.setObjectName(u"glyphLabel")
        sizePolicy = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.glyphLabel.sizePolicy().hasHeightForWidth())
        self.glyphLabel.setSizePolicy(sizePolicy)
        font = QFont()
        font.setFamily(u"Weather Icons")
        font.setPointSize(20)
        self.glyphLabel.setFont(font)
        self.glyphLabel.setLayoutDirection(Qt.LeftToRight)
        self.glyphLabel.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        self.verticalLayout_2.addWidget(self.glyphLabel)

        self.currentConditionLabel = QLabel(conditions)
        self.currentConditionLabel.setObjectName(u"currentConditionLabel")
        sizePolicy1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.currentConditionLabel.sizePolicy().hasHeightForWidth())
        self.currentConditionLabel.setSizePolicy(sizePolicy1)
        font1 = QFont()
        font1.setFamily(u"SF Compact Rounded")
        font1.setPointSize(30)
        self.currentConditionLabel.setFont(font1)
        self.currentConditionLabel.setAlignment(Qt.AlignCenter)

        self.verticalLayout_2.addWidget(self.currentConditionLabel)

        self.forecastStringLabel = QLabel(conditions)
        self.forecastStringLabel.setObjectName(u"forecastStringLabel")
        font2 = QFont()
        font2.setFamily(u"SF Compact Rounded")
        font2.setPointSize(20)
        self.forecastStringLabel.setFont(font2)
        self.forecastStringLabel.setAlignment(Qt.AlignCenter)

        self.verticalLayout_2.addWidget(self.forecastStringLabel)

        self.retranslateUi(conditions)

        QMetaObject.connectSlotsByName(conditions)
    # setupUi

    def retranslateUi(self, conditions):
	    conditions.setWindowTitle(QCoreApplication.translate("conditions", u"Frame", None))
	    self.glyphLabel.setText(QCoreApplication.translate("conditions", u"\uf02e", None))
	    self.currentConditionLabel.setText(QCoreApplication.translate("conditions", u"TextLabel", None))
        self.forecastStringLabel.setText(QCoreApplication.translate("conditions", u"TextLabel", None))
    # retranslateUi


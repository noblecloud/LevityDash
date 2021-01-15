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

from widgets.DynamicLabel import DynamicGlyph


class Ui_conditions(object):
    def setupUi(self, conditions):
        if not conditions.objectName():
            conditions.setObjectName(u"conditions")
        conditions.resize(447, 472)
        conditions.setMinimumSize(QSize(447, 472))
        conditions.setBaseSize(QSize(447, 472))
        conditions.setFrameShape(QFrame.StyledPanel)
        conditions.setFrameShadow(QFrame.Raised)
        self.verticalLayout_2 = QVBoxLayout(conditions)
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 10)
        self.glyphLabel = DynamicGlyph(conditions)
        self.glyphLabel.setObjectName(u"glyphLabel")
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.glyphLabel.sizePolicy().hasHeightForWidth())
        self.glyphLabel.setSizePolicy(sizePolicy)
        self.glyphLabel.setAlignment(Qt.AlignCenter)

        self.verticalLayout_2.addWidget(self.glyphLabel)

        self.currentConditionLabel = QLabel(conditions)
        self.currentConditionLabel.setObjectName(u"currentConditionLabel")
        sizePolicy1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.currentConditionLabel.sizePolicy().hasHeightForWidth())
        self.currentConditionLabel.setSizePolicy(sizePolicy1)
        font = QFont()
        font.setPointSize(30)
        self.currentConditionLabel.setFont(font)
        self.currentConditionLabel.setAlignment(Qt.AlignCenter)

        self.verticalLayout_2.addWidget(self.currentConditionLabel)

        self.forecastStringLabel = QLabel(conditions)
        self.forecastStringLabel.setObjectName(u"forecastStringLabel")
        font1 = QFont()
        font1.setPointSize(20)
        self.forecastStringLabel.setFont(font1)
        self.forecastStringLabel.setAlignment(Qt.AlignCenter)

        self.verticalLayout_2.addWidget(self.forecastStringLabel)


        self.retranslateUi(conditions)

        QMetaObject.connectSlotsByName(conditions)
    # setupUi

    def retranslateUi(self, conditions):
        conditions.setWindowTitle(QCoreApplication.translate("conditions", u"Frame", None))
        self.glyphLabel.setText(QCoreApplication.translate("conditions", u"\u2600\ufe0e", None))
        self.currentConditionLabel.setText(QCoreApplication.translate("conditions", u"TextLabel", None))
        self.forecastStringLabel.setText(QCoreApplication.translate("conditions", u"TextLabel", None))
    # retranslateUi


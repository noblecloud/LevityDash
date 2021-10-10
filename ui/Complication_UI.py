# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'Complication.ui'
##
## Created by: Qt User Interface Compiler version 5.15.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from widgets.DynamicLabel import DynamicLabel


class Ui_Frame(object):
    def setupUi(self, Frame):
        if not Frame.objectName():
            Frame.setObjectName(u"Frame")
        Frame.resize(73, 60)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(Frame.sizePolicy().hasHeightForWidth())
        Frame.setSizePolicy(sizePolicy)
        Frame.setMinimumSize(QSize(60, 60))
        Frame.setSizeIncrement(QSize(100, 100))
        font = QFont()
        font.setFamily(u"SF Compact Display")
        Frame.setFont(font)
        Frame.setProperty("showUnit", False)
        self.verticalLayout = QVBoxLayout(Frame)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.titleLabel = DynamicLabel(Frame)
        self.titleLabel.setObjectName(u"titleLabel")
        self.titleLabel.setMaximumSize(QSize(16777215, 100))

        self.verticalLayout.addWidget(self.titleLabel)

        self.valueLabel = DynamicLabel(Frame)
        self.valueLabel.setObjectName(u"valueLabel")

        self.verticalLayout.addWidget(self.valueLabel)

        self.verticalLayout.setStretch(0, 1)
        self.verticalLayout.setStretch(1, 9)

        self.retranslateUi(Frame)

        QMetaObject.connectSlotsByName(Frame)
    # setupUi

    def retranslateUi(self, Frame):
        Frame.setWindowTitle(QCoreApplication.translate("Frame", u"Frame", None))
    # retranslateUi


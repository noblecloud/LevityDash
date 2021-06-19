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
        Frame.resize(106, 100)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(Frame.sizePolicy().hasHeightForWidth())
        Frame.setSizePolicy(sizePolicy)
        Frame.setMinimumSize(QSize(50, 50))
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
        sizePolicy1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(5)
        sizePolicy1.setHeightForWidth(self.valueLabel.sizePolicy().hasHeightForWidth())
        self.valueLabel.setSizePolicy(sizePolicy1)

        self.verticalLayout.addWidget(self.valueLabel)

        self.valueWidget = QWidget(Frame)
        self.valueWidget.setObjectName(u"valueWidget")
        sizePolicy1.setHeightForWidth(self.valueWidget.sizePolicy().hasHeightForWidth())
        self.valueWidget.setSizePolicy(sizePolicy1)

        self.verticalLayout.addWidget(self.valueWidget)

        self.verticalLayout.setStretch(0, 2)
        self.verticalLayout.setStretch(1, 7)
        self.verticalLayout.setStretch(2, 7)

        self.retranslateUi(Frame)

        QMetaObject.connectSlotsByName(Frame)
    # setupUi

    def retranslateUi(self, Frame):
        Frame.setWindowTitle(QCoreApplication.translate("Frame", u"Frame", None))
    # retranslateUi


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
        Frame.resize(110, 69)
        font = QFont()
        font.setFamily(u"SF Compact Display")
        Frame.setFont(font)
        self.verticalLayout = QVBoxLayout(Frame)
        self.verticalLayout.setSpacing(1)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 5, 0, 5)
        self.title = DynamicLabel(Frame)
        self.title.setObjectName(u"title")
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.title.sizePolicy().hasHeightForWidth())
        self.title.setSizePolicy(sizePolicy)
        font1 = QFont()
        font1.setFamily(u"SF Compact Display")
        font1.setPointSize(26)
        self.title.setFont(font1)
        self.title.setAlignment(Qt.AlignBottom|Qt.AlignHCenter)

        self.verticalLayout.addWidget(self.title)

        self.value = DynamicLabel(Frame)
        self.value.setObjectName(u"value")
        font2 = QFont()
        font2.setFamily(u"SF Compact Display")
        font2.setPointSize(21)
        self.value.setFont(font2)
        self.value.setAlignment(Qt.AlignHCenter|Qt.AlignTop)

        self.verticalLayout.addWidget(self.value)

        self.verticalLayout.setStretch(0, 1)
        self.verticalLayout.setStretch(1, 3)

        self.retranslateUi(Frame)

        QMetaObject.connectSlotsByName(Frame)
    # setupUi

    def retranslateUi(self, Frame):
        Frame.setWindowTitle(QCoreApplication.translate("Frame", u"Frame", None))
        self.title.setText(QCoreApplication.translate("Frame", u"TextLabel", None))
        self.value.setText(QCoreApplication.translate("Frame", u"TextLabel", None))
    # retranslateUi


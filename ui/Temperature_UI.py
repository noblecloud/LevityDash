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


class Ui_Form(object):
    def setupUi(self, Form):
        if not Form.objectName():
            Form.setObjectName(u"Form")
        Form.resize(335, 285)
        Form.setMinimumSize(QSize(335, 285))
        font = QFont()
        font.setFamily(u"SF Compact Rounded")
        Form.setFont(font)
        Form.setStyleSheet(u"")
        self.verticalLayout = QVBoxLayout(Form)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel(Form)
        self.title.setObjectName(u"title")
        font1 = QFont()
        font1.setFamily(u"SF Pro Rounded")
        font1.setPointSize(39)
        font1.setBold(True)
        font1.setWeight(75)
        self.title.setFont(font1)
        self.title.setAlignment(Qt.AlignCenter)

        self.verticalLayout.addWidget(self.title)

        self.temperature = DynamicLabel(Form)
        self.temperature.setObjectName(u"temperature")
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.temperature.sizePolicy().hasHeightForWidth())
        self.temperature.setSizePolicy(sizePolicy)
        font2 = QFont()
        font2.setFamily(u"SF Pro Rounded")
        font2.setPointSize(129)
        self.temperature.setFont(font2)
        self.temperature.setAlignment(Qt.AlignCenter)

        self.verticalLayout.addWidget(self.temperature)

        self.frame = QFrame(Form)
        self.frame.setObjectName(u"frame")
        self.gridLayout = QGridLayout(self.frame)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName(u"gridLayout")
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.SubAValue = DynamicLabel(self.frame)
        self.SubAValue.setObjectName(u"SubAValue")
        sizePolicy1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.SubAValue.sizePolicy().hasHeightForWidth())
        self.SubAValue.setSizePolicy(sizePolicy1)
        font3 = QFont()
        font3.setFamily(u"SF Compact Rounded")
        font3.setPointSize(75)
        self.SubAValue.setFont(font3)
        self.SubAValue.setText(u"31")
        self.SubAValue.setAlignment(Qt.AlignBottom|Qt.AlignHCenter)

        self.gridLayout.addWidget(self.SubAValue, 0, 0, 1, 1)

        self.SubBValue = DynamicLabel(self.frame)
        self.SubBValue.setObjectName(u"SubBValue")
        sizePolicy2 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.SubBValue.sizePolicy().hasHeightForWidth())
        self.SubBValue.setSizePolicy(sizePolicy2)
        self.SubBValue.setFont(font3)
        self.SubBValue.setAlignment(Qt.AlignBottom|Qt.AlignHCenter)

        self.gridLayout.addWidget(self.SubBValue, 0, 1, 1, 1)

        self.subATitle = DynamicLabel(self.frame)
        self.subATitle.setObjectName(u"subATitle")
        sizePolicy3 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.subATitle.sizePolicy().hasHeightForWidth())
        self.subATitle.setSizePolicy(sizePolicy3)
        font4 = QFont()
        font4.setFamily(u"SF Compact Rounded")
        font4.setPointSize(21)
        self.subATitle.setFont(font4)
        self.subATitle.setAlignment(Qt.AlignHCenter|Qt.AlignTop)

        self.gridLayout.addWidget(self.subATitle, 1, 0, 1, 1)

        self.subBTitle = DynamicLabel(self.frame)
        self.subBTitle.setObjectName(u"subBTitle")
        sizePolicy3.setHeightForWidth(self.subBTitle.sizePolicy().hasHeightForWidth())
        self.subBTitle.setSizePolicy(sizePolicy3)
        self.subBTitle.setFont(font4)
        self.subBTitle.setAlignment(Qt.AlignHCenter|Qt.AlignTop)

        self.gridLayout.addWidget(self.subBTitle, 1, 1, 1, 1)


        self.verticalLayout.addWidget(self.frame)

        self.verticalLayout.setStretch(0, 1)
        self.verticalLayout.setStretch(1, 10)
        self.verticalLayout.setStretch(2, 2)
#if QT_CONFIG(shortcut)
        self.title.setBuddy(self.temperature)
        self.SubAValue.setBuddy(self.temperature)
        self.SubBValue.setBuddy(self.temperature)
        self.subATitle.setBuddy(self.temperature)
        self.subBTitle.setBuddy(self.temperature)
#endif // QT_CONFIG(shortcut)

        self.retranslateUi(Form)

        QMetaObject.connectSlotsByName(Form)
    # setupUi

    def retranslateUi(self, Form):
        self.title.setText(QCoreApplication.translate("Form", u"Location", None))
        self.temperature.setText(QCoreApplication.translate("Form", u"35.4\u00ba", None))
        self.SubBValue.setText(QCoreApplication.translate("Form", u"45%", None))
        self.subATitle.setText(QCoreApplication.translate("Form", u"TextLabel", None))
        self.subBTitle.setText(QCoreApplication.translate("Form", u"TextLabel", None))
        pass
    # retranslateUi


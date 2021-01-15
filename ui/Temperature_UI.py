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
        Form.resize(246, 272)
        sizePolicy = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.MinimumExpanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(Form.sizePolicy().hasHeightForWidth())
        Form.setSizePolicy(sizePolicy)
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
        sizePolicy1 = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Maximum)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.title.sizePolicy().hasHeightForWidth())
        self.title.setSizePolicy(sizePolicy1)
        font1 = QFont()
        font1.setFamily(u"SF Pro Rounded")
        font1.setPointSize(45)
        self.title.setFont(font1)
        self.title.setAlignment(Qt.AlignCenter)

        self.verticalLayout.addWidget(self.title)

        self.temperature = DynamicLabel(Form)
        self.temperature.setObjectName(u"temperature")
        sizePolicy2 = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Expanding)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(2)
        sizePolicy2.setHeightForWidth(self.temperature.sizePolicy().hasHeightForWidth())
        self.temperature.setSizePolicy(sizePolicy2)
        self.temperature.setMinimumSize(QSize(0, 80))
        self.temperature.setMaximumSize(QSize(16777215, 100))
        font2 = QFont()
        font2.setFamily(u"SF Pro Rounded")
        font2.setPointSize(80)
        self.temperature.setFont(font2)
        self.temperature.setAutoFillBackground(False)
        self.temperature.setStyleSheet(u"max-height:100%;")
        self.temperature.setLineWidth(0)
        self.temperature.setAlignment(Qt.AlignCenter)
        self.temperature.setMargin(0)
        self.temperature.setIndent(0)

        self.verticalLayout.addWidget(self.temperature)

        self.frame = QFrame(Form)
        self.frame.setObjectName(u"frame")
        sizePolicy3 = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.frame.sizePolicy().hasHeightForWidth())
        self.frame.setSizePolicy(sizePolicy3)
        self.frame.setMinimumSize(QSize(0, 100))
        self.gridLayout = QGridLayout(self.frame)
        self.gridLayout.setSpacing(0)
        self.gridLayout.setObjectName(u"gridLayout")
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.subs = QHBoxLayout()
        self.subs.setSpacing(0)
        self.subs.setObjectName(u"subs")
        self.subs.setSizeConstraint(QLayout.SetMinimumSize)
        self.gridLayout_4 = QGridLayout()
        self.gridLayout_4.setObjectName(u"gridLayout_4")
        self.SubAValue = DynamicLabel(self.frame)
        self.SubAValue.setObjectName(u"SubAValue")
        sizePolicy4 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.SubAValue.sizePolicy().hasHeightForWidth())
        self.SubAValue.setSizePolicy(sizePolicy4)
        font3 = QFont()
        font3.setFamily(u"SF Compact Rounded")
        font3.setPointSize(70)
        self.SubAValue.setFont(font3)
        self.SubAValue.setAlignment(Qt.AlignBottom|Qt.AlignHCenter)

        self.gridLayout_4.addWidget(self.SubAValue, 0, 0, 1, 1)

        self.subATitle = DynamicLabel(self.frame)
        self.subATitle.setObjectName(u"subATitle")
        sizePolicy5 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        sizePolicy5.setHorizontalStretch(0)
        sizePolicy5.setVerticalStretch(0)
        sizePolicy5.setHeightForWidth(self.subATitle.sizePolicy().hasHeightForWidth())
        self.subATitle.setSizePolicy(sizePolicy5)
        font4 = QFont()
        font4.setFamily(u"SF Compact Rounded")
        font4.setPointSize(20)
        self.subATitle.setFont(font4)
        self.subATitle.setAlignment(Qt.AlignHCenter|Qt.AlignTop)

        self.gridLayout_4.addWidget(self.subATitle, 1, 0, 1, 1)

        self.SubBValue = DynamicLabel(self.frame)
        self.SubBValue.setObjectName(u"SubBValue")
        sizePolicy4.setHeightForWidth(self.SubBValue.sizePolicy().hasHeightForWidth())
        self.SubBValue.setSizePolicy(sizePolicy4)
        self.SubBValue.setFont(font3)
        self.SubBValue.setAlignment(Qt.AlignBottom|Qt.AlignHCenter)

        self.gridLayout_4.addWidget(self.SubBValue, 0, 1, 1, 1)

        self.subBTitle = DynamicLabel(self.frame)
        self.subBTitle.setObjectName(u"subBTitle")
        sizePolicy5.setHeightForWidth(self.subBTitle.sizePolicy().hasHeightForWidth())
        self.subBTitle.setSizePolicy(sizePolicy5)
        self.subBTitle.setFont(font4)
        self.subBTitle.setAlignment(Qt.AlignHCenter|Qt.AlignTop)

        self.gridLayout_4.addWidget(self.subBTitle, 1, 1, 1, 1)


        self.subs.addLayout(self.gridLayout_4)


        self.gridLayout.addLayout(self.subs, 0, 0, 1, 1)


        self.verticalLayout.addWidget(self.frame)

        self.verticalSpacer_2 = QSpacerItem(20, 0, QSizePolicy.Minimum, QSizePolicy.Fixed)

        self.verticalLayout.addItem(self.verticalSpacer_2)

        self.verticalLayout.setStretch(0, 3)
        self.verticalLayout.setStretch(1, 1)

        self.retranslateUi(Form)

        QMetaObject.connectSlotsByName(Form)
    # setupUi

    def retranslateUi(self, Form):
        self.title.setText(QCoreApplication.translate("Form", u"Location", None))
        self.temperature.setText(QCoreApplication.translate("Form", u"123\u00ba", None))
        self.SubAValue.setText(QCoreApplication.translate("Form", u"89\u00ba", None))
        self.subATitle.setText(QCoreApplication.translate("Form", u"TextLabel", None))
        self.SubBValue.setText(QCoreApplication.translate("Form", u"45%", None))
        self.subBTitle.setText(QCoreApplication.translate("Form", u"TextLabel", None))
        pass
    # retranslateUi


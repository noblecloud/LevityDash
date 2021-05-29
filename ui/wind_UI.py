# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'wind.ui'
##
## Created by: Qt User Interface Compiler version 5.15.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


class Ui_Frame(object):
    def setupUi(self, Frame):
        if not Frame.objectName():
            Frame.setObjectName(u"Frame")
        Frame.resize(447, 472)
        Frame.setMinimumSize(QSize(447, 471))
        Frame.setBaseSize(QSize(479, 471))
        font = QFont()
        font.setFamily(u"SF Pro Rounded")
        Frame.setFont(font)
        Frame.setFrameShape(QFrame.StyledPanel)
        Frame.setFrameShadow(QFrame.Raised)
        self.verticalLayout_2 = QVBoxLayout(Frame)
        self.verticalLayout_2.setSpacing(0)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalLayout_2.setContentsMargins(0, 15, 0, 15)
        self.mainFrame = QFrame(Frame)
        self.mainFrame.setObjectName(u"mainFrame")
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(10)
        sizePolicy.setHeightForWidth(self.mainFrame.sizePolicy().hasHeightForWidth())
        self.mainFrame.setSizePolicy(sizePolicy)
        self.verticalLayout = QVBoxLayout(self.mainFrame)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)

        self.verticalLayout_2.addWidget(self.mainFrame)

        self.subDataFrame = QFrame(Frame)
        self.subDataFrame.setObjectName(u"subDataFrame")
        sizePolicy1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(1)
        sizePolicy1.setHeightForWidth(self.subDataFrame.sizePolicy().hasHeightForWidth())
        self.subDataFrame.setSizePolicy(sizePolicy1)
        font1 = QFont()
        font1.setFamily(u"SF Pro Rounded")
        font1.setPointSize(29)
        font1.setBold(False)
        font1.setWeight(50)
        self.subDataFrame.setFont(font1)
        self.horizontalLayout_3 = QHBoxLayout(self.subDataFrame)
        self.horizontalLayout_3.setSpacing(10)
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.horizontalLayout_3.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setSpacing(0)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.leftSubSpacer = QSpacerItem(40, 0, QSizePolicy.Minimum, QSizePolicy.Minimum)

        self.horizontalLayout_2.addItem(self.leftSubSpacer)

        self.maxTitle = QLabel(self.subDataFrame)
        self.maxTitle.setObjectName(u"maxTitle")
        sizePolicy2 = QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        sizePolicy2.setHorizontalStretch(6)
        sizePolicy2.setVerticalStretch(3)
        sizePolicy2.setHeightForWidth(self.maxTitle.sizePolicy().hasHeightForWidth())
        self.maxTitle.setSizePolicy(sizePolicy2)
        font2 = QFont()
        font2.setFamily(u"SF Pro Rounded")
        font2.setPointSize(33)
        font2.setBold(True)
        font2.setWeight(75)
        self.maxTitle.setFont(font2)
        self.maxTitle.setAlignment(Qt.AlignRight | Qt.AlignTrailing | Qt.AlignVCenter)

        self.horizontalLayout_2.addWidget(self.maxTitle)

        self.maxValueLabel = QLabel(self.subDataFrame)
        self.maxValueLabel.setObjectName(u"maxValueLabel")
        sizePolicy3 = QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        sizePolicy3.setHorizontalStretch(6)
        sizePolicy3.setVerticalStretch(9)
        sizePolicy3.setHeightForWidth(self.maxValueLabel.sizePolicy().hasHeightForWidth())
        self.maxValueLabel.setSizePolicy(sizePolicy3)
        font3 = QFont()
        font3.setFamily(u"SF Pro Rounded")
        font3.setPointSize(33)
        font3.setBold(False)
        font3.setWeight(50)
        self.maxValueLabel.setFont(font3)
        self.maxValueLabel.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignVCenter)

        self.horizontalLayout_2.addWidget(self.maxValueLabel)


        self.horizontalLayout_3.addLayout(self.horizontalLayout_2)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.gustTitle = QLabel(self.subDataFrame)
        self.gustTitle.setObjectName(u"gustTitle")
        sizePolicy2.setHeightForWidth(self.gustTitle.sizePolicy().hasHeightForWidth())
        self.gustTitle.setSizePolicy(sizePolicy2)
        self.gustTitle.setFont(font2)
        self.gustTitle.setAlignment(Qt.AlignRight | Qt.AlignTrailing | Qt.AlignVCenter)

        self.horizontalLayout.addWidget(self.gustTitle)

        self.gustValueLabel = QLabel(self.subDataFrame)
        self.gustValueLabel.setObjectName(u"gustValueLabel")
        sizePolicy3.setHeightForWidth(self.gustValueLabel.sizePolicy().hasHeightForWidth())
        self.gustValueLabel.setSizePolicy(sizePolicy3)
        self.gustValueLabel.setFont(font3)
        self.gustValueLabel.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignVCenter)

        self.horizontalLayout.addWidget(self.gustValueLabel)

        self.rightSubSpacer = QSpacerItem(40, 0, QSizePolicy.Minimum, QSizePolicy.Minimum)

        self.horizontalLayout.addItem(self.rightSubSpacer)


        self.horizontalLayout_3.addLayout(self.horizontalLayout)

        self.horizontalLayout_3.setStretch(0, 1)
        self.horizontalLayout_3.setStretch(1, 1)

        self.verticalLayout_2.addWidget(self.subDataFrame)

        # if QT_CONFIG(shortcut)
        self.maxTitle.setBuddy(self.maxValueLabel)
        self.gustTitle.setBuddy(self.gustValueLabel)
        #endif // QT_CONFIG(shortcut)

        self.retranslateUi(Frame)

        QMetaObject.connectSlotsByName(Frame)
    # setupUi

    def retranslateUi(self, Frame):
	    Frame.setWindowTitle(QCoreApplication.translate("Frame", u"Frame", None))
	    self.maxTitle.setText(QCoreApplication.translate("Frame", u"Lull:", None))
	    self.maxValueLabel.setText(QCoreApplication.translate("Frame", u"0", None))
	    self.gustTitle.setText(QCoreApplication.translate("Frame", u"Gust:", None))
	    self.gustValueLabel.setText(QCoreApplication.translate("Frame", u"0", None))
    # retranslateUi


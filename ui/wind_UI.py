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

from widgets.DynamicLabel import DynamicLabel
from widgets.DynamicLabel import DynamicLabelBuddy


class Ui_Frame(object):
    def setupUi(self, Frame):
        if not Frame.objectName():
            Frame.setObjectName(u"Frame")
        Frame.resize(620, 626)
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
        self.topSpacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.verticalLayout.addItem(self.topSpacer)

        self.centerCluster = QVBoxLayout()
        self.centerCluster.setSpacing(0)
        self.centerCluster.setObjectName(u"centerCluster")
        self.verticalSpacer = QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.centerCluster.addItem(self.verticalSpacer)

        self.directionLabel = DynamicLabel(self.mainFrame)
        self.directionLabel.setObjectName(u"directionLabel")
        sizePolicy1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.directionLabel.sizePolicy().hasHeightForWidth())
        self.directionLabel.setSizePolicy(sizePolicy1)
        font1 = QFont()
        font1.setFamily(u"SF Pro Rounded")
        font1.setPointSize(90)
        font1.setBold(True)
        font1.setWeight(75)
        self.directionLabel.setFont(font1)
        self.directionLabel.setAlignment(Qt.AlignBottom|Qt.AlignHCenter)

        self.centerCluster.addWidget(self.directionLabel)

        self.speedLabel = DynamicLabel(self.mainFrame)
        self.speedLabel.setObjectName(u"speedLabel")
        sizePolicy2 = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.speedLabel.sizePolicy().hasHeightForWidth())
        self.speedLabel.setSizePolicy(sizePolicy2)
        self.speedLabel.setFont(font1)
        self.speedLabel.setAlignment(Qt.AlignHCenter|Qt.AlignTop)

        self.centerCluster.addWidget(self.speedLabel)

        self.centerCluster.setStretch(1, 5)
        self.centerCluster.setStretch(2, 2)

        self.verticalLayout.addLayout(self.centerCluster)

        self.bottomSpacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.verticalLayout.addItem(self.bottomSpacer)

        self.verticalLayout.setStretch(0, 1)
        self.verticalLayout.setStretch(1, 2)
        self.verticalLayout.setStretch(2, 1)

        self.verticalLayout_2.addWidget(self.mainFrame)

        self.subDataFrame = QFrame(Frame)
        self.subDataFrame.setObjectName(u"subDataFrame")
        sizePolicy3 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(1)
        sizePolicy3.setHeightForWidth(self.subDataFrame.sizePolicy().hasHeightForWidth())
        self.subDataFrame.setSizePolicy(sizePolicy3)
        font2 = QFont()
        font2.setPointSize(29)
        font2.setBold(False)
        font2.setWeight(50)
        self.subDataFrame.setFont(font2)
        self.horizontalLayout_3 = QHBoxLayout(self.subDataFrame)
        self.horizontalLayout_3.setSpacing(0)
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.horizontalLayout_3.setContentsMargins(0, 0, 0, 0)
        self.leftSubSpacer = QSpacerItem(40, 0, QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.horizontalLayout_3.addItem(self.leftSubSpacer)

        self.gustTitle = DynamicLabelBuddy(self.subDataFrame)
        self.gustTitle.setObjectName(u"gustTitle")
        sizePolicy4 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy4.setHorizontalStretch(6)
        sizePolicy4.setVerticalStretch(3)
        sizePolicy4.setHeightForWidth(self.gustTitle.sizePolicy().hasHeightForWidth())
        self.gustTitle.setSizePolicy(sizePolicy4)
        self.gustTitle.setFont(font)
        self.gustTitle.setAlignment(Qt.AlignRight | Qt.AlignTrailing | Qt.AlignVCenter)

        self.horizontalLayout_3.addWidget(self.gustTitle)

        self.gustValueLabel = DynamicLabel(self.subDataFrame)
        self.gustValueLabel.setObjectName(u"gustValueLabel")
        sizePolicy5 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy5.setHorizontalStretch(6)
        sizePolicy5.setVerticalStretch(9)
        sizePolicy5.setHeightForWidth(self.gustValueLabel.sizePolicy().hasHeightForWidth())
        self.gustValueLabel.setSizePolicy(sizePolicy5)
        self.gustValueLabel.setFont(font)
        self.gustValueLabel.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignVCenter)

        self.horizontalLayout_3.addWidget(self.gustValueLabel)

        self.maxTitle = DynamicLabelBuddy(self.subDataFrame)
        self.maxTitle.setObjectName(u"maxTitle")
        sizePolicy4.setHeightForWidth(self.maxTitle.sizePolicy().hasHeightForWidth())
        self.maxTitle.setSizePolicy(sizePolicy4)
        self.maxTitle.setFont(font)
        self.maxTitle.setAlignment(Qt.AlignRight | Qt.AlignTrailing | Qt.AlignVCenter)

        self.horizontalLayout_3.addWidget(self.maxTitle)

        self.maxValueLabel = DynamicLabel(self.subDataFrame)
        self.maxValueLabel.setObjectName(u"maxValueLabel")
        sizePolicy5.setHeightForWidth(self.maxValueLabel.sizePolicy().hasHeightForWidth())
        self.maxValueLabel.setSizePolicy(sizePolicy5)
        self.maxValueLabel.setFont(font)
        self.maxValueLabel.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignVCenter)

        self.horizontalLayout_3.addWidget(self.maxValueLabel)

        self.rightSubSpacer = QSpacerItem(40, 0, QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.horizontalLayout_3.addItem(self.rightSubSpacer)


        self.verticalLayout_2.addWidget(self.subDataFrame)

#if QT_CONFIG(shortcut)
        self.gustTitle.setBuddy(self.gustValueLabel)
        self.maxTitle.setBuddy(self.maxValueLabel)
#endif // QT_CONFIG(shortcut)

        self.retranslateUi(Frame)

        QMetaObject.connectSlotsByName(Frame)
    # setupUi

    def retranslateUi(self, Frame):
        Frame.setWindowTitle(QCoreApplication.translate("Frame", u"Frame", None))
        self.directionLabel.setText(QCoreApplication.translate("Frame", u"W", None))
        self.speedLabel.setText(QCoreApplication.translate("Frame", u"2.2", None))
        self.gustTitle.setText(QCoreApplication.translate("Frame", u"Gust: ", None))
        self.gustValueLabel.setText(QCoreApplication.translate("Frame", u"12mph", None))
        self.maxTitle.setText(QCoreApplication.translate("Frame", u"Lull:", None))
        self.maxValueLabel.setText(QCoreApplication.translate("Frame", u"30mph", None))
    # retranslateUi


# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'ComplicationCluster.ui'
##
## Created by: Qt User Interface Compiler version 5.15.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

from widgets.DynamicLabel import DynamicLabel
from widgets.ComplicationArray import ClusterGrid
from widgets.ComplicationArray import ClusterGridCenter


class Ui_ComplicationGroup(object):
    def setupUi(self, ComplicationGroup):
        if not ComplicationGroup.objectName():
            ComplicationGroup.setObjectName(u"ComplicationGroup")
        ComplicationGroup.resize(892, 641)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(ComplicationGroup.sizePolicy().hasHeightForWidth())
        ComplicationGroup.setSizePolicy(sizePolicy)
        font = QFont()
        font.setFamily(u"SF Compact Rounded")
        ComplicationGroup.setFont(font)
        ComplicationGroup.setStyleSheet(u"")
        self.mainLayout = QVBoxLayout(ComplicationGroup)
        self.mainLayout.setSpacing(0)
        self.mainLayout.setObjectName(u"mainLayout")
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.TopRow = QHBoxLayout()
        self.TopRow.setSpacing(1)
        self.TopRow.setObjectName(u"TopRow")
        self.topLeft = ClusterGrid(ComplicationGroup)
        self.topLeft.setObjectName(u"topLeft")
        sizePolicy1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy1.setHorizontalStretch(2)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.topLeft.sizePolicy().hasHeightForWidth())
        self.topLeft.setSizePolicy(sizePolicy1)
        self.topLeft.setStyleSheet(u"background: purple")

        self.TopRow.addWidget(self.topLeft)

        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setSpacing(1)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.titleLabel = DynamicLabel(ComplicationGroup)
        self.titleLabel.setObjectName(u"titleLabel")
        sizePolicy2 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.titleLabel.sizePolicy().hasHeightForWidth())
        self.titleLabel.setSizePolicy(sizePolicy2)
        self.titleLabel.setMinimumSize(QSize(0, 30))
        self.titleLabel.setMaximumSize(QSize(16777215, 50))
        self.titleLabel.setStyleSheet(u"background: gray")

        self.verticalLayout.addWidget(self.titleLabel)

        self.topArray = ClusterGrid(ComplicationGroup)
        self.topArray.setObjectName(u"topArray")
        sizePolicy3 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.topArray.sizePolicy().hasHeightForWidth())
        self.topArray.setSizePolicy(sizePolicy3)
        self.topArray.setStyleSheet(u"background: yellow")

        self.verticalLayout.addWidget(self.topArray)


        self.TopRow.addLayout(self.verticalLayout)

        self.topRight = ClusterGrid(ComplicationGroup)
        self.topRight.setObjectName(u"topRight")
        sizePolicy1.setHeightForWidth(self.topRight.sizePolicy().hasHeightForWidth())
        self.topRight.setSizePolicy(sizePolicy1)
        self.topRight.setStyleSheet(u"background: green")

        self.TopRow.addWidget(self.topRight)

        self.TopRow.setStretch(1, 6)

        self.mainLayout.addLayout(self.TopRow)

        self.CenterRow = QHBoxLayout()
        self.CenterRow.setSpacing(1)
        self.CenterRow.setObjectName(u"CenterRow")
        self.leftArray = ClusterGrid(ComplicationGroup)
        self.leftArray.setObjectName(u"leftArray")
        sizePolicy4 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy4.setHorizontalStretch(2)
        sizePolicy4.setVerticalStretch(5)
        sizePolicy4.setHeightForWidth(self.leftArray.sizePolicy().hasHeightForWidth())
        self.leftArray.setSizePolicy(sizePolicy4)
        self.leftArray.setStyleSheet(u"background: lightblue")

        self.CenterRow.addWidget(self.leftArray)

        self.center = ClusterGridCenter(ComplicationGroup)
        self.center.setObjectName(u"center")
        sizePolicy5 = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Minimum)
        sizePolicy5.setHorizontalStretch(6)
        sizePolicy5.setVerticalStretch(6)
        sizePolicy5.setHeightForWidth(self.center.sizePolicy().hasHeightForWidth())
        self.center.setSizePolicy(sizePolicy5)
        self.center.setStyleSheet(u"background: pink")

        self.CenterRow.addWidget(self.center)

        self.rightArray = ClusterGrid(ComplicationGroup)
        self.rightArray.setObjectName(u"rightArray")
        sizePolicy4.setHeightForWidth(self.rightArray.sizePolicy().hasHeightForWidth())
        self.rightArray.setSizePolicy(sizePolicy4)
        self.rightArray.setStyleSheet(u"background:orange")

        self.CenterRow.addWidget(self.rightArray)

        self.CenterRow.setStretch(1, 6)

        self.mainLayout.addLayout(self.CenterRow)

        self.BottomRow = QHBoxLayout()
        self.BottomRow.setSpacing(1)
        self.BottomRow.setObjectName(u"BottomRow")
        self.bottomLeft = ClusterGrid(ComplicationGroup)
        self.bottomLeft.setObjectName(u"bottomLeft")
        sizePolicy1.setHeightForWidth(self.bottomLeft.sizePolicy().hasHeightForWidth())
        self.bottomLeft.setSizePolicy(sizePolicy1)
        self.bottomLeft.setStyleSheet(u"background: brown")

        self.BottomRow.addWidget(self.bottomLeft)

        self.bottomArray = ClusterGrid(ComplicationGroup)
        self.bottomArray.setObjectName(u"bottomArray")
        sizePolicy6 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy6.setHorizontalStretch(6)
        sizePolicy6.setVerticalStretch(2)
        sizePolicy6.setHeightForWidth(self.bottomArray.sizePolicy().hasHeightForWidth())
        self.bottomArray.setSizePolicy(sizePolicy6)
        self.bottomArray.setStyleSheet(u"background: red")

        self.BottomRow.addWidget(self.bottomArray)

        self.bottomRight = ClusterGrid(ComplicationGroup)
        self.bottomRight.setObjectName(u"bottomRight")
        sizePolicy1.setHeightForWidth(self.bottomRight.sizePolicy().hasHeightForWidth())
        self.bottomRight.setSizePolicy(sizePolicy1)
        self.bottomRight.setStyleSheet(u"background: gray")

        self.BottomRow.addWidget(self.bottomRight)


        self.mainLayout.addLayout(self.BottomRow)

        self.mainLayout.setStretch(0, 3)
        self.mainLayout.setStretch(1, 6)
        self.mainLayout.setStretch(2, 3)

        self.retranslateUi(ComplicationGroup)

        QMetaObject.connectSlotsByName(ComplicationGroup)
    # setupUi

    def retranslateUi(self, ComplicationGroup):
        pass
    # retranslateUi


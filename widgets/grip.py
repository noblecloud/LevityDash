from PySide2.QtCore import QSize, Qt
from PySide2.QtGui import QPainter
from PySide2.QtWidgets import QSizeGrip


class Gripper(QSizeGrip):

	def __init__(self, *args, **kwargs):
		super(Gripper, self).__init__(*args, **kwargs)

	def paintEvent(self, event):
		p = QPainter(self)
		p.drawRect(self.rect())
		super(Gripper, self).paintEvent(event)

	def mousePressEvent(self, event):
		p = self.parent().parent()
		# self.parent().setWindowFlag(Qt.SubWindow, True)
		p.layout.removeWidget(self.parent())
		# self.setMinimumHeight(100)
		# self.setMinimumWidth(100)
		# self.setMinimumWidth(100000)
		# self.setMaximumWidth(100000)
		# self.parent().setParent(None)
		# self.parent().setParent(p)
		super(Gripper, self).mousePressEvent(event)

	def mouseMoveEvent(self, event):
		super(Gripper, self).mouseMoveEvent(event)

	def mouseReleaseEvent(self, event):
		self.parent().autoSetCell()
		self.parent().parent().buildGrid()
# self.setMinimumHeight((self.parent().cell.h * 100) - 30)
# self.setMaximumHeight(self.parent().cell.h * 100)
# self.setMinimumWidth((self.parent().cell.w * 100) - 30)
# self.setMaximumWidth(self.parent().cell.w * 100)

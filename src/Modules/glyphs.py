from PySide2.QtGui import QPainterPath, QPalette, Qt
from PySide2.QtWidgets import QApplication, QGraphicsPathItem


class Glyph(QGraphicsPathItem):
	def __init__(self, parent=None, weight=None, color=None, size=None):
		super().__init__(parent)

		if size is None:
			size = 0.8
		self.size = size

		if color is None:
			color = QApplication.palette().color(QPalette.WindowText)

		self.color = color

		if weight is None:
			weight = 15

		self.weight = weight

		pen = self.pen()
		pen.setColor(self.color)
		pen.setWidth(self.weight)
		# set pen to round line
		pen.setJoinStyle(Qt.RoundJoin)
		pen.setCapStyle(Qt.RoundCap)
		self.setPen(pen)
		self.setPath(self.create_path())

	# def show(self):
	# 	# move to center of parent
	# 	# weight = self.weight * self.parentItem().containingRect().width() * self.size
	# 	#
	# 	# pen = self.pen()
	# 	# pen.setWidthF(weight)
	#
	# 	self.setPos(self.parentItem().containingRect().center())
	# 	# self.setPos(self.size, self.size)

	def itemChange(self, change, value):
		if change == QGraphicsPathItem.ItemVisibleChange:
			if value:
				self.setPos(self.parentItem().containingRect().center())
			# self.setPos(self.size, self.size)
		return super().itemChange(change, value)


class Plus(Glyph):

	def create_path(self):
		path = QPainterPath()
		size = self.parentItem().containingRect().width()*self.size/4
		path.moveTo(0, -size)
		path.lineTo(0, size)
		path.moveTo(-size, 0)
		path.lineTo(size, 0)
		return path


class BackArrow(Glyph):

	def create_path(self):
		path = QPainterPath()
		size = self.size*self.parentItem().containingRect().width()/4
		path.moveTo(.5*size, -1*size)
		path.lineTo(-0.5*size, 0*size)
		path.lineTo(.5*size, 1*size)
		path.translate(-size*0.3, 0)
		# path.moveTo(-1, -1)
		# path.lineTo(-1 * size, 1 * size)
		# path.lineTo(-1, 2 * size)
		# move to center by moving half of the width
		# path.translate(size/2, size/-2)

		return path

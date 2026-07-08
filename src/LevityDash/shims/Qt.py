from functools import cached_property
from typing import ClassVar

import numpy as np
import PySide6

from PySide6.QtGui import QPixmap as _QPixmap
from PySide6.QtGui import QImage as _QImage
from PySide6.QtWidgets import QGraphicsPixmapItem as _QGraphicsPixmapItem


class QImage(_QImage):
	__name__: ClassVar[str] = 'QImage[asArray]'

	def asArray(self) -> np.array:
		incomingImage = self.convertToFormat(PySide6.QtGui.QImage.Format.Format_RGB32)

		width = incomingImage.width()
		height = incomingImage.height()

		ptr = incomingImage.constBits()
		arr = np.array(ptr).reshape((height, width, 4))
		return arr

	@cached_property
	def array(self) -> np.array:
		return self.asArray()


class QPixmap(_QPixmap):
	__name__: ClassVar[str] = 'QPixmap[asArray]'

	def asArray(self) -> np.array:
		return self.toImage().asArray()

	@cached_property
	def array(self) -> np.array:
		return self.asArray()


class QGraphicsPixmapItem(_QGraphicsPixmapItem):
	__name__: ClassVar[str] = 'QGraphicsPixmapItem[asArray]'

	def asArray(self) -> np.array:
		return self.pixmap().asArray()

	@property
	def array(self) -> np.array:
		return self.asArray()


PySide6.QtGui.QImage.QImage = QImage
PySide6.QtGui.QPixmap.QPixmap = QPixmap
PySide6.QtWidgets.QGraphicsPixmapItem.QGraphicsPixmapItem = QGraphicsPixmapItem

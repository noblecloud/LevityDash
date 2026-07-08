from PySide6.QtGui import QPainterPath, QPen, QPainter, QBrush, Qt

from LevityDash.shims.Qt import QImage


def path_to_image(
	path: QPainterPath,
	painter: QPainter = None,
	pen: QPen = None,
	brush: QBrush = None
) -> QImage:

	if painter is None:
		painter = QPainter()
	if pen is None:
		pen = QPen()
	if brush is None:
		brush = QBrush()

	bounding_rect = path.boundingRect()

	image = QImage(bounding_rect.size().toSize(), QImage.Format.Format_RGB32)
	image.fill(Qt.GlobalColor.white)

	painter.begin(image)
	painter.setPen(pen)
	painter.setBrush(brush)
	painter.drawPath(path.translated(-bounding_rect.topLeft()))
	painter.end()

	return image

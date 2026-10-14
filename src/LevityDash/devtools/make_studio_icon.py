"""Dev-only: draw the Studio icon from the LevityDash icon, so the two can be told apart in the Dock.

    QT_QPA_PLATFORM=offscreen python src/LevityDash/devtools/make_studio_icon.py

The LevityDash icon's purple becomes teal, and one tile gets the corner handles of a selection, the mark of an editor.
Writes `resources/ui-elements/icon-studio.png`. Run it again only if the LevityDash icon changes.
"""
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen

ART = Path(__file__).resolve().parents[1] / 'resources' / 'ui-elements'
SHIFT = -100  # degrees of hue: purple (about 265) to teal (about 165)


def shifted(image: QImage) -> QImage:
	out = image.convertToFormat(QImage.Format.Format_ARGB32)
	for y in range(out.height()):
		for x in range(out.width()):
			c = out.pixelColor(x, y)
			if c.alpha() and c.hsvSaturation() > 40:
				hue, sat, val, alpha = c.getHsv()
				c.setHsv((hue + SHIFT) % 360, sat, val, alpha)
				out.setPixelColor(x, y, c)
	return out


def main() -> int:
	QGuiApplication.instance() or QGuiApplication(sys.argv)
	icon = shifted(QImage(str(ART / 'icon512.png')))
	painter = QPainter(icon)
	painter.setRenderHint(QPainter.RenderHint.Antialiasing)
	tile = QRectF(206, 226, 178, 68)  # the long middle tile
	painter.setPen(QPen(QColor('#ffb020'), 5))
	painter.setBrush(Qt.BrushStyle.NoBrush)
	painter.drawRect(tile)
	painter.setPen(QPen(QColor('#ffb020'), 5))
	painter.setBrush(QColor('#ffffff'))
	for corner in (tile.topLeft(), tile.topRight(), tile.bottomLeft(), tile.bottomRight()):
		painter.drawRect(QRectF(corner.x() - 11, corner.y() - 11, 22, 22))
	painter.end()
	icon.save(str(ART / 'icon-studio.png'))
	return 0


if __name__ == '__main__':
	raise SystemExit(main())

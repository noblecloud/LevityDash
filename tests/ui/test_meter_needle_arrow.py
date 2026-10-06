"""The wind arrow (`needle: {type: arrow}`) must be one silhouette, not stacked parts.

`Needle._style_arrow` composes the arrow from four pieces: a stroked head shaft,
a head triangle, a stroked tail shaft and a tail dot. The head sits over the end
of the shaft and the dot over the end of the tail, so the pieces overlap. Left as
separate subpaths the fill double-covers those overlaps; under the default
odd-even rule the overlaps cancel instead - a slot through the arrowhead and a
bite out of the tail dot, the winding seam `wrap-compass.levity` shows.

The invariant this pins: a path with no overlapping subpaths describes the same
region under odd-even and winding fill, so the two fill areas agree. Stacked,
overlapping parts make them disagree - the odd-even area drops what the winding
area keeps - which is exactly the bug.

Building the arrow through a real sandbox gauge (as `test_gauge_fill_sources`
does) means the test exercises the same `Needle.draw` path the app uses.
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath

from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import Realtime

#: The arrow `wrap-compass.levity` draws, minus its 800ms animation.
ARROW = {
	'type': 'arrow', 'length': '34%', 'width': '2.2%',
	'head': '12%', 'tail': '28%', 'tail-dot': '5%',
}
#: The same arrow with its head at the inner end. Its triangle winds the opposite
#: way to `out`'s, so it is the case a fill-rule-only fix leaves overlapping.
ARROW_IN = {**ARROW, 'point': 'in'}

RASTER_SCALE = 4.0


def _arrow_needle(dashboard, needle):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '40%', 'height': '40%'})
	sandbox.state = {'items': [{
		'type': 'realtime.gauge', 'name': 'g', 'key': 'environment.temperature.temperature',
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
		'display': {'needle': dict(needle)},
	}]}
	dashboard.app.processEvents()
	gauge = next(c for c in sandbox.childPanels if isinstance(c, Realtime)).display
	return sandbox, gauge


def _fill_area(path: QPainterPath, rule) -> float:
	"""The path's filled area in px^2, rasterised offscreen under ``rule``."""
	rect = path.boundingRect().adjusted(-2, -2, 2, 2)
	image = QImage(max(1, int(rect.width() * RASTER_SCALE)), max(1, int(rect.height() * RASTER_SCALE)),
	               QImage.Format.Format_Grayscale8)
	image.fill(0)
	painter = QPainter(image)
	painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
	painter.scale(RASTER_SCALE, RASTER_SCALE)
	painter.translate(-rect.left(), -rect.top())
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(QColor(255, 255, 255))
	shaped = QPainterPath(path)
	shaped.setFillRule(rule)
	painter.drawPath(shaped)
	painter.end()
	filled = sum(1 for byte in bytes(image.constBits()) if byte > 127)
	return filled / (RASTER_SCALE * RASTER_SCALE)


def _subpath_count(path: QPainterPath) -> int:
	move = QPainterPath.ElementType.MoveToElement
	return sum(1 for i in range(path.elementCount()) if path.elementAt(i).type == move)


@pytest.mark.parametrize('needle', [ARROW, ARROW_IN], ids=['point-out', 'point-in'])
def test_arrow_fill_has_no_overlapping_subpaths(dashboard, needle):
	sandbox, gauge = _arrow_needle(dashboard, needle)
	try:
		path = gauge.needle.path()
		assert not path.isEmpty(), 'the arrow drew nothing'
		odd = _fill_area(path, Qt.FillRule.OddEvenFill)
		wind = _fill_area(path, Qt.FillRule.WindingFill)
		assert odd > 0
		assert odd == wind, (
			'the arrow is stacked overlapping subpaths: the odd-even fill '
			f'({odd:.1f}px^2) drops the overlaps the winding fill ({wind:.1f}px^2) keeps'
		)
	finally:
		sandbox.scene().removeItem(sandbox)


@pytest.mark.parametrize('needle', [ARROW, ARROW_IN], ids=['point-out', 'point-in'])
def test_arrow_parts_merge_into_two_silhouettes(dashboard, needle):
	"""The four pieces flatten to the head+shaft and the tail+dot, and no more."""
	sandbox, gauge = _arrow_needle(dashboard, needle)
	try:
		path = gauge.needle.path()
		assert _subpath_count(path) == 2, (
			f'the arrow is {_subpath_count(path)} subpaths; the overlapping head/shaft and '
			'tail/dot should each have merged into one boundary'
		)
	finally:
		sandbox.scene().removeItem(sandbox)

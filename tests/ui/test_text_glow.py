"""A tick label, a caption and a plain GaugeText draw their glow from their own glyphs.

`paintGlow` draws the halo and nothing else; the core text follows, unchanged. These
tests capture what each item's `paint` hands the helper: the item's own glyph outline
path, `filled=True`, and the glyph stroke thickness as the base width. With no glow the
helper is never reached, so the old paint path is untouched and the bounds do not grow.

The halo must be the glyph outline, never a box around the item's bounding rect, so the
tests also check the path's shape: one subpath per glyph contour (a rectangle is one),
and the counters of a letter left empty (a box would fill them).
"""
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QStyleOptionGraphicsItem

from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import Realtime
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter import elements
from LevityDash.lib.ui.glow import Glow


def _gauge(dashboard, display):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '40%', 'height': '40%'})
	sandbox.state = {'items': [{
		'type': 'realtime.gauge', 'name': 'g', 'key': 'environment.temperature.temperature',
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
		'display': {'range': {'min': 0, 'max': 100}, **display},
	}]}
	dashboard.app.processEvents()
	gauge = next(c for c in sandbox.childPanels if isinstance(c, Realtime)).display
	return sandbox, gauge


def _first_label(dashboard, gauge):
	"""A laid-out major tick label: its glyph path is built and not empty."""
	labels = gauge.majorDivisions.labels
	dashboard.wait_until(lambda: any(not label.path().isEmpty() for label in labels), message='a tick label lays out')
	return next(label for label in labels if not label.path().isEmpty())


class _Capture:
	def __init__(self):
		self.calls = []

	def __call__(self, painter, path, brush, width, glow, filled=False, dashes=None):
		self.calls.append((path, width, glow, filled))


@pytest.fixture
def capture(monkeypatch):
	cap = _Capture()
	monkeypatch.setattr(elements, 'paintGlow', cap)
	return cap


def _paint(item, capture):
	"""Paint one item and return only the calls that paint made.

	The scene paints itself while events are pumped, so the recorder is cleared right
	before the item is painted and the call is read straight back.
	"""
	capture.calls.clear()
	image = QImage(8, 8, QImage.Format.Format_ARGB32_Premultiplied)
	image.fill(0)
	painter = QPainter(image)
	try:
		item.paint(painter, QStyleOptionGraphicsItem(), None)
	finally:
		painter.end()
	return list(capture.calls)


def _assert_glyph_halo(path, item):
	"""The halo path is the item's own glyph outline, not a box around its bounds."""
	assert path == item.path(), "the halo is drawn from the item's glyph path, not a rectangle"
	subpaths = path.toSubpathPolygons()
	assert len(subpaths) > 1, 'one closed subpath means a box; glyph outlines give one per contour'
	assert path.elementCount() > 5, 'a rectangle path is five elements; glyph outlines carry curves'


def test_a_tick_label_draws_the_group_glow(dashboard, capture):
	sandbox, gauge = _gauge(dashboard, {'major': {'labels': {'glow': True}}})
	try:
		label = _first_label(dashboard, gauge)
		assert label._glowToDraw() == Glow(), 'the label resolves the glow its group carries'
		calls = _paint(label, capture)
		assert len(calls) == 1, 'the label reaches paintGlow exactly once'
		path, width, glow, filled = calls[0]
		assert filled is True and not path.isEmpty(), 'the halo is the filled glyph outline'
		assert width > 0, 'the halo has a base width to grow from'
		_assert_glyph_halo(path, label)
	finally:
		sandbox.scene().removeItem(sandbox)


def test_a_glowing_label_grows_its_bounds(dashboard):
	sandbox, gauge = _gauge(dashboard, {})
	try:
		label = _first_label(dashboard, gauge)
		bare = label.boundingRect()
		label.glow = True
		grown = label.boundingRect()
		assert grown.contains(bare) and grown != bare, 'the halo needs the extra room or it clips'
	finally:
		sandbox.scene().removeItem(sandbox)


def test_no_glow_leaves_the_paint_untouched(dashboard, capture):
	sandbox, gauge = _gauge(dashboard, {})
	try:
		label = _first_label(dashboard, gauge)
		assert label._glowToDraw() is None, 'no glow anywhere: nothing to draw'
		bare = label.boundingRect()
		label.glow = False
		assert label.boundingRect() == bare, 'glow: false must not grow the bounds'
		assert _paint(label, capture) == [], 'no glow: paintGlow is never reached'
	finally:
		sandbox.scene().removeItem(sandbox)


def test_a_caption_draws_its_own_glow(dashboard, capture):
	sandbox, gauge = _gauge(dashboard, {'caption': {'text': 'Humidity', 'glow': True}})
	try:
		item = gauge._captionItem
		assert item is not None and item.glow == Glow()
		calls = _paint(item, capture)
		assert len(calls) == 1
		path, width, glow, filled = calls[0]
		assert filled is True and not path.isEmpty() and width > 0
		_assert_glyph_halo(path, item)
	finally:
		sandbox.scene().removeItem(sandbox)


def test_the_halo_leaves_a_letter_counter_empty(dashboard, capture):
	"""A box around the text would fill the holes in an O; the glyph outline does not."""
	sandbox, gauge = _gauge(dashboard, {'caption': {'text': 'OO', 'size': '34%', 'glow': True}})
	try:
		item = gauge._captionItem
		path = _paint(item, capture)[0][0]
		_assert_glyph_halo(path, item)
		rect = path.boundingRect()
		for fraction in (0.25, 0.75):
			centre = QPointF(rect.left() + rect.width() * fraction, rect.center().y())
			assert not path.contains(centre), 'the counter is empty; a bounding box would fill it'
		assert path.contains(QPointF(rect.left() + 2, rect.center().y())), 'the glyph stroke is ink'
	finally:
		sandbox.scene().removeItem(sandbox)


def test_a_caption_without_glow_draws_no_halo(dashboard, capture):
	sandbox, gauge = _gauge(dashboard, {'caption': {'text': 'Humidity'}})
	try:
		item = gauge._captionItem
		assert item is not None and item.glow is None
		assert _paint(item, capture) == []
	finally:
		sandbox.scene().removeItem(sandbox)


def test_gauge_text_draws_its_own_glow(dashboard, capture, monkeypatch):
	# GaugeText cannot be built through its normal init: its base chain reaches
	# GaugeItem.__init__ with no arguments and no gauge (a pre-existing dead class,
	# unchanged here), so the gauge lookup is stubbed to exercise its paint.
	sandbox, gauge = _gauge(dashboard, {})
	monkeypatch.setattr(elements.GaugeItem, '_GaugeItem__extract_gauge', lambda self, args, kwargs: gauge)
	try:
		text = elements.GaugeText(labelGroup=gauge.majorDivisions.labels, value='X')
		text.glow = True
		calls = _paint(text, capture)
		assert len(calls) == 1
		path, width, glow, filled = calls[0]
		assert filled is True and not path.isEmpty() and width > 0
	finally:
		sandbox.scene().removeItem(sandbox)

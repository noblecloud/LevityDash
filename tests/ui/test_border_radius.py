"""`border: {radius: …}` rounds the corners of a border on all edges."""
import pytest
from PySide6.QtCore import QPointF, Qt

from tests.conftest import pump
from LevityDash.lib.ui.frontends.PySide.Modules import Panel


@pytest.fixture
def box(dashboard):
	item = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '40%', 'height': '30%'})
	yield item
	if item.scene() is not None:
		item.scene().removeItem(item)


def border(dashboard, box, **state):
	box.state = {'border': {'enabled': True, **state}}
	pump(dashboard.app, 0.2)
	return box.borderProp


def corner_cut(path, rect):
	"""True when the path leaves the rect's top-left corner point out."""
	return not path.contains(QPointF(rect.left() + 0.5, rect.top() + 0.5))


def test_without_a_radius_the_border_is_a_plain_rectangle(dashboard, box):
	edge = border(dashboard, box)
	assert not corner_cut(edge.path(), box.rect())


def test_a_pixel_radius_cuts_the_corner(dashboard, box):
	edge = border(dashboard, box, radius='20px')
	assert corner_cut(edge.path(), box.rect())


def test_a_percent_radius_is_a_share_of_the_shorter_side_and_stops_at_half(dashboard, box):
	edge = border(dashboard, box, radius='50%')
	rect = box.rect()
	assert edge.radius_px(rect) == pytest.approx(min(rect.width(), rect.height()) / 2)
	assert border(dashboard, box, radius='900px').radius_px(rect) == pytest.approx(min(rect.width(), rect.height()) / 2)


def test_a_bad_radius_is_zero(dashboard, box):
	edge = border(dashboard, box, radius='round')
	assert edge.radius_px(box.rect()) == 0.0


def test_the_radius_survives_a_save(dashboard, box):
	edge = border(dashboard, box, radius='12px')
	assert edge.state['radius'] == '12px'
	assert edge.radius_px(box.rect()) == pytest.approx(12.0)


def test_a_fill_paints_inside_the_rounded_border_and_sits_behind_the_content(dashboard, box):
	edge = border(dashboard, box, radius='20px', fill='#336699', weight=0)
	assert edge.brush().color().name() == '#336699'
	assert edge.pen().style() == Qt.NoPen
	assert edge.flags() & edge.GraphicsItemFlag.ItemStacksBehindParent


def test_no_fill_leaves_the_border_a_line_on_top(dashboard, box):
	edge = border(dashboard, box, radius='20px')
	assert edge.brush().style() == Qt.NoBrush
	assert not edge.flags() & edge.GraphicsItemFlag.ItemStacksBehindParent


def test_a_fill_on_some_edges_only_is_ignored(dashboard, box):
	edge = border(dashboard, box, edges='top', fill='#336699')
	assert edge.brush().style() == Qt.NoBrush


def test_a_fill_takes_a_translucent_colour(dashboard, box):
	edge = border(dashboard, box, radius='20px', fill='#ffffff22', weight=0)
	assert edge.brush().color().alpha() == 0x22


def test_a_fill_takes_a_colour_with_alpha_written_as_a_mapping(dashboard, box):
	edge = border(dashboard, box, radius='20px', fill={'color': '#ffffff', 'alpha': 0.2}, weight=0)
	assert edge.brush().color().alpha() == pytest.approx(51, abs=1)

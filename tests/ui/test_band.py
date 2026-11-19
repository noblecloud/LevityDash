"""The `band` container: a ring of items that scrolls, a page at a time or continuously."""
import pytest

from tests.conftest import pump
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Containers.Band import Band, scrolls, slots


@pytest.fixture
def slot(dashboard):
	box = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': '40%', 'height': '10%'})
	yield box
	if box.scene() is not None:
		box.scene().removeItem(box)


def make(slot, count=5, **settings) -> Band:
	state = {'type': 'band', 'name': 'band', 'visible': 3, 'dwell': 3600, 'transition': 0, **settings}
	state['items'] = [{'type': 'group', 'name': f'c{i}'} for i in range(count)]
	slot.state = {'items': [state]}
	return next(c for c in slot.childItems() if isinstance(c, Band))


def child(band, name):
	return next(c for c in band.choices if c.stateName == name)


def test_ring_slots():
	assert slots(5, 0, 1) == [0, 1, 2, 3, -1]  # the last waits just off the start, ready to come in
	assert slots(5, 1, 1) == [-1, 0, 1, 2, 3]
	assert slots(5, 5, 1) == slots(5, 0, 1)
	assert slots(5, 1, -1) == [1, 2, 3, -1, 0]
	assert all(-1 <= v < 4 for p in range(0, 50) for v in slots(5, p / 10, 1))


def test_scrolls_needs_one_more_than_visible():
	assert scrolls(5, 3) and scrolls(4, 3)
	assert not scrolls(3, 3) and not scrolls(4, 3.5) and not scrolls(1, 1)


def test_items_share_the_band(dashboard, slot):
	band = make(slot, gap='0%')
	pump(dashboard.app, 0.3)
	third = band.rect().width() / 3
	for c in band.choices:
		assert c.rect().width() == pytest.approx(third, rel=0.01)
	assert child(band, 'c1').pos().x() == pytest.approx(third, rel=0.01)


def test_step_moves_a_stride(dashboard, slot):
	band = make(slot, mode='step')
	pump(dashboard.app, 0.3)
	stride = band.rect().width() / 3
	band._advance()
	assert band.position == pytest.approx(1)
	x = lambda c: c.pos().x() + c.transform().dx()
	assert x(child(band, 'c1')) == pytest.approx(0, abs=1)
	assert x(child(band, 'c0')) == pytest.approx(-stride, rel=0.01)  # left the start, waiting off screen


def test_wraps_to_start(dashboard, slot):
	band = make(slot, mode='step')
	pump(dashboard.app, 0.3)
	for _ in range(5):
		band._advance()
	assert band.position == pytest.approx(0)
	assert child(band, 'c0').transform().dx() == pytest.approx(0) and child(band, 'c2').transform().dx() == pytest.approx(0)


def test_continuous_ticks_and_stops_when_it_fits(dashboard, slot):
	band = make(slot, count=3, mode='continuous')
	pump(dashboard.app, 0.3)
	assert not band.running and not band._frameTimer.isActive()
	band = make(slot, count=5, mode='continuous', speed=2)
	pump(dashboard.app, 0.3)
	assert band.running
	band.dwell
	dashboard.wait_until(lambda: band._frameTimer.isActive(), message='the marquee runs')


def test_right_reverses(dashboard, slot):
	band = make(slot, mode='step', direction='right')
	pump(dashboard.app, 0.3)
	band._advance()
	assert band.position == pytest.approx(4)


def test_vertical_uses_y(dashboard, slot):
	band = make(slot, direction='up')
	pump(dashboard.app, 0.3)
	assert band.vertical
	assert child(band, 'c1').pos().y() == pytest.approx(band.rect().height() / 3, rel=0.01)


def test_bad_settings_are_named(dashboard, slot):
	band = make(slot)
	for name, value in (('mode', 'sideways'), ('direction', 'north'), ('visible', 0), ('gap', '80%')):
		with pytest.raises(ValueError):
			getattr(Band, name).decodeValue(value, band)


def test_when_takes_an_item_out_of_the_ring(dashboard, slot):
	"""An item whose `when:` fails is hidden and the others close up; when it holds again the item comes back in place."""
	state = {'type': 'band', 'name': 'band', 'visible': 3, 'dwell': 3600, 'transition': 0, 'gap': '0%'}
	state['items'] = [{'type': 'group', 'name': f'c{i}'} for i in range(5)]
	state['items'][1]['when'] = False
	slot.state = {'items': [state]}
	band = next(c for c in slot.childItems() if isinstance(c, Band))
	pump(dashboard.app, 0.3)
	third = band.rect().width() / 3
	at = lambda c: c.pos().x() + c.transform().dx()
	assert [c.stateName for c in band.shown] == ['c0', 'c2', 'c3', 'c4']
	assert not child(band, 'c1').isVisible()
	assert at(child(band, 'c2')) == pytest.approx(third, rel=0.01)  # moved up into c1's slot
	child(band, 'c1').when = True
	pump(dashboard.app, 0.3)
	assert child(band, 'c1').isVisible() and len(band.shown) == 5
	assert at(child(band, 'c2')) == pytest.approx(2 * third, rel=0.01)
	assert at(child(band, 'c1')) == pytest.approx(third, rel=0.01)

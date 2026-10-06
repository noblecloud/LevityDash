"""The bar meter: loading, placing values on the track, saving, and releasing value sources."""
import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter

from LevityDash.lib.plugins.computed import computedEngine
from LevityDash.lib.ui.frontends.PySide.Modules import Panel
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Realtime import Realtime
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.bar import Bar, _niceStep
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.track import LineTrack

KEY = 'environment.temperature.temperature'
EXPR = 'max(environment.temperature.temperature, today)'


def _bar(dashboard, display, key=KEY, width='60%', height='20%'):
	sandbox = Panel(parent=dashboard.scene.base, geometry={'x': '0%', 'y': '0%', 'width': width, 'height': height})
	sandbox.state = {'items': [{
		'type': 'realtime.bar', 'name': 'b', 'key': key,
		'geometry': {'x': '0%', 'y': '0%', 'width': '100%', 'height': '100%'},
		'display': {'range': {'min': 0, 'max': 100}, **display},
	}]}
	dashboard.app.processEvents()
	panel = next(c for c in sandbox.childPanels if isinstance(c, Realtime))
	return sandbox, panel, panel.display


def _paint(bar) -> QImage:
	"""The bar's own paint pass on a blank image, so a test can look at pixels without a scene render."""
	rect = bar.rect()
	image = QImage(int(rect.width()) + 4, int(rect.height()) + 4, QImage.Format.Format_ARGB32)
	image.fill(0)
	painter = QPainter(image)
	painter.translate(2 - rect.left(), 2 - rect.top())
	bar.paintBar(painter)
	painter.end()
	return image


def _red(image: QImage) -> int:
	return sum(1 for x in range(0, image.width(), 3) for y in range(0, image.height(), 3)
		if (c := image.pixelColor(x, y)).red() > 200 and c.green() < 60 and c.alpha() > 200)


def _ink(image: QImage) -> int:
	return sum(1 for x in range(0, image.width(), 3) for y in range(0, image.height(), 3) if image.pixelColor(x, y).alpha())


def test_nice_step():
	assert _niceStep(100) == 20
	assert _niceStep(12) == 2
	assert _niceStep(1) == 0.2
	assert _niceStep(0) == 1


def test_line_track_runs_both_ways():
	from PySide6.QtCore import QPointF
	up = LineTrack(QPointF(10, 100), QPointF(10, 0))
	assert up.pointAt(0.25) == QPointF(10, 75)
	assert up.normalAt(0.5) == QPointF(1, 0), 'a standing bar has its `after` side on the right'
	across = LineTrack(QPointF(0, 5), QPointF(100, 5))
	assert across.normalAt(0.5) == QPointF(0, 1), 'a lying bar has its `after` side below'


def test_bar_loads_and_draws(dashboard):
	sandbox, panel, bar = _bar(dashboard, {'caption': 'Test', 'fill': {'color': '#ff8a3d'}, 'value-label': {'position': 'end'}})
	assert isinstance(bar, Bar) and panel.subtag == 'bar'
	bar.value = 40.0
	assert _ink(_paint(bar)) > 50
	sandbox.scene().removeItem(sandbox)


def test_fill_end_follows_the_value(dashboard):
	sandbox, panel, bar = _bar(dashboard, {'fill': {'color': '#ff0000'}, 'value-label': {'visible': False}})
	bar.value = 25.0
	narrow = _red(_paint(bar))
	bar.value = 75.0
	wide = _red(_paint(bar))
	assert wide > narrow, 'more of the track is filled at 75 than at 25'
	sandbox.scene().removeItem(sandbox)


def test_every_style_and_orientation_paints(dashboard):
	for display in ({'style': 'battery'}, {'style': 'thermometer'}, {'orientation': 'vertical'},
					{'fill': {'color': '#fff', 'segments': 8, 'gap': '4%'}}, {'pointer': {'type': 'dot'}},
					{'major': {'interval': 25, 'labels': True}, 'minor': {'count': 5}},
					{'value-label': {'position': 'inside'}}, {'value-label': {'position': 'above'}}):
		sandbox, panel, bar = _bar(dashboard, display, height='40%')
		bar.value = 60.0
		assert _ink(_paint(bar)) > 20, f'{display} drew nothing'
		sandbox.scene().removeItem(sandbox)


def test_zone_colours_the_fill_by_position(dashboard):
	zones = [{'to': 50, 'color': '#ff0000'}, {'from': 50, 'color': '#00ff00'}]
	sandbox, panel, bar = _bar(dashboard, {'zones': zones, 'fill': {'color': 'zone'}})
	assert bar._zoneColorAt(0.25).name() == '#ff0000'
	assert bar._zoneColorAt(0.75).name() == '#00ff00'
	sandbox.scene().removeItem(sandbox)


def test_round_trip(dashboard):
	display = {
		'orientation': 'vertical', 'style': 'battery', 'track': {'weight': '20%', 'cap': 'flat'},
		'fill': {'to': 50, 'color': '#ff8a3d', 'segments': 5},
		'zones': [{'to': 50, 'color': '#ff0000'}], 'markers': [{'value': 20, 'type': 'dot'}],
		'pointer': {'type': 'triangle'}, 'major': {'interval': 25, 'labels': True},
		'value-label': {'position': 'end'}, 'caption': 'Charge',
	}
	sandbox, panel, bar = _bar(dashboard, display)
	state = bar.state
	for key, value in display.items():
		assert state[key] == value, key
	assert panel.subtag == 'bar'
	sandbox.scene().removeItem(sandbox)


def test_bad_specs_never_raise(dashboard):
	sandbox, panel, bar = _bar(dashboard, {
		'zones': [{'to': 'x', 'color': '#fff'}, {'color': None}, 'junk'],
		'fill': {'cap': 'pointy'},
		'markers': [{'value': True}, {'value': 5, 'type': 'star'}, 'junk'],
		'major': {'side': 'sideways'}, 'caption': 7,
	})
	bar.value = 10.0
	_paint(bar)
	assert not bar._zones and bar._fill is None and not bar._markers
	sandbox.scene().removeItem(sandbox)


def test_fill_follows_source_and_releases(dashboard):
	engine = computedEngine()
	sandbox, panel, bar = _bar(dashboard, {'range': {'min': -20, 'max': 120}, 'fill': {'from': 0, 'to': EXPR}})
	assert bar._pending == {('fill', 'to')}, 'no value yet: the fill is hidden'
	key = bar._bindings[0][1].source.key
	assert engine.refcount(key) >= 1
	before = engine.refcount(key)
	bar.fill = None
	assert engine.refcount(key) == before - 1, 'dropping the fill releases its source'
	assert not bar._bindings
	sandbox.scene().removeItem(sandbox)

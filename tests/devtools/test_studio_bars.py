"""The gauge editor edits a `realtime.bar` too: it draws the real `Bar`, shows the bar's own controls and writes a bar back."""
import pytest
import yaml

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from LevityDash.devtools import _studio_library as library  # noqa: E402
from LevityDash.devtools import studio  # noqa: E402
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.meter.bar import Bar  # noqa: E402

BARS = library.REFERENCES / 'bars'


@pytest.fixture
def editor(tmp_path, monkeypatch):
	monkeypatch.setenv('LEVITYDASH_STUDIO_DIR', str(tmp_path))
	win = studio.Studio(None)
	win.show()
	yield win
	win.close()


def test_the_library_lists_single_bars_as_gauge_editor_files():
	found = library.entries(realRoots=[])
	bars = {e.label for e in found if e.group == 'Bars'}
	assert {'bar progress', 'bar battery', 'bar thermometer'} <= bars
	assert library.classify(BARS / 'bar-progress.levity') == library.GAUGE
	assert library.classify(BARS / 'bar-showcase.levity') == library.DASHBOARD, 'many bars in a container stay in the dashboard editor'


def test_a_bar_opens_draws_and_saves_as_a_bar(editor):
	editor.loadFile(BARS / 'bar-battery.levity')
	assert editor.studio.kind == 'bar' and isinstance(editor.studio.gauge, Bar)
	assert editor.layer.gauge is None, 'a bar has no arc or needle handles'
	paths = {p for p in editor.rows}
	assert ('style',) in paths and ('orientation',) in paths
	assert ('needle', 'type') not in paths, 'the bar never draws the needle it inherits'
	[entry] = yaml.safe_load(editor.exportLevity())
	assert entry['type'] == 'realtime.bar' and entry['display']['style'] == 'battery'


def test_a_bar_edit_rebuilds_and_undoes(editor):
	editor.loadFile(BARS / 'bar-progress.levity')
	editor._edited(('style',), 'thermometer')
	editor.commitPending()
	QTest.qWait(50)
	assert editor.studio.gauge.style == 'thermometer'
	assert yaml.safe_load(editor.exportLevity())[0]['display']['style'] == 'thermometer'
	editor.undo()
	assert editor.studio.gauge.style == 'bar'


def test_opening_a_gauge_after_a_bar_goes_back_to_the_dial(editor):
	editor.loadFile(BARS / 'bar-progress.levity')
	editor.loadFile(library.REFERENCES / 'presets' / 'fill-dial.levity')
	assert editor.studio.kind == 'gauge' and not isinstance(editor.studio.gauge, Bar)
	assert yaml.safe_load(editor.exportLevity())[0]['type'] == 'realtime.gauge'


def _handles(editor):
	editor.layer.rebuildNow()
	return {(i.spec.kind, i.spec.tip.split(' to ')[0] if False else i.spec.tip): i for i in editor.layer.items}


def _drag(editor, item, fraction, cross=0.0):
	"""Drag `item` to the point `fraction` along the track, as the layer does on a mouse move."""
	from LevityDash.devtools._studio_bar_handles import Run
	run = Run(editor.studio.gauge)
	point = run.at(fraction, cross)
	editor.layer.begin(item, item.spec.position())
	editor.layer.move(item, point, Qt.KeyboardModifier.ControlModifier)
	editor.layer.end(item)
	editor.commitPending()


def test_a_bar_has_handles_and_they_sit_on_the_track(editor):
	from LevityDash.devtools._studio_bar_handles import Run
	editor.loadFile(BARS / 'bar-progress.levity')
	editor.layer.setEnabled(True)
	editor.layer.force = True
	items = editor.layer.items or (editor.layer.rebuildNow() or editor.layer.items)
	kinds = {i.spec.kind for i in items}
	assert {'needle', 'weight'} <= kinds
	run = Run(editor.studio.gauge)
	needle = next(i for i in items if i.spec.kind == 'needle')
	at = needle.spec.position()
	assert abs(run.crossOf(at)) < 1.0, 'the value handle is on the track'
	assert 0.0 <= run.tOf(at) <= 1.0


def test_dragging_the_value_handle_sets_the_value_and_the_weight_handle_writes_the_track(editor):
	editor.loadFile(BARS / 'bar-progress.levity')
	editor.layer.rebuildNow()
	needle = next(i for i in editor.layer.items if i.spec.kind == 'needle')
	_drag(editor, needle, 0.25)
	r = editor.studio.gauge.value_scale
	assert abs(float(editor.studio.gauge.value) - (r.min + r.span * 0.25)) < r.span * 0.02
	weight = next(i for i in editor.layer.items if i.spec.kind == 'weight')
	from LevityDash.devtools._studio_bar_handles import Run
	was = (yaml.safe_load(editor.exportLevity())[0]['display'].get('track') or {}).get('weight')
	half = Run(editor.studio.gauge).u * 0.2
	_drag(editor, weight, 0.3, cross=half)
	now = yaml.safe_load(editor.exportLevity())[0]['display']['track']['weight']
	assert now.endswith('%') and now != was
	editor.undo()
	assert (yaml.safe_load(editor.exportLevity())[0]['display'].get('track') or {}).get('weight') == was


def test_dragging_a_zone_edge_moves_the_cutoff_both_zones_share(editor):
	editor.loadFile(BARS / 'bar-progress.levity')
	editor.layer.rebuildNow()
	zones = [i for i in editor.layer.items if i.spec.kind == 'zone']
	if not zones:
		pytest.skip('this bar has no numeric zone edges')
	before = [dict(z) for z in editor.studio.gauge._zoneSpecs]
	_drag(editor, zones[0], 0.5)
	after = editor.studio.gauge._zoneSpecs
	assert after != before and any(abs(float(z[e]) - 50) < 3 for z in after for e in ('from', 'to') if isinstance(z.get(e), (int, float)))

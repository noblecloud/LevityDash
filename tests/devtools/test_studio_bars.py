"""The gauge editor edits a `realtime.bar` too: it draws the real `Bar`, shows the bar's own controls and writes a bar back."""
import pytest
import yaml

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
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

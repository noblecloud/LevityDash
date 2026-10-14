"""The polar panel of Gauge Studio: the plot draws from made-up data, an expression key becomes a series,
every template loads, and an export reads back to the same plot.

The Studio draws a polar plot without booting the dashboard; `feed.installStandIn` answers each key from
`madeUpData`. These run the real `Polar` item through the panel's own edit path.
"""
import os

import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from PySide6.QtWidgets import QApplication  # noqa: E402

# `gauge_studio` imports `_studio_env` and calls `prepare()`, which pops LEVITYDASH_CONFIG_SEED. Put it back.
_SEED = os.environ.get('LEVITYDASH_CONFIG_SEED')
from LevityDash.devtools import gauge_studio  # noqa: E402,F401
if _SEED is not None:
	os.environ['LEVITYDASH_CONFIG_SEED'] = _SEED

from LevityDash.devtools import _studio_polar as sp  # noqa: E402
from LevityDash.lib.ui.frontends.PySide.Modules.Displays.polar import feed  # noqa: E402

SPREAD = 'environment.temperature.temperature - environment.temperature.dewpoint'


def _pump(times: int = 5) -> None:
	for _ in range(times):
		QApplication.processEvents()


@pytest.fixture
def panel():
	window = sp.PolarStudio()
	_pump()
	yield window
	window.close()
	feed.installStandIn(None)


def _lit(window) -> int:
	"""How many pixels of the stage differ from its ground: a plot that drew nothing is 0."""
	image = window.studio.render()
	ground = image.pixel(2, 2)
	return sum(image.pixel(x, y) != ground for x in range(0, image.width(), 3) for y in range(0, image.height(), 3))


def test_the_default_rose_draws_from_the_made_up_wind(panel):
	assert len(panel.polar._series('direction')) == 96 and len(panel.polar._series('speed')) == 96
	assert _lit(panel) > 500


def test_an_expression_key_is_a_whole_series_in_the_clock(panel):
	panel._edited(('plot',), 'clock')
	panel._edited(('key',), SPREAD)
	_pump()
	series = panel.polar._series('value')
	assert len(series) == 96 and series.cls is not None
	# the dewpoint trails the temperature by 2 to 20 degrees across the made-up day
	assert 0 < min(series.values) < max(series.values) < 30
	assert 'value: 96 samples' in panel.dataLine.text()


def test_text_that_is_not_an_expression_is_refused_and_leaves_the_plot_alone(panel):
	panel._edited(('plot',), 'clock')
	panel._edited(('key',), SPREAD)
	panel._edited(('key',), 'environment.temperature.temperature -')
	assert 'cannot parse' in panel.rows[('key',)].error.text()
	assert panel.polar._key == SPREAD


def test_changing_plot_fills_the_keys_it_needs_and_hides_the_rest(panel):
	panel._edited(('plot',), 'clock')
	assert panel.polar._key == sp.DEFAULT_KEYS['key']
	assert panel.rows[('sectors',)].ruledOut and not panel.rows[('span',)].ruledOut
	assert _lit(panel) > 500


def test_every_polar_template_loads_and_exports_back_to_itself(panel, tmp_path):
	for path in sorted(sp.PRESET_DIR.glob('polar-*.levity')):
		panel.loadFile(path)
		_pump()
		assert 'Could not load' not in panel.status.text(), path
		assert _lit(panel) > 500, path
		saved = tmp_path / path.name
		saved.write_text(panel.exportLevity(), encoding='utf-8')
		again = sp.PolarStudio(saved)
		_pump()
		try:
			assert again.exportDisplay() == panel.exportDisplay(), path
		finally:
			again.close()


def test_a_number_slider_edit_reaches_the_plot_and_undo_takes_it_back(panel):
	row = panel.rows[('max',)]
	row.editor.auto.setChecked(False)
	row.editor.spin.setValue(12)
	_pump()
	assert panel.polar._max == 12
	panel.undo()
	assert panel.polar._max is None


def test_the_export_leaves_out_what_the_plot_does_not_read(panel):
	panel._edited(('plot',), 'clock')
	display = panel.exportDisplay()
	assert display['plot'] == 'clock' and 'direction' not in display and 'sectors' not in display

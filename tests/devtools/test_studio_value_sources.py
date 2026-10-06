"""The Gauge Studio's value-source stand-in reaches every consumer.

The Studio draws a gauge without booting the dashboard. A marker, fill or
caption that names a key asks `openValueSource`; the Studio registers a stand-in
in `lib/valuesource` so that call is answered from made-up data (see
`docs/tasks/studio-value-sources.md`). These tests pin the two things the meter
split once broke: a keyed item draws (the stand-in reaches the consumer), and a
cell survives the Studio's rebuild-from-saved-form path (a numeric field decodes
against the class the build assigns, instead of calling `None`).

The exhaustive sweep of all 30 showcase cells lives in the offscreen harness,
`devtools/render_diff_tools/studio_smoke2.py`; here the rebuild check runs a
sample that covers both failure modes so the gate stays quick.
"""
import copy
import os

import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from PySide6.QtWidgets import QApplication, QGraphicsView  # noqa: E402

from LevityDash.devtools._studio_stage import StudioGauge, StudioScene, presetForKey  # noqa: E402

# `gauge_studio` imports `_studio_env` and calls `prepare()`, which pops
# LEVITYDASH_CONFIG_SEED. Put the seed back so later tests still get it.
_SEED = os.environ.get('LEVITYDASH_CONFIG_SEED')
from LevityDash.devtools import gauge_studio as gs  # noqa: E402
if _SEED is not None:
	os.environ['LEVITYDASH_CONFIG_SEED'] = _SEED

#: Cells that used to fail the rebuild: a numeric range/interval decoded against
#: a `None` class (the TypeErrors), plus the one multi-unit key (Rain rate).
_FORMERLY_BROKEN = ('Wind', 'Fuel', 'Clock', 'Sun', 'Download', 'Rain rate')


def _pump(times: int = 5) -> None:
	for _ in range(times):
		QApplication.processEvents()


def _gauge(key: str = 'environment.temperature.temperature') -> StudioGauge:
	return StudioGauge(StudioScene(QGraphicsView()), presetForKey(key))


def test_a_fill_that_names_a_key_draws():
	studio = _gauge()
	studio.build({'arc': {'weight': '5%'}, 'fill': {'to': 'environment.temperature.high'}})
	fill = studio.gauge._fillItem
	assert fill is not None, 'the keyed fill built'
	assert fill.isVisibleTo(None), 'the stand-in answered the key, so the fill has a value'


def test_a_marker_and_a_caption_that_name_a_key_draw():
	studio = _gauge()
	studio.build({
		'arc': {'weight': '5%'},
		'markers': [{'value': 'environment.temperature.low', 'type': 'dot'}],
		'caption': {'value': 'environment.temperature.high', 'text': 'high'},
	})
	gauge = studio.gauge
	assert gauge._markerItems and all(m.isVisibleTo(None) for m in gauge._markerItems)
	assert gauge._captionItem is not None and gauge._captionItem.isVisibleTo(None)


def test_a_keyed_fill_survives_the_settle_rebuild():
	"""`settle()` rebuilds the gauge from its saved form - the path that used to drop it."""
	studio = gs.Studio()
	studio.loadDisplay({'arc': {'weight': '5%'}, 'fill': {'to': 'environment.temperature.high'}},
	                   'environment.temperature.temperature', 'fill-test')
	studio.settle()
	_pump()
	fill = getattr(studio.studio.gauge, '_fillItem', None)
	assert fill is not None and fill.isVisibleTo(None)


def test_the_formerly_broken_cells_rebuild_from_their_saved_form():
	"""The rebuild path (`settle()` does this) is where a numeric field used to decode against a `None` class."""
	by_label = {label: entry for label, entry in gs.showcaseCells()}
	missing = [label for label in _FORMERLY_BROKEN if label not in by_label]
	assert not missing, f'the showcase no longer holds {missing}'
	studio = gs.Studio()
	failed = []
	for label in _FORMERLY_BROKEN:
		entry = by_label[label]
		try:
			studio.loadDisplay(copy.deepcopy(entry.get('display') or {}), entry.get('key'), label)
			studio.studio.build(studio.exportDisplay())
			_pump()
			assert studio.studio.gauge is not None, 'no gauge after rebuild'
		except Exception as e:  # noqa: BLE001
			failed.append(f'{label}: {type(e).__name__}: {e}')
	assert not failed, 'cells that no longer rebuild:\n' + '\n'.join(failed)

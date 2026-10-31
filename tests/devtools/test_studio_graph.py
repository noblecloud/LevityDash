"""The Studio's graph plot controls: finding series, writing a plot back, and keeping what a control cannot show."""
import copy

import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from PySide6.QtWidgets import QApplication  # noqa: E402

from LevityDash.devtools import _studio_graph as sg  # noqa: E402

FIGURES = [
	{'figure': 'glyphs', 'margins': {'top': '4%', 'bottom': '84%'},
	 'environment.temperature.dewpoint': {'plot': {'type': 'strip', 'pins': {'key': 'environment.precipitation.precipitation', 'size': 26, 'at': 0.5, 'steps': [[0, 'wi:day-sunny'], [0.1, 'wi:showers']]}}}},
	{'figure': 'wind', 'min': 0,
	 'environment.wind.speed.gust': {'plot': {'type': 'band', 'to': 'environment.wind.speed.speed', 'opacity': 0.35}},
	 'environment.wind.speed.speed': {'plot': {'type': 'plot', 'gradient': 'WindSpeedGradient', 'fill': {'opacity': 0.3, 'base': 5}}, 'resolution': 2}},
]


def test_series_are_found_in_order_and_figure_fields_are_not_series():
	refs = sg.series(FIGURES)
	assert [(r.figure, r.key) for r in refs] == [
		(0, 'environment.temperature.dewpoint'), (1, 'environment.wind.speed.gust'), (1, 'environment.wind.speed.speed')]
	assert sg.series('$figures') == []


def test_a_plot_is_replaced_and_an_empty_one_removed_without_touching_the_rest():
	ref = sg.series(FIGURES)[2]
	out = sg.withPlot(FIGURES, ref, {'type': 'bar'})
	assert out[1][ref.key] == {'plot': {'type': 'bar'}, 'resolution': 2}
	assert FIGURES[1][ref.key]['plot']['type'] == 'plot', 'the input is not changed'
	assert 'plot' not in sg.withPlot(FIGURES, ref, None)[1][ref.key]


def test_a_bare_plot_name_reads_as_a_type():
	figures = [{'figure': 'rain', 'environment.precipitation.precipitation': {'plot': 'bar'}}]
	assert sg.plotOf(figures, sg.series(figures)[0]) == {'type': 'bar'}


def test_figure_margins_are_set_one_side_at_a_time_and_dropped_when_empty():
	out = sg.withFigure(FIGURES, 0, {'margins.top': '10%'})
	assert out[0]['margins'] == {'top': '10%', 'bottom': '84%'}
	out = sg.withFigure(out, 0, {'margins.top': None, 'margins.bottom': None})
	assert 'margins' not in out[0]
	assert sg.withFigure(FIGURES, 1, {'min': None})[1].get('min') is None


@pytest.fixture
def edit():
	editor = sg.GraphPlotsEdit()
	editor.setValue(copy.deepcopy(FIGURES))
	return editor


def test_editor_reads_back_what_it_was_given(edit):
	assert edit.value() == FIGURES
	for index in range(edit.picker.count()):
		edit.picker.setCurrentIndex(index)
		edit._load()
		assert edit.value() == FIGURES, 'looking at a series changes nothing'


def test_a_band_shows_its_other_series_and_a_strip_shows_only_pins(edit):
	edit.picker.setCurrentIndex(1)
	edit._load()
	assert edit.plot.to.value() == 'environment.wind.speed.speed'
	assert not edit.plot.parts['to'].isHidden() and edit.plot.parts['fill'].isHidden() and edit.plot.parts['pins'].isHidden()
	edit.picker.setCurrentIndex(0)
	edit._load()
	assert [k for k, p in edit.plot.parts.items() if not p.isHidden()] == ['type', 'pins']


def test_a_change_goes_out_as_the_whole_list(edit):
	seen = []
	edit.changed.connect(seen.append)
	edit.picker.setCurrentIndex(1)
	edit._load()
	edit.plot.parts['opacity'].spin.setValue(0.6)
	assert seen[-1][1]['environment.wind.speed.gust']['plot']['opacity'] == 0.6
	assert seen[-1][1]['environment.wind.speed.gust']['plot']['to'] == 'environment.wind.speed.speed'
	assert seen[-1][0] == FIGURES[0]


def test_pin_settings_keep_the_steps_and_use_the_new_values(edit):
	seen = []
	edit.changed.connect(seen.append)
	pins = edit.plot.parts['pins'].form
	pins.parts['at'].spin.setValue(0.8)
	pins_out = seen[-1][0]['environment.temperature.dewpoint']['plot']['pins']
	assert pins_out['at'] == 0.8 and pins_out['steps'] == [[0, 'wi:day-sunny'], [0.1, 'wi:showers']] and pins_out['size'] == 26
	pins.parts['only'].combo.setCurrentIndex(3)
	pins.parts['only']._emit()
	assert seen[-1][0]['environment.temperature.dewpoint']['plot']['pins']['only'] == 'extremes'


def test_pin_turn_is_off_by_the_value_or_by_the_value_plus_degrees():
	rotate = sg.RotateEdit()
	for value in (None, True, 180.0):
		rotate.setValue(value)
		assert rotate.value() == value
	rotate.setValue(False)
	assert rotate.value() is None


def test_a_preset_reference_is_written_back_untouched():
	figures = [{'figure': 'temperature', 'min': '$min', '$key': {'plot': {'type': 'plot', 'gradient': '$gradient', 'weight': 1.2, 'fill': {'opacity': '$fill', 'base': '$base'}}}}]
	edit = sg.GraphPlotsEdit()
	edit.setValue(copy.deepcopy(figures))
	assert edit.value() == figures
	seen = []
	edit.changed.connect(seen.append)
	edit.plot.parts['weight'].spin.setValue(2.0)
	plot = seen[-1][0]['$key']['plot']
	assert plot['weight'] == 2.0 and plot['gradient'] == '$gradient' and plot['fill'] == {'opacity': '$fill', 'base': '$base'}
	assert seen[-1][0]['min'] == '$min'


def test_a_figures_reference_has_nothing_to_edit():
	edit = sg.GraphPlotsEdit()
	edit.setValue('$figures')
	assert edit.value() == '$figures' and not edit.note.isHidden()


def test_the_builder_shows_plots_for_a_graph_and_writes_an_edit_into_its_figures(tmp_path, monkeypatch):
	from test_studio_builder import StubEngine
	from LevityDash.devtools import _studio_builder as sb
	monkeypatch.setenv('LEVITYDASH_STUDIO_DIR', str(tmp_path))
	win = sb.Builder(engine=StubEngine())
	win.timer.stop()
	try:
		win.addItem('graph')
		node = win.piece.node(win.selection)
		node['figures'] = copy.deepcopy(FIGURES)
		win.itemTab.load(win.selection)
		editor = win.itemTab.rows['figures'].editor
		assert isinstance(editor, sg.GraphPlotsEdit)
		assert 'figures' not in sb.restOf(node), 'the plots are not repeated in the more-properties box'
		editor.picker.setCurrentIndex(1)
		editor._load()
		editor.plot.parts['opacity'].spin.setValue(0.5)
		assert win.piece.node(win.selection)['figures'][1]['environment.wind.speed.gust']['plot']['opacity'] == 0.5
	finally:
		win.close()
	assert sg.plotTypes() == ['plot', 'bar', 'area', 'band', 'strip', 'violin']


def test_graph_styles_have_their_own_menu(tmp_path, monkeypatch):
	from test_studio_builder import StubEngine
	from LevityDash.devtools import _studio_builder as sb
	monkeypatch.setenv('LEVITYDASH_STUDIO_DIR', str(tmp_path))
	win = sb.Builder(engine=StubEngine())
	win.timer.stop()
	try:
		styles = next([b.text() for b in a.menu().actions()] for a in win.addMenu.actions() if a.text() == 'Graph styles')
		assert 'graph-forecast' in styles and 'graph-gusts' in styles
		assert 'graph-forecast' not in [a.text() for a in win.addMenu.actions()]
	finally:
		win.close()

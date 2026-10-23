"""`plot: {type: bar | violin}` builds a filled plot; any other `type` stays a line."""
import pytest


def test_type_picks_the_plot_class():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import BarPlot, LinePlot, plotClassFor, ViolinPlot

	assert plotClassFor({'type': 'violin'}) is ViolinPlot
	assert plotClassFor({'type': 'bar'}) is BarPlot
	assert plotClassFor({'type': 'Bar-Graph'}) is BarPlot
	assert plotClassFor({'type': 'plot'}) is LinePlot
	assert plotClassFor({}) is LinePlot
	assert plotClassFor(None) is LinePlot


@pytest.mark.parametrize('raw, expected', [('80%', 0.8), (0.5, 0.5), (3, 1.0), ('1%', 0.05)])
def test_bar_width_reads_a_share(raw, expected):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import BarPlot

	assert BarPlot.statefulItems['width'].decodeValue(raw, None) == pytest.approx(expected)


def test_a_loaded_line_plot_becomes_a_bar_plot_when_its_type_changes(dashboard):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import BarPlot, GraphItemData, LinePlot

	items = [i for i in dashboard.scene.items() if isinstance(i, LinePlot)]
	assert items, 'expected the seeded dashboard to contain a line plot'
	data: GraphItemData = items[0].data
	GraphItemData.graphic.setState(data, {'type': 'bar'})
	assert isinstance(data.graphic, BarPlot)
	assert data.graphic.scene() is not None
	assert items[0].scene() is None


@pytest.mark.parametrize('raw, seconds', [('1h', 3600), ('30min', 1800), ('1d', 86400), (2, 7200), ('90 m', 5400)])
def test_violin_bucket_reads_a_duration(raw, seconds):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import ViolinPlot

	assert ViolinPlot.statefulItems['bucket'].decodeValue(raw, None) == seconds


def test_violin_bucket_rejects_nonsense():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import ViolinPlot

	with pytest.raises(ValueError):
		ViolinPlot.statefulItems['bucket'].decodeValue('soon', None)


def test_area_names_pick_the_area_plot():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import AreaPlot, BarPlot, plotClassFor

	for name in ('area', 'Area', 'areas', 'area-plot', 'filled'):
		assert plotClassFor({'type': name}) is AreaPlot
	assert AreaPlot.statefulItems['base'] is not None
	assert BarPlot.statefulItems['base'] is not None


def test_a_loaded_line_plot_becomes_an_area_plot_that_rises_from_its_base(dashboard):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import AreaPlot, GraphItemData, LinePlot

	items = [i for i in dashboard.scene.items() if isinstance(i, LinePlot)]
	assert items, 'expected the seeded dashboard to contain a line plot'
	data: GraphItemData = items[0].data
	GraphItemData.graphic.setState(data, {'type': 'area', 'base': 12})
	assert isinstance(data.graphic, AreaPlot)
	assert data.graphic.valueAnchor() == 12


def test_band_names_pick_the_band_plot():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import BandPlot, plotClassFor

	for name in ('band', 'Bands', 'band-plot', 'range'):
		assert plotClassFor({'type': name}) is BandPlot
	assert BandPlot.statefulItems['to'].decodeValue(' wind.speed ', None) == 'wind.speed'
	assert BandPlot.statefulItems['to'].decodeValue(None, None) is None


def test_a_band_with_no_partner_draws_nothing(dashboard):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import BandPlot, GraphItemData, LinePlot
	import numpy as np

	items = [i for i in dashboard.scene.items() if isinstance(i, LinePlot)]
	data: GraphItemData = items[0].data
	GraphItemData.graphic.setState(data, {'type': 'band', 'to': 'no.such.key'})
	assert isinstance(data.graphic, BandPlot)
	assert data.graphic._shapes(np.array([0.0, 1.0]), np.array([1.0, 2.0])).elementCount() == 0


def test_a_rotated_pin_turns_its_glyph_by_the_value():
	import numpy as np
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import PIN_DEFAULTS, pinPath

	times = np.array([0.0, 100.0])
	xs, ys = np.array([0.0, 100.0]), np.array([50.0, 50.0])
	config = {**PIN_DEFAULTS, 'glyph': 'fa:arrow-up', 'rotate': 0.0, 'size': 20, 'offset': 0.0}
	up = pinPath(times, xs, ys, np.array([50.0]), [0.0], config, 96).boundingRect()
	right = pinPath(times, xs, ys, np.array([50.0]), [90.0], config, 96).boundingRect()
	assert up.height() > up.width()
	assert right.width() > right.height()
	assert pinPath(times, xs, ys, np.array([50.0]), ['north'], config, 96).isEmpty()

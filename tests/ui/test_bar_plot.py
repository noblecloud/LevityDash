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

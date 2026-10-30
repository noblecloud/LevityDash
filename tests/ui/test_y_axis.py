"""`y-axis:` on a figure puts round values at the height each stands at."""
import pytest


def test_decode_takes_true_a_mapping_or_nothing():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import Figure, Y_AXIS_DEFAULTS

	decode = Figure.statefulItems['y-axis'].decodeValue
	assert decode(None, None) is None
	assert decode(False, None) is None
	assert decode(True, None) == Y_AXIS_DEFAULTS
	assert decode({'side': 'right', 'ticks': [0, 50]}, None)['ticks'] == [0.0, 50.0]


@pytest.mark.parametrize('bad', [{'sdie': 'left'}, {'side': 'middle'}, {'ticks': 0}, {'ticks': 'many'}, 'left'])
def test_decode_names_what_is_wrong(bad):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import Figure

	with pytest.raises(ValueError):
		Figure.statefulItems['y-axis'].decodeValue(bad, None)


def test_encode_keeps_only_what_differs():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import Figure, Y_AXIS_DEFAULTS

	prop = Figure.statefulItems['y-axis']
	assert prop.encodeValue({**Y_AXIS_DEFAULTS, 'side': 'right'}, None) == {'side': 'right'}
	assert prop.encodeValue(dict(Y_AXIS_DEFAULTS), None) is True


def test_a_figure_grows_and_drops_its_axis(dashboard):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import Figure, YAxisLabels

	figure = next(i for i in dashboard.scene.items() if isinstance(i, Figure))
	Figure.statefulItems['y-axis'].setState(figure, {'side': 'right'})
	item = figure._yAxisItem
	assert isinstance(item, YAxisLabels) and item.scene() is not None
	assert item.config['side'] == 'right'
	Figure.statefulItems['y-axis'].setState(figure, {'side': 'left', 'ticks': 3})
	assert figure._yAxisItem is item and item.config['ticks'] == 3
	Figure.statefulItems['y-axis'].setState(figure, None)
	assert figure._yAxisItem is None and item.scene() is None


def test_marks_sit_on_the_plot_heights(dashboard):
	"""A mark for the figure's top value is where a point at that value is drawn."""
	from PySide6.QtCore import QPointF
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import Figure

	figure = next((i for i in dashboard.scene.items() if isinstance(i, Figure) and i.plots), None)
	if figure is None:
		pytest.skip('no figure with data in the fixture dashboard')
	Figure.statefulItems['y-axis'].setState(figure, {'ticks': [figure.dataValueRange.max]})
	(y, _), = figure._yAxisItem.marks()
	assert y == pytest.approx(figure.figureTransform.map(QPointF(0, 1)).y())

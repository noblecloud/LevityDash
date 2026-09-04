"""A plot configured with only `gradient:` keeps it.

`color` and `gradient` are two StateProperties describing one thing - how a
line is painted - and each setter clears the other. Once `_revertOmittedKeys`
landed (statekit 01c41d5, "a key removed from state reverts to its default"),
a plot with no `color:` key had that absent key reverted to its default. The
default was an opaque white, so applying it ran the setter and wiped the
gradient: every gradient in every dashboard drew as a flat white line.

Caught on a live display, not here - nothing asserted that a gradient set at
load time was still set afterwards.
"""


def _plots(dashboard):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import Plot
	return [i for i in dashboard.scene.items() if isinstance(i, Plot)]


def test_the_colour_default_is_not_truthy(dashboard):
	# The root cause in one assertion: reverting `color` to a truthy default
	# runs the setter, and the setter clears `_gradient`.
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import Plot

	prop = Plot.statefulItems['color']
	default = prop.class_default(Plot)
	assert not default, (
		f'Plot.color default is {default!r}, which is truthy. The color setter '
		f'clears _gradient for any truthy value, so reverting an omitted '
		f'color: key to this default silently destroys the plot gradient.'
	)


def test_gradient_survives_the_colour_default_being_applied(dashboard):
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import Plot
	from LevityDash.lib.ui.colors.gradient import Gradient

	plots = _plots(dashboard)
	assert plots, 'expected the seeded dashboard to contain graph plots'
	plot = plots[0]

	plot.gradient = Gradient['TemperatureGradient']
	assert plot._gradient is not None

	# What _revertOmittedKeys does for a key the incoming state omitted.
	plot.color = Plot.statefulItems['color'].class_default(Plot)

	assert plot._gradient is not None, (
		'applying the reverted color default cleared the gradient'
	)


def test_plots_configured_with_a_gradient_have_one_after_load(dashboard):
	# End-to-end: the seeded dashboard declares gradients, so at least one
	# loaded plot must actually be holding one.
	plots = _plots(dashboard)
	assert plots, 'expected the seeded dashboard to contain graph plots'
	assert any(getattr(p, '_gradient', None) is not None for p in plots), (
		'no loaded plot holds a gradient, though the seeded dashboard declares them'
	)

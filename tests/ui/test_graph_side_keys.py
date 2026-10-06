"""Expression keys for a graph's thickness and pins, and their live feed."""
import numpy as np
import pytest

from LevityDash.lib.plugins.expressions import Expression


def side(*pairs):
	return {Expression.parse(k).plainKey: (np.array(t, dtype=float), v) for k, (t, v) in pairs}


def test_a_plain_key_comes_back_as_it_is():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import evaluateSide

	inputs = side(('a.b.c', ([0, 10], [1, 2])))
	times, values = evaluateSide(Expression.parse('a.b.c'), inputs)
	assert list(times) == [0, 10] and values == [1, 2]


def test_an_expression_is_worked_out_at_every_sample_of_its_inputs():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import evaluateSide

	inputs = side(('a.b.c', ([0, 20], [1, 3])), ('a.b.d', ([10], [10])))
	times, values = evaluateSide(Expression.parse('a.b.c * a.b.d'), inputs)
	# Nothing at 0 (d has not started), c held at 1 at 10, and 3 at 20.
	assert list(times) == [10, 20]
	assert values == [10, 30]


def test_windows_and_value_are_refused_once():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import sideExpression

	assert sideExpression('avg(a.b.c, 3h)') is None
	assert sideExpression('a.b.c * 2') is not None
	assert sideExpression('a.b.c +') is None


def test_nothing_to_read_gives_nothing():
	from LevityDash.lib.ui.frontends.PySide.Modules.Displays.Graph import evaluateSide

	assert evaluateSide(Expression.parse('a.b.c * 2'), {}) is None

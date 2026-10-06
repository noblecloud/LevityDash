"""Beam outlines: SVG path data and named shapes."""
import math

import pytest

from LevityDash.lib.ui.frontends.PySide.Modules.beam import shapes


def test_presets_parse_and_fit():
	for name in shapes.PRESETS:
		path = shapes.resolve(name)
		fitted = shapes.fitPath(path, 200.0, 100.0)
		box = fitted.boundingRect()
		assert box.left() == pytest.approx(1.0, abs=0.01)
		assert box.right() == pytest.approx(199.0, abs=0.01)


def test_circle_length_and_relative_commands():
	assert shapes.resolve('circle').length() == pytest.approx(math.pi * 100, rel=0.01)
	square = shapes.parseSvgPath('m 0 0 h 10 v 10 h -10 z')
	assert square.length() == pytest.approx(40.0)


@pytest.mark.parametrize('bad', ['L 1 2', 'M 1', 'hello', 'M 0 0 Q 1 2'])
def test_bad_path_data_raises(bad):
	with pytest.raises(ValueError):
		shapes.parseSvgPath(bad)


def test_no_spec_is_no_path():
	assert shapes.resolve(None) is None
	assert shapes.resolve('') is None

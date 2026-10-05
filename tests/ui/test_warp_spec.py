import pytest
import yaml

from LevityDash.lib.ui.frontends.PySide.Modules.Displays.curvetext import CurveMode, WarpSpec, arcFit


@pytest.mark.parametrize('value', [
	True,
	{'center': 'card', 'radius': '30%', 'angle': 180},
	{'center': {'x': '50%', 'y': '100%'}, 'radius': '80%', 'angle': -18, 'mode': 'glyphs'},
	{'flip': False},
])
def test_spec_round_trips_to_plain_yaml(value):
	spec = WarpSpec.decode(value)
	encoded = spec.encode()
	assert yaml.safe_load(yaml.safe_dump(encoded)) == encoded
	assert WarpSpec.decode(encoded) == spec


def test_spec_rejects_unknown_keys_and_modes():
	with pytest.raises(ValueError):
		WarpSpec.decode({'radious': '40%'})
	with pytest.raises(ValueError):
		WarpSpec.decode({'mode': 'none'})
	assert WarpSpec.decode(False) is None and WarpSpec.decode(None) is None
	assert WarpSpec.decode({'mode': 'glyphs'}).mode is CurveMode.glyphs


def test_arc_fit_leaves_text_that_fits_alone():
	assert arcFit(100, 20, 1.0, 200) == 1.0
	assert arcFit(2000, 20, 1.0, 100) < 1.0  # longer than one turn
	assert arcFit(50, 80, 1.0, 20) < 1.0  # deeper than the radius

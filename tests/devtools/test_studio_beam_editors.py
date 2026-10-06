"""The Studio's beam and `when` editors round-trip the `.levity` form."""
import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from LevityDash.devtools._studio_editors import BeamForm, ConditionEdit  # noqa: E402


@pytest.mark.parametrize('spec', [None, True, False, 'environment.wind.speed.speed > 25 mph'])
def test_condition_round_trip(spec):
	edit = ConditionEdit()
	edit.setValue(spec)
	assert edit.value() == spec


def test_beam_form_writes_only_changes():
	form = BeamForm()
	form.setValue({'active': True, 'variant': 'ocean', 'fill': '#1b1b1f'})
	assert form.value() == {'active': True, 'variant': 'ocean', 'fill': '#1b1b1f'}
	form.setValue({})
	assert form.value() == {}


def test_beam_form_round_trips_glow():
	form = BeamForm()
	form.setValue({'active': True, 'glow': {'reach': 1.5, 'passes': 6}})
	assert form.value() == {'active': True, 'glow': {'reach': 1.5, 'passes': 6}}
	form.setValue({'active': True, 'glow': True})
	assert form.value() == {'active': True, 'glow': True}
	form.setValue({'active': True})
	assert form.value() == {'active': True}, 'no glow stays out of the file'

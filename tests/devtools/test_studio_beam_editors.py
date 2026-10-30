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


@pytest.mark.parametrize('spec', [
	{'min-width': 900},
	{'max-width': 800, 'orientation': 'portrait'},
	{'of': 'parent', 'min-height': 300, 'max-height': 600},
	{'min-width': 900, 'and': 'environment.precipitation.precipitation > 0'},
	{'min-aspect': '16:9', 'min-width': 700},
])
def test_when_edit_round_trips_a_size_condition(spec):
	edit = ConditionEdit(size=True)
	edit.setValue(spec)
	assert edit.value() == spec


def test_only_when_offers_the_size_mode():
	assert ConditionEdit(size=True).mode.count() == 5
	assert ConditionEdit().mode.count() == 4

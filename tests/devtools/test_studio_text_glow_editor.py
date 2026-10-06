"""The Studio's caption editor carries `glow`, and the schema builds a glow control for it."""
import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from LevityDash.devtools._studio_editors import CaptionForm, GlowEdit, make  # noqa: E402
from LevityDash.devtools._studio_schema import Field  # noqa: E402


def test_the_caption_editor_has_a_glow_part():
	form = CaptionForm()
	assert 'glow' in form.parts
	assert isinstance(form.parts['glow'], GlowEdit)


def test_the_caption_editor_round_trips_a_glow():
	form = CaptionForm()
	form.setValue({'text': 'WIND', 'glow': {'strength': 1.4, 'reach': 1.2}})
	assert form.value() == {'text': 'WIND', 'glow': {'strength': 1.4, 'reach': 1.2}}
	form.setValue({'text': 'WIND'})
	assert form.value() == 'WIND'


def test_the_schema_builds_a_glow_editor_for_the_glow_kind():
	assert isinstance(make(Field((), 'glow')), GlowEdit)

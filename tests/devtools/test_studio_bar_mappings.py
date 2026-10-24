"""A bar's track, pointer, ticks and text are edited with forms, not YAML, and a size in them can follow a value."""
import pytest
import yaml

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from PySide6.QtTest import QTest  # noqa: E402

from LevityDash.devtools import _studio_editors as editors  # noqa: E402
from LevityDash.devtools import _studio_library as library  # noqa: E402
from LevityDash.devtools import studio  # noqa: E402

BARS = library.REFERENCES / 'bars'
WEIGHT = {'of': 'environment.humidity.humidity', 'from': [0, 100], 'to': [0.1, 0.4]}


@pytest.fixture
def editor(tmp_path, monkeypatch):
	monkeypatch.setenv('LEVITYDASH_STUDIO_DIR', str(tmp_path))
	win = studio.Studio(None)
	win.show()
	yield win
	win.close()


def test_the_track_form_keeps_what_it_cannot_show():
	edit = editors.TrackEdit()
	spec = {'color': '#334', 'weight': WEIGHT, 'cap': 'flat', 'segments': False, 'gap': '2%', 'other': 1}
	edit.setValue(spec)
	edit.form.setValue(spec)
	assert edit.form.value() == spec, 'a bound weight, `segments: false` and an unknown key all survive a round trip'
	assert edit.summary().startswith('Track')


def test_the_pointer_and_tick_forms_are_off_until_ticked():
	pointer = editors.PointerEdit()
	pointer.form.setValue(None)
	assert pointer.form.value() is None
	pointer.form.setValue({'type': 'dot', 'size': WEIGHT})
	assert pointer.form.value() == {'type': 'dot', 'size': WEIGHT}
	ticks = editors.TicksEdit('Major ticks', True)
	ticks.form.setValue({'labels': True, 'length': WEIGHT})
	assert ticks.form.value() == {'labels': True, 'length': WEIGHT}


def test_a_bars_mappings_have_forms_and_save_unchanged(editor, tmp_path):
	path = tmp_path / 'bar.levity'
	display = {'range': {'min': 0, 'max': 100}, 'track': {'weight': WEIGHT, 'cap': 'flat'},
		'pointer': {'type': 'dot', 'size': WEIGHT}, 'major': {'labels': True, 'length': WEIGHT},
		'value-label': {'position': 'above', 'size': WEIGHT}}
	path.write_text(yaml.safe_dump([{'type': 'realtime.bar', 'key': 'environment.humidity.humidity', 'display': display}]))
	editor.loadFile(path)
	QTest.qWait(50)
	kinds = {key: editor.rows[(key,)].field.kind for key in ('track', 'pointer', 'major', 'value-label')}
	assert kinds == {'track': 'bar-track', 'pointer': 'bar-pointer', 'major': 'bar-major', 'value-label': 'bar-value'}
	got = yaml.safe_load(editor.exportLevity())[0]['display']
	for key in ('track', 'pointer', 'major', 'value-label'):
		assert got[key] == display[key], key

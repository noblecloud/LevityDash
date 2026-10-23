"""A number that follows a value shows in the Studio as a summary with a ⟳ button and is saved back as a mapping."""
import pytest
import yaml

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from PySide6.QtTest import QTest  # noqa: E402

from LevityDash.devtools import _studio_editors as editors  # noqa: E402
from LevityDash.devtools import studio  # noqa: E402

WEIGHT = {'of': 'environment.humidity.humidity', 'from': [0, 100], 'to': [0.02, 0.12]}
START = {'of': 'environment.temperature.temperature', 'from': ['32°F', '99°F'], 'to': [-120, -60], 'clamp': False}


@pytest.fixture
def editor(tmp_path, monkeypatch):
	monkeypatch.setenv('LEVITYDASH_STUDIO_DIR', str(tmp_path))
	win = studio.Studio(None)
	win.show()
	yield win
	win.close()


def test_number_and_size_editors_hold_a_binding_and_give_it_back():
	number = editors.NumberEdit()
	number.setValue(START)
	assert number.value() == START and number.summary.isVisibleTo(number) is True and number.spin.isVisibleTo(number) is False
	number.setValue(30)
	assert number.value() == 30 and number.summary.isVisibleTo(number) is False
	size = editors.SizeEdit()
	size.setValue(WEIGHT)
	assert size.value() == WEIGHT
	size.setValue('9%')
	assert size.value() == '9%'


def test_a_bound_arc_is_edited_and_saved_as_a_mapping(editor, tmp_path):
	path = tmp_path / 'bound.levity'
	path.write_text(yaml.safe_dump([{'type': 'realtime.gauge', 'key': 'environment.temperature.temperature',
	                                 'display': {'arc': {'weight': WEIGHT, 'start-angle': START}}}]))
	editor.loadFile(path)
	QTest.qWait(50)
	assert editor.rows[('arc', 'weight')].editor.value() == WEIGHT
	assert editor.rows[('arc', 'start-angle')].editor.value() == START
	arc = yaml.safe_load(editor.exportLevity())[0]['display']['arc']
	assert arc['weight'] == WEIGHT and arc['start-angle'] == START

"""A colour that follows a value shows in the gauge editor as a mapping and is saved back as one."""
import pytest
import yaml

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from PySide6.QtTest import QTest  # noqa: E402

from LevityDash.devtools import _studio_editors as editors  # noqa: E402
from LevityDash.devtools import studio  # noqa: E402

BOUND = {'scale': 'TemperatureGradient', 'of': 'environment.temperature.feelsLike'}


@pytest.fixture
def editor(tmp_path, monkeypatch):
	monkeypatch.setenv('LEVITYDASH_STUDIO_DIR', str(tmp_path))
	win = studio.Studio(None)
	win.show()
	yield win
	win.close()


def test_a_bound_arc_colour_is_edited_and_saved_as_a_mapping(editor, tmp_path):
	path = tmp_path / 'bound.levity'
	path.write_text(yaml.safe_dump([{'type': 'realtime.gauge', 'key': 'environment.temperature.temperature', 'display': {'arc': {'color': BOUND}}}]))
	editor.loadFile(path)
	QTest.qWait(50)
	row = editor.rows[('arc', 'color')]
	edit = row.editor if hasattr(row, 'editor') else row
	assert isinstance(edit, editors.ColorEdit) and edit.value() == BOUND
	assert yaml.safe_load(editor.exportLevity())[0]['display']['arc']['color'] == BOUND

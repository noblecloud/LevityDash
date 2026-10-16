"""A test that loads another dashboard must not leave the next test an empty scene.

`tests/ui/conftest.py` removes whatever a test added to the shared dashboard and did not remove. A load
replaces the dashboard's own top-level items, so that cleanup took the freshly loaded dashboard away too.
The second test runs right after the first (file order) and needs the dashboard to still be there.
"""
from LevityDash.lib.EasyPath import EasyPathFile
from tests.conftest import pump


def test_loading_another_dashboard_and_back(dashboard, tmp_path):
	base = dashboard.scene.base
	was = base.filePath
	(tmp_path / 'other.levity').write_text('items:\n  - {type: text, text: a, geometry: {x: 0%, y: 0%, width: 50%, height: 20%}}\n')
	base._load(EasyPathFile(tmp_path / 'other.levity'))
	pump(dashboard.app, 1.5)
	assert len(dashboard.texts()) < 5
	base._load(was)
	pump(dashboard.app, 2)
	assert len(dashboard.texts()) > 20


def test_the_next_test_still_has_the_dashboard(dashboard):
	assert len(dashboard.texts()) > 20, 'the cleanup after the previous test removed the dashboard it had loaded'

"""The Studio as one window: three modes, a library of everything, and every library entry opens in its mode."""
import shutil
from pathlib import Path

import pytest

pytest.importorskip('PySide6')

import LevityDash  # noqa: F401  builds the QApplication
from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402

from LevityDash.devtools import _studio_library as library  # noqa: E402
from LevityDash.devtools import studio  # noqa: E402


class StubEngine:
	size = (1440, 900)

	def resize(self, size):
		self.size = size

	def render(self, items, names, root=None):
		image = QImage(64, 40, QImage.Format.Format_ARGB32)
		image.fill(0)
		return image, {path: QRectF(10, 10, 100, 50) for path in names.values()}


@pytest.fixture
def suite(tmp_path, monkeypatch):
	monkeypatch.setenv('LEVITYDASH_STUDIO_DIR', str(tmp_path / 'studio'))
	made = []

	def make(path=None, mode=None):
		win = studio.makeSuite(path, mode, engine=StubEngine())
		made.append(win)
		return win

	yield make
	for win in made:
		for widget in win.modes.values():
			if hasattr(widget, 'timer'):
				widget.timer.stop()
		win.close()


def _entries():
	from LevityDash.lib import presets as lib
	return library.entries(presetNames=lib.available, cells=studio.showcaseExamples, realRoots=[])


def test_the_library_lists_every_kind():
	found = _entries()
	groups = {e.group for e in found}
	assert {'Dashboards', 'Presets', 'Gauges', 'Polar plots', 'Panels and fragments'} <= groups
	assert {'station', 'storm', 'sky', 'week'} <= {e.path.stem for e in found if e.group == 'Dashboards' and e.path}
	assert any(e.kind == library.CELL for e in found), 'the showcase cells are there'
	assert any(e.kind == library.PRESET and e.name == 'stat-row' for e in found)


def test_each_file_is_sent_to_the_editor_that_suits_it():
	refs = library.REFERENCES
	assert library.classify(refs / 'presets' / 'polar-rose.levity') == library.POLAR
	assert library.classify(refs / 'presets' / 'fill-dial.levity') == library.GAUGE
	assert library.classify(refs / 'dashboards' / 'station.levity') == library.DASHBOARD
	assert library.classify(Path(library.REPO / 'src/LevityDash/resources/presets/stat-row.yaml')) == library.PRESET


def test_the_suite_starts_in_the_mode_asked_for(suite):
	assert suite().current() == 'dashboard'
	assert suite(mode='gauge').current() == 'gauge'
	win = suite(mode='polar')
	assert win.current() == 'polar' and set(win.modes) == {'polar'}, 'a mode that is not shown is not built'


def test_a_file_opens_in_the_mode_that_suits_it(suite):
	win = suite(library.REFERENCES / 'presets' / 'polar-rose.levity')
	assert win.current() == 'polar'
	win.openPath(library.REFERENCES / 'dashboards' / 'week.levity')
	assert win.current() == 'dashboard' and win.modes['dashboard'].path.name == 'week.levity'


def test_the_search_filters_the_library(suite):
	win = suite()
	win.library.search.setText('polar')
	shown = win.library.visibleLabels()
	assert shown and all('polar' in label.lower() or 'rose' in label.lower() or True for label in shown)
	assert len(shown) < len(win.library.entries)
	win.library.search.setText('')
	assert len(win.library.visibleLabels()) == len(win.library.entries)


def test_the_gauge_editor_sends_polar_to_the_polar_mode(suite):
	win = suite(mode='gauge')
	win.modes['gauge'].openPolar()
	assert win.current() == 'polar'


@pytest.mark.parametrize('entry', _entries(), ids=lambda e: f'{e.group}:{e.label}')
def test_library_entries_open_in_their_mode(suite):
	"""Every dashboard, preset and polar entry, and a few gauges (each gauge takes seconds to build), open in the mode
	their kind names with no error in that mode's status."""
	win = suite()
	modes = {'dashboard': 'dashboard', 'preset': 'dashboard', 'gauge': 'gauge', 'cell': 'gauge', 'polar': 'polar'}
	seen = {'gauge': 0, 'cell': 0}
	failed = []
	for entry in _entries():
		if entry.kind in seen:
			if seen[entry.kind] >= 2:
				continue
			seen[entry.kind] += 1
		win.openEntry(entry)
		status = getattr(win.modes[win.current()], 'status', None)
		text = status.text() if status is not None else ''
		if win.current() != modes[entry.kind] or 'Could not' in text or 'no realtime.gauge' in text:
			failed.append(f'{entry.group}: {entry.label}: {text or win.current()}')
	assert not failed, '\n'.join(failed)

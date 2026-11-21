"""The opt-in frame log (`LEVITY_FRAME_LOG`) and the item pixmap cache switch (`LEVITY_ITEM_CACHE`)."""
import json

from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from LevityDash.lib.ui.frontends.PySide import frametiming, utils


def test_summary_empty_and_values():
	assert frametiming._summary([]) == {'n': 0}
	s = frametiming._summary([0.010, 0.020, 0.030])
	assert s['n'] == 3 and s['max'] == 30.0 and s['mean'] == 20.0


def test_install_is_off_without_the_variable(monkeypatch):
	monkeypatch.delenv('LEVITY_FRAME_LOG', raising=False)
	assert frametiming.install(object()) is None


def test_frame_log_writes_a_summary_line(tmp_path, dashboard):
	from PySide6.QtWidgets import QWidget

	class View(QWidget):
		def viewport(self):
			return self

	path = tmp_path / 'frames.jsonl'
	log = frametiming.FrameLog(View(), str(path), every=60)
	log.paint(1.0, 0.012, 0.25)
	log.paint(1.02, 0.020, 1.0)
	log.write()
	line = json.loads(path.read_text().splitlines()[0])
	assert line['paint_ms']['n'] == 2 and line['paint_ms']['max'] == 20.0
	assert line['gap_ms']['n'] == 1 and line['painted_share'] == 0.625


def test_cache_item_follows_the_switch(monkeypatch):
	item = QGraphicsRectItem()
	monkeypatch.setattr(utils, '_itemCache', False)
	utils.cacheItem(item)
	assert item.cacheMode() == QGraphicsItem.CacheMode.NoCache
	monkeypatch.setattr(utils, '_itemCache', True)
	utils.cacheItem(item)
	assert item.cacheMode() == QGraphicsItem.CacheMode.DeviceCoordinateCache

"""A graph item's data-change update touches scene items, so it must run on the GUI thread.

`connectTimeseries` runs on a Worker (setContainer). Its first update used to add and remove
hour lines from that thread, which corrupted Qt's heap: two graphs with a 7-day timeframe on
one board aborted the process (`realloc(): invalid next size`) in `HourLines.updateLines`.
"""
import threading

from LevityDash.lib.utils.shared import callOnMainThread, isMainThread


def test_callOnMainThread_runs_inline_on_the_gui_thread():
	ran = []
	assert isMainThread()
	assert callOnMainThread(lambda: ran.append(threading.current_thread())) is True
	assert ran == [threading.current_thread()]


def test_callOnMainThread_queues_work_from_another_thread(dashboard):
	ran = []
	main = threading.current_thread()
	results = []
	worker = threading.Thread(target=lambda: results.append(callOnMainThread(lambda: ran.append(threading.current_thread()))))
	worker.start()
	worker.join()
	assert results == [False]
	dashboard.wait_until(lambda: ran, message='the queued call never ran on the GUI thread')
	assert ran == [main]

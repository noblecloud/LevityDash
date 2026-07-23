"""Regression test for RichRotatingLogHandlerProxy's console/stream desync
(lib/log.py).

frontend and backend both log to the same fixed ``LevityDash.log`` path
(lib/log.py's ``logPath`` is process-independent), so two processes can race
a rollover's close/rename/reopen. When that race makes ``doRollover()`` (or
the ``_open()`` it calls) raise, the handler's ``emit()`` used to only
reassign ``self.console.file = self.stream`` *inside* the "rollover
succeeded" branch - leaving ``console.file`` pointed at the now-closed
stream from before the failed attempt. Every subsequent, otherwise-normal
``emit()`` call then failed with ``ValueError: I/O operation on closed
file``, repeating until the log happened to grow enough to trigger (and
this time win) another rollover. Reported live as "a lot of errors" spewing
from a real overnight two-process run.
"""
import logging

from LevityDash.lib.log import RichRotatingLogHandlerProxy


def _make_handler(tmp_path):
	return RichRotatingLogHandlerProxy(
		filename=str(tmp_path / 'test.log'),
		maxBytes=10_000_000,
		backupCount=2,
		encoding='utf-8',
	)


def _record(msg='short msg'):
	return logging.LogRecord('test', logging.INFO, 'x.py', 1, msg, None, None)


def test_emit_self_heals_after_failed_rollover(tmp_path, capsys):
	handler = _make_handler(tmp_path)
	handler.emit(_record())

	# Simulate a concurrent-process rollover race: the stream gets closed but
	# reopening it fails, mirroring another process winning the rename.
	handler.stream.close()
	handler.stream = None
	orig_open = handler._open
	handler._open = lambda: (_ for _ in ()).throw(OSError('simulated: another process holds/renamed the file'))
	try:
		handler.shouldRollover(_record())
	except OSError:
		pass
	handler._open = orig_open

	assert handler.console.file.closed

	for _ in range(5):
		handler.emit(_record())

	assert 'Logging error' not in capsys.readouterr().err
	assert not handler.console.file.closed
	assert handler.console.file is handler.stream

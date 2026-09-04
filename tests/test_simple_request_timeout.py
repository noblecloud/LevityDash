"""`simpleRequest` must give up rather than wait on a socket forever.

`urlopen` with no timeout blocks indefinitely. That is not an exception, so
the `except Exception` fallback around `guessLocation` (config.py:553, which
falls back to 0,0/UTC) could never fire: when ipapi.co answered slowly or
rate-limited, startup simply hung with no error and the app never booted.
"""
import socket
import threading
import time

import pytest

from LevityDash.lib.utils.shared import simpleRequest


@pytest.fixture
def blackholePort():
	"""A listener that accepts a connection and then never replies."""
	server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	server.bind(('127.0.0.1', 0))
	server.listen(1)
	held = []

	def accept():
		try:
			conn, _ = server.accept()
			held.append(conn)  # kept open, deliberately never written to
		except OSError:
			pass

	thread = threading.Thread(target=accept, daemon=True)
	thread.start()
	try:
		yield server.getsockname()[1]
	finally:
		for conn in held:
			conn.close()
		server.close()
		thread.join(timeout=2)


def test_a_silent_server_raises_instead_of_hanging(blackholePort):
	start = time.monotonic()
	with pytest.raises(Exception):
		simpleRequest(f'http://127.0.0.1:{blackholePort}/', timeout=1)
	elapsed = time.monotonic() - start
	# The point is that it returns at all; the bound keeps a regression from
	# passing just because the test itself eventually gave up.
	assert elapsed < 15, f'simpleRequest took {elapsed:.1f}s - it is not honouring its timeout'


def test_the_failure_is_catchable_by_the_caller(blackholePort):
	# config.py's guessLocation wraps this in `except Exception` and falls
	# back to 0,0/UTC. A timeout has to arrive as an ordinary exception for
	# that fallback to work at all.
	try:
		simpleRequest(f'http://127.0.0.1:{blackholePort}/', timeout=1)
	except Exception:
		return
	pytest.fail('expected simpleRequest to raise')

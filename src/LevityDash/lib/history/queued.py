"""The part every network backend shares: writes that never block a plugin, and survive an outage.

`write` puts rows on a queue and a thread sends them in batches. While the server is down the rows wait (up to
`MAX_BUFFERED`, then the oldest go) and go out when it comes back. A failure is logged once, not once per minute.
A subclass says how to connect, how to send a batch and how to read; it never has to think about threads.
"""
import json
import logging
import threading
import time
from collections import deque
from typing import Deque, Iterable, List, Optional
from urllib import error, request

from .base import HistoryBackend, Sample

__all__ = ['QueuedBackend', 'MAX_BUFFERED', 'BATCH']

log = logging.getLogger('LevityDash.history')

MAX_BUFFERED = 200_000
BATCH = 5000
RETRY_EVERY = 15.0


class QueuedBackend(HistoryBackend):
	label = 'server'

	def __init__(self, base: str, headers: dict | None = None, timeout: float = 5.0):
		self.base = base
		self.timeout = timeout
		self._headers = dict(headers or {})
		self._queue: Deque[Sample] = deque()
		self._cond = threading.Condition()
		self._stop = False
		self._thread: Optional[threading.Thread] = None
		self._ready = False
		self._warned = False
		self._inflight = 0

	# -- for a subclass -----------------------------------------------------------------------------------------

	def _prepare(self) -> None:
		"""Make whatever the server needs before the first write (a table, a database). Raises on failure."""
		raise NotImplementedError

	def _send(self, batch: List[Sample]) -> None:
		"""Deliver `batch`. Raises on failure."""
		raise NotImplementedError

	# -- connection ---------------------------------------------------------------------------------------------

	def _warn(self, message: str, exc: BaseException | None = None) -> None:
		"""One log line per outage."""
		if not self._warned:
			self._warned = True
			log.warning(f'{self.label} at {self.base}: {message}' + (f' ({exc})' if exc else ''))

	def _ok(self) -> None:
		if self._warned:
			log.info(f'{self.label} at {self.base} is reachable again')
		self._warned = False

	def _open(self, req: request.Request) -> bytes:
		try:
			with request.urlopen(req, timeout=self.timeout) as response:
				return response.read()
		except error.HTTPError as e:
			raise OSError(f'{e.code} {e.read().decode("utf-8", "replace")[:300]}') from e

	def _getJSON(self, url: str):
		return json.loads(self._open(request.Request(url, headers=self._headers)))

	def connect(self) -> bool:
		"""Reach the server and prepare it. False (and one log line) when that cannot be done."""
		try:
			self._prepare()
		except Exception as e:  # noqa: BLE001
			self._warn('is not reachable', e)
			self._ready = False
			return False
		self._ok()
		self._ready = True
		self._start()
		return True

	@property
	def healthy(self) -> bool:
		return self._ready

	# -- writing ------------------------------------------------------------------------------------------------

	def _start(self) -> None:
		with self._cond:
			if self._thread is None or not self._thread.is_alive():
				self._stop = False
				self._thread = threading.Thread(target=self._run, name=f'History-{self.name}', daemon=True)
				self._thread.start()

	def write(self, samples: Iterable[Sample]) -> None:
		with self._cond:
			self._queue.extend(samples)
			self._trim()
			self._cond.notify()
		self._start()

	def _trim(self) -> None:
		for _ in range(max(len(self._queue) - MAX_BUFFERED, 0)):
			self._queue.popleft()

	def _run(self) -> None:
		while True:
			with self._cond:
				while not self._queue and not self._stop:
					self._cond.wait(1.0)
				if self._stop and not self._queue:
					return
				batch = [self._queue.popleft() for _ in range(min(BATCH, len(self._queue)))]
				self._inflight = len(batch)
			try:
				if not self._ready:
					self._prepare()
					self._ready = True
				self._send(batch)
				self._ok()
			except Exception as e:  # noqa: BLE001
				with self._cond:
					self._queue.extendleft(reversed(batch))
					self._trim()
				self._ready = False
				self._warn('rows are waiting for it to come back', e)
				with self._cond:
					if self._cond.wait_for(lambda: self._stop, timeout=RETRY_EVERY):
						return
			with self._cond:
				self._inflight = 0
				self._cond.notify_all()

	def _applied(self) -> bool:
		"""True once what was sent can be read back. A server that applies writes at once says True."""
		return True

	def flush(self, timeout: float = 5.0) -> None:
		end = time.monotonic() + timeout
		with self._cond:
			while (self._queue or self._inflight) and self._ready and time.monotonic() < end:
				self._cond.wait(0.05)
		while time.monotonic() < end:
			try:
				if self._applied():
					return
			except Exception:  # noqa: BLE001
				return
			time.sleep(0.05)

	def close(self) -> None:
		self.flush(2.0)
		with self._cond:
			self._stop = True
			self._cond.notify_all()
		if self._thread is not None:
			self._thread.join(2.0)

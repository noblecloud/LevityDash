"""Running the blocking fetches of `data.py` off the GUI thread and handing results back on it."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Hashable

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImage

__all__ = ['Loader', 'toArray', 'toImage']


def toArray(data: bytes) -> np.ndarray:
	"""Decoded PNG or JPEG bytes as `(h, w, 4)` RGBA bytes. Raises when the bytes are not an image."""
	image = QImage.fromData(data)
	if image.isNull():
		raise ValueError('not an image')
	image = image.convertToFormat(QImage.Format.Format_RGBA8888)
	w, h, stride = image.width(), image.height(), image.bytesPerLine()
	raw = np.frombuffer(image.constBits(), dtype=np.uint8, count=stride*h).reshape(h, stride)
	return raw[:, :w*4].reshape(h, w, 4).copy()


def toImage(array: np.ndarray) -> QImage:
	"""`(h, w, 4)` RGBA bytes as a QImage that owns its pixels."""
	array = np.ascontiguousarray(array, dtype=np.uint8)
	h, w = array.shape[:2]
	return QImage(array.data, w, h, w*4, QImage.Format.Format_RGBA8888).copy()


class Loader(QObject):
	"""Runs jobs on a small pool; each result is delivered to its callback on the thread this was made on (the GUI's).

	A key that is already in flight is not queued twice. `close()` drops what has not started and ignores what
	has, so an item can go away while its tiles are still arriving.
	"""

	_arrived = Signal(object, object, object)

	def __init__(self, workers: int = 4, parent=None):
		super().__init__(parent)
		self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='WeatherMap')
		self._inflight: dict[Hashable, Callable] = {}
		self._closed = False
		self._arrived.connect(self._deliver)

	def busy(self, key: Hashable) -> bool:
		return key in self._inflight

	def request(self, key: Hashable, job: Callable[[], object], done: Callable[[Hashable, object, object], None]) -> bool:
		"""Run `job()` for `key`; `done(key, result, error)` is called later, with one of the last two None."""
		if self._closed or key in self._inflight:
			return False
		self._inflight[key] = done
		future = self._pool.submit(job)
		future.add_done_callback(lambda f, key=key: self._finished(key, f))
		return True

	def _finished(self, key, future):  # on a worker thread
		try:
			result, error = future.result(), None
		except Exception as e:  # noqa: BLE001 - delivered to the callback
			result, error = None, e
		try:
			self._arrived.emit(key, result, error)
		except RuntimeError:  # the QObject went first
			pass

	@Slot(object, object, object)
	def _deliver(self, key, result, error):  # on the GUI thread
		done = self._inflight.pop(key, None)
		if done is not None and not self._closed:
			done(key, result, error)

	def close(self):
		self._closed = True
		self._inflight.clear()
		self._pool.shutdown(wait=False, cancel_futures=True)

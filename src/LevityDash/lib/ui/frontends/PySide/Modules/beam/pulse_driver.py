"""Shared frame-rate-capped loop driving every animated beam.

Mirrors the React project's `pulseDriver.ts`: one shared timer (~30 fps) instead of one
animation per beam. The driver keeps a clock in seconds. A beam reads the clock when it paints,
and evaluates its oscillators (`styles.pulse_values`) at that time.

Differences from `border-beam-qt`, which counted references:

- A beam *subscribes* while it has something to animate and *unsubscribes* when it is done.
  The timer runs only while at least one beam is subscribed, so a dashboard with no active
  beam pays nothing: no timer, no repaint.
- `set_time()` freezes the clock. A frozen driver ignores subscriptions until `unfreeze()`.
  Tests and renders freeze it so a frame is the same every run.
- The clock advances by the real time since the last tick (capped), not by a fixed 1/30 s.
  A slow machine then drops frames instead of slowing the animation.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer

_MAX_STEP = 0.1  # seconds; a stalled GUI thread must not make the clock jump


class PulseDriver(QObject):
	"""Singleton. Frame-rate-capped shared clock for the beams."""

	_shared: PulseDriver | None = None

	def __init__(self) -> None:
		super().__init__()
		self._timer = QTimer(self)
		self._timer.setInterval(33)  # ~30fps, matching upstream
		self._timer.timeout.connect(self._tick)
		self._t = 0.0
		self._last = 0.0
		self._frozen = False
		self._subscribers: list = []

	@classmethod
	def shared(cls) -> PulseDriver:
		if cls._shared is None:
			cls._shared = PulseDriver()
		return cls._shared

	@property
	def t(self) -> float:
		"""Shared clock in seconds. It stands still while no beam is subscribed."""
		return self._t

	@property
	def frozen(self) -> bool:
		return self._frozen

	@property
	def running(self) -> bool:
		try:
			return self._timer.isActive()
		except RuntimeError:
			return False

	@property
	def subscriberCount(self) -> int:
		return len(self._subscribers)

	def set_time(self, value: float) -> None:
		"""Force the clock (tests, renders). Freezes the driver: the timer stops and stays stopped."""
		self._t = max(0.0, float(value))
		self._frozen = True
		# `stop()` must tolerate a dead QTimer: the interpreter destroys it first at shutdown.
		try:
			self._timer.stop()
		except RuntimeError:
			pass

	def unfreeze(self) -> None:
		self._frozen = False
		if self._subscribers:
			self._start()

	def subscribe(self, beam) -> None:
		"""Call `beam.tick(t)` on every frame until `unsubscribe`."""
		if beam not in self._subscribers:
			self._subscribers.append(beam)
		if not self._frozen:
			self._start()

	def unsubscribe(self, beam) -> None:
		try:
			self._subscribers.remove(beam)
		except ValueError:
			return
		if not self._subscribers:
			try:
				self._timer.stop()
			except RuntimeError:
				pass

	def _start(self) -> None:
		try:
			if not self._timer.isActive():
				self._last = time.monotonic()
				self._timer.start()
		except RuntimeError:
			pass

	def _tick(self) -> None:
		now = time.monotonic()
		self._t += min(now - self._last, _MAX_STEP)
		self._last = now
		for beam in tuple(self._subscribers):
			try:
				beam.tick(self._t)
			except RuntimeError:
				# The C++ item is gone (a dashboard reload) and nobody unsubscribed it.
				self.unsubscribe(beam)

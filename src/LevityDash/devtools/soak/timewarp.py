"""Time dilation for soak tests: one real second passes as ``speed`` virtual seconds.

Standalone on purpose (stdlib only, never imports ``LevityDash``): a soak child
imports this *first*, installs it, and only then imports the app, so every module
binds the warped clock functions instead of the real ones.

What is warped, so that timers, sleeps and wall-clock reads all agree:

- ``time.time`` / ``time.monotonic`` (and ``_ns``), ``time.localtime``/``gmtime``/``ctime``/``strftime``
  called without a time, and ``datetime.now()/utcnow()/today()`` (``datetime.datetime`` is replaced
  by a subclass; its instances are plain ``datetime`` objects, so equality, YAML and ``type()`` checks
  keep working).
- ``time.sleep``, ``threading.Condition.wait`` (so ``Event.wait``, ``Queue.get`` and ``Thread.join``
  timeouts), the asyncio loop clock and its selector timeout. A ``call_later(60)`` fires after
  ``60 / speed`` real seconds. Loops on the threads in ``realtimeThreads`` (the wire server and client) keep real
  time instead, so socket-level timeouts do not fire early.
- ``QTimer`` (``start``, ``setInterval``, ``singleShot``, the ``interval=`` constructor argument, and the
  getters, which answer in virtual milliseconds). Call ``warpQt()`` once PySide6 is importable.

Not warped: ``perf_counter`` and ``process_time`` (they measure real work), Qt animations, socket
timeouts inside the kernel. CPU work does not shrink, so a high ``speed`` means the app sees a slower CPU.

``jump()`` moves the wall clock without moving the monotonic clock: a laptop waking from sleep, an NTP
step, a DST rule applied by hand. ``schedule`` runs jumps at virtual-elapsed offsets.

Environment (read by ``installFromEnvironment``):

- ``LEVITYDASH_SOAK_SPEED``  virtual seconds per real second (default 1)
- ``LEVITYDASH_SOAK_START``  ISO local start time, e.g. ``2026-10-31T18:00`` (default: now)
- ``LEVITYDASH_SOAK_TZ``     IANA zone applied to the process (``TZ`` + ``tzset``)
- ``LEVITYDASH_SOAK_JUMPS``  ``elapsedSeconds:+deltaSeconds`` pairs, comma separated
"""
import datetime as _datetime
import os
import selectors
import sys
import threading
import time as _time

_real = {
	'time':         _time.time,
	'time_ns':      _time.time_ns,
	'monotonic':    _time.monotonic,
	'monotonic_ns': _time.monotonic_ns,
	'sleep':        _time.sleep,
	'localtime':    _time.localtime,
	'gmtime':       _time.gmtime,
	'ctime':        _time.ctime,
	'strftime':     _time.strftime,
}
_RealDatetime = _datetime.datetime
_RealDate = _datetime.date

_state = {'speed': 1.0, 'wall0': 0.0, 'real0': 0.0, 'mono0': 0.0, 'offset': 0.0, 'installed': False}


def speed() -> float:
	return _state['speed']


def wall() -> float:
	"""Virtual epoch seconds."""
	s = _state
	return s['wall0'] + s['offset'] + (_real['time']() - s['real0']) * s['speed']


def mono() -> float:
	"""Virtual monotonic seconds. Unaffected by ``jump``."""
	s = _state
	return s['mono0'] + (_real['monotonic']() - s['mono0']) * s['speed']


def elapsed() -> float:
	"""Virtual seconds since install, monotonic (a jump does not count)."""
	return (_real['monotonic']() - _state['mono0']) * _state['speed']


def realElapsed() -> float:
	"""Real seconds since install."""
	return _real['monotonic']() - _state['mono0']


def jump(seconds: float) -> None:
	_state['offset'] += seconds


def schedule(jumps) -> None:
	"""Run ``[(atElapsedSeconds, deltaSeconds), ...]`` on a daemon thread."""
	pending = sorted(jumps)
	if not pending:
		return

	def run():
		for at, delta in pending:
			while elapsed() < at:
				_real['sleep'](min(0.05, max(0.001, (at - elapsed()) / _state['speed'])))
			jump(delta)
			print(f'[timewarp] wall clock jumped {delta:+.0f}s at +{elapsed():.0f}s -> {_RealDatetime.fromtimestamp(wall()).isoformat()}', file=sys.stderr, flush=True)

	threading.Thread(target=run, name='timewarp-jumps', daemon=True).start()


class _Meta(type):
	def __instancecheck__(cls, obj):
		return isinstance(obj, _RealDatetime)

	def __subclasscheck__(cls, sub):
		return issubclass(sub, _RealDatetime)


class _DateMeta(type):
	def __instancecheck__(cls, obj):
		return isinstance(obj, _RealDate)

	def __subclasscheck__(cls, sub):
		return issubclass(sub, _RealDate)


class WarpedDatetime(_RealDatetime, metaclass=_Meta):
	"""``datetime.datetime`` whose ``now()`` reads the warped clock. Every instance is a real ``datetime``."""

	def __new__(cls, *args, **kwargs):
		return _RealDatetime(*args, **kwargs)

	@classmethod
	def now(cls, tz=None):
		return _RealDatetime.fromtimestamp(wall(), tz)

	@classmethod
	def utcnow(cls):
		return _RealDatetime.fromtimestamp(wall(), _datetime.timezone.utc).replace(tzinfo=None)

	@classmethod
	def today(cls):
		return _RealDatetime.fromtimestamp(wall())

	@classmethod
	def fromtimestamp(cls, ts, tz=None):
		return _RealDatetime.fromtimestamp(ts, tz)

	@classmethod
	def utcfromtimestamp(cls, ts):
		return _RealDatetime.fromtimestamp(ts, _datetime.timezone.utc).replace(tzinfo=None)

	@classmethod
	def strptime(cls, *args):
		return _RealDatetime.strptime(*args)

	@classmethod
	def fromisoformat(cls, text):
		return _RealDatetime.fromisoformat(text)

	@classmethod
	def combine(cls, *args, **kwargs):
		return _RealDatetime.combine(*args, **kwargs)

	min = _RealDatetime.min
	max = _RealDatetime.max


class WarpedDate(_RealDate, metaclass=_DateMeta):
	def __new__(cls, *args, **kwargs):
		return _RealDate(*args, **kwargs)

	@classmethod
	def today(cls):
		return _RealDatetime.fromtimestamp(wall()).date()

	@classmethod
	def fromtimestamp(cls, ts):
		return _RealDate.fromtimestamp(ts)

	@classmethod
	def fromisoformat(cls, text):
		return _RealDate.fromisoformat(text)

	min = _RealDate.min
	max = _RealDate.max


def _localtime(secs=None):
	return _real['localtime'](wall() if secs is None else secs)


def _gmtime(secs=None):
	return _real['gmtime'](wall() if secs is None else secs)


def _ctime(secs=None):
	return _real['ctime'](wall() if secs is None else secs)


def _strftime(fmt, t=None):
	return _real['strftime'](fmt, _localtime() if t is None else t)


def _sleep(seconds):
	_real['sleep'](seconds / _state['speed'])


#: Threads whose event loops keep real time. The wire server and client talk over a real socket, and their
#: timeouts (websocket heartbeat, request deadlines) guard real latency: scaled down, a GIL stall of half a
#: second looks like a dead peer and the connection flaps for a reason the app does not have in production.
realtimeThreads = ['WireServer', 'WireClientThread', 'soak-feeds']


def _realtime() -> bool:
	name = threading.current_thread().name
	return any(name.startswith(prefix) for prefix in realtimeThreads)


def _scaled(timeout):
	if timeout is None or timeout <= 0:
		return timeout
	return timeout / _state['speed']


def _loopScaled(timeout):
	return timeout if _realtime() else _scaled(timeout)


def install(speed: float = 1.0, start: _RealDatetime | None = None, tz: str | None = None) -> None:
	"""Start the warped clock at ``start`` (local time; default: the real now)."""
	if _state['installed']:
		raise RuntimeError('timewarp is already installed')
	if tz:
		os.environ['TZ'] = tz
		_time.tzset()
	wall0 = _real['time']() if start is None else start.timestamp()
	_state.update(speed=float(speed), wall0=wall0, real0=_real['time'](), mono0=_real['monotonic'](), installed=True)

	_time.time = wall
	_time.time_ns = lambda: int(wall() * 1e9)
	_time.monotonic = mono
	_time.monotonic_ns = lambda: int(mono() * 1e9)
	_time.sleep = _sleep
	_time.localtime = _localtime
	_time.gmtime = _gmtime
	_time.ctime = _ctime
	_time.strftime = _strftime
	_datetime.datetime = WarpedDatetime
	_datetime.date = WarpedDate

	# Condition.wait is what Event.wait, Queue.get and Thread.join timeouts reduce to.
	_conditionWait = threading.Condition.wait

	def wait(self, timeout=None):
		return _conditionWait(self, _scaled(timeout))

	threading.Condition.wait = wait

	# The selector timeout is the one real sleep in an asyncio loop.
	_select = selectors.DefaultSelector.select

	def select(self, timeout=None):
		return _select(self, _loopScaled(timeout))

	selectors.DefaultSelector.select = select

	import asyncio.base_events as base_events
	base_events.BaseEventLoop.time = lambda self: _real['monotonic']() if _realtime() else mono()

	sweep()


def sweep() -> None:
	"""Rebind ``from time import monotonic``-style names in already-imported modules to the warped ones.

	Safe to call again after the app is imported: modules that did ``from datetime import datetime`` before
	``install`` hold the real class and are fixed here; later imports already got the warped one.
	"""
	swaps = {
		_real['time']: wall, _real['time_ns']: _time.time_ns, _real['monotonic']: mono,
		_real['monotonic_ns']: _time.monotonic_ns, _real['sleep']: _sleep, _real['localtime']: _localtime,
		_real['gmtime']: _gmtime, _real['ctime']: _ctime, _real['strftime']: _strftime,
		_RealDatetime: WarpedDatetime, _RealDate: WarpedDate,
	}
	for module in list(sys.modules.values()):
		if module is None or module is sys.modules.get(__name__):
			continue
		try:
			namespace = vars(module)
		except TypeError:
			continue
		for name, value in list(namespace.items()):
			try:
				replacement = swaps.get(value)
			except TypeError:  # unhashable module attribute
				continue
			if replacement is not None and name not in ('__builtins__',):
				try:
					setattr(module, name, replacement)
				except (AttributeError, TypeError):
					pass


def warpQt() -> None:
	"""Scale ``QTimer`` to the warped clock. Call once, after PySide6 is importable and before timers exist."""
	from PySide6.QtCore import QTimer
	k = _state['speed']
	if k == 1.0 or getattr(QTimer, '_warped', False):
		return

	def down(ms):
		return ms if ms <= 0 else max(1, round(ms / k))

	_init, _start, _setInterval, _interval, _remaining, _singleShot = (
		QTimer.__init__, QTimer.start, QTimer.setInterval, QTimer.interval, QTimer.remainingTime, QTimer.singleShot,
	)

	def init(self, *args, **kwargs):
		if 'interval' in kwargs:
			kwargs['interval'] = down(kwargs['interval'])
		_init(self, *args, **kwargs)

	def start(self, *args):
		if args and isinstance(args[0], int):
			args = (down(args[0]),) + args[1:]
		return _start(self, *args)

	def setInterval(self, ms):
		return _setInterval(self, down(ms))

	def interval(self):
		return round(_interval(self) * k)

	def remainingTime(self):
		value = _remaining(self)
		return value if value < 0 else round(value * k)

	def singleShot(msec, *args):
		return _singleShot(down(msec), *args)

	QTimer.__init__ = init
	QTimer.start = start
	QTimer.setInterval = setInterval
	QTimer.interval = interval
	QTimer.remainingTime = remainingTime
	QTimer.singleShot = staticmethod(singleShot)
	QTimer._warped = True


def warpApp() -> None:
	"""Fix ``startTimerSafe``, whose cross-thread branch queues ``start(int)`` by name, past the ``QTimer.start``
	wrapper. Call after ``LevityDash.lib.utils.shared`` is imported, and again after later imports."""
	from PySide6.QtCore import QMetaObject, Qt, Q_ARG, QThread
	k = _state['speed']
	if k == 1.0:
		return

	def down(ms):
		return ms if ms <= 0 else max(1, round(ms / k))

	for module in list(sys.modules.values()):
		if getattr(module, '__name__', '') == 'LevityDash.lib.utils.shared' and hasattr(module, 'startTimerSafe'):
			def startTimerSafe(timer, msec=None, _orig=module.startTimerSafe):
				if QThread.currentThread() is timer.thread():
					timer.start() if msec is None else timer.start(msec)
				elif msec is None:
					QMetaObject.invokeMethod(timer, 'start', Qt.ConnectionType.QueuedConnection)
				else:
					QMetaObject.invokeMethod(timer, 'start', Qt.ConnectionType.QueuedConnection, Q_ARG(int, down(msec)))

			original = module.startTimerSafe
			for other in list(sys.modules.values()):
				if other is not None and getattr(other, 'startTimerSafe', None) is original:
					other.startTimerSafe = startTimerSafe


def parseJumps(text: str):
	jumps = []
	for part in filter(None, (p.strip() for p in (text or '').split(','))):
		at, _, delta = part.partition(':')
		jumps.append((float(at), float(delta)))
	return jumps


def installFromEnvironment() -> bool:
	"""Install from the ``LEVITYDASH_SOAK_*`` variables. Returns whether a warp was installed."""
	k = float(os.environ.get('LEVITYDASH_SOAK_SPEED', '1') or 1)
	start = os.environ.get('LEVITYDASH_SOAK_START')
	tz = os.environ.get('LEVITYDASH_SOAK_TZ')
	if k == 1.0 and not start and not tz:
		return False
	if tz:
		os.environ['TZ'] = tz
		_time.tzset()
	install(k, _RealDatetime.fromisoformat(start) if start else None, tz)
	schedule(parseJumps(os.environ.get('LEVITYDASH_SOAK_JUMPS', '')))
	return True

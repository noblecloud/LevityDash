"""Generic plugin lifecycle + shared BLE scanning.

Two things live here, in dependency order:

``LifecyclePlugin``
	The ``start()``/``stop()`` shape that every builtin plugin had
	copy-pasted into its own ``bootstrap()`` closure - run a task on a
	dedicated event loop in an executor thread, wait on ``self.future``, then
	tear the loop *and the future* down so the next ``start()`` is fresh.
	The missing ``del self.future`` in that closure was a real bug (a plugin
	stopped once could never start again for the rest of the process's life);
	having one implementation means it cannot be half-fixed in four places.
	See ``tests/plugins/test_plugin_lifecycle.py``.

``BLEPlugin`` + ``SharedScanner``
	One ``BleakScanner`` for the whole process, routing each advertisement to
	whichever plugin instances claim it. Mirrors Home Assistant's Bluetooth
	platform, where the scanner is shared infrastructure and each device gets
	its own coordinator, rather than each integration running a scanner and
	each device fighting over it.

Nothing here is Govee-specific: no payload parsing, no model knowledge, no
config format. That is policy and belongs to the plugin.
"""
import asyncio
from abc import abstractmethod
from threading import Lock
from typing import Any, Callable, ClassVar, Dict, Optional, Set, TYPE_CHECKING

from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.plugin import Plugin
from LevityDash.lib.plugins.web.reconnect import Backoff

if TYPE_CHECKING:
	from bleak import BleakScanner

log = LevityPluginLog.getChild('BLE')

__all__ = ['LifecyclePlugin', 'BLEPlugin', 'BluetoothUnavailable', 'SharedScanner', 'shared_scanner', 'explainScanFailure']


class BluetoothUnavailable(Exception):
	"""The radio cannot scan right now. The message says why, in plain words."""


def explainScanFailure(error: BaseException) -> str:
	"""Say in one line why a scan could not start.

	bleak raises a different type on each platform (and a bare
	`FileNotFoundError` on Linux with no BlueZ), so this reads the text too.
	"""
	text = str(error).lower()
	if isinstance(error, PermissionError) or any(w in text for w in ('permission', 'not authorized', 'unauthorized', 'denied')):
		return 'Bluetooth permission denied (on macOS: System Settings > Privacy & Security > Bluetooth)'
	if any(w in text for w in ('powered off', 'turned off', 'not turned on', 'disabled', 'radio')):
		return 'Bluetooth is turned off'
	if isinstance(error, FileNotFoundError) or any(w in text for w in ('no bluetooth adapter', 'no adapter', 'not available', 'bluez', 'dbus')):
		return 'no Bluetooth adapter found'
	return f'Bluetooth could not start ({type(error).__name__}: {error})'


class LifecyclePlugin(Plugin):
	"""A ``Plugin`` with the standard run-a-loop-in-a-thread lifecycle.

	Subclasses implement ``onStart``/``onStop`` (both optional, both async)
	and get ``start``/``stop``/``asyncStart``/``asyncStop``/``running`` for
	free. The ordering guarantees callers depend on:

	- ``start()`` on an already-running plugin is a no-op, not a second loop.
	- ``stop()`` resolves ``future``, which releases the ``await`` inside the
	  bootstrap thread, which then deletes **both** ``loop`` and ``future``.
	- After a full stop, ``start()`` works again. Deleting ``loop`` without
	  ``future`` is the specific bug this class exists to make unrepeatable:
	  ``future`` is a ``cached_property`` and a resolved Future stays resolved,
	  so the next ``await self.future`` returns instantly and the plugin
	  shuts itself down the moment it starts.
	"""

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._running = False
		self._task = None

	# -- subclass hooks ------------------------------------------------------

	async def onStart(self) -> None:
		"""Bring the plugin up. Runs on ``self.loop``, before it starts waiting."""

	async def onStop(self) -> None:
		"""Tear the plugin down. Runs while the loop is still alive."""

	# -- lifecycle -----------------------------------------------------------

	@property
	def running(self) -> bool:
		return self._running

	def start(self):
		if self._running:
			self.pluginLog.info(f'{self.name}: already running')
			return self

		self.pluginLog.info(f'{self.name}: starting')

		async def async_bootstrap():
			try:
				await self.onStart()
			except Exception as e:
				self.pluginLog.error(f'{self.name}: failed to start: {e}')
				self.pluginLog.exception(e)
				return
			self._running = True
			self.pluginLog.info(f'{self.name}: started')
			await self.future
			self.pluginLog.info(f'{self.name}: starting shutdown')

		def bootstrap():
			self._task = async_bootstrap()
			self.loop.run_until_complete(self._task)
			self._running = False
			# Both must go. `loop` alone leaves a resolved `future` cached,
			# and every later start() then returns instantly - see the class
			# docstring and tests/plugins/test_plugin_lifecycle.py.
			del self.loop
			del self.future
			self.pluginLog.info(f'{self.name}: shutdown complete')

		self.loop.run_in_executor(None, bootstrap)
		return self

	async def asyncStart(self):
		self.loop.call_soon(self.start)

	def stop(self, callback: Optional[Callable] = None):
		if not self._running:
			self.pluginLog.info(f'{self.name}: not running')
			return
		self.pluginLog.info(f'{self.name}: stopping')
		asyncio.run_coroutine_threadsafe(self.asyncStop(), self.loop)
		if callback is not None:
			callback()

	async def asyncStop(self):
		self._running = False
		try:
			await self.onStop()
		except Exception as e:
			self.pluginLog.error(f'{self.name}: error during shutdown: {e}')
		# Resolving future releases the `await` in async_bootstrap, which lets
		# the bootstrap thread run its teardown. Guarded because stop() can
		# race with a shutdown already in flight.
		if not self.future.done():
			self.future.set_result(True)
		self.pluginLog.info(f'{self.name}: stopped')


class SharedScanner:
	"""One ``BleakScanner`` for the process, fanned out to many subscribers.

	Why shared: a ``BleakScanner`` is a system-wide resource. Two of them
	against the same adapter is at best redundant and at worst a lifecycle
	fight - which is exactly what a plugin-per-device design would have
	produced (N devices, N scanners, each stopping the others' discovery).
	Home Assistant solved this the same way: the Bluetooth platform owns the
	scanner, integrations subscribe.

	Subscribers are ``(predicate, callback)`` pairs. The scanner runs while at
	least one subscriber exists and stops when the last one leaves, so an
	all-devices-stopped state leaves no radio work running.
	"""

	_scanner: Optional['BleakScanner']
	_subscribers: Dict[Any, tuple[Callable[[Any, Any], bool], Callable[[Any, Any], None]]]

	def __init__(self):
		self._scanner = None
		self._subscribers = {}
		self._lock = Lock()
		self._starting = False

	@property
	def running(self) -> bool:
		return self._scanner is not None

	@property
	def subscribers(self) -> Set[Any]:
		return set(self._subscribers)

	def subscribe(self, owner: Any, predicate: Callable[[Any, Any], bool], callback: Callable[[Any, Any], None]) -> None:
		"""Route advertisements matching ``predicate`` to ``callback``.

		``owner`` is any hashable handle used to unsubscribe later - in
		practice the plugin instance.
		"""
		with self._lock:
			self._subscribers[owner] = (predicate, callback)

	def unsubscribe(self, owner: Any) -> None:
		with self._lock:
			self._subscribers.pop(owner, None)

	def dispatch(self, device, data) -> int:
		"""Hand one advertisement to every subscriber that wants it.

		Returns the number of subscribers that accepted it. Public and
		synchronous on purpose: it is the seam BLE-free tests drive with
		stand-in devices, so the whole routing path is exercised without a
		radio (live BLE cannot run headless on macOS - the process SIGABRTs
		without ``NSBluetoothAlwaysUsageDescription``).
		"""
		delivered = 0
		# Snapshot: a callback may unsubscribe (a device stopping mid-scan).
		for owner, (predicate, callback) in list(self._subscribers.items()):
			try:
				if not predicate(device, data):
					continue
			except Exception as e:
				log.error(f'{owner}: advertisement filter raised: {e}')
				continue
			delivered += 1
			try:
				callback(device, data)
			except Exception as e:
				log.error(f'{owner}: advertisement handler raised: {e}')
				log.exception(e)
		return delivered

	async def start(self, **kwargs) -> None:
		"""Start the underlying scanner if it is not already running."""
		with self._lock:
			if self._scanner is not None or self._starting:
				return
			self._starting = True
		try:
			from bleak import BleakScanner

			scanner = BleakScanner(detection_callback=self.dispatch, **kwargs)
			await scanner.start()
			with self._lock:
				self._scanner = scanner
			log.info('Shared BLE scanner started')
		except Exception as e:
			reason = explainScanFailure(e)
			log.warning(f'Unable to start shared BLE scanner: {reason}')
			raise BluetoothUnavailable(reason) from e
		finally:
			with self._lock:
				self._starting = False

	async def stop(self, force: bool = False) -> None:
		"""Stop the scanner once no subscriber still wants it.

		``force`` stops regardless - app shutdown, where the subscriber list
		is torn down separately.
		"""
		with self._lock:
			if self._scanner is None:
				return
			if self._subscribers and not force:
				return
			scanner, self._scanner = self._scanner, None
		try:
			await scanner.stop()
			log.info('Shared BLE scanner stopped')
		except Exception as e:
			log.error(f'Error stopping shared BLE scanner: {e}')


#: Process-wide scanner. Module-level rather than a classvar so non-Govee BLE
#: plugins share the same radio instead of each owning one.
shared_scanner = SharedScanner()


class BLEPlugin(LifecyclePlugin):
	"""A passive BLE plugin: subscribes to the shared scanner, never connects.

	"Passive" is Home Assistant's distinction and worth keeping: these devices
	broadcast advertisements and are never connected to, so there is no
	session to keep alive, reconnect, or lose. That makes the lifecycle a
	subscription, not a connection.
	"""

	#: Overridden per plugin; passed to the shared scanner on first start.
	scannerKwargs: ClassVar[dict] = {}

	@abstractmethod
	def wants(self, device, data) -> bool:
		"""Whether this instance should receive ``device``'s advertisement."""
		raise NotImplementedError

	@abstractmethod
	def handleAdvertisement(self, device, data) -> None:
		"""Consume an advertisement this instance claimed."""
		raise NotImplementedError

	@property
	def scanner(self) -> SharedScanner:
		return shared_scanner

	#: None while the scanner is up; the reason while it is not.
	bluetoothProblem: Optional[str] = None
	_scanRetry: Optional[asyncio.Task] = None

	async def onStart(self) -> None:
		shared_scanner.subscribe(self, self.wants, self.handleAdvertisement)
		try:
			await shared_scanner.start(**type(self).scannerKwargs)
		except BluetoothUnavailable as e:
			# The plugin stays up, so the rest of the dashboard is untouched,
			# and tries again: an adapter can be plugged in or permission granted later.
			self.bluetoothProblem = str(e)
			self.pluginLog.warning(f'{self.name}: {e}; will keep trying')
			self._scanRetry = asyncio.ensure_future(self._retryScan())

	async def _retryScan(self, backoff: Optional[Backoff] = None) -> None:
		backoff = backoff or Backoff(initial=30, maximum=600)
		while True:
			await asyncio.sleep(backoff.next())
			try:
				await shared_scanner.start(**type(self).scannerKwargs)
			except BluetoothUnavailable as e:
				self.bluetoothProblem = str(e)
				continue
			self.bluetoothProblem = None
			self.pluginLog.info(f'{self.name}: Bluetooth is available, scanning')
			return

	async def onStop(self) -> None:
		if self._scanRetry is not None:
			self._scanRetry.cancel()
			self._scanRetry = None
		shared_scanner.unsubscribe(self)
		# Only actually stops if this was the last subscriber, so one device
		# stopping does not blind the others.
		await shared_scanner.stop()

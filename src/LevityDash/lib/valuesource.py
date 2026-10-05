"""Value sources for the Qt frontend: a number, a key or an expression.

statekit's `Binding` is thread-agnostic. This module is the LevityDash side:
`KeySource` reads a key through the dispatcher and delivers each change on the
GUI thread, never on the plugin thread that published it.

`openValueSource(text)` is what a `.levity` slot calls. A number gives a
`Constant`. A key or an expression gives a `KeySource` that holds one
`acquireValueSource` lease, and `release()` returns it.
"""
from numbers import Number
from typing import Any, Callable, List, Optional

from PySide6.QtCore import QObject, Slot

from LevityDash import LevityDashboard
from LevityDash.lib.log import LevityPluginLog
from LevityDash.lib.plugins.categories import CategoryItem
from LevityDash.lib.plugins.computed import acquireValueSource, releaseValueSource
from LevityDash.lib.plugins.expressions import Expression, ExpressionError
from LevityDash.lib.plugins.plugin import AnySource
from LevityDash.lib.stateful import Constant, ValueSource
from qolkit import Unset

__all__ = ["KeySource", "openValueSource", "installStandIn"]

log = LevityPluginLog.getChild("ValueSource")


class _Feed(QObject):
	"""Connects to the key's container and relays changes to callbacks.

	A `QObject` so the channel signal reaches `updateSlot` on the GUI thread.
	"""

	def __init__(self, source: 'KeySource'):
		super().__init__()
		self._owner = source
		self._connected = None
		self._closed = False
		self._multi = LevityDashboard.get_container(source.key)
		self._multi.getPreferredSourceContainer(self, AnySource, self._attach)

	def _attach(self):
		if self._closed or self._connected is not None:
			return
		source = self._multi.getRealtimeContainer(AnySource) or self._multi.getRealtimeContainer(AnySource, False)
		if source is None:
			return
		if not source.channel.connectSlot(self.updateSlot):
			log.warning(f'value source {self._owner.key} failed to connect to {source.log_repr}')
			return
		self._connected = source
		self.updateSlot()

	def current(self) -> Any:
		try:
			return self._multi.value.now.value
		except (AttributeError, ValueError):
			return Unset

	@Slot(object)
	def updateSlot(self, *args):
		if self._closed:
			return
		value = self.current()
		if value is Unset:
			return
		self._owner._emit(value)

	def close(self):
		self._closed = True
		if self._connected is not None:
			try:
				self._connected.channel.disconnectSlot(self.updateSlot)
			except Exception:
				pass
			self._connected = None


class KeySource:
	"""A key, or the computed key of an expression, as a ValueSource.

	Build it with `openValueSource`, not directly: that call holds the
	acquire that `release()` undoes.
	"""

	def __init__(self, text: str, key: CategoryItem):
		self.text = text
		self.key = key
		self._callbacks: List[Callable[[Any], None]] = []
		self._feed: Optional[_Feed] = None
		self._released = False

	def get(self) -> Any:
		if self._feed is not None:
			return self._feed.current()
		try:
			return LevityDashboard.get_container(self.key).value.now.value
		except (AttributeError, ValueError):
			return Unset

	def subscribe(self, callback: Callable[[Any], None]) -> Callable[[], None]:
		if self._released:
			return lambda: None
		self._callbacks.append(callback)
		if self._feed is None:
			self._feed = _Feed(self)

		def unsubscribe():
			try:
				self._callbacks.remove(callback)
			except ValueError:
				return
			if not self._callbacks and self._feed is not None:
				self._feed.close()
				self._feed = None

		return unsubscribe

	@property
	def subscriberCount(self) -> int:
		return len(self._callbacks)

	def _emit(self, value: Any) -> None:
		for callback in tuple(self._callbacks):
			try:
				callback(value)
			except RuntimeError:
				# The target was deleted (dashboard reload) and this source outlived it.
				if callback in self._callbacks:
					self._callbacks.remove(callback)

	def release(self) -> None:
		"""Close the feed and return the acquire. Safe to call twice."""
		if self._released:
			return
		self._released = True
		self._callbacks.clear()
		if self._feed is not None:
			self._feed.close()
			self._feed = None
		releaseValueSource(self.text)

	def __repr__(self):
		return f'KeySource({self.text!r})'


_standIn: Optional[Callable[..., Optional[ValueSource]]] = None


def installStandIn(standIn: Optional[Callable[..., Optional[ValueSource]]]) -> None:
	"""Answer every `openValueSource` call with `standIn` instead of the dispatcher.

	For tools that draw items without booting the dashboard (Gauge Studio). The
	stand-in takes the same arguments as `openValueSource`. Pass None to restore
	the real lookup. Consumers call `openValueSource`, so no module that imports
	it by name needs patching.
	"""
	global _standIn
	_standIn = standIn


def openValueSource(value: Any, label: str = 'value source', effect: str = 'it shows no value') -> Optional[ValueSource]:
	"""The ValueSource for a `.levity` slot, or None after a logged warning.

	A number is a `Constant`. Text is a key or an expression: a `KeySource`
	holding one acquire. `label` names the slot in the log and `effect` says
	what the user sees instead. Never raises.
	"""
	if _standIn is not None:
		return _standIn(value, label, effect)
	if isinstance(value, bool):
		log.warning(f'{label} {value!r} must be a number, a key or an expression; {effect}')
		return None
	if isinstance(value, Number):
		return Constant(value)
	if not isinstance(value, str):
		log.warning(f'{label} {value!r} must be a number, a key or an expression; {effect}')
		return None
	try:
		Expression.parse(value)
	except ExpressionError as e:
		log.warning(f'{label} {value!r} is not a valid value source ({e}); {effect}')
		return None
	except Exception as e:
		log.warning(f'{label} {value!r} could not be read ({e!r}); {effect}')
		return None
	if (key := acquireValueSource(value)) is None:
		log.warning(f'{label} {value!r} could not be registered; {effect}')
		return None
	return KeySource(value, key)

"""One-way binding from a value source to a setter.

A value source is anything with `get()` and `subscribe(callback)`. A Binding
pushes the source's value into a setter now and on every change, until
`unlink()`. statekit does not know what a source reads from, and it does not
know which thread a callback runs on. A consumer that needs the GUI thread
wraps its source so `subscribe` delivers there.

This is `dlink` from traitlets. The name `link` already means a Stateful
reference in statekit, so this is `bind`.

Pure Python. No Qt, no LevityDash.
"""
import logging
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from qolkit import Unset

__all__ = ["ValueSource", "Constant", "Binding"]

log = logging.getLogger(__name__)


@runtime_checkable
class ValueSource(Protocol):
	"""Where a value comes from.

	`get()` returns the current value, or Unset when there is none yet.
	`subscribe(callback)` calls `callback(value)` on each change and returns a
	function that stops it. A source that holds a resource also has
	`release()`; the Binding calls it once, on `unlink()`.
	"""

	def get(self) -> Any: ...

	def subscribe(self, callback: Callable[[Any], None]) -> Callable[[], None]: ...


class Constant:
	"""A source whose value never changes."""
	__slots__ = ("value",)

	def __init__(self, value: Any):
		self.value = value

	def get(self) -> Any:
		return self.value

	def subscribe(self, callback: Callable[[Any], None]) -> Callable[[], None]:
		return _noop

	def __repr__(self):
		return f"Constant({self.value!r})"


def _noop() -> None:
	pass


class Binding:
	"""Push `transform(source value)` into `setter` now and on each change.

	An Unset value is skipped (no value yet). A setter or transform that
	raises is logged and skipped: one bad value must not abort a dashboard
	load, and a subscriber callback has no caller to raise to.
	"""

	def __init__(
		self,
		source: ValueSource,
		setter: Callable[[Any], None],
		transform: Optional[Callable[[Any], Any]] = None,
	):
		self.source = source
		self._setter = setter
		self._transform = transform
		self._unsubscribe: Optional[Callable[[], None]] = None
		self._linked = True
		self._unsubscribe = source.subscribe(self._deliver)
		self.push()

	@property
	def linked(self) -> bool:
		return self._linked

	def push(self) -> None:
		"""Push the source's current value."""
		try:
			value = self.source.get()
		except Exception as e:
			log.error(f"{self.source!r} could not be read: {e!r}")
			return
		self._deliver(value)

	def _deliver(self, value: Any) -> None:
		if not self._linked or value is Unset:
			return
		try:
			if self._transform is not None:
				value = self._transform(value)
			self._setter(value)
		except Exception as e:
			log.error(f"binding from {self.source!r} dropped a value: {e!r}")

	def unlink(self) -> None:
		"""Stop delivering and release the source. Safe to call twice."""
		if not self._linked:
			return
		self._linked = False
		unsubscribe, self._unsubscribe = self._unsubscribe, None
		if unsubscribe is not None:
			try:
				unsubscribe()
			except Exception as e:
				log.error(f"{self.source!r} could not be unsubscribed: {e!r}")
		if (release := getattr(self.source, "release", None)) is not None:
			try:
				release()
			except Exception as e:
				log.error(f"{self.source!r} could not be released: {e!r}")

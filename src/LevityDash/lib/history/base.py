"""What a history backend is: rows in, rows out. Nothing here knows about plugins, Qt or a database."""
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional

__all__ = ['Sample', 'Extent', 'HistoryBackend', 'numberOf', 'toTimestamp', 'fromTimestamp']

log = logging.getLogger('LevityDash.history')


def toTimestamp(when: datetime | float) -> float:
	"""Seconds since the epoch, UTC. A naive datetime is taken as UTC."""
	# Not isinstance: LevityDash's shims stand a subclass in for `datetime`, and a plain one is not an instance of it.
	if hasattr(when, 'timestamp'):
		if when.tzinfo is None:
			when = when.replace(tzinfo=timezone.utc)
		return when.timestamp()
	return float(when)


def fromTimestamp(ts: float) -> datetime:
	return datetime.fromtimestamp(ts, timezone.utc)


def numberOf(value: Any) -> Optional[float]:
	"""The number inside a JSON-safe value, for the aggregate queries: a plain number, or the `value` of an encoded measurement."""
	if isinstance(value, bool):
		return None
	if isinstance(value, (int, float)):
		return float(value) if value == value and abs(value) != float('inf') else None
	if isinstance(value, dict) and value.get('__type__') == 'measurement':
		return numberOf(value.get('value'))
	return None


@dataclass(slots=True)
class Sample:
	"""One value of one key of one plugin.

	`stream` says what the row is: `log` (the realtime values a plugin recorded), `hourly`, `daily`, `minutely`
	(forecast and observation endpoints), `realtime` (a snapshot of the current values) or `raw` (a response body as
	fetched, `key` naming the endpoint). `ts` is when the value is *for*; `fetched` is when it was pulled.
	"""
	plugin: str
	stream: str
	key: str
	ts: float
	value: Any
	fetched: float = 0.0
	number: Optional[float] = field(default=None)

	def __post_init__(self):
		if self.number is None:
			self.number = numberOf(self.value)
		if not self.fetched:
			self.fetched = datetime.now(timezone.utc).timestamp()

	def encoded(self) -> str:
		return json.dumps(self.value, separators=(',', ':'))


@dataclass(frozen=True, slots=True)
class Extent:
	"""The range of one key over a time span, as the graphs and the daily high and low need it."""
	count: int
	minimum: Optional[float]
	maximum: Optional[float]
	mean: Optional[float]


class HistoryBackend(ABC):
	"""A place samples are kept. Every method is safe to call from any thread and never raises: a backend that
	cannot do what was asked logs it (once, not per call) and returns an empty answer."""

	name: str = 'backend'

	@abstractmethod
	def write(self, samples: Iterable[Sample]) -> None:
		"""Keep `samples`. A row with the same plugin, stream, key and `ts` replaces the older one."""

	@abstractmethod
	def read(self, plugin: str, stream: str, since: datetime | float, until: datetime | float | None = None, key: str | None = None) -> List[Sample]:
		"""The samples of `plugin`'s `stream` with `since <= ts <= until`, oldest first; `key` narrows to one key."""

	@abstractmethod
	def extent(self, plugin: str, stream: str, key: str, since: datetime | float, until: datetime | float | None = None) -> Extent:
		"""Count, minimum, maximum and mean of the numbers of `key` over the span."""

	@abstractmethod
	def latest(self, plugin: str, stream: str, key: str | None = None) -> Optional[Sample]:
		"""The newest sample of the stream (of one key), or None."""

	@abstractmethod
	def prune(self, stream: str | None, before: datetime | float) -> None:
		"""Delete samples with `ts < before` (all streams when `stream` is None)."""

	def flush(self, timeout: float = 5.0) -> None:
		"""Wait until everything written so far can be read back. Backends that write at once do nothing."""

	def close(self) -> None:
		"""Release the file or connection."""

	@property
	def healthy(self) -> bool:
		return True

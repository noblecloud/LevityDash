"""Keep a long-lived connection up.

A weather station's socket should outlive a Wi-Fi drop, a laptop sleep and a hub
reboot. `keepConnected` runs one connection attempt after another, waiting longer
after each failure, until it is cancelled.
"""

import asyncio
from logging import Logger
from typing import Awaitable, Callable

__all__ = ['Backoff', 'keepConnected']


class Backoff:
	"""A delay that grows after each failure and starts over after a success."""

	def __init__(self, initial: float = 2.0, maximum: float = 300.0, factor: float = 2.0):
		self.initial = initial
		self.maximum = maximum
		self.factor = factor
		self._next = initial

	def next(self) -> float:
		delay = self._next
		self._next = min(self._next * self.factor, self.maximum)
		return delay

	def reset(self):
		self._next = self.initial


async def keepConnected(connect: Callable[[], Awaitable[None]], log: Logger, name: str, backoff: Backoff | None = None):
	"""Call `connect` again each time it returns or fails.

	`connect` opens the connection and returns when it is lost. It signals a good
	connection by calling `backoff.reset()`, which the caller gets from `backoff`.
	Cancel the task to stop.
	"""
	backoff = backoff or Backoff()
	while True:
		try:
			await connect()
			log.warning(f'{name}: connection lost')
		except asyncio.CancelledError:
			raise
		except Exception as e:
			log.warning(f'{name}: {type(e).__name__}: {e}')
		delay = backoff.next()
		log.info(f'{name}: reconnecting in {delay:g}s')
		await asyncio.sleep(delay)

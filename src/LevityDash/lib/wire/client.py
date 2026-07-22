"""WireClient — the frontend half of the process split (Phase 4.2).

An aiohttp WebSocket client that connects to a ``WireServer``, reads update
messages off the socket, and hands each decoded message dict to a callback.
Transport counterpart to ``LoopbackBridge``'s receive half.

This class owns only the transport: connect, read loop, clean shutdown. Turning
a received message into ``RemoteContainer`` updates against a ``RemoteSource``
registry and pushing them to the dispatcher (mirroring
``LoopbackBridge._on_published``) is the mode=remote integration step; that
logic lives above this, in the ``on_message`` callback. Reconnect/backoff also
lands there.
"""
import asyncio
import json
from typing import Callable, Optional

import aiohttp

from LevityDash.lib.log import LevityPluginLog

log = LevityPluginLog.getChild('Wire').getChild('Client')

__all__ = ['WireClient']


class WireClient:
	def __init__(self, url: str, on_message: Callable[[dict], None]):
		self.url = url
		self._on_message = on_message
		self._session: Optional[aiohttp.ClientSession] = None
		self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
		self._task: Optional[asyncio.Task] = None

	async def connect(self) -> None:
		self._session = aiohttp.ClientSession()
		self._ws = await self._session.ws_connect(self.url)
		self._task = asyncio.create_task(self._read_loop())
		log.info(f'WireClient connected to {self.url}')

	async def _read_loop(self) -> None:
		try:
			async for msg in self._ws:
				if msg.type == aiohttp.WSMsgType.TEXT:
					try:
						self._on_message(json.loads(msg.data))
					except Exception as e:
						log.warning(f'failed to handle wire message: {e!r}')
				elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
					break
		except asyncio.CancelledError:
			pass

	async def wait_closed(self) -> None:
		"""Block until the read loop ends (server closed the socket, error, or
		close()) - lets a reconnect loop await the lifetime of a connection."""
		if self._task is not None:
			try:
				await self._task
			except asyncio.CancelledError:
				pass

	async def close(self) -> None:
		if self._task is not None:
			self._task.cancel()
			try:
				await self._task
			except asyncio.CancelledError:
				pass
			self._task = None
		if self._ws is not None:
			await self._ws.close()
			self._ws = None
		if self._session is not None:
			await self._session.close()
			self._session = None

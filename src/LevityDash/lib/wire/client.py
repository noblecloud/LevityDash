"""WireClient — the frontend half of the process split (Phase 4.2).

An aiohttp WebSocket client that connects to a ``WireServer``, reads update
messages off the socket, and hands each decoded message dict to a callback.
Transport counterpart to ``LoopbackBridge``'s receive half.

This class owns only the transport: connect, read loop, clean shutdown, plus
a thin request/response correlation layer (``request()``) for messages that
expect a reply keyed by `id` (currently just 'ts_response', see messages.py) -
still pure transport, no knowledge of what a timeseries or a Container is.
Turning an 'update' message into ``RemoteContainer`` updates against a
``RemoteSource`` registry and pushing them to the dispatcher (mirroring
``LoopbackBridge._on_published``) is the mode=remote integration step; that
logic lives above this, in the ``on_message`` callback. Reconnect/backoff also
lands there.
"""
import asyncio
import json
from typing import Callable, Dict, Optional

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
		self._pending: Dict[str, asyncio.Future] = {}

	async def connect(self) -> None:
		self._session = aiohttp.ClientSession()
		self._ws = await self._session.ws_connect(self.url)
		self._task = asyncio.create_task(self._read_loop())
		log.info(f'WireClient connected to {self.url}')

	async def send(self, message: dict) -> None:
		await self._ws.send_str(json.dumps(message))

	async def request(self, message: dict, *, timeout: float = 10.0) -> dict:
		"""Send a message carrying an `id` and await the matching response
		(matched by that same `id` in _read_loop below), or raise
		asyncio.TimeoutError if nothing answers in time."""
		request_id = message['id']
		future: asyncio.Future = asyncio.get_running_loop().create_future()
		self._pending[request_id] = future
		try:
			await self.send(message)
			return await asyncio.wait_for(future, timeout)
		finally:
			self._pending.pop(request_id, None)

	async def _read_loop(self) -> None:
		try:
			async for msg in self._ws:
				if msg.type == aiohttp.WSMsgType.TEXT:
					try:
						message = json.loads(msg.data)
					except Exception as e:
						log.warning(f'failed to parse wire message: {e!r}')
						continue
					if message.get('type') == 'ts_response':
						future = self._pending.get(message.get('id'))
						if future is not None and not future.done():
							future.set_result(message)
						# else: unmatched (already timed out and popped, or a
						# stray) - nobody's awaiting it anymore, drop silently.
						continue
					try:
						self._on_message(message)
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
		# fail fast instead of leaving any in-flight request() to time out
		for future in self._pending.values():
			if not future.done():
				future.set_exception(ConnectionError('WireClient closed while a request was pending'))
		self._pending.clear()

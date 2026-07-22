"""WireServer — the backend half of the process split (Phase 4.2).

An aiohttp WebSocket server that broadcasts encoded container-update messages
(the dicts from ``messages.encode_container``, wrapped in an envelope) to every
connected frontend, and replays the latest state to a newly-connected one so a
late joiner isn't blank.

This is the transport counterpart to ``LoopbackBridge``'s send half: loopback
hands the encoded dict straight to the decode half in-process; the WireServer
puts it on a real socket instead. Wiring live plugin ``Publisher`` output into
``broadcast`` (and the frontend->backend subscribe/request channel) lands in
the mode=remote integration step — this class is just the pipe.
"""
import json
from typing import Dict, Optional, Set

from aiohttp import WSMsgType, web

from LevityDash.lib.log import LevityPluginLog

log = LevityPluginLog.getChild('Wire').getChild('Server')

__all__ = ['WireServer']


class WireServer:
	def __init__(self, host: str = '127.0.0.1', port: int = 0, path: str = '/ws'):
		# port=0 lets the OS pick a free port; the bound port is resolved in
		# start() so tests (and eventually a spawned frontend) can read it back.
		self.host = host
		self.port = port
		self.path = path
		self._clients: Set[web.WebSocketResponse] = set()
		# Last update message seen per source, replayed to new clients. NOTE:
		# updates are incremental (changed keys only); merging them into a true
		# cumulative snapshot is a mode=remote-step refinement (TODO), this
		# keeps only the most recent batch for now.
		self._latest: Dict[str, dict] = {}
		self._app = web.Application()
		self._app.router.add_get(path, self._handle_ws)
		self._runner: Optional[web.AppRunner] = None
		self._site: Optional[web.TCPSite] = None

	@property
	def url(self) -> str:
		return f'ws://{self.host}:{self.port}{self.path}'

	async def start(self) -> None:
		self._runner = web.AppRunner(self._app)
		await self._runner.setup()
		self._site = web.TCPSite(self._runner, self.host, self.port)
		await self._site.start()
		if self.port == 0:
			# resolve the OS-assigned port off the actual bound socket
			for sock in self._site._server.sockets:
				self.port = sock.getsockname()[1]
				break
		log.info(f'WireServer listening on {self.url}')

	async def stop(self) -> None:
		for ws in list(self._clients):
			await ws.close()
		self._clients.clear()
		if self._runner is not None:
			await self._runner.cleanup()
			self._runner = None
			self._site = None

	async def broadcast(self, message: dict) -> None:
		if message.get('type') == 'update' and (name := message.get('source', {}).get('name')) is not None:
			self._latest[name] = message
		if not self._clients:
			return
		payload = json.dumps(message)
		for ws in list(self._clients):
			try:
				await ws.send_str(payload)
			except Exception as e:
				log.warning(f'dropping client after send failure: {e!r}')
				self._clients.discard(ws)

	async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
		ws = web.WebSocketResponse(heartbeat=30)
		await ws.prepare(request)
		self._clients.add(ws)
		# replay current snapshot so a late-joining frontend starts populated
		for message in self._latest.values():
			await ws.send_str(json.dumps(message))
		try:
			async for msg in ws:
				# frontend -> backend messages (subscribe/request) are handled
				# in a later step; for now just keep the socket alive and read
				# to notice a disconnect.
				if msg.type == WSMsgType.ERROR:
					log.warning(f'client socket error: {ws.exception()!r}')
					break
		finally:
			self._clients.discard(ws)
		return ws

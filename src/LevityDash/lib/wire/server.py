"""WireServer — the backend half of the process split (Phase 4.2).

An aiohttp WebSocket server that broadcasts encoded container-update messages
(the dicts from ``messages.encode_container``, wrapped in an envelope) to every
connected frontend, and replays the latest state to a newly-connected one so a
late joiner isn't blank.

This is the transport counterpart to ``LoopbackBridge``'s send half: loopback
hands the encoded dict straight to the decode half in-process; the WireServer
puts it on a real socket instead.

Frontend->backend messages ('ts_request', the timeseries-over-wire milestone)
are dispatched through the optional ``on_request`` hook rather than handled
here directly — this class stays ignorant of message-shape specifics beyond
"it's JSON"; response-shaping (including error cases) lives in the handler
(lib/wire/backend.py) and messages.py.
"""
import json
from typing import Awaitable, Callable, Dict, Optional, Set

from aiohttp import WSMsgType, web

from LevityDash.lib.log import LevityPluginLog

log = LevityPluginLog.getChild('Wire').getChild('Server')

__all__ = ['WireServer']


class WireServer:
	def __init__(
		self, host: str = '127.0.0.1', port: int = 0, path: str = '/ws',
		on_request: Optional[Callable[[dict], Awaitable[dict]]] = None,
	):
		# port=0 lets the OS pick a free port; the bound port is resolved in
		# start() so tests (and eventually a spawned frontend) can read it back.
		self.host = host
		self.port = port
		self.path = path
		# Handles a parsed frontend->backend request dict, returns the
		# finished response dict. Settable post-construction too (see
		# lib/backend.py, where the handler needs a RemoteBackend that isn't
		# built yet at server-construction time).
		self.on_request = on_request
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

	async def _safe_send(self, ws: web.WebSocketResponse, payload: str) -> bool:
		"""Send an already-serialized payload to one connection, dropping it
		from ``_clients`` on failure (a dead/closing socket) rather than
		raising - shared by broadcast's fan-out and the unicast ts_response
		reply below. Takes a pre-serialized string, not a dict, so broadcast
		can still serialize once and reuse it across every client."""
		try:
			await ws.send_str(payload)
			return True
		except Exception as e:
			log.warning(f'dropping client after send failure: {e!r}')
			self._clients.discard(ws)
			return False

	async def broadcast(self, message: dict) -> None:
		if message.get('type') == 'update' and (name := message.get('source', {}).get('name')) is not None:
			self._latest[name] = message
		if not self._clients:
			return
		payload = json.dumps(message)
		for ws in list(self._clients):
			await self._safe_send(ws, payload)

	async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
		ws = web.WebSocketResponse(heartbeat=30)
		await ws.prepare(request)
		self._clients.add(ws)
		# replay current snapshot so a late-joining frontend starts populated
		for message in self._latest.values():
			await self._safe_send(ws, json.dumps(message))
		try:
			async for msg in ws:
				if msg.type == WSMsgType.TEXT:
					await self._handle_incoming(ws, msg.data)
				elif msg.type == WSMsgType.ERROR:
					log.warning(f'client socket error: {ws.exception()!r}')
					break
		finally:
			self._clients.discard(ws)
		return ws

	async def _handle_incoming(self, ws: web.WebSocketResponse, raw: str) -> None:
		try:
			incoming = json.loads(raw)
		except Exception as e:
			log.warning(f'failed to parse client message: {e!r}')
			return
		if incoming.get('type') != 'ts_request':
			# subscribe/other frontend->backend message types are a later step;
			# unrecognized messages are ignored rather than erroring, so an
			# older/newer client can't crash this connection.
			return
		if self.on_request is None:
			log.warning(f'ts_request {incoming.get("id")} received but no handler is wired up')
			return
		try:
			response = await self.on_request(incoming)
		except Exception as e:
			log.error(f'on_request handler raised for {incoming.get("id")}: {e!r}')
			return
		await self._safe_send(ws, json.dumps(response))

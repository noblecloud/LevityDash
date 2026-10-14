import platform
from json import JSONDecodeError, loads

import asyncio
import logging
from time import monotonic
from abc import ABC, abstractmethod

from aiohttp import ClientSession
from PySide6.QtCore import QObject, Signal
from typing import Optional

from LevityDash.lib.plugins.web import Endpoint
from LevityDash.lib.plugins.web.reconnect import Backoff, keepConnected


class SocketMessageHandler(ABC):

	@abstractmethod
	def publish(self, message: dict):
		...


class LevityQtSocketMessageHandler(QObject):
	signal = Signal(dict)

	def __init__(self, parent=None):
		super().__init__(parent)

	def publish(self, message):
		self.signal.emit(message)

	def connectSlot(self, slot):
		self.signal.connect(slot)

	def disconnectSlot(self, slot):
		try:
			self.signal.disconnect(slot)
		except TypeError:
			pass
		except RuntimeError:
			pass


# class SocketIO(QThread):
# 	url: str
# 	params: dict
# 	socketParams: dict
# 	relay = Signal(dict)
#
# 	def __init__(self, params: dict = {}, *args, **kwargs):
# 		super(SocketIO, self).__init__()
# 		if 'plugins' in kwargs:
# 			self.plugins = kwargs['plugins']
# 		self.params = params
# 		self.socket.on("connect", self._connect)
# 		self.socket.on("disconnect", self._disconnect)
# 		self.socket.on('*', self._anything)
#
# 	def push(self, message):
# 		self.relay.emit(message)
#
# 	@property
# 	def url(self):
# 		return self.plugins.urls.socket
#
# 	@cached_property
# 	def socket(self):
# 		return socketio.Client(
# 			reconnection=True,
# 			reconnection_attempts=3,
# 			reconnection_delay=5,
# 			reconnection_delay_max=5
# 		)
#
# 	def run(self):
# 		self.socket.connect(url=self.url, **self.socketParams)
#
# 	def begin(self):
# 		self.start()
#
# 	def end(self):
# 		self.socket.disconnect()
#
# 	def _anything(self, data):
# 		self.log.warning('Catchall for SocketIO used')
# 		self.log.debug(data)
#
# 	def _connect(self):
# 		pass
#
# 	def _disconnect(self):
# 		pass

#
# class Websocket(QThread, Socket):
# 	urlBase = ''
#
# 	@property
# 	def url(self):
# 		return self.urlBase
#
# 	def __init__(self, *args, **kwargs):
# 		super(Websocket, self).__init__(*args, **kwargs)
#
# 	def run(self):
# 		self.socket.run_forever()
#
# 	def begin(self):
# 		self.start()
#
# 	def end(self):
# 		self.socket.close()
#
# 	def _open(self, ws):
# 		self.log.info(f'Socket {self.__class__.__name__}')
# 		print("### opened ###")
#
# 	def _message(self, ws, message):
# 		pass
#
# 	def _data(self, ws, data):
# 		pass
#
# 	def _error(self, ws, error: bytes):
# 		pass
#
# 	def _close(self, ws):
# 		self.log.info(f'Socket {self.__class__.__name__}')
# 		print("### closed ###")
#
# 	def terminate(self):
# 		self.socket.close()


class BaseSocketProtocol(asyncio.DatagramProtocol):
	api: 'REST'
	handler: 'SockeMessageHandler'

	def __init__(self, api: 'REST'):
		self._plugin = api
		self.handler = LevityQtSocketMessageHandler()
		self.lost: Optional[asyncio.Future] = None
		self.lastReceived = monotonic()
		self.log = api.pluginLog.getChild(self.__class__.__name__)

	def datagram_received(self, data, addr):
		self.lastReceived = monotonic()
		try:
			message = loads(data.decode('utf-8'))
			self.handler.publish(message)
		except JSONDecodeError as e:
			self.log.error(f'Received invalid JSON from {addr}')
			self.log.error(e)

	def connection_made(self, transport):
		self.log.debug('Connection made')
		self.lost = asyncio.get_running_loop().create_future()

	def connection_lost(self, exc):
		self.log.warning('Connection lost: %s', exc)
		if self.lost is not None and not self.lost.done():
			self.lost.set_result(exc)

	def error_received(self, exc):
		self.log.warning('Error received: %s', exc)

	def pause_writing(self):
		self._transport.pause_reading()

	def resume_writing(self):
		self._transport.resume_reading()

	def eof_received(self):
		self.log.warning('EOF received')

	def write(self, data):
		self.log.error('Not implemented')

	def close(self):
		self.log.info('Closing')

	def abort(self):
		self.log.info('Aborting')

	def push(self, data):
		self.log.error('Not implemented')


class Socket:
	protocol: BaseSocketProtocol
	transport: asyncio.DatagramTransport
	api: 'REST'

	def __init__(self, api: 'REST', *args, **kwargs):
		self.runTask: Optional[asyncio.Task] = None
		self.api = api
		self.log = api.pluginLog.getChild(self.__class__.__name__)
		super(Socket, self).__init__(*args, **kwargs)

	def start(self):
		self.log.debug(f'Starting socket for {self.api.name}')
		self.runTask = asyncio.create_task(self.run())

	def stop(self):
		if self.runTask:
			self.runTask.cancel()
			self.runTask = None
		transport = getattr(self, 'transport', None)
		if transport is not None:
			transport.close()
		self.protocol.close()

	@abstractmethod
	async def run(self):
		raise NotImplementedError

	@property
	def running(self) -> bool:
		try:
			return not (self.runTask.done() or self.runTask.cancelled())
		except AttributeError:
			return False


class UDPSocket(Socket):
	last: dict
	port: int

	def __init__(self, api: 'REST', address: Optional[str] = None, port: Optional[int] = None, silenceTimeout: Optional[float] = None, *args, **kwargs):
		super(UDPSocket, self).__init__(api=api, *args, **kwargs)
		# Seconds without a datagram before the socket is judged dead and rebound.
		# None never rebinds on silence (a quiet source is not a dead one).
		self.silenceTimeout = silenceTimeout
		self._address = address
		if port is not None:
			self.port = port
		self.protocol = BaseSocketProtocol(self.api)

	@property
	def handler(self):
		return self.protocol.handler

	@property
	def address(self) -> str:
		return self._address or '0.0.0.0'

	async def run(self):
		backoff = Backoff(maximum=60)

		async def connect():
			self.log.debug(f'Connecting UDP Socket: {self.api.name}')
			loop = asyncio.get_running_loop()
			self.transport, _ = await loop.create_datagram_endpoint(lambda: self.protocol, local_addr=(self.address, self.port))
			self.log.debug(f'Connected UDP Socket: {self.api.name}')
			backoff.reset()
			self.protocol.lastReceived = monotonic()
			try:
				await self._untilLostOrSilent()
			finally:
				self.transport.close()

		await keepConnected(connect, self.log, f'UDP {self.api.name}', backoff)

	async def _untilLostOrSilent(self):
		if self.silenceTimeout is None:
			await self.protocol.lost
			return
		while not self.protocol.lost.done():
			quiet = monotonic() - self.protocol.lastReceived
			if quiet >= self.silenceTimeout:
				self.log.warning(f'No data for {quiet:.0f}s, rebinding')
				return
			await asyncio.wait({self.protocol.lost}, timeout=self.silenceTimeout - quiet)
